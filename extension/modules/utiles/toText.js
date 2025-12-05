/**
 * Parsea una traza SSE en:
 *  - metadata: info útil de la sesión/respuesta (ids, eventos, título, estado, timestamps, etc.)
 *  - message: texto final reconstruido SOLO a partir de los ops sobre "/message/content/parts/0"
 *  - thoughts: texto reconstruido de los eventos de tipo "thoughts" (razonamiento/proceso)
 *
 * @param {string} raw - Traza completa SSE.
 * @returns {{ metadata: object, message: string, thoughts: string }}
 */
function parseSSE(raw) {
  const metadata = {
    events: [],
    responseIds: {},
    session: {},
    response: {},
    title: null,
    finished: false,
    close: null,
    extras: []
  };

  const messageParts = [];
  const thoughtsParts = [];
  let currentEvent = null;

  // Helpers básicos
  const safeParse = (txt) => {
    try { return JSON.parse(txt); } catch { return null; }
  };

  const pushText = (val) => {
    if (typeof val === 'string' && val.length) {
      messageParts.push(val);
    }
  };

  const pushThought = (val) => {
    if (typeof val === 'string' && val.length) {
      thoughtsParts.push(val);
    }
  };

  // Extraer texto de un array de "thoughts"
  const extractThoughtsFromThoughtArray = (arr) => {
    if (!Array.isArray(arr)) return;
    for (const th of arr) {
      if (!th || typeof th !== 'object') continue;
      if (typeof th.summary === 'string') pushThought(th.summary);
      if (typeof th.content === 'string') pushThought(th.content);
      if (Array.isArray(th.chunks)) {
        for (const ch of th.chunks) {
          if (typeof ch === 'string') pushThought(ch);
        }
      }
    }
  };

  // Extraer texto de un mensaje con content_type: "thoughts"
  const extractThoughtsFromMessage = (msg) => {
    if (!msg || typeof msg !== 'object') return;
    const content = msg.content;
    if (!content || typeof content !== 'object') return;
    if (content.content_type !== 'thoughts') return;
    extractThoughtsFromThoughtArray(content.thoughts);
  };

  // Extraer texto de un patch (ops) que afectan a /message/content/thoughts
  const extractThoughtsFromPatchOps = (ops) => {
    if (!Array.isArray(ops)) return;
    for (const op of ops) {
      if (!op || typeof op !== 'object') continue;

      if (typeof op.p === 'string' && op.p.includes('/message/content/thoughts')) {
        const v = op.v;

        if (typeof v === 'string') {
          // p.ej. replace summary con una string
          pushThought(v);
        } else if (Array.isArray(v)) {
          // puede ser array de strings o array de thoughts
          const allStrings = v.every(x => typeof x === 'string');
          if (allStrings) {
            v.forEach(x => pushThought(x));
          } else {
            extractThoughtsFromThoughtArray(v);
          }
        } else if (v && typeof v === 'object') {
          extractThoughtsFromThoughtArray([v]);
        }
      }
    }
  };

  // NUEVO: extraer texto visible SOLO de ops sobre /message/content/parts/0
  const extractMessageFromPartsOps = (ops) => {
    if (!Array.isArray(ops)) return false;
    let used = false;

    for (const op of ops) {
      if (!op || typeof op !== 'object') continue;
      if (typeof op.p !== 'string') continue;

      // Aquí “blindamos” el origen del mensaje:
      // solo rutas que empiezan por /message/content/parts/0
      if (!op.p.startsWith('/message/content/parts/0')) continue;

      const v = op.v;
      used = true;

      if (typeof v === 'string') {
        // p.ej. " /"
        pushText(v);
      } else if (Array.isArray(v)) {
        // Por si viene como array de strings u objetos simples
        const allStrings = v.every(x => typeof x === 'string');
        if (allStrings) {
          v.forEach(x => pushText(x));
        } else {
          for (const el of v) {
            if (!el || typeof el !== 'object') continue;
            if (typeof el.content === 'string') pushText(el.content);
            if (typeof el.v === 'string') pushText(el.v);
          }
        }
      } else if (v && typeof v === 'object') {
        if (typeof v.content === 'string') pushText(v.content);
        if (typeof v.v === 'string') pushText(v.v);
      }
    }

    return used;
  };

  const lines = raw.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith(':')) continue; // comentario SSE

    if (trimmed.startsWith('event:')) {
      currentEvent = trimmed.slice('event:'.length).trim();
      if (currentEvent) metadata.events.push(currentEvent);
      continue;
    }

    if (trimmed.startsWith('data:')) {
      const payloadTxt = trimmed.slice('data:'.length).trim();
      const obj = safeParse(payloadTxt);

      if (obj === null) {
        metadata.extras.push({ event: currentEvent, data: payloadTxt });
        continue;
      }

      // —— METADATA estándar —— //
      if (currentEvent === 'ready' && obj.request_message_id != null) {
        metadata.responseIds.request_message_id = obj.request_message_id;
        if (obj.response_message_id != null) {
          metadata.responseIds.response_message_id = obj.response_message_id;
        }
        continue;
      }

      if (currentEvent === 'update_session' && obj.updated_at != null) {
        metadata.session.updated_at = obj.updated_at;
        continue;
      }

      if (currentEvent === 'title' && typeof obj.content === 'string') {
        metadata.title = obj.content;
        continue;
      }

      if (currentEvent === 'finish') {
        metadata.finished = true;
        if (Object.keys(obj).length) metadata.extras.push({ event: 'finish', data: obj });
        continue;
      }

      if (currentEvent === 'close') {
        metadata.close = obj;
        continue;
      }

      // Snapshot de la respuesta si aparece
      if (obj && obj.v && obj.v.response && typeof obj.v.response === 'object') {
        metadata.response = { ...metadata.response, ...obj.v.response };
      }

      // —— EXTRACCIÓN DE THOUGHTS —— //

      // Caso 1: v.message con content_type "thoughts"
      if (obj && obj.v && obj.v.message) {
        extractThoughtsFromMessage(obj.v.message);
      }

      // —— EXTRACCIÓN DE MENSAJE VISIBLE SOLO DESDE /message/content/parts/0 —— //

      let usedPartsOps = false;

      // Caso A: patch clásico: { o: "patch", v: [ops...] }
      if (obj && obj.o === 'patch' && Array.isArray(obj.v)) {
        extractThoughtsFromPatchOps(obj.v);
        usedPartsOps = extractMessageFromPartsOps(obj.v);

        // Un patch no lo tratamos como mensaje genérico; ya hemos extraído lo que nos interesa
        metadata.extras.push({ event: currentEvent, data: obj });
        continue;
      }

      // Caso B: backend envía directamente un array de ops en obj.v (sin obj.o="patch")
      if (Array.isArray(obj.v)) {
        // Primero miramos si parecen ops (tienen p y o)
        const looksLikeOps = obj.v.some(
          el => el && typeof el === 'object' && typeof el.p === 'string' && typeof el.o === 'string'
        );

        if (looksLikeOps) {
          // Los tratamos como patch implícito
          extractThoughtsFromPatchOps(obj.v);
          usedPartsOps = extractMessageFromPartsOps(obj.v);

          metadata.extras.push({ event: currentEvent, data: obj });
          continue;
        }

        // ⚠️ IMPORTANTE:
        // Ya no usamos arrays genéricos para rellenar message,
        // porque queremos que message SOLO venga de /message/content/parts/0
        // Así que lo mandamos a extras.
        metadata.extras.push({ event: currentEvent, data: obj });
        continue;
      }

      // ⚠️ IMPORTANTE:
      // Tampoco usamos obj.v string genérico para message.
      // message SOLO se alimenta de extractMessageFromPartsOps().
      metadata.extras.push({ event: currentEvent, data: obj });
    }
  }

  return {
    metadata,
    // Contenido visible solo a partir de /message/content/parts/0
    message: messageParts.join(''),
    // Logs de proceso / razonamiento
    thoughts: thoughtsParts.join('\n')
  };
}
