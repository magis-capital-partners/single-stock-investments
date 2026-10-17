// Latest-quote rows: shape, staleness, and symbol hygiene for /api/v1/quotes.
//
// A quote older than STALE_AFTER_MS is still served -- a stale price labelled
// stale beats a blank strip -- but the flag is computed here, in one place,
// so the API and the page agree on what "stale" means.

export const STALE_AFTER_MS = 15 * 60 * 1000;
export const MAX_SYMBOLS = 50;
const SYMBOL = /^[A-Z0-9][A-Z0-9.\-]{0,11}$/;

export function parseSymbols(raw) {
  const seen = new Set();
  for (const part of String(raw || "").split(",")) {
    const symbol = part.trim().toUpperCase();
    if (SYMBOL.test(symbol)) seen.add(symbol);
    if (seen.size >= MAX_SYMBOLS) break;
  }
  return [...seen];
}

export function parseQuoteRow(row, now = Date.now()) {
  if (!row) return null;
  const price = row.price == null ? null : Number(row.price);
  const previousClose = row.previous_close == null ? null : Number(row.previous_close);
  const asOfMs = Date.parse(row.as_of || "");
  const ageMs = Number.isFinite(asOfMs) ? Math.max(0, now - asOfMs) : null;
  return {
    symbol: row.symbol,
    price: Number.isFinite(price) ? price : null,
    previous_close: Number.isFinite(previousClose) ? previousClose : null,
    change_pct:
      Number.isFinite(price) && Number.isFinite(previousClose) && previousClose !== 0
        ? Math.round(((price - previousClose) / previousClose) * 10000) / 100
        : null,
    as_of: row.as_of,
    source: row.source || null,
    age_seconds: ageMs == null ? null : Math.round(ageMs / 1000),
    stale: ageMs == null ? true : ageMs > STALE_AFTER_MS,
  };
}
