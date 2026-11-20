import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';

const modulePath = process.env.RS_FRESHNESS_WATCH_MODULE || './reverse-split-live/watch.mjs';
const {watchCollector} = await import(modulePath);

test('operations remain fresh while the collector waits between full checkpoints', async t => {
  const db = new DatabaseSync(':memory:');
  for (const name of readdirSync(new URL('./reverse-split-live/migrations/', import.meta.url)).filter(n => n.endsWith('.sql')).sort()) {
    db.exec(readFileSync(new URL('./reverse-split-live/migrations/' + name, import.meta.url), 'utf8'));
  }
  t.after(() => db.close());
  const env = {DB: localAdapter(db), SHADOW_ENABLED: 'true', pending: [], usage: {rows_read: 0, rows_written: 0}};
  env.controlDB = env.DB;
  env.JOBS = {send: async body => env.pending.push(body)};
  env.ENABLED = 'true';
  env.SEC_USER_AGENT = 'Synthetic offline regression';
  env.market = {health: {status: 'not_configured'}, quote: async () => {throw new Error('No quotes in this offline test');}};
  const objects = new Map(), generated = [], ages = [], stateAges = [];
  let lastGenerated = null, lastState = null;
  env.EVIDENCE = {
    put: async (key, bytes) => {
      const copy = new Uint8Array(bytes);
      objects.set(key, copy);
      if (key === 'collector-dashboard/operations.json') {
        const snapshot = JSON.parse(new TextDecoder().decode(copy));
        lastGenerated = Date.parse(snapshot.generated_at);
        lastState = Date.parse(snapshot.state_at || snapshot.generated_at);
        generated.push(lastGenerated);
      }
    },
    get: async key => objects.has(key) ? {arrayBuffer: async () => objects.get(key).slice().buffer} : null,
  };
  const savedFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('<feed></feed>');
  t.after(() => {globalThis.fetch = savedFetch;});
  let stopped = false;
  await watchCollector(env, {
    maximumMs: 20000,
    operations: {intervalMs: 500, maxStateAgeMs: 2000},
    shouldStop: () => stopped,
    sleep: async () => {
      for (let i = 0; i < 9; i++) {
        await new Promise(resolve => setTimeout(resolve, 400));
        if (lastGenerated !== null) ages.push(Date.now() - lastGenerated);
        if (lastState !== null) stateAges.push(Date.now() - lastState);
      }
      stopped = true;
    },
  });
  assert.ok(ages.length >= 8, 'must observe the actual published object between full saves');
  assert.ok(Math.max(...ages) < 2000,
    `published feed became stale between checkpoints: maximum observed age ${Math.max(...ages)} ms, limit 2000 ms`);
  assert.ok(Math.max(...stateAges) < 2000,
    `underlying saved data became stale: maximum observed age ${Math.max(...stateAges)} ms, limit 2000 ms`);
  assert.ok(new Set(generated).size >= 3, 'must publish genuinely re-evaluated snapshots between full saves');
});
