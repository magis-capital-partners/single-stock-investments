// Cron worker: refresh D1 latest quotes from a public source and POST them
// to the dashboard's ingest route. Runs on Cloudflare's scheduler, so quote
// freshness no longer waits on a GitHub commit or a Pages deploy.
//
// This reads a public quote file (Stooq). It never touches a brokerage
// session: this repo holds no idle Gateway connection, and the dashboard is
// a research surface, not an execution screen.
//
// Deploy (manual, like market-risk-ingest-worker.js):
//   wrangler deploy dashboard/cloudflare/quotes-ingest-worker.js \
//     --name magis-quotes-ingest --triggers "*/5 13-21 * * 1-5"
// Secrets / vars: DASHBOARD_URL (Pages origin), QUOTES_INGEST_TOKEN,
// QUOTES_SYMBOLS (optional, comma list; default SPY,QQQ).

const DEFAULT_SYMBOLS = ["SPY", "QQQ"];

export function stooqSymbol(symbol) {
  return `${symbol.toLowerCase()}.us`;
}

export function parseStooqCsv(text, fetchedAt = new Date()) {
  const lines = String(text || "").trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const column = (name) => header.indexOf(name);
  const rows = [];
  for (const line of lines.slice(1)) {
    const cells = line.split(",");
    const rawSymbol = (cells[column("symbol")] || "").trim().toUpperCase();
    const close = Number(cells[column("close")]);
    if (!rawSymbol || !Number.isFinite(close)) continue;
    const date = (cells[column("date")] || "").trim();
    const time = (cells[column("time")] || "").trim();
    const asOf = date && time ? new Date(`${date}T${time}Z`) : fetchedAt;
    rows.push({
      symbol: rawSymbol.replace(/\.US$/, ""),
      price: close,
      previous_close: null,
      as_of: (Number.isFinite(asOf.getTime()) ? asOf : fetchedAt).toISOString(),
      source: "stooq",
    });
  }
  return rows;
}

async function refresh(env) {
  const symbols = String(env.QUOTES_SYMBOLS || "")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  const wanted = (symbols.length ? symbols : DEFAULT_SYMBOLS).slice(0, 50);
  const query = wanted.map(stooqSymbol).join(",");
  const response = await fetch(`https://stooq.com/q/l/?s=${encodeURIComponent(query)}&f=sd2t2ohlcv&h&e=csv`);
  if (!response.ok) throw new Error(`stooq ${response.status}`);
  const quotes = parseStooqCsv(await response.text());
  if (!quotes.length) throw new Error("stooq returned no usable rows");
  const base = String(env.DASHBOARD_URL || "").replace(/\/$/, "");
  if (!base) throw new Error("DASHBOARD_URL is not configured");
  const posted = await fetch(`${base}/api/v1/quotes/ingest`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${env.QUOTES_INGEST_TOKEN || ""}`,
    },
    body: JSON.stringify({ quotes }),
  });
  if (!posted.ok) throw new Error(`ingest ${posted.status}`);
  return quotes.length;
}

export default {
  async scheduled(_event, env, context) {
    context.waitUntil(
      refresh(env).catch((error) => console.error(JSON.stringify({ message: "quotes refresh failed", error: String(error) }))),
    );
  },
  async fetch(request) {
    if (request.method !== "GET") return new Response("Method not allowed.", { status: 405 });
    return new Response("quotes ingest worker: cron only", { status: 404 });
  },
};
