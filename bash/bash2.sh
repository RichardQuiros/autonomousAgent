{{`
set -eu  # Salir si hay errores

DIR="/data/gamegen/context/queque"
PY_DIR="/home/node/python"

cd "$PY_DIR" || exit 1

export SOCKET_HOST="host.docker.internal"
export SOCKET_PORT="7345"

RESULTS=""

while :; do
  # FIFO — archivos más viejos primero
  FILES=$(ls -1tr "$DIR" 2>/dev/null || true)

  # Si no hay archivos, salir
  if [ -z "$FILES" ]; then
    break
  fi

  for NAME in $FILES; do
    FILE="$DIR/$NAME"

    # No procesar si no es archivo
    [ -f "$FILE" ] || continue

    # Ejecutar cli.py pasando EL ARCHIVO directamente
    if ! OUTPUT=$(python3 cli.py send "$FILE"); then
      echo "⚠️ Error procesando archivo: $FILE (no se borra)" >&2
      continue
    fi

    # Acumular con un salto de línea en blanco entre resultados
    if [ -z "$RESULTS" ]; then
      RESULTS="$OUTPUT"
    else
      RESULTS="${RESULTS}

$OUTPUT"
    fi

    # Borrar archivo procesado
    rm -f "$FILE"
  done
done

# Mostrar resultado final
printf '%s\n' "$RESULTS"
`}}