import { failure, json, requestId, requireDatabase } from "../../_lib/http.js";
import { parseQuoteRow, parseSymbols } from "../../_lib/quotes.js";
import { MARKET_RISK_TTL_SECONDS, withEdgeCache } from "../../_lib/edge-cache.js";

// Latest quotes from D1, written by the Cloudflare cron worker through
// /api/v1/quotes/ingest. Read-only and identical for every caller, so it is
// edge-cached like the market-risk routes. Symbols with no row yet are
// reported as stale with a null price rather than dropped, so the page can
// show "no quote yet" per symbol instead of guessing.
async function produce(context) {
  const id = requestId(context.request);
  try {
    const url = new URL(context.request.url);
    const symbols = parseSymbols(url.searchParams.get("symbols") || "SPY,QQQ");
    if (!symbols.length) {
      return json({ error: "No valid symbols.", request_id: id }, 400, { "cache-control": "no-store" });
    }
    const db = requireDatabase(context.env);
    const placeholders = symbols.map(() => "?").join(",");
    const result = await db
      .prepare(`SELECT symbol, price, previous_close, as_of, source FROM quotes WHERE symbol IN (${placeholders})`)
      .bind(...symbols)
      .all();
    const bySymbol = new Map((result.results || []).map((row) => [row.symbol, parseQuoteRow(row)]));
    const quotes = symbols.map(
      (symbol) => bySymbol.get(symbol) || { symbol, price: null, previous_close: null, change_pct: null, as_of: null, source: null, age_seconds: null, stale: true },
    );
    return json({
      schema_version: 1,
      research_only: true,
      generated_at: quotes.map((q) => q.as_of).filter(Boolean).sort().at(-1) || null,
      quotes,
      stale: quotes.some((q) => q.stale),
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}

export async function onRequestGet(context) {
  return withEdgeCache(context, MARKET_RISK_TTL_SECONDS, () => produce(context));
}
