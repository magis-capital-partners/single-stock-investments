// The command-channel peek, against real SQL.
//
// Two properties, and D1 bills for the first while the second is security:
//
//   * An idle bridge tick writes nothing. Before the peek, every 15s tick called
//     both claim routes, and each reserved a nonce row first -- ~34k billed row
//     writes a day, plus ~10k more when retention deleted them.
//   * A peek authenticates as a peek and as nothing else. It reserves no nonce,
//     so a peek that verified on any other route would be a fresh, unused
//     signature there for its whole 300s window. The first version shipped
//     exactly that: a captured peek replayed to a claim route leased the desk's
//     tickets away from the real bridge.

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
import { onRequestPost as publishOrder } from "../functions/api/v2/portfolio/ingest/order-requests/publish.js";
import { onRequestPost as publishLookup } from "../functions/api/v2/portfolio/ingest/contract-lookups/publish.js";
import { onRequestPost as ingest } from "../functions/api/v2/portfolio/ingest.js";

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

/**
 * A signed request exactly as publisher.signed_headers builds it: the body is
 * the canonical JSON (sorted keys, no spaces) and, with a domain, the signed
 * message is "<domain>\n<ts>\n<nonce>\n<body>".
 */
function signed(payload, { domain = null, url = "https://dash.example/x" } = {}) {
  const body = JSON.stringify(Object.fromEntries(Object.entries(payload).sort(([a], [b]) => a.localeCompare(b))));
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID().replace(/-/g, "");
  const signature = createHmac("sha256", TOKEN).update(`${domain ? `${domain}\n` : ""}${timestamp}\n${nonce}\n${body}`).digest("hex");
  return new Request(url, {
    method: "POST", body,
    headers: {
      "content-type": "application/json", "x-portfolio-timestamp": timestamp,
      "x-portfolio-nonce": nonce, "x-portfolio-signature": signature,
    },
  });
}

// What the new bridge sends (command_poller.py): a peek-domain signature over a
// body that names its purpose, and claims that say purpose "claim".
const peekRequest = () => signed({ account_alias: ACCOUNT, purpose: "peek" }, { domain: "peek" });
const env = (database) => ({ DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN, PRIVATE_ARTIFACTS: { put: async () => {} } });

async function send(handler, database, request) {
  const response = await handler({ request, env: env(database) });
  return { status: response.status, body: await response.json() };
}

const totalChanges = (database) => database.prepare("SELECT total_changes() AS n").get().n;
const nonces = (database) => database.prepare("SELECT COUNT(*) AS n FROM portfolio_ingest_nonces").get().n;
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

const leased = (database) => ({
  orders: database.prepare("SELECT COUNT(*) AS n FROM portfolio_order_requests WHERE claimed_at IS NOT NULL").get().n,
  lookups: database.prepare("SELECT COUNT(*) AS n FROM portfolio_contract_lookups WHERE claimed_at IS NOT NULL").get().n,
});

// ------------------------------------------------------------- idle cost

test("an idle peek writes no row at all -- no nonce, no lease", async () => {
  const database = freshDatabase();
  const before = totalChanges(database);
  const { status, body } = await send(peek, database, peekRequest());
  assert.equal(status, 200);
  assert.deepEqual(body.claimable, { order_requests: 0, contract_lookups: 0 });
  assert.equal(totalChanges(database) - before, 0, "the idle peek must not write");
  assert.equal(nonces(database), 0);
});

test("for contrast: the claims it replaces write a nonce row each, idle or not", async () => {
  const database = freshDatabase();
  await send(claimOrders, database, signed({ account_alias: ACCOUNT, purpose: "claim" }));
  await send(claimLookups, database, signed({ account_alias: ACCOUNT, purpose: "claim" }));
  assert.equal(nonces(database), 2);
});

test("a replayed peek is answered as a peek and still changes nothing", async () => {
  const database = freshDatabase();
  const key = seedRequest(database);
  const request = peekRequest();
  const before = totalChanges(database);
  assert.equal((await peek({ request: request.clone(), env: env(database) })).status, 200);
  assert.equal((await peek({ request, env: env(database) })).status, 200, "no nonce: a replay inside the window is answered");
  assert.equal(totalChanges(database) - before, 0);
  const row = database.prepare("SELECT state, claimed_at FROM portfolio_order_requests WHERE request_id=?").get(key);
  assert.equal(row.state, "requested");
  assert.equal(row.claimed_at, null, "a peek, replayed or not, never takes a lease");
});

// --------------------------------------------- a peek is never anything else

