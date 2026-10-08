import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { privateJson, requirePortfolioViewer } from "../../../_lib/auth.js";
import { loadBook } from "../../../_lib/sleeves.js";
import { evaluateSleeve } from "../../../_lib/time_average_growth.js";
import params from "../../../../data/time_average_growth_params.json" with { type: "json" };

export async function onRequestGet(context) {
  const id = requestId(context.request);
  const owner = new URL(context.request.url).searchParams.get("owner") || "michael";
  if (owner !== "michael") {
    return json({
      error: "Time-average growth is computed for Michael's sleeve only.",
      request_id: id,
    }, 400);
  }
  const viewer = await requirePortfolioViewer(context);
  if (!viewer) return privateJson({ error: "Unauthorized.", request_id: id }, 401);
  try {
    const db = requireDatabase(context.env);
    const book = await loadBook(db, "michael");
    const nav = Number(book.header?.nav_usd) || (book.positions || []).reduce(
      (sum, row) => sum + Math.abs(Number(row.market_value) || 0),
      0,
    );
    const panel = evaluateSleeve({
      nav,
      asOf: book.as_of,
      positions: book.positions || [],
      params,
    });
    return json({ ...panel, request_id: id }, 200, { "cache-control": "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}
