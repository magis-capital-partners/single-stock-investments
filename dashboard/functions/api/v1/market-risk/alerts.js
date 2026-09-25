import { boundedLimit, failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { ALL_ALERTS_SQL, OPEN_ALERTS_SQL } from "../../../_lib/market-risk.js";
import { MARKET_RISK_TTL_SECONDS, withEdgeCache } from "../../../_lib/edge-cache.js";

async function produce(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const url = new URL(context.request.url);
    const limit = boundedLimit(url.searchParams.get("limit"), 50, 250);
    const openOnly = url.searchParams.get("open") !== "false";
    // Index-ordered and LIMIT-bounded (migration 0020): reads ~`limit` rows,
    // not the whole table.
    const result = await db.prepare(openOnly ? OPEN_ALERTS_SQL : ALL_ALERTS_SQL).bind(limit).all();
    const items = (result.results || []).map((row) => {
      let reasons = [];
      let payload = {};
      try { reasons = JSON.parse(row.reason_codes_json || "[]"); } catch (_) { reasons = []; }
      try { payload = JSON.parse(row.payload_json || "{}"); } catch (_) { payload = {}; }
      return { ...row, reason_codes: reasons, payload };
    });
    return json({ items, count: items.length, open_only: openOnly, request_id: id });
  } catch (error) {
    return failure(error, id);
  }
}

// Public and identical for every caller, so served through the edge cache
// (market risk TTL; see _lib/edge-cache.js).
export async function onRequestGet(context) {
  return withEdgeCache(context, MARKET_RISK_TTL_SECONDS, () => produce(context));
}
