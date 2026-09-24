// Public read routes are served through the edge cache; private ones never are.
//
// Every SPA boot calls six public D1 routes. Their Cache-Control header was
// only ever honoured by the visitor's own browser -- Pages Functions responses
// are not stored by the CDN -- so each page load by each visitor re-ran the
// queries. These tests drive the real handlers against a stand-in for
// caches.default and pin: a repeat request inside the TTL reads D1 zero times,
// the TTL follows the route class, failures are never cached, a broken cache
// fails open, and no private route ever touches the cache.

import assert from "node:assert/strict";
import test, { afterEach, beforeEach } from "node:test";

import { onRequestGet as summary } from "../functions/api/v1/summary.js";
import { onRequestGet as valuationTasks } from "../functions/api/v1/valuation-tasks.js";
import { onRequestGet as securities } from "../functions/api/v1/securities.js";
import { onRequestGet as security } from "../functions/api/v1/security/[ticker].js";
import { onRequestGet as riskLatest } from "../functions/api/v1/market-risk/latest.js";
import { onRequestGet as riskHistory } from "../functions/api/v1/market-risk/history.js";
import { onRequestGet as riskAlerts } from "../functions/api/v1/market-risk/alerts.js";
import { onRequestGet as riskHealth } from "../functions/api/v1/market-risk/health.js";
import { onRequestGet as riskComponents } from "../functions/api/v1/market-risk/components.js";
import { onRequestGet as riskSectors } from "../functions/api/v1/market-risk/sectors.js";
import { onRequestGet as portfolioBook } from "../functions/api/v2/portfolio/book.js";
import { onRequestGet as portfolioOrders } from "../functions/api/v2/portfolio/orders.js";
import { onRequestGet as orderIntents } from "../functions/api/v2/portfolio/order-intents.js";
import { onRequestGet as sleeveBook } from "../functions/api/v1/sleeves/book.js";
import { MARKET_RISK_TTL_SECONDS, RESEARCH_TTL_SECONDS } from "../functions/_lib/edge-cache.js";

// A caches.default stand-in: stores by URL, honours nothing but presence.
class FakeCache {
  constructor({ failing = false } = {}) { this.entries = new Map(); this.matches = 0; this.puts = 0; this.failing = failing; }
  async match(request) {
    this.matches += 1;
    if (this.failing) throw new Error("cache unavailable");
    const hit = this.entries.get(request.url);
    return hit ? hit.clone() : undefined;
  }
  async put(request, response) {
    this.puts += 1;
    if (this.failing) throw new Error("cache unavailable");
    this.entries.set(request.url, response.clone());
  }
}

// A D1 double that answers every query with one plausible row and counts calls.
function countingDb() {
  const counter = { queries: 0 };
  const row = { ticker_count: 843, open_count: 0, run_id: "r", generated_at: "2026-09-24T00:00:00Z" };
  const statement = () => ({
    bind() { return this; },
    async all() { counter.queries += 1; return { results: [row] }; },
    async first() { counter.queries += 1; return row; },
    async run() { counter.queries += 1; return { meta: { changes: 0 } }; },
  });
  const db = {
    prepare: () => statement(),
    async batch(statements) { counter.queries += statements.length; return statements.map(() => ({ results: [row] })); },
  };
  return { db, counter };
}

let cache;
beforeEach(() => { cache = new FakeCache(); globalThis.caches = { default: cache }; });
afterEach(() => { delete globalThis.caches; });

