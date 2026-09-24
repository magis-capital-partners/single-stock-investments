// The command-channel peek, against real SQL.
//
// The property that matters is the one D1 bills for: an idle bridge tick must
// write nothing. Before the peek, every 15s tick called both claim routes, and
// each reserved a nonce row first -- ~34k billed row writes a day, plus ~10k
// more when retention deleted them, to say "nothing to do". These tests pin
// that the peek writes no row, answers a replay, agrees with the claim routes
// about what is claimable, and reads through an index rather than a scan.

import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { createHmac, randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { onRequestPost as peek, PEEK_CONTRACT_LOOKUPS_SQL, PEEK_ORDER_REQUESTS_SQL } from "../functions/api/v2/portfolio/ingest/peek.js";
import { onRequestPost as claimOrders } from "../functions/api/v2/portfolio/ingest/order-requests/claim.js";
import { onRequestPost as claimLookups } from "../functions/api/v2/portfolio/ingest/contract-lookups/claim.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKEN = "x".repeat(48);
const ACCOUNT = "U805366";

// A D1-shaped adapter whose batch() returns per-statement results the way D1
// does, so a batched SELECT is read back exactly as production reads it.
function d1(database) {
  const make = (sql, binds = []) => {
    const values = () => binds.map((value) => (value === undefined ? null : typeof value === "boolean" ? Number(value) : value));
    return {
      sql,
      bind: (...next) => make(sql, next),
      run: async () => ({ meta: { changes: Number(database.prepare(sql).run(...values()).changes || 0) } }),
      all: async () => ({ results: database.prepare(sql).all(...values()) }),
      first: async () => database.prepare(sql).get(...values()) ?? null,
      _batch: () => (/^\s*select/i.test(sql)
        ? { results: database.prepare(sql).all(...values()) }
        : { results: [], meta: { changes: Number(database.prepare(sql).run(...values()).changes || 0) } }),
    };
  };
  return { prepare: (sql) => make(sql), batch: async (statements) => statements.map((statement) => statement._batch()) };
}

function freshDatabase() {
  const database = new DatabaseSync(":memory:");
  const dir = join(HERE, "migrations");
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".sql")).sort()) {
    const sql = readFileSync(join(dir, file), "utf8").replace(/--[^\n]*/g, "");
    for (const statement of sql.split(";").map((part) => part.trim()).filter(Boolean)) {
      try { database.exec(statement); } catch (_) { /* unrelated legacy tables */ }
    }
  }
  return database;
}

function signed(url, payload) {
  const body = JSON.stringify(payload);
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID().replace(/-/g, "");
  const signature = createHmac("sha256", TOKEN).update(`${timestamp}\n${nonce}\n${body}`).digest("hex");
  return new Request(url, {
    method: "POST", body,
    headers: {
      "content-type": "application/json", "x-portfolio-timestamp": timestamp,
      "x-portfolio-nonce": nonce, "x-portfolio-signature": signature,
    },
  });
}

const env = (database) => ({ DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN });

async function call(handler, database, payload = { account_alias: ACCOUNT }) {
  const response = await handler({ request: signed("https://dash.example/x", payload), env: env(database) });
  return { status: response.status, body: await response.json() };
}

const totalChanges = (database) => database.prepare("SELECT total_changes() AS n").get().n;
const ago = (seconds) => new Date(Date.now() - seconds * 1000).toISOString();

function seedRequest(database, overrides = {}) {
  const row = {
    request_id: randomUUID(), account_alias: ACCOUNT, owner: "drew", strategy: "single_stock",
    conid: 272093, symbol: "MSFT", sec_type: "STK", action: "BUY", quantity_decimal: "1",
    limit_price_decimal: "400", tif: "DAY", outside_rth: 0, mode: "paper", state: "requested",
    created_at: ago(5), updated_at: ago(5), ...overrides,
  };
  database.prepare(`INSERT INTO portfolio_order_requests (${Object.keys(row).join(",")})
    VALUES (${Object.keys(row).map(() => "?").join(",")})`).run(...Object.values(row));
  return row.request_id;
}

function seedLookup(database, overrides = {}) {
  const row = {
    lookup_id: randomUUID(), account_alias: ACCOUNT, owner: "drew", kind: "contract",
    symbol: "MSFT", sec_type: "STK", state: "requested", created_at: ago(5), updated_at: ago(5), ...overrides,
  };
  database.prepare(`INSERT INTO portfolio_contract_lookups (${Object.keys(row).join(",")})
    VALUES (${Object.keys(row).map(() => "?").join(",")})`).run(...Object.values(row));
  return row.lookup_id;
}

