## Qué hace

Recibe **BASE64** (por STDIN o `--b64`), lo **decodifica**, **quita Markdown** (```), y **crea archivos** de forma segura.

---

## Uso básico

### 1️⃣ Crear **un solo archivo**

```bash
printf '%s' "$B64" | python3 /home/node/python/ai_write_files_b64.py \
  --outdir /ruta/proyecto \
  --single main.py \
  --lang python
```

➡ Base64 → decodifica → extrae `python` → escribe `main.py`

---

### 2️⃣ Crear **múltiples archivos**

El texto decodificado debe contener:

````text
file: src/app.py
```python
print("hola")
````

file: README.md

```md
# Proyecto
```

````

Ejecuta:
```bash
printf '%s' "$B64" | python3 /home/node/python/ai_write_files_b64.py --outdir /ruta/proyecto
````

➡ Crea todos los archivos automáticamente.

---

### 3️⃣ Pasar base64 como argumento (solo si es corto)

```bash
python3 /home/node/python/ai_write_files_b64.py \
  --outdir . \
  --single app.py \
  --b64 "cHJpbnQoImhvbGEiKQo="
```

---

### 4️⃣ Ver qué haría sin escribir nada

```bash
printf '%s' "$B64" | python3 /home/node/python/ai_write_files_b64.py \
  --outdir . \
  --single test.py \
  --dry-run
```

---

## Reglas importantes

* ✔ **NO** usar strings normales → **solo BASE64**
* ✔ Usar **STDIN** para contenido grande
* ✔ Elimina automáticamente `markdown`
* ✔ Bloquea rutas peligrosas (`../`)