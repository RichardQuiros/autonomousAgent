// bg.js

const METHODS = {
  async start() {
    init();
    return { ok: true, ts: Date.now() };
  },

  async reload() {
    sendCommand(
      this.botSetting.websites[0].TABS[0],
      this.botSetting.websites[0].COMMANDS.RELOAD
    );

    await new Promise(resolve => setTimeout(resolve, 3000));

    return { ok: true, ts: Date.now() };
  },

  async send(message = "", tabNumber = 0) {
    const tab = this.botSetting.websites[0].TABS[tabNumber];
    const template = this.botSetting.websites[0].COMMANDS.POST;

    // helper para cuando el placeholder está dentro de "?"
    function escapeForJsonString(str) {
      return String(str)
        .replace(/\\/g, "\\\\")
        .replace(/"/g, '\\"')
        .replace(/\n/g, "\\n")
        .replace(/\r/g, "\\r");
    }

    let command;

    // Si el template tiene "?" entre comillas, lo tratamos como string
    if (template.includes('"?"') || template.includes("'?'")) {
      const escaped = escapeForJsonString(message);
      command = template.replace("?", escaped);
    } else {
      // si no está entre comillas, asumimos que quiere JSON crudo
      command = template.replace("?", JSON.stringify(message));
    }

    sendCommand(tab, command);

    const body = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Timeout esperando respuesta")), 900_000); // 15 min
      pendingResponses.push((data) => {
        clearTimeout(timeout);
        resolve(data);
      });
    });
    return { ok: true, ts: Date.now(), body };
  }
};


// === 2) Ejecuta método por nombre de forma segura
async function runMethodByName(name, args = []) {
  const fn = METHODS[name];
  if (!fn) throw new Error(`Método no encontrado: ${name}`);
  return await fn(...args);
}

// === 3) (Opcional) Ejecutar en página activa si lo necesitas
async function runInActiveTab(funcSource, args = []) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("No hay pestaña activa");
  const [{ result, exceptionDetails }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id, allFrames: false },
    func: new Function('...args', `return (${funcSource})(...args)`),
    args
  });
  if (exceptionDetails) throw new Error("Error en la página");
  return result;
}

// === 4) Conexión al host nativo y puente TCP interno ===
const HOST_NAME = "com.local.cli_bridge";

let nativePort;
function connectNative() {
  nativePort = chrome.runtime.connectNative(HOST_NAME);

  nativePort.onMessage.addListener(async (msg) => {
    try {
      if (msg?.type === "RUN") {
        const res = await runMethodByName(msg.name, msg.args || []);
        nativePort.postMessage({ id: msg.id, ok: true, res });
      } else if (msg?.type === "RUN_IN_PAGE") {
        const res = await runInActiveTab(msg.funcSource, msg.args || []);
        nativePort.postMessage({ id: msg.id, ok: true, res });
      } else {
        nativePort.postMessage({ id: msg?.id, ok: false, error: "Tipo de mensaje no soportado" });
      }
    } catch (e) {
      nativePort.postMessage({ id: msg?.id, ok: false, error: String(e) });
    }
  });

  nativePort.onDisconnect.addListener(() => {
    console.log("Native host disconnected, retrying in 1s...");
    setTimeout(connectNative, 1000);
  });
}

connectNative();