test("an idle peek writes no row at all -- no nonce, no lease", async () => {
  const database = freshDatabase();
  const before = totalChanges(database);
  const { status, body } = await call(peek, database);
  assert.equal(status, 200);
  assert.deepEqual(body.claimable, { order_requests: 0, contract_lookups: 0 });
  assert.equal(totalChanges(database) - before, 0, "the idle peek must not write");
  assert.equal(database.prepare("SELECT COUNT(*) AS n FROM portfolio_ingest_nonces").get().n, 0);
});

test("for contrast: the claims it replaces write a nonce row each, idle or not", async () => {
  // This is the cost the peek removes. Two signed claims per 15s tick, each a
  // nonce insert, on a desk with nothing to do.
  const database = freshDatabase();
  await call(claimOrders, database);
  await call(claimLookups, database);
  assert.equal(database.prepare("SELECT COUNT(*) AS n FROM portfolio_ingest_nonces").get().n, 2);
});

test("a replayed peek is answered and still changes nothing", async () => {
  const database = freshDatabase();
  const key = seedRequest(database);
  const request = signed("https://dash.example/x", { account_alias: ACCOUNT });
  const before = totalChanges(database);
  const first = await peek({ request: request.clone(), env: env(database) });
  const second = await peek({ request, env: env(database) });
  assert.equal(first.status, 200);
  assert.equal(second.status, 200, "no nonce: a replay inside the signature window is answered");
  assert.equal(totalChanges(database) - before, 0);
  const row = database.prepare("SELECT state, claimed_at FROM portfolio_order_requests WHERE request_id=?").get(key);
  assert.equal(row.state, "requested");
  assert.equal(row.claimed_at, null, "a peek, replayed or not, never takes a lease");
});

test("an unsigned or tampered peek is refused", async () => {
  const database = freshDatabase();
  const unsigned = await peek({ request: new Request("https://dash.example/x", { method: "POST", body: "{}" }), env: env(database) });
  assert.equal(unsigned.status, 401);
  const request = signed("https://dash.example/x", { account_alias: ACCOUNT });
  const tampered = new Request(request.url, { method: "POST", headers: request.headers, body: JSON.stringify({ account_alias: "U999" }) });
  assert.equal((await peek({ request: tampered, env: env(database) })).status, 401);
});

test("the peek counts exactly what a claim would take", async () => {
  const database = freshDatabase();
  seedRequest(database);                                                   // claimable
  seedRequest(database, { state: "previewed", claimed_at: ago(10), claimed_by: "b" }); // lease live
  seedRequest(database, { state: "approved", claimed_at: ago(120), claimed_by: "b" }); // lease lapsed
  seedRequest(database, { state: "filled" });                              // terminal
  seedRequest(database, { account_alias: "OTHER" });                       // other account
  seedLookup(database);                                                    // claimable
  seedLookup(database, { state: "resolving", claimed_at: ago(5), claimed_by: "b" });   // lease live
  seedLookup(database, { state: "resolved" });                             // done

  const { body } = await call(peek, database);
  assert.deepEqual(body.claimable, { order_requests: 2, contract_lookups: 1 });

  const orders = await call(claimOrders, database);
  const lookups = await call(claimLookups, database);
  assert.equal(orders.body.requests.length, body.claimable.order_requests);
  assert.equal(lookups.body.lookups.length, body.claimable.contract_lookups);

  // And once claimed, the peek goes quiet for the length of the lease.
  const after = await call(peek, database);
  assert.deepEqual(after.body.claimable, { order_requests: 0, contract_lookups: 0 });
});

test("both peek statements seek an index instead of scanning the table", () => {
  const database = freshDatabase();
  const plan = (sql, binds) => database.prepare(`EXPLAIN QUERY PLAN ${sql}`).all(...binds).map((row) => row.detail).join(" | ");
  const orders = plan(PEEK_ORDER_REQUESTS_SQL, ["requested", "drafting", "previewed", "approved", "submitting", ACCOUNT, ago(90)]);
  const lookups = plan(PEEK_CONTRACT_LOOKUPS_SQL, ["requested", "resolving", ACCOUNT, ago(60)]);
  assert.match(orders, /USING (COVERING )?INDEX idx_order_requests_state/, orders);
  assert.match(lookups, /USING (COVERING )?INDEX idx_contract_lookups_state/, lookups);
  assert.doesNotMatch(`${orders} ${lookups}`, /SCAN portfolio_/);
});

test("the peek requires an account and a well-formed body", async () => {
  const database = freshDatabase();
  assert.equal((await call(peek, database, {})).status, 422);
});
