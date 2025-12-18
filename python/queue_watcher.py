import asyncio
import time
import re
from pathlib import Path
import httpx

# -----------------------------
# CONFIG
# -----------------------------
QUEUE_DIR = Path("/data/gamegen/context/queque")
BASE_DIR  = Path("/data/gamegen/context")

PROMPT_DIR  = Path("/prompt")
HUMAN_PROMPT_FILE = PROMPT_DIR / "human_prompt.txt"
MACHINE_PROMPT_FILE = PROMPT_DIR / "machine_prompt.txt"

OUT_LOG_DIR     = BASE_DIR / "log"
OUT_MESSAGE_DIR = BASE_DIR / "message"

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
MODEL_HUMAN = "llama3.1:8b"
MODEL_MACHINE = "qwen2.5:14b"

POLL_SECONDS = 2.0  # <-- cada cuánto revisa nuevos archivos

# -----------------------------
# RESERVED WORDS STRIPPER
# -----------------------------
# 1) Convierte flow_XXX -> XXX (mantiene la parte útil)
FLOW_UNDERSCORE_RE = re.compile(r"\bflow_([A-Za-z0-9_]+)\b", re.IGNORECASE)

# 2) Si queda algún token raro tipo flowStep / FLOWABC (sin underscore) lo elimina completo
FLOW_TOKEN_RE = re.compile(r"\bflow[A-Za-z0-9_]*\b", re.IGNORECASE)

EMPTY_PARENS_RE = re.compile(r"\(\s*\)")  # elimina paréntesis vacíos resultantes

def strip_flow_reserved(text: str) -> str:
    if not text:
        return text

    # Primero: flow_XXX -> XXX
    text = FLOW_UNDERSCORE_RE.sub(r"\1", text)

    # Luego: elimina cualquier flowToken restante (sin underscore, etc.)
    text = FLOW_TOKEN_RE.sub("", text)

    # limpia paréntesis vacíos
    text = EMPTY_PARENS_RE.sub("", text)

    # colapsa espacios múltiples
    text = re.sub(r"[ \t]{2,}", " ", text)

    # limpia espacios antes de puntuación simple
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)

    return text.strip()

# -----------------------------
# HELPERS
# -----------------------------
def safe_mkdirs():
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MESSAGE_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8")

def load_prompts() -> tuple[str, str]:
    human_tpl = read_text(HUMAN_PROMPT_FILE)
    machine_tpl = read_text(MACHINE_PROMPT_FILE)
    return human_tpl, machine_tpl

def render_prompt(template: str, raw_logs: str) -> str:
    return template.replace("{{RAW_LOG_TEXT}}", raw_logs)

def list_txt_files():
    # Solo .txt (ignora .processing)
    return sorted([p for p in QUEUE_DIR.glob("*.txt") if p.is_file()])

async def ollama_generate(client: httpx.AsyncClient, model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2}
    }
    r = await client.post(OLLAMA_URL, json=payload, timeout=600)
    r.raise_for_status()
    return r.json().get("response", "").strip()

async def process_file(file_path: Path, human_tpl: str, machine_tpl: str):
    # Claim atómico para que no se procese doble
    processing_path = file_path.with_suffix(file_path.suffix + ".processing")
    try:
        file_path.rename(processing_path)
    except Exception:
        return

    raw_logs = read_text(processing_path)

    human_prompt = render_prompt(human_tpl, raw_logs)
    machine_prompt = render_prompt(machine_tpl, raw_logs)

    async with httpx.AsyncClient() as client:
        t1 = asyncio.create_task(ollama_generate(client, MODEL_HUMAN, human_prompt))
        t2 = asyncio.create_task(ollama_generate(client, MODEL_MACHINE, machine_prompt))
        human_text, machine_text = await asyncio.gather(t1, t2)

    # ---- LIMPIEZA DE FLOW_* ANTES DE GUARDAR (AMBOS SALEN TXT) ----
    human_text = strip_flow_reserved(human_text)
    machine_text = strip_flow_reserved(machine_text)

    original_name = file_path.name
    human_filename = f"human_{original_name}"
    machine_filename = f"log_{original_name}"

    # humano: log y message
    write_text(OUT_LOG_DIR / human_filename, human_text)
    write_text(OUT_MESSAGE_DIR / human_filename, human_text)

    # máquina: ahora también como TXT (NO JSON)
    write_text(OUT_LOG_DIR / machine_filename, machine_text)
    # si también quieres machine en message, descomenta:
    # write_text(OUT_MESSAGE_DIR / machine_filename, machine_text)

    processing_path.unlink(missing_ok=True)

async def main():
    safe_mkdirs()

    print(f"[Watcher] Queue: {QUEUE_DIR}")
    print(f"[Watcher] Prompts: {PROMPT_DIR}")
    print(f"[Watcher] Output log: {OUT_LOG_DIR}")
    print(f"[Watcher] Output message: {OUT_MESSAGE_DIR}")
    print(f"[Watcher] Poll every {POLL_SECONDS}s")
    print("[Watcher] Running. Stop with CTRL+C.\n")

    while True:
        try:
            human_tpl, machine_tpl = load_prompts()
        except FileNotFoundError:
            print("[ERROR] Prompt files not found. Create:")
            print(f" - {HUMAN_PROMPT_FILE}")
            print(f" - {MACHINE_PROMPT_FILE}")
            time.sleep(POLL_SECONDS)
            continue

        files = list_txt_files()
        if files:
            for f in files:
                try:
                    await process_file(f, human_tpl, machine_tpl)
                    print(f"[OK] Processed: {f.name}")
                except Exception as e:
                    proc = f.with_suffix(f.suffix + ".processing")
                    if proc.exists():
                        try:
                            proc.rename(f)
                        except Exception:
                            pass
                    print(f"[ERROR] Failed: {f.name} -> {e}")

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Watcher] Stopped by user (CTRL+C).")
