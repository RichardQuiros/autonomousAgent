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

POLL_SECONDS = 2.0  # cada cuánto revisa nuevos archivos

# -----------------------------
# RESERVED WORDS STRIPPER
# -----------------------------
# 1) Convierte flow_XXX -> XXX
FLOW_UNDERSCORE_RE = re.compile(r"\bflow_([A-Za-z0-9_]+)\b", re.IGNORECASE)

# 2) Elimina cualquier token tipo flowStep / FLOWABC (sin underscore)
FLOW_TOKEN_RE = re.compile(r"\bflow[A-Za-z0-9_]*\b", re.IGNORECASE)

EMPTY_PARENS_RE = re.compile(r"\(\s*\)")  # elimina paréntesis vacíos resultantes

# EOF -> E-O-F (referencial)
EOF_RE = re.compile(r"\bEOF\b", re.IGNORECASE)

def strip_reserved(text: str) -> str:
    """
    Limpia:
    - EOF -> E-O-F
    - flow_XXX -> XXX
    - flowXXXX -> (elimina)
    """
    if not text:
        return text

    # EOF -> E-O-F
    text = EOF_RE.sub("E-O-F", text)

    # flow_XXX -> XXX
    text = FLOW_UNDERSCORE_RE.sub(r"\1", text)

    # elimina cualquier flowToken restante
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
    # SIEMPRE texto plano. Nunca formateo JSON, nunca pretty, nunca validación.
    path.write_text(content if content is not None else "", encoding="utf-8", errors="replace")

def load_prompts() -> tuple[str, str]:
    human_tpl = read_text(HUMAN_PROMPT_FILE)
    machine_tpl = read_text(MACHINE_PROMPT_FILE)
    return human_tpl, machine_tpl

def render_prompt(template: str, raw_logs: str) -> str:
    return template.replace("{{RAW_LOG_TEXT}}", raw_logs)

def list_txt_files():
    # Solo .txt (ignora .processing)
    return sorted([p for p in QUEUE_DIR.glob("*.txt") if p.is_file()])

# -----------------------------
# OLLAMA (MÁS SEGURO ANTI-FALLOS)
# -----------------------------
def extract_response_field(obj) -> str:
    """
    Extrae obj["response"] si existe y es string.
    Si no existe o no es string, devuelve "".
    """
    if isinstance(obj, dict):
        resp = obj.get("response", "")
        if isinstance(resp, str):
            return resp
    return ""

async def ollama_generate(client: httpx.AsyncClient, model: str, prompt: str) -> str:
    """
    Estrategia anti-fallos:
    1) Hace POST usando json=payload (request correcto y estándar).
    2) Intenta parsear r.json() de forma segura.
    3) Si falla el parseo o falta "response", NO rompe: regresa r.text.
    4) Nunca usa regex para extraer (evita falsos positivos por contenido del modelo).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2}
    }

    r = await client.post(OLLAMA_URL, json=payload, timeout=600)
    r.raise_for_status()

    # Intento 1: JSON real
    try:
        data = r.json()
        resp = extract_response_field(data)
        if isinstance(resp, str) and resp.strip():
            return resp.strip()
        # si viene JSON sin "response" o vacío, igual no falles
        return (r.text or "").strip()
    except Exception:
        # Intento 2: texto crudo, sin parseo
        return (r.text or "").strip()

# -----------------------------
# PROCESSING
# -----------------------------
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

    # Si falla Ollama por cualquier razón, preferimos NO botar el watcher completo.
    # Devolvemos strings de fallback para poder guardar algo y continuar.
    async with httpx.AsyncClient() as client:
        try:
            t1 = asyncio.create_task(ollama_generate(client, MODEL_HUMAN, human_prompt))
            t2 = asyncio.create_task(ollama_generate(client, MODEL_MACHINE, machine_prompt))
            human_text, machine_text = await asyncio.gather(t1, t2)
        except Exception as e:
            # fallback duro: guarda el error como texto plano
            human_text = f"[ERROR] OLLAMA_FAILED: {e}"
            machine_text = f"[ERROR] OLLAMA_FAILED: {e}"

    # ---- LIMPIEZA ANTES DE GUARDAR (TODO TXT PLANO) ----
    human_text = strip_reserved(human_text)
    machine_text = strip_reserved(machine_text)

    original_name = file_path.name
    human_filename = f"human_{original_name}"
    machine_filename = f"log_{original_name}"

    # humano: log y message
    write_text(OUT_LOG_DIR / human_filename, human_text)
    write_text(OUT_MESSAGE_DIR / human_filename, human_text)

    # máquina: TXT plano
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
                    # rollback del .processing si existe
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
