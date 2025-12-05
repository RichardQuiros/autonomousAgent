#!/usr/bin/env python3
import sys
import json
import socket
import os

HOST = os.getenv("SOCKET_HOST", "localhost")
PORT = int(os.getenv("SOCKET_PORT", "7345"))

def main():
    if len(sys.argv) < 2:
        print('Uso: cli.py <metodo> [mensaje|archivo] [numero] [--file]')
        sys.exit(1)

    write_to_file = False
    if "--file" in sys.argv:
        write_to_file = True
        sys.argv.remove("--file")

    name = sys.argv[1]
    args = []

    if name == "send":
        # 1) Primer argumento: mensaje o archivo
        if len(sys.argv) > 2:
            candidate = sys.argv[2]

            if os.path.exists(candidate) and os.path.isfile(candidate):
                with open(candidate, "r", encoding="utf-8") as f:
                    message = f.read().strip()
            else:
                message = candidate
        else:
            if not os.path.exists("prompt.txt"):
                print("Error: No se encontró el archivo prompt.txt")
                sys.exit(1)
            with open("prompt.txt", "r", encoding="utf-8") as f:
                message = f.read().strip()

        args.append(message)

        # 2) Segundo parámetro numérico (default = 0)
        if len(sys.argv) > 3:
            try:
                numeric_value = int(sys.argv[3])
            except ValueError:
                print("El segundo parámetro debe ser numérico")
                sys.exit(1)
        else:
            numeric_value = 0

        args.append(numeric_value)

    else:
        # Otros métodos igual que antes
        if len(sys.argv) > 2:
            for a in sys.argv[2:]:
                try:
                    args.append(json.loads(a))
                except Exception:
                    args.append(a)

    payload = {
        "type": "RUN",
        "name": name,
        "args": args,
    }

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(900)

    try:
        s.connect((HOST, PORT))
    except Exception:
        print(f"⚠️ No se pudo conectar a {HOST}:{PORT}. Probando fallback localhost:7345...")
        s.connect(("localhost", 7345))

    s.sendall(json.dumps(payload).encode("utf-8"))

    chunks = []
    while True:
        part = s.recv(4096)
        if not part:
            break
        chunks.append(part)

    s.close()

    resp = b"".join(chunks)
    decoded = resp.decode("utf-8")

    if write_to_file:
        with open("response.txt", "w", encoding="utf-8") as f:
            f.write(decoded)
    else:
        print(decoded)


if __name__ == "__main__":
    main()
