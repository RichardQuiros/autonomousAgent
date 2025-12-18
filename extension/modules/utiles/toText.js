/**
 * Parsea una traza SSE en:
 *  - metadata: info útil de la sesión/respuesta (ids, eventos, título, estado, timestamps, etc.)
 *  - message: texto final reconstruido (principalmente desde "/message/content/parts/0",
 *             pero también soporta el patrón de "delta {v:'...'}" sin ruta)
 *  - thoughts: texto reconstruido de los eventos de tipo "thoughts"
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

  // ---- NUEVO: estado para capturar deltas sin "p" ----
  // Cuando detectamos que el stream está escribiendo en /message/content/parts/0,
  // algunos backends envían los siguientes trozos como { v: "..." } sin ruta.
  let streamingParts0 = false;

  const safeParse = (txt) => {
    try { return JSON.parse(txt); } catch { return null; }
  };

  const pushText = (val) => {
    if (typeof val === 'string' && val.length) messageParts.push(val);
  };

  const pushThought = (val) => {
    if (typeof val === 'string' && val.length) thoughtsParts.push(val);
  };

  const extractThoughtsFromThoughtArray = (arr) => {
    if (!Array.isArray(arr)) return;
    for (const th of arr) {
      if (!th || typeof th !== 'object') continue;
      if (typeof th.summary === 'string') pushThought(th.summary);
      if (typeof th.content === 'string') pushThought(th.content);
      if (Array.isArray(th.chunks)) {
        for (const ch of th.chunks) if (typeof ch === 'string') pushThought(ch);
      }
    }
  };

  const extractThoughtsFromMessage = (msg) => {
    if (!msg || typeof msg !== 'object') return;
    const content = msg.content;
    if (!content || typeof content !== 'object') return;
    if (content.content_type !== 'thoughts') return;
    extractThoughtsFromThoughtArray(content.thoughts);
  };

  const extractThoughtsFromPatchOps = (ops) => {
    if (!Array.isArray(ops)) return;
    for (const op of ops) {
      if (!op || typeof op !== 'object') continue;
      if (typeof op.p === 'string' && op.p.includes('/message/content/thoughts')) {
        const v = op.v;
        if (typeof v === 'string') pushThought(v);
        else if (Array.isArray(v)) {
          const allStrings = v.every(x => typeof x === 'string');
          if (allStrings) v.forEach(x => pushThought(x));
          else extractThoughtsFromThoughtArray(v);
        } else if (v && typeof v === 'object') {
          extractThoughtsFromThoughtArray([v]);
        }
      }
    }
  };

  // Extrae texto SOLO de ops sobre /message/content/parts/0
  // y activa streamingParts0 para capturar deltas posteriores sin "p".
  const extractMessageFromPartsOps = (ops) => {
    if (!Array.isArray(ops)) return false;
    let used = false;

    for (const op of ops) {
      if (!op || typeof op !== 'object') continue;
      if (typeof op.p !== 'string') continue;

      if (!op.p.startsWith('/message/content/parts/0')) continue;

      used = true;
      streamingParts0 = true; // <-- NUEVO: activa modo streaming

      const v = op.v;

      if (typeof v === 'string') {
        pushText(v);
      } else if (Array.isArray(v)) {
        const allStrings = v.every(x => typeof x === 'string');
        if (allStrings) v.forEach(x => pushText(x));
        else {
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

  // Opcional: corta el streaming cuando detectamos que terminó el turno
  const maybeStopStreamingFromOps = (ops) => {
    if (!Array.isArray(ops)) return;
    for (const op of ops) {
      if (!op || typeof op !== 'object') continue;
      // en tu traza aparece un patch con /message/end_turn true y status finished_successfully
      if (op.p === '/message/end_turn' && op.v === true) streamingParts0 = false;
      if (op.p === '/message/status' && typeof op.v === 'string' && op.v.startsWith('finished')) streamingParts0 = false;
    }
  };

  const lines = raw.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith(':')) continue;

    if (trimmed.startsWith('event:')) {
      currentEvent = trimmed.slice('event:'.length).trim();
      if (currentEvent) metadata.events.push(currentEvent);
      continue;
    }

    if (trimmed.startsWith('data:')) {
      const payloadTxt = trimmed.slice('data:'.length).trim();
      const obj = safeParse(payloadTxt);

      if (obj === null) {
        // Por ejemplo: [DONE]
        metadata.extras.push({ event: currentEvent, data: payloadTxt });
        // si llega DONE, cortamos streaming
        if (payloadTxt === '[DONE]') streamingParts0 = false;
        continue;
      }

      // Si viene un marcador de fin “tipo message_stream_complete”
      if (obj.type === 'message_stream_complete') {
        streamingParts0 = false;
        metadata.extras.push({ event: currentEvent, data: obj });
        continue;
      }

      // —— METADATA estándar —— //
      if (currentEvent === 'ready' && obj.request_message_id != null) {
        metadata.responseIds.request_message_id = obj.request_message_id;
        if (obj.response_message_id != null) metadata.responseIds.response_message_id = obj.response_message_id;
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
        streamingParts0 = false;
        if (Object.keys(obj).length) metadata.extras.push({ event: 'finish', data: obj });
        continue;
      }

      if (currentEvent === 'close') {
        metadata.close = obj;
        streamingParts0 = false;
        continue;
      }

      // Snapshot de la respuesta si aparece
      if (obj && obj.v && obj.v.response && typeof obj.v.response === 'object') {
        metadata.response = { ...metadata.response, ...obj.v.response };
      }

      // —— THOUGHTS —— //
      if (obj && obj.v && obj.v.message) extractThoughtsFromMessage(obj.v.message);

      // —— MENSAJE —— //

      // Caso A: patch explícito
      if (obj && obj.o === 'patch' && Array.isArray(obj.v)) {
        extractThoughtsFromPatchOps(obj.v);
        extractMessageFromPartsOps(obj.v);
        maybeStopStreamingFromOps(obj.v);
        metadata.extras.push({ event: currentEvent, data: obj });
        continue;
      }

      // Caso B: array de ops “implícito”
      if (Array.isArray(obj.v)) {
        const looksLikeOps = obj.v.some(
          el => el && typeof el === 'object' && typeof el.p === 'string' && typeof el.o === 'string'
        );

        if (looksLikeOps) {
          extractThoughtsFromPatchOps(obj.v);
          extractMessageFromPartsOps(obj.v);
          maybeStopStreamingFromOps(obj.v);
          metadata.extras.push({ event: currentEvent, data: obj });
          continue;
        }

        metadata.extras.push({ event: currentEvent, data: obj });
        continue;
      }

      // ---- NUEVO: soporte al patrón `event: delta` con `{ "v": "texto" }` sin ruta ----
      // Solo lo usamos si ya detectamos que se está streameando parts/0.
      if (currentEvent === 'delta' && streamingParts0 && typeof obj.v === 'string') {
        pushText(obj.v);
        continue;
      }

      // (Opcional extra) Si llega un delta con p directamente (no patch)
      // como en tu primer "append" (**El)
      if (currentEvent === 'delta' && typeof obj.p === 'string' && obj.p.startsWith('/message/content/parts/0')) {
        streamingParts0 = true;
        if (typeof obj.v === 'string') pushText(obj.v);
        metadata.extras.push({ event: currentEvent, data: obj });
        continue;
      }

      metadata.extras.push({ event: currentEvent, data: obj });
    }
  }

  return {
    metadata,
    message: messageParts.join(''),
    thoughts: thoughtsParts.join('\n')
  };
}
