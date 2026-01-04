#!/bin/sh
set -e

SOCK=/tmp/ssh-agent.sock
rm -f "$SOCK"

# Arranca el agente usando un socket fijo
eval "$(ssh-agent -a "$SOCK" -s)"

# Carga la llave
ssh-add /home/shh/id_ed25519

# Ejecuta el proceso real (n8n)
exec "$@"
