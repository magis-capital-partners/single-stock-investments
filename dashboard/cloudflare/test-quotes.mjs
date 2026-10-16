// Quotes pilot: D1-backed latest quotes, honest staleness, token-gated ingest.
import assert from "node:assert/strict";
import test from "node:test";

import { parseQuoteRow, parseSymbols } from "../functions/_lib/quotes.js";
import { onRequestGet } from "../functions/api/v1/quotes.js";
import { onRequestPost } from "../functions/api/v1/quotes/ingest.js";
import { parseStooqCsv } from "./quotes-ingest-worker.js";

const TOKEN = "q".repeat(32);

function fakeDb(rows) {
  const stored = new Map(rows.map((r) => [r.symbol, r]));
  const statement = (sql) => ({
    values: [],
    bind(...values) { this.values = values; return this; },
    async all() {
      return { results: this.values.filter((s) => stored.has(s)).map((s) => stored.get(s)) };
    },
    async run() { return { meta: { changes: 1 } }; },
    _sql: sql,
  });
  return {
    stored,
    prepare: (sql) => statement(sql),
    async batch(statements) {
      for (const stmt of statements) {
        const [symbol, price, previous_close, as_of, source, updated_at] = stmt.values;
        stored.set(symbol, { symbol, price, previous_close, as_of, source, updated_at });
      }
      return statements.map(() => ({ meta: { changes: 1 } }));
    },
  };
}

test("parseSymbols dedupes, uppercases, and rejects junk", () => {
  assert.deepEqual(parseSymbols("spy, QQQ,spy,bad symbol!,AAPL"), ["SPY", "QQQ", "AAPL"]);
  assert.equal(parseSymbols("x".repeat(60)).length <= 50, true);
});

test("parseQuoteRow computes change and staleness", () => {
  const now = Date.parse("2026-10-16T16:00:00Z");
  const fresh = parseQuoteRow({ symbol: "SPY", price: 505, previous_close: 500, as_of: "2026-10-16T15:59:00Z", source: "stooq" }, now);
  assert.equal(fresh.change_pct, 1);
  assert.equal(fresh.stale, false);
  const old = parseQuoteRow({ symbol: "SPY", price: 505, previous_close: 500, as_of: "2026-10-16T15:00:00Z", source: "stooq" }, now);
  assert.equal(old.stale, true);
  assert.equal(parseQuoteRow({ symbol: "SPY", price: 1, previous_close: 0, as_of: "bad", source: "x" }, now).stale, true);
});

test("GET serves stored quotes and reports missing symbols as stale", async () => {
  const db = fakeDb([{ symbol: "SPY", price: 505, previous_close: 500, as_of: new Date().toISOString(), source: "stooq" }]);
  const response = await onRequestGet({ request: new Request("https://dash.example/api/v1/quotes?symbols=SPY,QQQ"), env: { DB: db } });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.quotes.length, 2);
  assert.equal(body.quotes[0].symbol, "SPY");
  assert.equal(body.quotes[1].price, null);
  assert.equal(body.quotes[1].stale, true);
});

test("ingest requires the token and upserts rows", async () => {
  const db = fakeDb([]);
  const payload = JSON.stringify({ quotes: [{ symbol: "spy", price: 505, previous_close: 500, as_of: "2026-10-16T15:59:00Z", source: "stooq" }] });
  const denied = await onRequestPost({ request: new Request("https://dash.example/api/v1/quotes/ingest", { method: "POST", body: payload }), env: { DB: db, QUOTES_INGEST_TOKEN: TOKEN } });
  assert.equal(denied.status, 401);
  const accepted = await onRequestPost({
    request: new Request("https://dash.example/api/v1/quotes/ingest", { method: "POST", body: payload, headers: { authorization: `Bearer ${TOKEN}` } }),
    env: { DB: db, QUOTES_INGEST_TOKEN: TOKEN },
  });
  assert.equal(accepted.status, 202);
  assert.equal(db.stored.get("SPY").price, 505);
});

test("worker parses Stooq CSV into quote rows", () => {
  const rows = parseStooqCsv("Symbol,Date,Time,Open,High,Low,Close,Volume\nSPY.US,2026-10-16,15:59:00,1,1,1,505,100\nBAD.US,2026-10-16,15:59:00,1,1,1,N/D,0\n");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].symbol, "SPY");
  assert.equal(rows[0].price, 505);
  assert.equal(rows[0].source, "stooq");
});
