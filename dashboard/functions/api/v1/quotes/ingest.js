import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { parseSymbols } from "../../../_lib/quotes.js";

// Ingest for the cron worker (dashboard/cloudflare/quotes-ingest-worker.js).
// Bearer-token gated with QUOTES_INGEST_TOKEN; quotes are public market data,
// so this guards against casual writes, not against a determined attacker --
// keep the token long and rotate it like the other ingest tokens.
const MAX_BODY_BYTES = 64_000;
const MAX_ROWS = 50;

function authorized(request, env) {
  const expected = String(env?.QUOTES_INGEST_TOKEN || "");
  const supplied = String(request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (expected.length < 24 || supplied.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < expected.length; index += 1) {
    difference |= expected.charCodeAt(index) ^ supplied.charCodeAt(index);
  }
  return difference === 0;
}

function finite(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    if (!authorized(context.request, context.env)) {
      return json({ error: "Unauthorized.", request_id: id }, 401, { "cache-control": "no-store" });
    }
    const body = await context.request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return json({ error: "Payload too large.", request_id: id }, 413, { "cache-control": "no-store" });
    }
    let payload;
    try {
      payload = JSON.parse(new TextDecoder().decode(body));
    } catch (_) {
      return json({ error: "Invalid JSON.", request_id: id }, 400, { "cache-control": "no-store" });
    }
    const rows = Array.isArray(payload.quotes) ? payload.quotes : [];
    if (!rows.length || rows.length > MAX_ROWS) {
      return json({ error: "Expected 1-50 quote rows.", request_id: id }, 400, { "cache-control": "no-store" });
    }
    const db = requireDatabase(context.env);
    const receivedAt = new Date().toISOString();
    const statements = [];
    for (const row of rows) {
      const [symbol] = parseSymbols(String(row.symbol || ""));
      const price = finite(row.price);
      const asOf = row.as_of && Number.isFinite(Date.parse(row.as_of)) ? row.as_of : null;
      if (!symbol || price == null || !asOf) {
        return json({ error: "Invalid quote row.", request_id: id }, 400, { "cache-control": "no-store" });
      }
      statements.push(
        db.prepare(`
          INSERT INTO quotes (symbol, price, previous_close, as_of, source, updated_at)
          VALUES (?, ?, ?, ?, ?, ?)
          ON CONFLICT (symbol) DO UPDATE SET
            price=excluded.price, previous_close=excluded.previous_close,
            as_of=excluded.as_of, source=excluded.source, updated_at=excluded.updated_at
        `).bind(symbol, price, finite(row.previous_close), asOf, String(row.source || "stooq"), receivedAt),
      );
    }
    await db.batch(statements);
    return json({ accepted: statements.length, request_id: id }, 202, { "cache-control": "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}
