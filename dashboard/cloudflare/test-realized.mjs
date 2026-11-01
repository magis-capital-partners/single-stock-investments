import assert from 'node:assert/strict';
import { createHash, createHmac, webcrypto } from 'node:crypto';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import { addDecimal, canonical, loadRealized, storeRealized, summarize, validDate } from '../functions/_lib/realized.js';
import { onRequestPost } from '../functions/api/v1/sleeves/realized-ingest.js';
import { onRequestGet } from '../functions/api/v1/sleeves/realized.js';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const hash = value => createHash('sha256').update(typeof value === 'string' ? value : canonical(value)).digest('hex');
const migration = ['0024_sleeve_realized.sql', '0025_sleeve_realized_pages.sql']
  .map(name => readFileSync(new URL(`./migrations/${name}`, import.meta.url), 'utf8')).join('\n');
let NativeDatabase;
try { NativeDatabase = (await import('node:sqlite')).DatabaseSync; } catch { /* Python adapter below also exercises real SQLite. */ }

function database() {
  const path = join(mkdtempSync(join(tmpdir(), 'ssi-realized-')), 'db.sqlite');
  const native = NativeDatabase ? new NativeDatabase(path) : null;
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const script = `import json,sqlite3,sys\nx=json.load(sys.stdin)\nc=sqlite3.connect(x['path']);c.row_factory=sqlite3.Row\nwith c:\n if 'schema' in x:c.executescript(x['schema']);print('[]')\n else:\n  out=[]\n  for q in x['queries']:\n   cur=c.execute(q['sql'],q['args']);out.append({'results':[dict(r) for r in cur.fetchall()] if cur.description else [],'meta':{'changes':max(cur.rowcount,0)}})\n  print(json.dumps(out))`;
  function call(queries, schema) {
    if (native) {
      if (schema) { native.exec(schema); return []; }
      native.exec('BEGIN');
      try {
        const results = queries.map(q => {
          const statement = native.prepare(q.sql);
          if (/^\s*(SELECT|PRAGMA|WITH)\b/i.test(q.sql)) return { results: statement.all(...q.args).map(r => ({ ...r })), meta: { changes: 0 } };
          const result = statement.run(...q.args); return { results: [], meta: { changes: Number(result.changes) } };
        });
        native.exec('COMMIT'); return results;
      } catch (error) { native.exec('ROLLBACK'); throw error; }
    }
    const result = spawnSync(python, ['-c', script], { input: JSON.stringify({ path, queries, schema }), encoding: 'utf8' });
    if (result.status) throw new Error(result.stderr); return JSON.parse(result.stdout);
  }
  call([], `${migration}\nCREATE TABLE sleeve_ingest_nonces(nonce TEXT PRIMARY KEY);`);
  return {
    prepare(sql) {
      const statement = args => ({ sql, args, bind(...values) { return statement(values); }, async all() { return call([{ sql, args }])[0]; }, async first() { return call([{ sql, args }])[0].results[0] || null; }, async run() { return call([{ sql, args }])[0]; } });
      return statement([]);
    },
    async batch(statements) { return call(statements); },
    close() { native?.close(); },
  };
}

const row = (id, owner = 'drew', extra = {}) => ({ record_id: id, account: 'TEST', owner, report_id: 'a'.repeat(64), contract_label: 'TEST', trade_date: '2026-10-23', settlement_date: '2026-10-26', settlement_status: 'date_reached', ticker: 'TEST', currency: 'USD', realized_usd: '0.10', realized_native: '0.10', confidence: 'legacy_inferred', quantity: '-1', ...extra });

