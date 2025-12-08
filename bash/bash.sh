#!/bin/bash
#set var
sed -i '/export SESSION_ID=/d' ~/.bashrc
echo "export SESSION_ID={{$('chat').item.json.sessionId}}" >> ~/.bashrc
source ~/.bashrc

# Lee los argumentos de n8n:
PREV_NODE="{{ $prevNode.name }}"

if [ "$PREV_NODE" = "chat" ]; then
    INPUT_MESSAGE='{{ $json?.chatInput }}'
else
    INPUT_MESSAGE='{{(()=>{
    let data = $('terminal')
    if(!$json?.chatInput){
      const message = JSON.stringify(data.item.json) 
      return message;
    }
    return '';
    })()}}'
fi

# echo "$PREV_NODE"
# echo "$INPUT_MESSAGE"

CONTEXT_FILE="/data/gamegen/context"       # Ruta del archivo de contexto estático

# 1. Variables y Rutas
PROMPT_FILE_PATH="/home/node/python/prompt.txt"
SHOULD_CONTINUE="true"  # Por defecto, continuar

# Creamos la carpeta si no existe
mkdir -p "$(dirname "$PROMPT_FILE_PATH")"

# 2. Detección de Palabra Clave y Asignación de Modo (Limpiar y Guardar)

# Convertimos el mensaje a mayúsculas para la detección (usaremos grep -q para IF)
UPPER_MESSAGE=$(echo "$INPUT_MESSAGE" | tr '[:lower:]' '[:upper:]')
MODE="DEFAULT"

# Prioridad 1: FLOW_FINISH (Máxima prioridad)
if echo "$UPPER_MESSAGE" | grep -q 'FLOW_FINISH'; then
    MODE="FINISH"
    CLEAN_MESSAGE=""
    SHOULD_CONTINUE="false"
    
    # Prioridad 2: FLOW_INITIAL
    elif echo "$UPPER_MESSAGE" | grep -q 'FLOW_INITIAL'; then
    MODE="INITIAL"
    # Quita la palabra clave del inicio del mensaje
    CLEAN_MESSAGE=$(echo "$INPUT_MESSAGE" | sed -e 's/FLOW_INITIAL//i' -e 's/^[[:space:]]*//')
    
    # Prioridad 3: FLOW_CONTINUE
    elif echo "$UPPER_MESSAGE" | grep -q 'FLOW_CONTINUE'; then
    MODE="CONTINUE"
    # Quita la palabra clave del inicio del mensaje
    CLEAN_MESSAGE=$(echo "$INPUT_MESSAGE" | sed -e 's/FLOW_CONTINUE//i' -e 's/^[[:space:]]*//')
    
else
    MODE="DEFAULT"
    CLEAN_MESSAGE="$INPUT_MESSAGE"
fi

# 3. Lógica del Switch y Construcción del Prompt con Here Document

# Usamos una variable para construir el contenido final del prompt.txt
FINAL_PROMPT_CONTENT=""

case "$MODE" in
    "INITIAL")
        # Concatena el archivo de contexto estático y el JSON de input.
        read -r -d '' FINAL_PROMPT_CONTENT <<EOF_INITIAL
$(cat $CONTEXT_FILE/prompt/initial.txt)

$CLEAN_MESSAGE
EOF_INITIAL
    ;;
    
    "CONTINUE")
        # Concatena el archivo de contexto estático, el mensaje limpio y el JSON de input.
        read -r -d '' FINAL_PROMPT_CONTENT <<EOF_CONTINUE
$(cat "$CONTEXT_FILE/prompt/initial.txt")

$(cat "$CONTEXT_FILE/prompt/continue.txt")

$CLEAN_MESSAGE
EOF_CONTINUE
    ;;
    
    "FINISH")
        # El comando FINISH no necesita un prompt complejo, pero lo crea para consistencia.
        FINAL_PROMPT_CONTENT="[FIN DE FLUJO]. No se requiere respuesta. shouldContinue=false"
    ;;
    
    "DEFAULT")
        # Concatena el mensaje original y el JSON de input.
        read -r -d '' FINAL_PROMPT_CONTENT <<EOF_DEFAULT
$CLEAN_MESSAGE
EOF_DEFAULT
    ;;
esac

# 4. Guardar el Prompt Final en prompt.txt
# Usamos 'echo -e' para asegurar que los saltos de línea se interpreten correctamente.
echo "$FINAL_PROMPT_CONTENT" > "$PROMPT_FILE_PATH"

# 5. Imprimir la SALIDA JSON MÍNIMA (SOLO EL BOOLEANO)
# Esto es lo único que n8n recibirá para el nodo IF.
echo "$SHOULD_CONTINUE"
# cat "$PROMPT_FILE_PATH"