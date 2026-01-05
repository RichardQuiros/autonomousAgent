#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+-]*)[ \t]*\n(?P<body>.*?)(?:\n```[ \t]*\n?|```[ \t]*$)",
    re.DOTALL,
)

FILE_HEADER_RE = re.compile(
    r"(?im)^(?:\s*(?:#+\s*)?)?(?:file|archivo)\s*:\s*(?P<path>.+?)\s*$"
)

@dataclass
class CodeBlock:
    lang: str
    body: str
    start: int
    end: int


def read_b64_input(b64_arg: Optional[str], input_file: Optional[str]) -> str:
    """
    Lee base64 desde:
      - --b64 (argumento)
      - --input-file (archivo con base64)  [por si tu pipeline lo permite; si no, ignora]
      - STDIN (recomendado)
    Devuelve el contenido decodificado como texto UTF-8 (con reemplazo en errores).
    """
    if input_file:
        b64_text = Path(input_file).read_text(encoding="utf-8", errors="replace")
    elif b64_arg is not None:
        b64_text = b64_arg
    else:
        b64_text = sys.stdin.read()

    # limpiar espacios y saltos de línea (base64 a veces viene "wrappeado")
    b64_text = "".join(b64_text.split())

    if not b64_text:
        raise ValueError("Entrada base64 vacía.")

    raw = b64_decode_flexible(b64_text)
    # Si parece gzip, opcionalmente descomprimir
    if raw.startswith(b"\x1f\x8b"):
        try:
            raw = gzip.decompress(raw)
        except Exception:
            # Si falla, lo dejamos como está
            pass

    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def b64_decode_flexible(s: str) -> bytes:
    """
    Decodifica base64 estándar o base64url, tolerando padding faltante.
    """
    # detectar si es urlsafe (tiene - o _)
    is_urlsafe = ("-" in s) or ("_" in s)

    # arreglar padding si falta
    pad = (-len(s)) % 4
    if pad:
        s = s + ("=" * pad)

    try:
        if is_urlsafe:
            return base64.urlsafe_b64decode(s.encode("ascii", errors="ignore"))
        return base64.b64decode(s.encode("ascii", errors="ignore"), validate=False)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"Base64 inválido: {e}") from e


def find_code_blocks(text: str) -> List[CodeBlock]:
    blocks: List[CodeBlock] = []
    for m in FENCE_RE.finditer(text):
        lang = (m.group("lang") or "").strip().lower()
        body = m.group("body").replace("\r\n", "\n").replace("\r", "\n")
        blocks.append(CodeBlock(lang=lang, body=body, start=m.start(), end=m.end()))
    return blocks


def choose_best_block(blocks: List[CodeBlock], lang: Optional[str]) -> Optional[CodeBlock]:
    if not blocks:
        return None
    if lang:
        lang = lang.lower().strip()
        aliases = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "sh": "bash",
            "shell": "bash",
            "yml": "yaml",
        }
        target = aliases.get(lang, lang)
        for b in blocks:
            b_lang = aliases.get(b.lang, b.lang)
            if b_lang == target:
                return b
    return max(blocks, key=lambda b: len(b.body))


def strip_md_wrappers(text: str, prefer_lang: Optional[str]) -> str:
    blocks = find_code_blocks(text)
    if not blocks:
        return text
    chosen = choose_best_block(blocks, prefer_lang)
    return chosen.body if chosen else text


def split_into_file_sections(text: str) -> List[Tuple[str, str]]:
    matches = list(FILE_HEADER_RE.finditer(text))
    if not matches:
        return []
    sections: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        relpath = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        sections.append((relpath, body))
    return sections


def safe_join(base: Path, rel: str) -> Path:
    rel = rel.strip().strip('"').strip("'")
    rel = re.sub(r"^[.]/+", "", rel)
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if base_resolved == target or base_resolved in target.parents:
        return target
    raise ValueError(f"Ruta insegura (path traversal): {rel}")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", errors="replace",
        dir=str(path.parent), delete=False, newline="\n"
    ) as tf:
        tmp_name = tf.name
        tf.write(content)
        tf.flush()
        os.fsync(tf.fileno())
    os.replace(tmp_name, path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Decodifica base64 (posible Markdown) y crea archivos de forma robusta."
    )
    ap.add_argument("--outdir", required=True, help="Directorio base donde se escribirán los archivos.")
    ap.add_argument("--b64", help="Contenido en base64 como argumento (mejor usar STDIN).")
    ap.add_argument("--input-file", help="Archivo que contiene base64 (opcional).")
    ap.add_argument("--single", help="Modo archivo único: ruta relativa a escribir (ej: main.py).")
    ap.add_argument("--lang", help="En modo --single, lenguaje preferido del fence (python, bash, etc.).")
    ap.add_argument("--dry-run", action="store_true", help="No escribe; solo muestra qué haría.")
    args = ap.parse_args()

    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        decoded_text = read_b64_input(args.b64, args.input_file)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Si piden un único archivo
    if args.single:
        content = strip_md_wrappers(decoded_text, args.lang)
        try:
            target = safe_join(outdir, args.single)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 3

        if args.dry_run:
            print(f"[DRY-RUN] escribiría: {target}")
            print("----- inicio contenido -----")
            print(content)
            print("----- fin contenido -----")
            return 0

        atomic_write_text(target, content)
        print(f"OK: escrito {target}")
        return 0

    # Modo multi-archivo por headers "file:"
    sections = split_into_file_sections(decoded_text)
    if sections:
        wrote = False
        for relpath, section_text in sections:
            content = strip_md_wrappers(section_text, None)
            try:
                target = safe_join(outdir, relpath)
            except ValueError as e:
                print(f"SKIP: {e}", file=sys.stderr)
                continue

            if args.dry_run:
                print(f"[DRY-RUN] escribiría: {target} (len={len(content)})")
                wrote = True
                continue

            atomic_write_text(target, content)
            print(f"OK: escrito {target}")
            wrote = True

        if not wrote:
            print("No se escribió ningún archivo (rutas inseguras o vacías).", file=sys.stderr)
            return 4
        return 0

    # Si no hay "file:", escribe a un default
    default_name = "output.txt"
    content = strip_md_wrappers(decoded_text, None)
    target = safe_join(outdir, default_name)

    if args.dry_run:
        print(f"[DRY-RUN] no se detectó 'file:'; escribiría: {target}")
        return 0

    atomic_write_text(target, content)
    print(f"OK: no se detectó 'file:'; escrito {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