async function stage(env, rows, suffix = '1', extra = {}) {
  const base = { schema_version: 'sleeve_realized.v1', generation_id: suffix.repeat(64), account: 'TEST' };
  const manifest = { storage: 'packed_v1', through: '2026-10-26', row_count: rows.length, batch_hashes: rows.length ? [hash(rows)] : [], archives: [],
    coverage: { from: '2026-01-01', through: '2026-10-26', gaps: [] }, reconciliation: { status: 'matched' }, ...extra };
  await storeRealized(env, { ...base, kind: 'begin', manifest });
  if (rows.length) await storeRealized(env, { ...base, kind: 'batch', batch_index: 0, records: rows });
  return base;
}

const envFor = db => ({ DB: db, PRIVATE_ARTIFACTS: { objects: new Map(), async put(key, value) { this.objects.set(key, value); } } });
const params = values => new URLSearchParams({ owner: 'drew', ...values });

test('ticker view aggregates every matching lot, pins pagination, and keeps LS review rows out of Michael', async () => {
  const db = database(), env = envFor(db);
  const base = await stage(env, [
    row('first', 'michael', { ticker: 'ASST', realized_usd: '0.1', trade_date: '2026-10-22' }),
    row('second', 'michael', { ticker: 'ASST', realized_usd: '0.2' }),
    row('option', 'michael', { ticker: 'ASST', contract_label: 'ASST option', realized_usd: '-0.01' }),
    row('other', 'michael', { ticker: 'OTHER', realized_usd: '9' }),
    row('ls-review', 'unallocated', { ticker: 'NBIZ', strategy: 'ownership_review' }),
  ]);
  await storeRealized(env, { ...base, kind: 'complete' });
  const first = await loadRealized(db, params({ owner: 'michael', view: 'tickers', limit: '1' }));
  assert.equal(first.view, 'tickers');
  assert.equal(first.group_count, 2);
  assert.equal(first.groups.length, 1);
  assert.equal(first.groups[0].ticker, 'ASST');
  assert.equal(first.groups[0].summary.realized_usd, '0.29');
  assert.equal(first.groups[0].summary.count, 3);
  assert.equal(first.groups[0].from, '2026-10-22');
  assert.equal(first.groups[0].through, '2026-10-23');
  assert.equal(first.summary.realized_usd, '9.29');
  assert.equal(first.records.length, 0);
  const next = await loadRealized(db, params({ owner: 'michael', view: 'tickers', limit: '1', cursor: first.next_cursor, generation: first.generation_id }));
  assert.equal(next.groups[0].ticker, 'OTHER');
  assert.equal(next.next_cursor, null);
  const lots = await loadRealized(db, params({ owner: 'michael', ticker: 'ASST', generation: first.generation_id }));
  assert.equal(lots.records.length, 3);
  assert.equal(lots.summary.realized_usd, first.groups[0].summary.realized_usd);
  await assert.rejects(loadRealized(db, params({ owner: 'michael', cursor: first.next_cursor })), /Cursor/);
  assert.equal((await loadRealized(db, params({ owner: 'michael', ticker: 'NBIZ' }))).records.length, 0);
  db.close();
});

test('realized view has a latest-data refresh and ticker rows expand into separately fetched lots', () => {
  const window = {};
  runInNewContext(readFileSync(new URL('../sleeve-realized-viz.js', import.meta.url), 'utf8'), { window, Intl, Number, String, Map });
  assert.match(window.SleeveRealized.shell(), /data-realized-refresh/);
  const html = window.SleeveRealized.renderResults({ view: 'tickers', groups: [{ ticker: 'SAME', summary: summarize([row('a'), row('b')]), from: '2026-10-23', through: '2026-10-23' }],
    summary: summarize([row('a'), row('b')]), records: [], coverage: {}, through: '2026-10-26' });
  assert.equal((html.match(/data-realized-ticker=/g) || []).length, 1);
  assert.match(html, /2 lots/);
  assert.match(html, /0\.20/);
});

