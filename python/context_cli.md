# Guía rápida de uso – CLI de contexto con cursor

## Objetivo

Leer y enviar archivos de contexto (`human` o `log`) **por partes**, sin exceder límites de texto, usando un **cursor** para continuar exactamente donde se quedó.

---

## Tipos de archivo

* **human** → `human*.txt`
* **log** → `log*.txt`
  Otros archivos se ignoran.

Directorio por defecto:

```
/data/gamegen/context/log
```

---

## Comandos

### 1) Listar archivos

```bash
./script.py files [--type human|log] [--since FECHA] [--until FECHA]
```

Fechas válidas:

* `YYYY-MM-DD`
* `YYYY-MM-DDTHH:MM`
* `YYYY-MM-DDTHH:MM:SS`

---

### 2) Obtener texto por chunks

```bash
./script.py get --type human|log [--max-chars N] [--cursor CURSOR]
```

* `--type` es obligatorio
* `--max-chars` (default: `12000`)
* `--cursor` se usa **solo** para continuar

Salida:

* Texto del contexto
* `NEXT_CURSOR` si hay más
* `FIN` si ya terminó

---

## Flujo correcto para una IA

1. **Primera llamada (sin cursor)**

```bash
./script.py get --type log --max-chars 12000
```

2. **Guardar `NEXT_CURSOR`**

3. **Continuar leyendo**

```bash
./script.py get --type log --max-chars 12000 --cursor "<NEXT_CURSOR>"
```

4. **Repetir hasta que aparezca `FIN`**

---

## Reglas importantes

* ❌ No inventar cursores
* ❌ No cambiar `--type`, `--since`, `--until` entre llamadas
* ✅ Usar siempre el `NEXT_CURSOR` devuelto
* ✅ Mantener `max-chars` constante durante la lectura

---

## Qué es el cursor (no decodificar)

Es un marcador interno (base64) que indica:

* archivo actual
* posición dentro del archivo

La IA **solo debe copiarlo y reutilizarlo**.

---

## Uso típico

* `human` → contexto humano / instrucciones
* `log` → eventos, trazas, registros

Enviar siempre el texto **tal como lo entrega el script**, incluyendo cabeceras.