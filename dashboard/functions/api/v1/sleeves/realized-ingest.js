import { privateJson } from '../../../_lib/auth.js';
import { failure, requestId, requireDatabase } from '../../../_lib/http.js';
import { verifySleeveHmac } from '../../../_lib/sleeves.js';
import { MAX_INGEST_BYTES, storeRealized } from '../../../_lib/realized.js';

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    if (Number(context.request.headers.get('content-length') || 0) > MAX_INGEST_BYTES) return privateJson({ error: 'Payload too large.' }, 413);
    // Bound the stream before buffering; an absent Content-Length cannot bypass
    // the ingest cap and exhaust the Pages Function's memory.
    const reader = context.request.body?.getReader();
    const chunks = []; let size = 0;
    if (reader) {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_INGEST_BYTES) { await reader.cancel(); return privateJson({ error: 'Payload too large.' }, 413); }
        chunks.push(value);
      }
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const authorization = await verifySleeveHmac(context.request, context.env, bytes.buffer);
    if (!authorization) return privateJson({ error: 'Unauthorized or expired signature.' }, 401);
    let payload;
    try { payload = JSON.parse(new TextDecoder().decode(bytes)); } catch { return privateJson({ error: 'Invalid JSON.' }, 400); }
    const db = requireDatabase(context.env);
    const nonce = await db.prepare('INSERT OR IGNORE INTO sleeve_ingest_nonces(nonce) VALUES (?)').bind(authorization.nonce).run();
    if (Number(nonce.meta?.changes || 0) !== 1) return privateJson({ error: 'Replay rejected.' }, 409);
    const result = await storeRealized(context.env, payload);
    return privateJson({ ok: true, ...result, request_id: id });
  } catch (error) {
    if (error instanceof TypeError) return privateJson({ error: error.message, request_id: id }, 400);
    return failure(error, id);
  }
}