test('a ticker click replaces an obsolete NBIZ result and loads every individual lot in the new generation', async () => {
  const fields = new Map(['period', 'from', 'to', 'basis', 'settlement', 'ticker'].map(k => [k, { value: '', addEventListener() {} }]));
  const element = () => ({ innerHTML: '', textContent: '', hidden: true, dataset: {}, handlers: {},
    addEventListener(name, fn) { this.handlers[name] = fn; }, setAttribute(name, value) { this[name] = value; } });
  const form = { elements: { namedItem: key => fields.get(key) }, addEventListener() {} };
  const results = element(), refresh = element(), more = element(), status = element(), through = element();
  const rows = new Map(), buttons = new Map();
  const root = { dataset: {}, isConnected: true, querySelector(selector) {
    if (selector === '[data-realized-form]') return form;
    if (selector === '[data-realized-results]') return results;
    if (selector === '[data-realized-status]') return status;
    if (selector === '[data-realized-through]') return through;
    if (selector === '[data-realized-refresh]') return refresh;
    if (selector === '[data-realized-more]') return more;
    if (selector === '[data-realized-export]') return element();
    const match = selector.match(/^\[data-realized-(lots|ticker)="([^"]*)"\]$/);
    if (match) {
      const map = match[1] === 'lots' ? rows : buttons;
      if (!map.has(match[2])) {
        const el = element(), content = element(); el.querySelector = () => content;
        el.dataset.realizedTicker = match[2]; el.dataset.realizedLotsMore = match[2]; map.set(match[2], el);
      }
      return map.get(match[2]);
    }
    return null;
  } };
  const calls = [], oldGeneration = 'a'.repeat(64), newGeneration = 'b'.repeat(64);
  const three = [row('one', 'michael', { ticker: 'SAME' }), row('two', 'michael', { ticker: 'SAME' }), row('three', 'michael', { ticker: 'SAME' })];
  let groupedCalls = 0, delayNextGroup = false, releaseGroup;
  const common = { status: 'available', owner: 'michael', through: '2026-10-26', from: '2026-01-01', to: '2026-10-26',
    basis: 'trade_date', settlement: 'all', ticker: '', coverage: {}, records: [], next_cursor: null, is_current: true };
  const fetch = async url => {
    const query = new URL(url, 'https://example.com').searchParams; calls.push(Object.fromEntries(query));
    let body;
    if (query.get('view') === 'tickers') {
      const old = groupedCalls++ === 0 || delayNextGroup, ticker = old ? 'NBIZ' : 'SAME';
      body = { ...common, view: 'tickers', generation_id: old ? oldGeneration : newGeneration, group_count: 1,
        groups: [{ ticker, from: '2026-10-23', through: '2026-10-23', summary: summarize(three) }], summary: summarize(three) };
    } else if (query.get('ticker') === 'NBIZ') {
      body = { ...common, is_current: false, generation_id: oldGeneration, current_generation_id: newGeneration, records: [], summary: summarize([]) };
    } else {
      const next = query.has('cursor');
      body = { ...common, ticker: 'SAME', view: 'lots', generation_id: newGeneration,
        records: next ? three.slice(2) : three.slice(0, 2), summary: summarize(three), next_cursor: next ? null : 'page-two' };
    }
    const response = { ok: true, json: async () => body };
    if (query.get('view') === 'tickers' && delayNextGroup) {
      delayNextGroup = false;
      return new Promise(resolve => { releaseGroup = () => resolve(response); });
    }
    return response;
  };
  const window = {};
  runInNewContext(readFileSync(new URL('../sleeve-realized-viz.js', import.meta.url), 'utf8'), { window, fetch, URLSearchParams, AbortController, Intl, Number, String, Map });
  await window.SleeveRealized.attach({ querySelector: () => root }, 'michael');
  assert.match(results.innerHTML, /NBIZ/);
  const click = async (selector, key) => {
    const target = selector === 'ticker' ? root.querySelector(`[data-realized-ticker="${key}"]`) : { dataset: { realizedLotsMore: key } };
    results.handlers.click({ target: { closest: s => s === `[data-realized-${selector === 'ticker' ? 'ticker' : 'lots-more'}]` ? target : null } });
    await new Promise(resolve => setImmediate(resolve));
  };
  await click('ticker', 'NBIZ');
  assert.doesNotMatch(results.innerHTML, /NBIZ/);
  assert.match(results.innerHTML, /SAME/);
  await click('ticker', 'SAME');
  const content = root.querySelector('[data-realized-lots="SAME"]').querySelector();
  assert.match(content.innerHTML, /2 of 3 shown/);
  const detail = calls.at(-1);
  assert.equal(detail.generation, newGeneration); assert.equal(detail.ticker, 'SAME'); assert.equal(detail.owner, 'michael');
  assert.equal(detail.from, '2026-01-01'); assert.equal(detail.to, '2026-10-26');
  assert.equal(detail.cursor, undefined);
  await click('more', 'SAME');
  assert.match(content.innerHTML, /3 of 3 shown/);
  assert.equal(calls.at(-1).cursor, 'page-two');
  const beforeCollapse = calls.length;
  await click('ticker', 'SAME'); await click('ticker', 'SAME');
  assert.equal(calls.length, beforeCollapse, 'reopening uses the loaded lots');
  refresh.handlers.click(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.at(-1).view, 'tickers');
  assert.equal(calls.at(-1).generation, undefined); assert.equal(calls.at(-1).cursor, undefined);
  delayNextGroup = true; refresh.handlers.click();
  refresh.handlers.click(); await new Promise(resolve => setImmediate(resolve));
  assert.match(results.innerHTML, /SAME/);
  releaseGroup(); await new Promise(resolve => setImmediate(resolve));
  assert.doesNotMatch(results.innerHTML, /NBIZ/, 'a slower obsolete response cannot replace freshly loaded results');
});

