import assert from 'node:assert/strict';
import test from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import * as health from './reverse-split-live/session-health.mjs';

test('local quote coverage advances independently of the last remote heartbeat',async t=>{
  const db=new DatabaseSync(':memory:');
  t.after(()=>db.close());
  db.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT); CREATE TABLE rs_sources(id,last_success,status,coverage_gap)');
  const env={DB:localAdapter(db)};
  let market={dataset:'EQUS.MINI',quote_access:'awaiting_live_quote'};
  const sampler=health.createSessionHealthSampler(env,()=>({
    status:'running',heartbeat_at:'2026-11-27T14:29:00.000Z',market_data:market,
  }),error=>assert.fail(error));
  const tick=(time,quote=false)=>sampler.sample(Date.parse(time),quote);
  tick('2026-11-27T14:29:59.000Z');
  tick('2026-11-27T14:30:01.000Z');
  market={dataset:'EQUS.MINI',quote_access:'received',last_success:'2026-11-27T14:30:59.100Z'};
  tick('2026-11-27T14:30:59.100Z',true);
  tick('2026-11-27T14:30:59.500Z',true);
  tick('2026-11-27T14:31:01.000Z');
  market={dataset:'EQUS.MINI',quote_access:'received',last_success:'2026-11-27T14:32:10.000Z'};
  tick('2026-11-27T14:32:10.000Z',true);
  tick('2026-11-27T18:00:00.000Z',true);
  await sampler.flush();
  const rows=db.prepare('SELECT value FROM rs_state ORDER BY key').all().map(r=>JSON.parse(r.value));
  assert.deepEqual(rows.map(r=>[r.at.slice(11,16),r.market_data.quote_access]),[
    ['14:30','received'],['14:31','awaiting_live_quote'],['14:32','received'],
  ]);
  assert.equal(rows[0].at,'2026-11-27T14:30:59.100Z');
  assert.ok(rows.every(r=>r.heartbeat_at==='2026-11-27T14:29:00.000Z'));
});
