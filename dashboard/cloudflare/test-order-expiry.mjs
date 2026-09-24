// Stale `previewed` tickets expire server-side.
//
// Nothing advances a `previewed` ticket except a human approval inside its
// window, so one nobody approved stayed open forever: the bridge re-leased it
// every 90s (a nonce row and a lease write each time) and the browser's ticket
// poll kept running at 1 Hz for as long as the Orders view was open. These tests
// pin that such a ticket is marked `expired` once it is well past its window,
// that a ticket still inside (or just past) its window is left alone, and that
// no approval or transmit guard moved.

import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { createHmac, randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { onRequestPost as claimOrders } from "../functions/api/v2/portfolio/ingest/order-requests/claim.js";
import { onRequestGet as listIntents } from "../functions/api/v2/portfolio/order-intents.js";
import { onRequestPost as approve } from "../functions/api/v2/portfolio/order-intents/[request]/approve.js";
import { PREVIEW_EXPIRY_GRACE_SECONDS, expireStalePreviewsStatement } from "../functions/_lib/command-channel.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKEN = "x".repeat(48);
const ACCOUNT = "U805366";

function d1(database) {
  const make = (sql, binds = []) => {
    const values = () => binds.map((value) => (value === undefined ? null : typeof value === "boolean" ? Number(value) : value));
    const run = async () => ({ meta: { changes: Number(database.prepare(sql).run(...values()).changes || 0) } });
    return {
      sql, bind: (...next) => make(sql, next), run,
      all: async () => ({ results: database.prepare(sql).all(...values()) }),
      first: async () => database.prepare(sql).get(...values()) ?? null,
    };
  };
  return { prepare: (sql) => make(sql), batch: async (statements) => Promise.all(statements.map((statement) => statement.run())) };
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

const ago = (seconds) => new Date(Date.now() - seconds * 1000).toISOString();
// The hub writes approval_expires_at with Python's isoformat(): "+00:00", not "Z".
const pythonIso = (seconds) => ago(seconds).replace("Z", "+00:00");

function seedRequest(database, overrides = {}) {
  const row = {
    request_id: randomUUID(), account_alias: ACCOUNT, owner: "drew", strategy: "single_stock",
    conid: 272093, symbol: "MSFT", sec_type: "STK", action: "BUY", quantity_decimal: "1",
    limit_price_decimal: "400", tif: "DAY", outside_rth: 0, mode: "paper", state: "previewed",
    contract_fingerprint: "MSFT | STK | SMART/USD | conId 272093",
    created_at: ago(3 * 3600), updated_at: ago(3 * 3600), ...overrides,
  };
  database.prepare(`INSERT INTO portfolio_order_requests (${Object.keys(row).join(",")})
    VALUES (${Object.keys(row).map(() => "?").join(",")})`).run(...Object.values(row));
  return row.request_id;
}

function signedClaim() {
  const body = JSON.stringify({ account_alias: ACCOUNT });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID().replace(/-/g, "");
  const signature = createHmac("sha256", TOKEN).update(`${timestamp}\n${nonce}\n${body}`).digest("hex");
  return new Request("https://dash.example/c", {
    method: "POST", body,
    headers: { "x-portfolio-timestamp": timestamp, "x-portfolio-nonce": nonce, "x-portfolio-signature": signature },
  });
}

const stateOf = (database, key) => database.prepare("SELECT state FROM portfolio_order_requests WHERE request_id=?").get(key).state;
const localEnv = (database) => ({ DB: d1(database), PORTFOLIO_AUTH_MODE: "development", PORTFOLIO_DEVELOPMENT_OWNER: "drew" });

test("a preview long past its approval window expires when the bridge next claims", async () => {
  const database = freshDatabase();
  const stale = seedRequest(database, { approval_expires_at: pythonIso(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  const response = await claimOrders({ request: signedClaim(), env: { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN } });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(stateOf(database, stale), "expired");
  assert.equal(body.requests.length, 0, "an expired ticket is no longer leased to the bridge");
  const row = database.prepare("SELECT reject_reason, claimed_at FROM portfolio_order_requests WHERE request_id=?").get(stale);
  assert.equal(row.reject_reason, "approval_expired");
  assert.equal(row.claimed_at, null);
});

test("a preview inside or just past its window is left for the human", async () => {
  const database = freshDatabase();
  const live = seedRequest(database, { approval_expires_at: pythonIso(-90), created_at: ago(30), updated_at: ago(30) });
  const lapsed = seedRequest(database, { approval_expires_at: pythonIso(60), created_at: ago(200), updated_at: ago(200) });
  await claimOrders({ request: signedClaim(), env: { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN } });
  assert.equal(stateOf(database, live), "previewed");
  assert.equal(stateOf(database, lapsed), "previewed", "the grace keeps a just-lapsed ticket readable");
});

test("tickets the hub owns are never expired, however old", async () => {
  const database = freshDatabase();
  const approved = seedRequest(database, { state: "approved", approval_expires_at: pythonIso(86_400) });
  const submitting = seedRequest(database, { state: "submitting", approval_expires_at: pythonIso(86_400) });
  const requested = seedRequest(database, { state: "requested" });
  await claimOrders({ request: signedClaim(), env: { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN } });
  assert.equal(stateOf(database, approved), "approved");
  assert.equal(stateOf(database, submitting), "submitting", "a submitting ticket may already be at the broker");
  assert.equal(stateOf(database, requested), "requested");
});

test("a preview without a recorded window expires on its last update instead", async () => {
  const database = freshDatabase();
  const key = seedRequest(database, { approval_expires_at: null, updated_at: ago(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  await claimOrders({ request: signedClaim(), env: { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN } });
  assert.equal(stateOf(database, key), "expired");
});

test("the desk's own read expires a stale preview even when no bridge is running", async () => {
  const database = freshDatabase();
  const stale = seedRequest(database, { approval_expires_at: pythonIso(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  const theirs = seedRequest(database, { owner: "michael", approval_expires_at: pythonIso(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  const response = await listIntents({ request: new Request("http://localhost/api/v2/portfolio/order-intents"), env: localEnv(database) });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.requests.find((row) => row.request_id === stale).state, "expired",
    "the poll sees a terminal state and stops");
  assert.equal(stateOf(database, theirs), "previewed", "a viewer only ever expires their own tickets");
});

test("an expired ticket cannot be approved -- the guard is unchanged", async () => {
  const database = freshDatabase();
  const key = seedRequest(database, { approval_expires_at: pythonIso(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  await listIntents({ request: new Request("http://localhost/api/v2/portfolio/order-intents"), env: localEnv(database) });
  const response = await approve({
    request: new Request(`http://localhost/api/v2/portfolio/order-intents/${key}/approve`, {
      method: "POST", body: JSON.stringify({ contract_fingerprint: "MSFT | STK | SMART/USD | conId 272093" }),
    }),
    env: localEnv(database), params: { request: key },
  });
  assert.equal(response.status, 409);
  assert.equal(stateOf(database, key), "expired");
});

// ------------------------------------------------ cost and failure isolation


// The SQL and binds a statement builder produces, without running it.
function captured(build) {
  const db = { prepare: (sql) => ({ sql, bind: (...binds) => ({ sql, binds }) }) };
  return build(db);
}

function seedHistory(database, count) {
  // A long-lived owner: thousands of finished tickets and a handful still
  // previewed -- the shape the table grows into, since nothing prunes it.
  const insert = database.prepare(`INSERT INTO portfolio_order_requests
    (request_id, account_alias, owner, strategy, conid, symbol, sec_type, action, quantity_decimal,
     limit_price_decimal, tif, outside_rth, mode, state, created_at, updated_at)
    VALUES (?, ?, 'drew', 'single_stock', 272093, 'MSFT', 'STK', 'BUY', '1', '400', 'DAY', 0, 'paper', ?, ?, ?)`);
  const terminal = ["filled", "expired", "rejected", "cancelled"];
  for (let index = 0; index < count; index += 1) {
    const state = index % 500 === 0 ? "previewed" : terminal[index % terminal.length];
    const stamp = new Date(Date.parse("2026-01-01T00:00:00Z") + index * 60_000).toISOString();
    insert.run(randomUUID(), ACCOUNT, state, stamp, stamp);
  }
}

test("the expiry reads previews through the state index, with or without ANALYZE", () => {
  const database = freshDatabase();
  const planOf = (scope) => {
    const { sql, binds } = captured((db) => expireStalePreviewsStatement(db, { ...scope, now: new Date() }));
    return database.prepare(`EXPLAIN QUERY PLAN ${sql}`).all(...binds).map((row) => row.detail).join(" | ");
  };
  const check = (label) => {
    for (const scope of [{ owner: "drew" }, { accountAlias: ACCOUNT }]) {
      const plan = planOf(scope);
      assert.match(plan, /SEARCH portfolio_order_requests USING INDEX idx_order_requests_state \(state=\?\)/, `${label}: ${plan}`);
      assert.doesNotMatch(plan, /idx_order_requests_owner|SCAN portfolio_order_requests/, `${label}: ${plan}`);
    }
  };
  check("no statistics");
  seedHistory(database, 5_000);
  database.exec("ANALYZE");
  check("after ANALYZE over a 5,000-ticket history");
});

// A D1 double that records every statement run and can refuse the expiry.
function spyDb(database, { refuseExpiry = false } = {}) {
  const base = d1(database);
  const ran = [];
  const wrap = (statement) => ({
    ...statement,
    bind: (...args) => wrap(statement.bind(...args)),
    run: async () => {
      ran.push(statement.sql);
      if (refuseExpiry && /SET state='expired'/.test(statement.sql)) {
        throw new Error("D1_ERROR: Exceeded D1's free tier daily row write limit");
      }
      return statement.run();
    },
  });
  return { db: { prepare: (sql) => wrap(base.prepare(sql)), batch: base.batch }, ran };
}

const isExpiry = (sql) => /SET state='expired'/.test(sql);

test("the desk's read issues no expiry UPDATE unless a listed ticket is a stale preview", async () => {
  const database = freshDatabase();
  seedRequest(database, { state: "requested", created_at: ago(30), updated_at: ago(30) });
  seedRequest(database, { approval_expires_at: pythonIso(-60), created_at: ago(20), updated_at: ago(20) });
  const { db, ran } = spyDb(database);
  const response = await listIntents({ request: new Request("http://localhost/api/v2/portfolio/order-intents"), env: { ...localEnv(database), DB: db } });
  assert.equal(response.status, 200);
  assert.equal(ran.filter(isExpiry).length, 0, "a poll over live tickets writes nothing and reads no extra rows");
});

test("a refused expiry never fails the desk's read or stops its poll", async () => {
  const database = freshDatabase();
  const stale = seedRequest(database, { approval_expires_at: pythonIso(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  const { db, ran } = spyDb(database, { refuseExpiry: true });
  const response = await listIntents({ request: new Request("http://localhost/api/v2/portfolio/order-intents"), env: { ...localEnv(database), DB: db } });
  const body = await response.json();
  assert.equal(response.status, 200, "the list is still served");
  assert.equal(ran.filter(isExpiry).length, 1, "the expiry was attempted");
  assert.equal(body.requests.find((row) => row.request_id === stale).state, "previewed", "served as it stands");
});

test("a refused expiry never costs the bridge its claim", async () => {
  const database = freshDatabase();
  seedRequest(database, { approval_expires_at: pythonIso(PREVIEW_EXPIRY_GRACE_SECONDS + 60) });
  const live = seedRequest(database, { state: "requested", created_at: ago(10), updated_at: ago(10) });
  const { db } = spyDb(database, { refuseExpiry: true });
  const response = await claimOrders({ request: signedClaim(), env: { DB: db, PORTFOLIO_INGEST_TOKEN: TOKEN } });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.ok(body.requests.some((row) => row.request_id === live), "the live ticket was still leased");
});