test('ticker grouping preserves date and settlement filters across batches and Unicode pagination', async () => {
  const db = database(), env = envFor(db);
  const a = [row('a', 'drew', { ticker: 'ÅBC' }), row('p', 'drew', { ticker: 'ÅBC', settlement_status: 'pending', settlement_date: '2026-10-28' })];
  const b = [row('b', 'drew', { ticker: 'ÅBC', realized_usd: '0.20' }), row('c', 'drew', { ticker: '東京' })];
  const base = { schema_version: 'sleeve_realized.v1', generation_id: '9'.repeat(64), account: 'TEST' };
  await storeRealized(env, { ...base, kind: 'begin', manifest: { storage: 'packed_v1', through: '2026-10-26',
    row_count: 4, batch_hashes: [hash(a), hash(b)], archives: [], coverage: {}, reconciliation: {} } });
  await storeRealized(env, { ...base, kind: 'batch', batch_index: 0, records: a });
  await storeRealized(env, { ...base, kind: 'batch', batch_index: 1, records: b });
  await storeRealized(env, { ...base, kind: 'complete' });
  const selected = { view: 'tickers', basis: 'settlement_date', settlement: 'date_reached', limit: '1' };
  const first = await loadRealized(db, params(selected));
  assert.equal(first.groups[0].summary.realized_usd, '0.3');
  assert.equal(first.groups[0].summary.count, 2);
  assert.equal(first.summary.count, 3);
  const second = await loadRealized(db, params({ ...selected, cursor: first.next_cursor, generation: first.generation_id }));
  assert.equal(second.groups[0].ticker, '東京');
  assert.equal(second.next_cursor, null);
  await assert.rejects(loadRealized(db, params({ view: 'invalid' })), /view/);
  db.close();
});

