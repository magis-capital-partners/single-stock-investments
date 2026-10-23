import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { onRequestPost } from '../functions/api/v2/portfolio/order-intents.js';
import { frameworkRequestCore, validateOrderRequest } from '../functions/_lib/order-requests.js';

function database() {
  const db = new DatabaseSync(':memory:');
  for (const filename of readdirSync(new URL('./migrations/', import.meta.url)).filter(f => f.endsWith('.sql')).sort()) {
    const sql = readFileSync(new URL('./migrations/' + filename, import.meta.url), 'utf8').replace(/--[^\n]*/g, '');
    for (const statement of sql.split(';').map(s => s.trim()).filter(Boolean)) {
      try { db.exec(statement); } catch (_) { /* unrelated legacy tables */ }
    }
  }
  db.prepare(`INSERT INTO portfolio_source_runs(source_run_id,schema_version,source,account_alias,as_of,complete,content_sha256,object_key)
    VALUES('test','test','ibkr','TEST_ACCOUNT','2026-10-22T20:00:00Z',1,'test','test')`).run();
  return db;
}
function adapter(db) {
  const make = (sql, binds = []) => ({
    bind: (...values) => make(sql, values),
    first: async () => db.prepare(sql).get(...binds) || null,
    all: async () => ({ results: db.prepare(sql).all(...binds) }),
    run: async () => ({ meta: { changes: Number(db.prepare(sql).run(...binds).changes) } }),
  });
  return { prepare: sql => make(sql) };
}
function request(action = 'SELL') {
  const base = { conid: 123, symbol: 'TEST', sec_type: 'STK', action, quantity: '10', limit_price: '10',
    currency: 'USD', tif: 'DAY', outside_rth: false, mode: 'dry_run', strategy: 'short_framework', framework_decision_id: 'a'.repeat(64) };
  const digest = createHash('sha256').update(JSON.stringify(Object.fromEntries(Object.entries(base).sort(([a], [b]) => a.localeCompare(b))))).digest('hex');
  return { ...base, framework_request_sha256: digest, rationale: 'SF1:' + base.framework_decision_id + ':' + digest };
}
function context(db, body, owner = 'michael') {
  return { request: new Request('http://localhost/api/v2/portfolio/order-intents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    env: { DB: adapter(db), PORTFOLIO_AUTH_MODE: 'development', PORTFOLIO_DEVELOPMENT_OWNER: owner } };
}
test('framework preview request writes once and never transmits', async t => {
  const db = database(); t.after(() => db.close());
  const payload = request(), first = await onRequestPost(context(db, payload)), body = await first.json();
  assert.equal(first.status, 201); assert.equal(body.transmitted, false);
  const second = await onRequestPost(context(db, payload)), duplicate = await second.json();
  assert.equal(second.status, 200); assert.equal(duplicate.idempotent, true);
  assert.equal(body.request_id_created, duplicate.request_id_created);
  assert.equal(db.prepare('SELECT count(*) AS n FROM portfolio_order_requests').get().n, 1);
});
test('changing size without a new private request binding is rejected', async t => {
  const db = database(); t.after(() => db.close());
  const payload = { ...request(), quantity: '11' }, response = await onRequestPost(context(db, payload));
  assert.equal(response.status, 400); assert.match((await response.json()).error, /contents changed/);
  assert.equal(db.prepare('SELECT count(*) AS n FROM portfolio_order_requests').get().n, 0);
});
test('framework binding cannot be reused by another owner', async t => {
  const db = database(); t.after(() => db.close());
  await onRequestPost(context(db, request()));
  const response = await onRequestPost(context(db, request(), 'drew'));
  assert.equal(response.status, 409);
});
test('reduce-only cover request uses the same exact-content binding contract', async t => {
  const db = database(); t.after(() => db.close());
  const payload = request('BUY'), normalized = validateOrderRequest(payload, 'michael');
  assert.equal(frameworkRequestCore(normalized).action, 'BUY');
  const response = await onRequestPost(context(db, payload));
  assert.equal(response.status, 201);
  assert.equal(db.prepare('SELECT action FROM portfolio_order_requests').get().action, 'BUY');
});
