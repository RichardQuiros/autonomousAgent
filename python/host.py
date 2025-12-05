# host.py
import sys, json, struct, socket, threading, queue, os, platform, time, traceback, logging
from logging.handlers import RotatingFileHandler

# =========================
#  Configuración de logging
# =========================
def setup_logger():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "host.log")

    logger = logging.getLogger("cli_bridge")
    logger.setLevel(logging.INFO)

    # Evitar handlers duplicados si el script se recarga
    if not logger.handlers:
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fmt = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(threadName)s %(name)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    # No propagar al root para evitar que algo imprima a stderr
    logger.propagate = False
    return logger

LOG = setup_logger()

def log_env_info():
    try:
        LOG.info("==== Native Host starting ====")
        LOG.info("PID=%s | Python=%s | Platform=%s | CWD=%s",
                 os.getpid(), platform.python_version(), platform.platform(), os.getcwd())
    except Exception:
        # No imprimir a stdout/stderr — solo guardamos el stack al archivo
        LOG.exception("Error logging environment info")

# ==========================================
#  Utilidades de Native Messaging (STDIO)
#  ¡Nunca usar print()! Solo usar write_message con framing.
# ==========================================
def read_message():
    try:
        raw_len = sys.stdin.buffer.read(4)
        if not raw_len or len(raw_len) < 4:
            LOG.warning("STDIN cerrado o longitud inválida al leer encabezado.")
            return None
        msg_len = struct.unpack('<I', raw_len)[0]
        data = sys.stdin.buffer.read(msg_len)
        if not data or len(data) < msg_len:
            LOG.warning("STDIN datos insuficientes: esperados=%d, leídos=%d", msg_len, 0 if not data else len(data))
            return None
        obj = json.loads(data.decode('utf-8'))
        LOG.info("Desde EXTENSIÓN (STDIO) <= %s", safe_preview_json(obj))
        return obj
    except Exception:
        LOG.exception("Error leyendo mensaje desde EXTENSIÓN (STDIO).")
        return None

def write_message(msg_obj):
    try:
        data = json.dumps(msg_obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('<I', len(data)))
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        LOG.info("Hacia EXTENSIÓN (STDIO) => %s", safe_preview_json(msg_obj))
    except Exception:
        LOG.exception("Error escribiendo mensaje hacia EXTENSIÓN (STDIO).")

def safe_preview_json(obj, max_len=500):
    try:
        s = json.dumps(obj, ensure_ascii=False)
        return s if len(s) <= max_len else s[:max_len] + "...(trunc)"
    except Exception:
        return "<unserializable>"

# =======================
#  Puente TCP (CLI <-> Host)
# =======================
HOST = "0.0.0.0"
PORT = 7345

pending = {}
pending_lock = threading.Lock()

def tcp_client_handler(conn, addr):
    thread_name = threading.current_thread().name
    LOG.info("Conexión TCP aceptada desde %s:%s (thread=%s)", addr[0], addr[1], thread_name)
    req_id = None
    try:
        buf = conn.recv(900_000_000)
        if not buf:
            LOG.warning("Conexión vacía desde %s:%s", addr[0], addr[1])
            return

        try:
            msg = json.loads(buf.decode('utf-8'))
        except Exception as e:
            LOG.warning("JSON inválido desde %s:%s :: %s", addr[0], addr[1], e)
            conn.sendall(json.dumps({"ok": False, "error": f"JSON inválido: {e}"}).encode('utf-8'))
            return

        LOG.info("Desde CLI (TCP) <= %s", safe_preview_json(msg))

        req_id = msg.get("id")
        if not req_id:
            # id determinístico por cliente/puerto + timestamp corto
            req_id = f"tcp-{addr[0]}-{addr[1]}-{int(time.time()*1000)}"
            msg["id"] = req_id

        # Registrar cola y enviar a extensión
        q = queue.Queue(maxsize=1)
        with pending_lock:
            pending[req_id] = q

        write_message(msg)

        # Esperar respuesta de la extensión
        try:
            res = q.get(timeout=15 * 60)  # ajusta si necesitas más
        except queue.Empty:
            res = {"ok": False, "id": req_id, "error": "Timeout esperando respuesta de la extensión"}
            LOG.warning("Timeout esperando respuesta para id=%s", req_id)

        # Responder al cliente
        payload = json.dumps(res, ensure_ascii=False).encode('utf-8')
        conn.sendall(payload)
        LOG.info("Hacia CLI (TCP) => %s", safe_preview_json(res))
    except Exception:
        LOG.exception("Error en handler TCP para %s:%s", addr[0], addr[1])
        try:
            conn.sendall(json.dumps({"ok": False, "id": req_id, "error": "Excepción en host; ver logs"}).encode('utf-8'))
        except Exception:
            pass
    finally:
        with pending_lock:
            if req_id:
                pending.pop(req_id, None)
        try:
            conn.close()
        except Exception:
            pass
        LOG.info("Conexión TCP cerrada %s:%s", addr[0], addr[1])

def tcp_server():
    LOG.info("Iniciando servidor TCP… HOST=%s PORT=%s", HOST, PORT)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(8)
        LOG.info("Servidor TCP LISTENING en %s:%s (pid=%s)", HOST, PORT, os.getpid())
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=tcp_client_handler, args=(conn, addr), daemon=True)
            t.start()
    except Exception:
        LOG.exception("Error en servidor TCP principal.")
    finally:
        try:
            s.close()
        except Exception:
            pass
        LOG.info("Servidor TCP detenido.")

def from_extension_loop():
    LOG.info("Esperando mensajes desde EXTENSIÓN (loop STDIO)…")
    while True:
        msg = read_message()
        if msg is None:
            LOG.warning("Extensión desconectada o STDIN cerrado. Saliendo loop STDIO.")
            break

        req_id = msg.get("id")
        if not req_id:
            LOG.warning("Mensaje desde EXTENSIÓN sin 'id': %s", safe_preview_json(msg))
            continue

        # Entregar al cliente que espera esa respuesta
        with pending_lock:
            q = pending.get(req_id)

        if q:
            try:
                q.put(msg, timeout=0.1)
            except Exception:
                LOG.exception("No se pudo colocar respuesta en cola para id=%s", req_id)
        else:
            LOG.warning("Respuesta con id=%s no tiene cliente pendiente. ¿Timeout previo?", req_id)

def install_excepthook():
    def handle(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # No lo tratamos como error
            LOG.info("KeyboardInterrupt recibido. Cerrando.")
            return
        LOG.error("Excepción no capturada: %s", "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    sys.excepthook = handle

def main():
    install_excepthook()
    log_env_info()

    # Arranca el servidor TCP en un hilo
    tcp_thread = threading.Thread(target=tcp_server, name="TCP-Server", daemon=True)
    tcp_thread.start()

    # Bucle principal leyendo desde la extensión
    from_extension_loop()

    LOG.info("Terminando Native Host.")
    # Importante: salir sin imprimir nada
    os._exit(0)

if __name__ == "__main__":
    main()