test('pinned ticker pages identify newer history and empty selections remain empty', async () => {
  const db = database(), env = envFor(db);
  const old = await stage(env, [row('old', 'michael', { ticker: 'NBIZ' })], 'a');
  await storeRealized(env, { ...old, kind: 'complete' });
  const latest = await stage(env, [row('current', 'michael', { ticker: 'ASST' })], 'b');
  await storeRealized(env, { ...latest, kind: 'complete' });
  const pinned = await loadRealized(db, params({ owner: 'michael', view: 'tickers', generation: old.generation_id }));
  assert.equal(pinned.is_current, false);
  assert.equal(pinned.current_generation_id, latest.generation_id);
  const refreshed = await loadRealized(db, params({ owner: 'michael', view: 'tickers' }));
  assert.equal(refreshed.is_current, true);
  assert.deepEqual(refreshed.groups.map(g => g.ticker), ['ASST']);
  const none = await loadRealized(db, params({ owner: 'michael', view: 'tickers', ticker: 'NBIZ' }));
  assert.deepEqual(none.groups, []); assert.equal(none.group_count, 0); assert.equal(none.summary.count, 0);
  assert.equal(none.next_cursor, null);
  const legacy = await loadRealized(db, params({ owner: 'michael', limit: '1' }));
  assert.equal(legacy.view, 'lots'); assert.equal(legacy.records[0].ticker, 'ASST');
  db.close();
});

test('financial totals preserve decimal cents and missing amounts', () => {
  assert.equal(addDecimal('0.1', '0.2'), '0.3');
  assert.equal(addDecimal('-0.01', '0.001'), '-0.009');
  assert.equal(addDecimal('100.00', '0'), '100');
  assert.equal(addDecimal('12345678901234567890.01', '0.02'), '12345678901234567890.03');
  const sum = summarize([row('a'), row('b'), row('c', 'drew', { realized_usd: null })]);
  assert.equal(sum.realized_usd, '0.2'); assert.equal(sum.missing_usd, 1);
  assert.equal(validDate('2026-02-30'), false);
});

test('only completed generations are visible; failed replacement leaves previous view', async () => {
  const db = database(), env = envFor(db);
  const first = await stage(env, [row('a')]);
  assert.equal((await loadRealized(db, params())).status, 'not_ingested');
  await storeRealized(env, { ...first, kind: 'complete' });
  const second = await stage(env, [row('b', 'drew', { realized_usd: '999' })], '2');
  assert.equal((await loadRealized(db, params())).summary.realized_usd, '0.1');
  await storeRealized(env, { ...second, kind: 'complete' });
  assert.equal((await loadRealized(db, params())).summary.realized_usd, '999');
  db.close();
});

test('idempotent batches, generation integrity and original-archive completeness', async () => {
  const db = database(), env = envFor(db), rows = [row('a')];
  const base = await stage(env, rows);
  assert.equal((await storeRealized(env, { ...base, kind: 'batch', batch_index: 0, records: rows })).duplicate, true);
  await assert.rejects(storeRealized(env, { ...base, kind: 'batch', batch_index: 0, records: [row('wrong')] }), /checksum/);
  await storeRealized(env, { ...base, kind: 'complete' });
  assert.equal((await storeRealized(env, { ...base, kind: 'complete' })).duplicate, true);
  const incomplete = await stage(env, [], '3', { archives: [{ report_id: 'a'.repeat(64), part_shas: ['b'.repeat(64)] }] });
  await assert.rejects(storeRealized(env, { ...incomplete, kind: 'complete' }), /archive is incomplete/);
  db.close();
});

test('pagination is pinned to dataset and filter and summaries include all rows', async () => {
  const db = database(), env = envFor(db);
  const base = await stage(env, [row('a'), row('b'), row('c'), row('foreign', 'michael')]);
  await storeRealized(env, { ...base, kind: 'complete' });
  const first = await loadRealized(db, params({ limit: '1' }));
  assert.equal(first.summary.realized_usd, '0.3'); assert.equal(first.records.length, 1);
  const second = await loadRealized(db, params({ limit: '1', cursor: first.next_cursor, generation: first.generation_id }));
  assert.notEqual(first.records[0].record_id, second.records[0].record_id);
  await assert.rejects(loadRealized(db, params({ from: '2026-10-01', cursor: first.next_cursor })), /Cursor/);
  assert.equal((await loadRealized(db, params({ owner: 'michael' }))).summary.count, 1);
  db.close();
});

