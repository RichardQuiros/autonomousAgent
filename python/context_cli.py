#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


DEFAULT_DIR = Path("/data/gamegen/context/log")


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    """
    Parse datetime in:
      - YYYY-MM-DD
      - YYYY-MM-DDTHH:MM
      - YYYY-MM-DDTHH:MM:SS
    """
    if not s:
        return None
    s = s.strip()
    fmts = ["%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise SystemExit(f"Formato de fecha inválido: {s}. Usa YYYY-MM-DD o YYYY-MM-DDTHH:MM[:SS].")


def dt_from_mtime(mtime: float) -> datetime:
    return datetime.fromtimestamp(mtime)


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.1f}{u}" if u != "B" else f"{int(x)}B"
        x /= 1024


def detect_type(p: Path) -> Optional[str]:
    name = p.name.lower()
    if name.startswith("human") and name.endswith(".txt"):
        return "human"
    if name.startswith("log") and name.endswith(".txt"):
        return "log"
    return None


@dataclass
class FileInfo:
    path: Path
    ftype: str
    size: int
    mtime: float

    @property
    def dt(self) -> datetime:
        return dt_from_mtime(self.mtime)


def scan_files(directory: Path, ftype: Optional[str]) -> List[FileInfo]:
    if not directory.exists():
        raise SystemExit(f"No existe la ruta: {directory.resolve()}")
    files: List[FileInfo] = []
    for p in directory.iterdir():
        if not p.is_file():
            continue
        t = detect_type(p)
        if not t:
            continue
        if ftype and t != ftype:
            continue
        st = p.stat()
        files.append(FileInfo(path=p, ftype=t, size=st.st_size, mtime=st.st_mtime))
    # Orden: más antiguo -> más reciente (por mtime). Si hay empate, por nombre.
    files.sort(key=lambda x: (x.mtime, x.path.name))
    return files


def filter_by_time(files: List[FileInfo], since: Optional[datetime], until: Optional[datetime]) -> List[FileInfo]:
    out = []
    for f in files:
        d = f.dt
        if since and d < since:
            continue
        if until and d > until:
            continue
        out.append(f)
    return out


def encode_cursor(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(s: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(s.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise SystemExit("Cursor inválido. Debe ser un string base64 generado por este script.")


def read_chunk(files: List[FileInfo], start_file_idx: int, start_offset: int, max_chars: int) -> Tuple[str, Optional[str]]:
    """
    Lee texto concatenado desde files[start_file_idx:], comenzando en start_offset del archivo actual,
    hasta acumular max_chars. Devuelve (texto, next_cursor or None).
    """
    remaining = max_chars
    parts: List[str] = []
    i = start_file_idx
    offset = start_offset

    while i < len(files) and remaining > 0:
        f = files[i]
        with f.path.open("r", encoding="utf-8", errors="replace") as fp:
            fp.seek(offset)
            # Leemos un poco más de lo necesario para no pasarnos demasiado (aprox).
            data = fp.read(remaining)
            new_offset = fp.tell()

        if data:
            header = f"\n--- FILE {i+1}/{len(files)} | {f.path.name} | {f.dt.isoformat(sep=' ', timespec='seconds')} | {human_size(f.size)} ---\n"
            # Si no estamos al inicio del archivo, lo marcamos.
            if offset > 0:
                header = header.rstrip("\n") + f" (continuación desde byte {offset}) ---\n"
            parts.append(header)
            parts.append(data)
            remaining -= len(data)

        # Si terminamos archivo (offset llegó al tamaño) pasamos al siguiente
        if new_offset >= f.size:
            i += 1
            offset = 0
        else:
            # Aún queda contenido en el mismo archivo; cortamos aquí.
            offset = new_offset
            break

    text = "".join(parts).strip("\n")

    if not text:
        return "", None

    if i >= len(files) and offset == 0:
        # Consumimos todo
        return text, None

    next_cursor = encode_cursor({"file_idx": i, "offset": offset, "max_chars": max_chars})
    return text, next_cursor


def cmd_files(args: argparse.Namespace) -> None:
    directory = Path(args.dir)
    ftype = args.type
    since = parse_dt(args.since)
    until = parse_dt(args.until)

    files = scan_files(directory, ftype)
    files = filter_by_time(files, since, until)

    if not files:
        print("No hay archivos que coincidan con el filtro.")
        return

    # Output sencillo tipo tabla
    print(f"Ruta: {directory.resolve()}")
    print(f"Total: {len(files)} archivo(s)\n")
    print(f"{'#':>3}  {'tipo':<6}  {'fecha':<19}  {'tamaño':>10}  nombre")
    print("-" * 70)
    for idx, f in enumerate(files, 1):
        print(f"{idx:>3}  {f.ftype:<6}  {f.dt.isoformat(sep=' ', timespec='seconds'):<19}  {human_size(f.size):>10}  {f.path.name}")


def cmd_get(args: argparse.Namespace) -> None:
    directory = Path(args.dir)
    ftype = args.type
    since = parse_dt(args.since)
    until = parse_dt(args.until)
    max_chars = int(args.max_chars)

    files = scan_files(directory, ftype)
    files = filter_by_time(files, since, until)

    if not files:
        print("No hay archivos que coincidan con el filtro.")
        return

    # Cursor opcional
    if args.cursor:
        cur = decode_cursor(args.cursor)
        file_idx = int(cur.get("file_idx", 0))
        offset = int(cur.get("offset", 0))
        # Si el cursor trae max_chars, respetamos el que venga por CLI.
    else:
        file_idx = 0
        offset = 0

    text, next_cursor = read_chunk(files, file_idx, offset, max_chars)

    if not text:
        print("No se encontró texto para devolver (o el cursor ya está al final).")
        return

    print(text)
    print("\n" + "=" * 70)
    if next_cursor:
        print("NEXT_CURSOR:")
        print(next_cursor)
        print("=" * 70)
    else:
        print("FIN (no hay más contenido).")
        print("=" * 70)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="CLI para listar y consumir contexto (human/log) en chunks con cursor."
    )
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="Directorio de contexto (default: /data/gamegen/context/log)")

    sub = p.add_subparsers(dest="cmd", required=True)

    p_files = sub.add_parser("files", help="Listar archivos con detalles")
    p_files.add_argument("--type", choices=["human", "log"], default=None, help="Filtrar por tipo")
    p_files.add_argument("--since", default=None, help="Desde (YYYY-MM-DD o YYYY-MM-DDTHH:MM[:SS])")
    p_files.add_argument("--until", default=None, help="Hasta (YYYY-MM-DD o YYYY-MM-DDTHH:MM[:SS])")
    p_files.set_defaults(func=cmd_files)

    p_get = sub.add_parser("get", help="Obtener contexto en chunks (respeta max_chars) y da cursor")
    p_get.add_argument("--type", choices=["human", "log"], required=True, help="Tipo de contexto a leer")
    p_get.add_argument("--since", default=None, help="Desde (YYYY-MM-DD o YYYY-MM-DDTHH:MM[:SS])")
    p_get.add_argument("--until", default=None, help="Hasta (YYYY-MM-DD o YYYY-MM-DDTHH:MM[:SS])")
    p_get.add_argument("--max-chars", default="12000", help="Máximo de caracteres a devolver (default: 12000)")
    p_get.add_argument("--cursor", default=None, help="Cursor para continuar (lo imprime el comando get)")
    p_get.set_defaults(func=cmd_get)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