test("no request the peek accepts is accepted by any other signed route", async () => {
  // Every shape a bridge has ever sent to the peek route. Whichever of them the
  // peek accepts, replaying that exact request anywhere else must be refused
  // and must lease, move or write nothing. (The first shape is what the first
  // version of the bridge sent; against that edge this test fails.)
  const candidates = {
    "legacy signature, bare account body": () => signed({ account_alias: ACCOUNT }),
    "legacy signature, peek-purpose body": () => signed({ account_alias: ACCOUNT, purpose: "peek" }),
    "peek-domain signature, peek-purpose body": peekRequest,
  };
  const elsewhere = { claimOrders, claimLookups, publishOrder, publishLookup, ingest };
  let accepted = 0;
  for (const [shape, build] of Object.entries(candidates)) {
    const database = freshDatabase();
    const ticket = seedRequest(database);
    seedLookup(database);
    const request = build();
    const answer = await peek({ request: request.clone(), env: env(database) });
    if (answer.status !== 200) continue;
    accepted += 1;
    const before = totalChanges(database);
    for (const [route, handler] of Object.entries(elsewhere)) {
      const replay = await handler({ request: request.clone(), env: env(database) });
      assert.ok(replay.status >= 400 && replay.status < 500, `${shape} replayed to ${route} answered ${replay.status}`);
    }
    assert.deepEqual(leased(database), { orders: 0, lookups: 0 }, `${shape}: a replay leased work away from the bridge`);
    assert.equal(totalChanges(database) - before, 0, `${shape}: a replay wrote to D1`);
    assert.equal(database.prepare("SELECT state FROM portfolio_order_requests WHERE request_id=?").get(ticket).state, "requested");
  }
  assert.ok(accepted >= 1, "the peek must accept the bridge's own peek, or this test proves nothing");
});

test("both claim routes refuse a peek-purpose body even when signed the claim way, before any write", async () => {
  // The second, independent lock: a body that says it is a peek is never a
  // claim, whatever signature it carries.
  const database = freshDatabase();
  seedRequest(database);
  seedLookup(database);
  const before = totalChanges(database);
  for (const handler of [claimOrders, claimLookups]) {
    const { status, body } = await send(handler, database, signed({ account_alias: ACCOUNT, purpose: "peek" }));
    assert.equal(status, 422);
    assert.match(body.error, /not a claim/);
  }
  assert.deepEqual(leased(database), { orders: 0, lookups: 0 });
  assert.equal(totalChanges(database) - before, 0, "refused before the nonce was reserved");
});

test("the deployed bridge's legacy claim body (no purpose) still claims, as does purpose: claim", async () => {
  for (const payload of [{ account_alias: ACCOUNT }, { account_alias: ACCOUNT, purpose: "claim" }]) {
    const database = freshDatabase();
    const ticket = seedRequest(database);
    seedLookup(database);
    const orders = await send(claimOrders, database, signed(payload));
    const lookups = await send(claimLookups, database, signed(payload));
    assert.equal(orders.status, 200);
    assert.equal(orders.body.requests[0].request_id, ticket);
    assert.equal(lookups.status, 200);
    assert.equal(lookups.body.lookups.length, 1);
  }
});

test("the peek refuses a claim-style signature and a body without its purpose", async () => {
  const database = freshDatabase();
  const claimSigned = await send(peek, database, signed({ account_alias: ACCOUNT, purpose: "peek" }));
  assert.equal(claimSigned.status, 401, "a claim or ingest signature is not a peek signature");
  const unlabelled = await send(peek, database, signed({ account_alias: ACCOUNT }, { domain: "peek" }));
  assert.equal(unlabelled.status, 422, "the signed body must say what it is");
});

test("an unsigned or tampered peek is refused", async () => {
  const database = freshDatabase();
  const unsigned = await peek({ request: new Request("https://dash.example/x", { method: "POST", body: "{}" }), env: env(database) });
  assert.equal(unsigned.status, 401);
  const request = peekRequest();
  const tampered = new Request(request.url, { method: "POST", headers: request.headers, body: JSON.stringify({ account_alias: "U999", purpose: "peek" }) });
  assert.equal((await peek({ request: tampered, env: env(database) })).status, 401);
});

// ------------------------------------------------------------- semantics

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

  const { body } = await send(peek, database, peekRequest());
  assert.deepEqual(body.claimable, { order_requests: 2, contract_lookups: 1 });

  const orders = await send(claimOrders, database, signed({ account_alias: ACCOUNT, purpose: "claim" }));
  const lookups = await send(claimLookups, database, signed({ account_alias: ACCOUNT, purpose: "claim" }));
  assert.equal(orders.body.requests.length, body.claimable.order_requests);
  assert.equal(lookups.body.lookups.length, body.claimable.contract_lookups);

  // And once claimed, the peek goes quiet for the length of the lease.
  const after = await send(peek, database, peekRequest());
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

test("the peek requires an account", async () => {
  const database = freshDatabase();
  assert.equal((await send(peek, database, signed({ purpose: "peek" }, { domain: "peek" }))).status, 422);
});