test('packed pages preserve exact totals and pagination across batches with bounded database writes', async () => {
  const db = database(), env = envFor(db), base = { schema_version: 'sleeve_realized.v1', generation_id: 'd'.repeat(64), account: 'TEST' };
  const batches = [0, 1].map(batch => Array.from({ length: 80 }, (_, index) => row(`${batch}-${String(index).padStart(3, '0')}`)));
  const manifest = { storage: 'packed_v1', through: '2026-10-26', row_count: 160, batch_hashes: batches.map(hash), archives: [] };
  await storeRealized(env, { ...base, kind: 'begin', manifest });
  for (const [batch_index, records] of batches.entries()) await storeRealized(env, { ...base, kind: 'batch', batch_index, records });
  await storeRealized(env, { ...base, kind: 'complete' });
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM sleeve_realized_pages').first()).n, 2);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM sleeve_realized_records').first()).n, 0);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM sleeve_realized_daily').first()).n, 0);
  const first = await loadRealized(db, params({ limit: '100' }));
  assert.equal(first.summary.realized_usd, '16'); assert.equal(first.summary.count, 160);
  const second = await loadRealized(db, params({ limit: '100', cursor: first.next_cursor, generation: first.generation_id }));
  assert.equal(second.records.length, 60);
  assert.equal(new Set([...first.records, ...second.records].map(r => r.record_id)).size, 160);
  db.close();
});

test('duplicate record IDs across packed batches cannot become visible', async () => {
  const db = database(), env = envFor(db), records = [row('duplicate')];
  const base = { schema_version: 'sleeve_realized.v1', generation_id: 'e'.repeat(64), account: 'TEST' };
  await storeRealized(env, { ...base, kind: 'begin', manifest: { storage: 'packed_v1', through: '2026-10-26', row_count: 2, batch_hashes: [hash(records), hash(records)], archives: [] } });
  for (const batch_index of [0, 1]) await storeRealized(env, { ...base, kind: 'batch', batch_index, records });
  await assert.rejects(storeRealized(env, { ...base, kind: 'complete' }), /unique record count/);
  assert.equal((await loadRealized(db, params())).status, 'not_ingested');
  db.close();
});

test('unchanged pages are reused across generations without changing pinned views', async () => {
  const db = database(), env = envFor(db), rows = [row('unchanged')];
  const first = await stage(env, rows, 'a');
  await storeRealized(env, { ...first, kind: 'complete' });
  const second = await stage(env, rows, 'b');
  await storeRealized(env, { ...second, kind: 'complete' });
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM sleeve_realized_pages').first()).n, 1);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM sleeve_realized_batches').first()).n, 2);
  assert.equal((await loadRealized(db, params({ generation: first.generation_id }))).summary.realized_usd, '0.1');
  assert.equal((await loadRealized(db, params())).records[0].record_id, 'unchanged');
  db.close();
});

test('existing row-based generations remain readable during a storage upgrade', async () => {
  const db = database(), env = envFor(db);
  const base = await stage(env, [row('legacy')], 'f', { storage: 'row_v1' });
  await storeRealized(env, { ...base, kind: 'complete' });
  const result = await loadRealized(db, params());
  assert.equal(result.summary.realized_usd, '0.1');
  assert.equal(result.records[0].record_id, 'legacy');
  db.close();
});

