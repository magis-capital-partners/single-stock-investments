import { verifyPortfolioHmac } from "./portfolio.js";
import { privateJson } from "./auth.js";
import { requireDatabase } from "./http.js";

export const EXECUTION_DOMAIN = "rs_execution_paper";
export const EXECUTION_HEADER = "x-ssi-ingest-purpose";
const MAX_BYTES = 512_000;
const SESSION_ID = /^[a-f0-9]{32}$/;
const ORDER_REF = /^RSPAPER\|[a-f0-9]{20}$/;
const ISO_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const MAX_CLOCK_SKEW = 30_000;

export function validPaperExecution(body, now = Date.now()) {
  return body?.schema === "rs_execution.v1" && body.mode === "paper"
    && SESSION_ID.test(body.session_id ?? "") && ISO_TIME.test(body.observed_at ?? "")
    && Math.abs(Date.parse(body.observed_at) - now) <= MAX_CLOCK_SKEW
    && typeof body.ended === "boolean" && body.pnl?.currency === "USD"
    && Array.isArray(body.orders) && body.orders.every(row => ORDER_REF.test(row?.ref ?? ""))
    && Array.isArray(body.fills) && body.fills.every(row => ORDER_REF.test(row?.ref ?? ""))
    && Array.isArray(body.events) && body.events.every(row => !row?.ref || ORDER_REF.test(row.ref))
    && Array.isArray(body.positions);
}

export async function ingestPaperExecution(context, bytes) {
  if (bytes.byteLength > MAX_BYTES) return privateJson({ error: "Paper session exceeds the feed size limit." }, 413);
  const env = context.env;
  const key = env.RS_EXECUTION_PUBLISH_KEY;
  const domain = { domain: EXECUTION_DOMAIN };
  const authorization = await verifyPortfolioHmac(context.request, { PORTFOLIO_INGEST_TOKEN: key }, bytes, domain);
  if (!authorization || Math.abs(Date.now() - Number(authorization.timestamp) * 1000) > MAX_CLOCK_SKEW) {
    return privateJson({ error: "Invalid paper publisher signature." }, 401);
  }
  let body;
  try { body = JSON.parse(new TextDecoder().decode(bytes)); }
  catch { return privateJson({ error: "Invalid paper session JSON." }, 400); }
  if (body?.schema === "rs_execution_probe.v1") {
    // The supervised runner verifies the publisher and migration before a broker session.
    await requireDatabase(env).prepare("SELECT session_id FROM rs_execution_paper LIMIT 1").first();
    return privateJson({ available: true });
  }
  const now = Date.now();
  if (!validPaperExecution(body, now)) return privateJson({ error: "Invalid paper session snapshot." }, 422);
  const receivedAt = new Date(now).toISOString();
  const result = await requireDatabase(env).prepare(`INSERT INTO rs_execution_paper
      (session_id, observed_at, received_at, ended, body) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(session_id) DO UPDATE SET observed_at=excluded.observed_at,
        received_at=excluded.received_at, ended=excluded.ended, body=excluded.body
      WHERE excluded.observed_at > rs_execution_paper.observed_at
        AND rs_execution_paper.ended = 0
        AND json_array_length(excluded.body, '$.orders') >= json_array_length(rs_execution_paper.body, '$.orders')
        AND json_array_length(excluded.body, '$.fills') >= json_array_length(rs_execution_paper.body, '$.fills')
        AND json_array_length(excluded.body, '$.events') >= json_array_length(rs_execution_paper.body, '$.events')`)
    .bind(body.session_id, body.observed_at, receivedAt, Number(body.ended), JSON.stringify(body)).run();
  // Exact retries or older signed snapshots cannot change the stored session.
  return privateJson({ stored: Boolean(result.meta?.changes), received_at: receivedAt });
}

export async function readPaperExecution(context) {
  const requested = new URL(context.request.url).searchParams.get("session");
  if (requested !== null && !SESSION_ID.test(requested)) return privateJson({ error: "Invalid paper session." }, 400);
  const db = requireDatabase(context.env);
  const result = await db.prepare(`SELECT session_id, observed_at, received_at, ended FROM rs_execution_paper
    ORDER BY observed_at DESC, session_id DESC LIMIT 25`).all();
  const sessions = result.results ?? [];
  const id = requested ?? sessions[0]?.session_id;
  const row = id ? await db.prepare(
    "SELECT body, received_at FROM rs_execution_paper WHERE session_id = ?",
  ).bind(id).first() : null;
  if (requested && !row) return privateJson({ error: "Paper session not found." }, 404);
  return privateJson({
    mode: "paper",
    snapshot: row ? JSON.parse(row.body) : null,
    received_at: row?.received_at ?? null,
    sessions,
  });
}
