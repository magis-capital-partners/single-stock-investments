import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { onRequestPost } from "../functions/api/v2/portfolio/ingest.js";
import { onRequestGet } from "../functions/api/v2/portfolio/rs-execution.js";

const key = "paper-test-key".repeat(4);
const id = "a".repeat(32);
const url = "https://ssi.invalid/api/v2/portfolio";
const domain = "rs_execution_paper";
const ref = "RSPAPER|" + "b".repeat(20);

function database(raw) {
  return {prepare(sql) {
    const statement = raw.prepare(sql);
    function query(args) {
      return {
        first: async () => statement.get(...args),
        all: async () => ({results: statement.all(...args)}),
        run: async () => ({meta: statement.run(...args)}),
      };
    }
    return {...query([]), bind: (...args) => query(args)};
  }};
}

function request(body, { signingKey = key, purpose = domain } = {}) {
  const bytes = JSON.stringify(body);
  const ts = String(Math.floor(Date.now() / 1000));
  const nonce = "c".repeat(32);
  return new Request(url + "/ingest", {method: "POST", body: bytes, headers: {
    "x-ssi-ingest-purpose": purpose,
    "x-portfolio-timestamp": ts,
    "x-portfolio-nonce": nonce,
    "x-portfolio-signature": createHmac("sha256", signingKey).update(`${domain}\n${ts}\n${nonce}\n${bytes}`).digest("hex"),
  }});
}

test("paper ingestion is domain-separated, replay-safe, paper-scoped and owner-readable", async () => {
  const raw = new DatabaseSync(":memory:");
  raw.exec(readFileSync(new URL("./migrations/0028_reverse_split_execution.sql", import.meta.url), "utf8"));
  const portfolioKey = "unrelated-portfolio-key".repeat(3);
  const env = {DB: database(raw), PORTFOLIO_INGEST_TOKEN: portfolioKey, RS_EXECUTION_PUBLISH_KEY: key};
  const clock = Date.now();
  const at = n => new Date(clock + n).toISOString();
  const send = req => onRequestPost({env, request: req});
  const body = {
    schema: "rs_execution.v1", mode: "paper", session_id: id, observed_at: at(0), ended: false,
    orders: [{ref}], fills: [], events: [{ref}], positions: [], pnl: {currency: "USD"},
  };
  const probe = await send(request({schema: "rs_execution_probe.v1"}));
  assert.deepEqual(await probe.json(), {available: true});
  assert.equal(raw.prepare("SELECT count(*) AS n FROM rs_execution_paper").get().n, 0);
  assert.equal((await send(request(body, {signingKey: portfolioKey}))).status, 401);
  assert.equal((await send(request(body, {purpose: ""}))).status, 401);
  assert.equal((await send(request({...body, mode: "live"}))).status, 422);
  assert.equal((await send(request({...body, observed_at: at(-31_000)}))).status, 422);
  assert.equal((await send(request({...body, orders: [{ref: ref.replace("PAPER", "LIVE")}]}))).status, 422);
  assert.equal((await (await send(request(body))).json()).stored, true);
  assert.equal((await (await send(request(body))).json()).stored, false);
  assert.equal((await (await send(request({...body, events: [], observed_at: at(1)}))).json()).stored, false);
  const closed = {...body, ended: true, fills: [{ref}], observed_at: at(2)};
  assert.equal((await (await send(request(closed))).json()).stored, true);
  assert.equal((await (await send(request({...closed, ended: false, observed_at: at(3)}))).json()).stored, false);

  const read = new Request(url + "/rs-execution");
  assert.equal((await onRequestGet({request: read, env, data: {}})).status, 401);
  assert.equal((await onRequestGet({request: read, env, data: {humanViewer: {role: "reader"}}})).status, 403);
  const res = await onRequestGet({request: read, env, data: {humanViewer: {role: "owner"}}});
  assert.equal(res.headers.get("cache-control"), "no-store, private");
  const payload = await res.json();
  assert.equal(payload.mode, "paper");
  assert.equal(payload.snapshot.ended, true);
  assert.equal(payload.snapshot.fills.length, 1);
  raw.close();
});
