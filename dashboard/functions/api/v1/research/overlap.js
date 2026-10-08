import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { privateJson, requirePortfolioViewer } from "../../../_lib/auth.js";
import { loadBook } from "../../../_lib/sleeves.js";
import { baseMarketValue, loadPortfolio } from "../../../_lib/portfolio.js";
import { evaluateOverlap } from "../../../_lib/overlap_map.js";
import holdings from "../../../../data/overlap_holdings.json" with { type: "json" };

const SCOPES = new Set(["universe", "owned", "michael", "drew"]);

export async function onRequestGet(context) {
  const id = requestId(context.request);
  const scope = new URL(context.request.url).searchParams.get("scope") || "universe";
  if (!SCOPES.has(scope)) return json({ error: "Unknown scope.", request_id: id }, 400);
  if (scope !== "universe") {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return privateJson({ error: "Unauthorized.", request_id: id }, 401);
  }
  try {
    const positions = scope === "universe" ? null : await positionsFor(context, scope);
    const panel = evaluateOverlap({
      names: holdings.names,
      scope,
      positions,
      asOf: holdings.as_of,
      quarter: holdings.quarter,
      coverage: {
        ...(holdings.coverage || {}),
        holder_set_note: holdings.holder_set_note,
        mode: holdings.mode,
        built_at: holdings.built_at,
      },
    });
    return json({ ...panel, request_id: id }, 200, { "cache-control": scope === "universe" ? "public, max-age=3600" : "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}

async function positionsFor(context, scope) {
  if (scope === "michael" || scope === "drew") {
    const db = requireDatabase(context.env);
    const book = await loadBook(db, scope);
    return (book.positions || [])
      .filter((row) => row.sec_type === "STK" && Number(row.market_value))
      .map((row) => ({ ticker: row.ticker, market_value: Number(row.market_value) }));
  }
  const book = await loadPortfolio(context.env, "all");
  const totals = new Map();
  for (const row of book.positions || []) {
    if (row.sec_type !== "STK") continue;
    const value = baseMarketValue(row, "USD");
    if (value == null || value === 0) continue;
    const ticker = String(row.symbol || "").toUpperCase();
    totals.set(ticker, (totals.get(ticker) || 0) + value);
  }
  return [...totals.entries()].map(([ticker, market_value]) => ({ ticker, market_value }));
}