test('settlement and ticker filtering produce matching rows and totals', async () => {
  const db = database(), env = envFor(db);
  const base = await stage(env, [row('a'), row('b', 'drew', { ticker: 'OTHER', settlement_status: 'pending', settlement_date: '2026-10-28' }),
    row('c', 'drew', { settlement_status: 'unknown', settlement_date: null }), row('u', 'unallocated')]);
  await storeRealized(env, { ...base, kind: 'complete' });
  assert.equal((await loadRealized(db, params({ ticker: 'OTHER' }))).summary.count, 1);
  assert.equal((await loadRealized(db, params({ settlement: 'unknown' }))).summary.count, 1);
  assert.equal((await loadRealized(db, params({ basis: 'settlement_date', to: '2026-10-26' }))).summary.count, 1);
  assert.equal((await loadRealized(db, params())).unresolved.count, 1);
  await assert.rejects(loadRealized(db, params({ owner: 'excluded' })), /owner/);
  await assert.rejects(loadRealized(db, params({ from: '2026-02-30' })), /date/);
  db.close();
});

test('history generation row-count mismatch never advances current pointer', async () => {
  const db = database(), env = envFor(db);
  const base = await stage(env, [row('a')], '4', { row_count: 2 });
  await assert.rejects(storeRealized(env, { ...base, kind: 'complete' }), /count/);
  assert.equal((await loadRealized(db, params())).status, 'not_ingested');
  db.close();
});

test('a late completion from an older broker source cannot rewind the active history', async () => {
  const db = database(), env = envFor(db);
  const old = await stage(env, [row('old')], '6', { source_generated: '2026-10-27T05:00:00' });
  const latest = await stage(env, [row('latest', 'drew', { realized_usd: '123' })], '7', { source_generated: '2026-10-27T06:00:00' });
  await storeRealized(env, { ...latest, kind: 'complete' });
  await storeRealized(env, { ...old, kind: 'complete' });
  assert.equal((await loadRealized(db, params())).summary.realized_usd, '123');
  db.close();
});

test('read route requires the existing verified owner identity', async () => {
  const response = await onRequestGet({ request: new Request('https://example.com/api/v1/sleeves/realized'), env: {}, data: {} });
  assert.equal(response.status, 401);
  assert.match(response.headers.get('cache-control'), /private/);
});

test('machine ingest verifies HMAC and rejects nonce replay before mutation', async () => {
  const db = database(), env = { ...envFor(db), SLEEVE_INGEST_TOKEN: 'test-secret-'.repeat(5) };
  const body = JSON.stringify({ schema_version: 'sleeve_realized.v1', account: 'TEST', generation_id: '5'.repeat(64), kind: 'begin',
    manifest: { through: '2026-10-26', row_count: 0, batch_hashes: [], archives: [] } });
  const timestamp = String(Math.floor(Date.now() / 1000)), nonce = 'c'.repeat(32);
  const signature = createHmac('sha256', env.SLEEVE_INGEST_TOKEN).update(`${timestamp}\n${nonce}\n${body}`).digest('hex');
  const make = sign => ({ request: new Request('https://example.com/api/v1/sleeves/realized-ingest', { method: 'POST', body,
    headers: { 'x-sleeve-timestamp': timestamp, 'x-sleeve-nonce': nonce, 'x-sleeve-signature': sign } }), env });
  assert.equal((await onRequestPost(make('0'.repeat(64)))).status, 401);
  assert.equal((await onRequestPost(make(signature))).status, 200);
  assert.equal((await onRequestPost(make(signature))).status, 409);
  db.close();
});

test('realized UI renders closed-only history, escapes descriptions, and exports safe CSV', () => {
  const window = {};
  runInNewContext(readFileSync(new URL('../sleeve-realized-viz.js', import.meta.url), 'utf8'), { window, Intl, Number, String, Map });
  const record = { ...row('a'), contract_label: '<script>bad</script>', description: '<img>', report_id: 'a'.repeat(64), record_kind: 'closure' };
  const html = window.SleeveRealized.renderResults({ summary: summarize([record]), records: [record], coverage: {}, through: '2026-10-26' });
  assert.ok(html.includes('&lt;script&gt;')); assert.ok(!html.includes('<script>bad'));
  assert.ok(html.includes('0.10')); assert.ok(html.includes('Date reached'));
  assert.ok(window.SleeveRealized.csv([{ ...record, ticker: '=bad()' }]).includes("'=bad()"));
});