const PUBLIC_ROUTES = [
  ["summary", summary, "/api/v1/summary", RESEARCH_TTL_SECONDS],
  ["valuation-tasks", valuationTasks, "/api/v1/valuation-tasks?due=true&limit=100", RESEARCH_TTL_SECONDS],
  ["securities", securities, "/api/v1/securities?limit=5", RESEARCH_TTL_SECONDS],
  ["security", security, "/api/v1/security/MSFT", RESEARCH_TTL_SECONDS, { ticker: "MSFT" }],
  ["market-risk/latest", riskLatest, "/api/v1/market-risk/latest", MARKET_RISK_TTL_SECONDS],
  ["market-risk/history", riskHistory, "/api/v1/market-risk/history?symbol=SPY&limit=250", MARKET_RISK_TTL_SECONDS],
  ["market-risk/alerts", riskAlerts, "/api/v1/market-risk/alerts?open=false&limit=100", MARKET_RISK_TTL_SECONDS],
  ["market-risk/health", riskHealth, "/api/v1/market-risk/health", MARKET_RISK_TTL_SECONDS],
  ["market-risk/components", riskComponents, "/api/v1/market-risk/components", MARKET_RISK_TTL_SECONDS],
  ["market-risk/sectors", riskSectors, "/api/v1/market-risk/sectors", MARKET_RISK_TTL_SECONDS],
];

for (const [name, handler, path, ttl, params] of PUBLIC_ROUTES) {
  test(`${name}: a repeat request inside the TTL reads D1 zero times`, async () => {
    const { db, counter } = countingDb();
    const context = () => ({ request: new Request(`https://dash.example${path}`), env: { DB: db }, params: params || {} });

    const first = await handler(context());
    assert.equal(first.status, 200);
    assert.equal(first.headers.get("x-edge-cache"), "MISS");
    const queriesAfterFirst = counter.queries;
    assert.ok(queriesAfterFirst > 0);

    const second = await handler(context());
    assert.equal(second.status, 200);
    assert.equal(second.headers.get("x-edge-cache"), "HIT");
    assert.equal(counter.queries, queriesAfterFirst, "the second request must be served without touching D1");
    assert.deepEqual(await second.json(), await first.json());

    const stored = cache.entries.get(`https://dash.example${path}`);
    assert.equal(stored.headers.get("cache-control"), `public, max-age=${ttl}`);
    assert.equal(second.headers.get("cache-control"), first.headers.get("cache-control"),
      "the browser sees the same Cache-Control on a hit as on a miss");
  });
}

test("the key is the full URL: a different query is a different entry", async () => {
  const { db, counter } = countingDb();
  await riskHistory({ request: new Request("https://dash.example/api/v1/market-risk/history?symbol=SPY"), env: { DB: db } });
  const before = counter.queries;
  const other = await riskHistory({ request: new Request("https://dash.example/api/v1/market-risk/history?symbol=QQQ"), env: { DB: db } });
  assert.equal(other.headers.get("x-edge-cache"), "MISS");
  assert.ok(counter.queries > before);
});

test("an error is never cached", async () => {
  const broken = { prepare() { throw new Error("D1 over quota"); }, async batch() { throw new Error("D1 over quota"); } };
  const first = await summary({ request: new Request("https://dash.example/api/v1/summary"), env: { DB: broken } });
  assert.equal(first.status, 500);
  assert.equal(cache.puts, 0);
  const { db } = countingDb();
  const second = await summary({ request: new Request("https://dash.example/api/v1/summary"), env: { DB: db } });
  assert.equal(second.status, 200, "a recovered database answers at once, not after a cached 500 expires");
});

test("a failing cache fails open to the live handler", async () => {
  globalThis.caches = { default: new FakeCache({ failing: true }) };
  const { db, counter } = countingDb();
  const response = await summary({ request: new Request("https://dash.example/api/v1/summary"), env: { DB: db } });
  assert.equal(response.status, 200);
  assert.ok(counter.queries > 0);
});

test("private routes never read or write the cache", async () => {
  const { db } = countingDb();
  const env = { DB: db, PORTFOLIO_AUTH_MODE: "development", PORTFOLIO_DEVELOPMENT_OWNER: "drew" };
  for (const [handler, path] of [
    [portfolioBook, "/api/v2/portfolio/book?owner=all"],
    [portfolioOrders, "/api/v2/portfolio/orders"],
    [orderIntents, "/api/v2/portfolio/order-intents"],
    [sleeveBook, "/api/v1/sleeves/book?owner=drew"],
  ]) {
    await handler({ request: new Request(`http://localhost${path}`), env, params: {} });
  }
  assert.equal(cache.matches, 0, "a private route consulted the edge cache");
  assert.equal(cache.puts, 0, "a private route wrote to the edge cache");
});
