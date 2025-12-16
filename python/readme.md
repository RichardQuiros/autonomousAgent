Perfecto. Aquí tienes un **README.md** claro, ordenado y “copiar/pegar friendly”, pensado para que **tú (o cualquier otro)** pueda montar el bridge sin dolor dentro de 3 meses 😄

---

# CLI ↔ Extension Native Messaging Bridge

Este proyecto implementa un **Native Messaging Host** para Chrome / Edge que actúa como **puente** entre:

* una **extensión de navegador** (STDIO – protocolo Native Messaging)
* un **servidor TCP local** (CLI / Docker / procesos externos)

Arquitectura resumida:

```
Extension (Chrome/Edge)
        │
        │  Native Messaging (STDIO)
        ▼
     host.py
        │
        │  TCP (JSON)
        ▼
   Clientes CLI / Docker / Apps
```

---

## 📁 Estructura del proyecto

Todos los archivos deben vivir **en la misma carpeta**:

```
/python
  ├─ host.py
  ├─ host.cmd
  ├─ bridge.json
  ├─ setup_bridge.ps1
  └─ logs/
      └─ host.log
```

---

## ✅ Requisitos

* Windows 10/11
* Python 3.x (recomendado instalar desde python.org)

  * ✅ marcar **“Add Python to PATH”**
* PowerShell
* Permisos de Administrador (para firewall)

Navegadores compatibles:

* Google Chrome
* Microsoft Edge

---

## 🧠 Componentes

### `host.py`

* Proceso principal (Native Host)
* Lee mensajes desde la extensión por **STDIO**
* Abre un servidor TCP local (`0.0.0.0:7345`)
* Reenvía mensajes entre extensión ⇄ clientes TCP
* Logs rotativos en `logs/host.log`

---

### `host.cmd`

* Lanzador para Windows
* Calcula automáticamente la ruta a `host.py`
* Ejecuta Python usando `py`, `python` o `python3`
* Permite ejecutar el host de forma oculta

---

### `bridge.json`

* Manifiesto de Native Messaging
* Declarado en el registro de Windows
* Define:

  * nombre del bridge (`com.local.cli_bridge`)
  * path a `host.cmd`
  * extensiones permitidas (`allowed_origins`)

---

### `setup_bridge.ps1`

✅ **Script instalador automático**

Se encarga de:

* Detectar rutas automáticamente
* Pedir el **ID de la extensión**
* Actualizar `bridge.json`
* Registrar el Native Host en:

  * Chrome
  * Edge
* Crear regla de **Windows Firewall**
* (Opcional) definir variables de entorno

---

## 🚀 Instalación paso a paso

### 1️⃣ Colocar los archivos

Copia estos archivos en una carpeta:

```
host.py
host.cmd
bridge.json
setup_bridge.ps1
```

Ejemplo de ruta:

```
C:\Users\pqric\Documents\extensions\tooltBot\python
```

---

### 2️⃣ Abrir PowerShell como Administrador

⚠️ Obligatorio para crear la regla de firewall.

---

### 3️⃣ Ir a la carpeta del proyecto

```powershell
cd "C:\Users\pqric\Documents\extensions\tooltBot\python"
```

---

### 4️⃣ Permitir ejecución de scripts (solo la primera vez)

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Responde `Y` si lo pide.

---

### 5️⃣ Ejecutar el instalador

```powershell
.\setup_bridge.ps1
```

El instalador te pedirá:

* ✅ **ID de la extensión**
  Ejemplo:

  ```
  pjkgfpacjkfdafcppfjimceefbpnimed
  ```

* ✅ **Puerto TCP** (por defecto `7345`)
  Pulsa ENTER para aceptar.

* ✅ Si quieres definir variables de entorno

  * `SOCKET_HOST=host.docker.internal`
  * `SOCKET_PORT=7345`

---

### 6️⃣ Reiniciar Chrome / Edge

Los navegadores **deben cerrarse y abrirse de nuevo** para reconocer el Native Host.

---

## ▶️ Ejecutar el host (modo oculto)

Para arrancar el bridge en segundo plano:

```powershell
Start-Process cmd.exe `
  -ArgumentList "/c C:\Users\pqric\Documents\extensions\tooltBot\python\host.cmd" `
  -WindowStyle Hidden
```

🟢 No aparece ninguna ventana
🟢 El socket queda escuchando
🟢 La extensión puede conectarse

---

## 🔎 Verificar que el servidor TCP está activo

```powershell
netstat -ano | findstr :7345
```

Deberías ver algo como:

```
TCP    0.0.0.0:7345    0.0.0.0:0    LISTENING
```

---

## 🔐 Puertos y seguridad

* El servidor escucha en `0.0.0.0:7345`
* Uso recomendado:

  * conexiones **locales**
  * Docker mediante `host.docker.internal`
* El instalador crea una regla de firewall **solo para ese puerto**

---

## 📄 Logs

Los logs se escriben en:

```
logs/host.log
```

Incluyen:

* arranque del host
* conexiones TCP
* mensajes enviados/recibidos
* errores y excepciones

---

## 🛑 Detener el host

Como se ejecuta sin ventana:

1. Abre el Administrador de tareas
2. Busca `python.exe`
3. Finaliza el proceso

(O crea luego un servicio con NSSM para controlarlo mejor)

---

## ✅ Estado final

Después de completar los pasos tendrás:

* ✅ Native Messaging configurado
* ✅ Bridge funcional (STDIO ⇄ TCP)
* ✅ Firewall abierto
* ✅ Logs activos
* ✅ Ejecución en background

---

## 📌 Notas finales

* Este bridge usa **TCP + JSON**, no WebSockets.
* Si necesitas WebSocket para navegador directo, se debe añadir otro servidor.
* El diseño actual es ideal para:

  * extensiones
  * CLI tools
  * Docker
  * automatización local

---

Si quieres, el siguiente paso puede ser:

* ejemplo de **cliente TCP**
* auto-arranque con Windows
* convertirlo en servicio
* endurecer seguridad (bind solo a localhost)

Tú mandas 🚀
