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
