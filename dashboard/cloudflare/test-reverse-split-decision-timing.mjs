import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {decisionTiming} from './reverse-split-live/decision-timing.mjs';
import {operationalEvidence} from './reverse-split-live/operational-evidence.mjs';
function setup(t){const db=new DatabaseSync(':memory:');for(const n of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+n,import.meta.url),'utf8'));t.after(()=>db.close());return db;}
test('later rescoring cannot replace initial decision latency on the operations dashboard',t=>{
 const db=setup(t),event={id:'forward',first_seen_at:'2026-11-09T14:30:58.067Z',analyzed_at:'2026-11-09T14:34:36.950Z',latency_seconds:218.883,financials:{score:27.8,signal_count:4}};
 db.prepare('INSERT INTO rs_events(id,first_seen_at,payload) VALUES(?,?,?)').run(event.id,event.first_seen_at,JSON.stringify(event));const put=db.prepare('INSERT INTO rs_decisions(id,event_id,recorded_at,policy,payload) VALUES(?,?,?,?,?)');
 put.run('first',event.id,'2026-11-09T14:31:03.922Z','frozen',JSON.stringify({...event,latency_seconds:5.855}));put.run('rescore',event.id,event.analyzed_at,'frozen',JSON.stringify(event));
 const row=operationalEvidence(db,'2026-11-09T19:00:00Z').candidates[0];assert.equal(row.receipt_to_filters_seconds,5.855);assert.equal(row.first_scored_decision_id,'first');assert.equal(row.analyzed_at,event.analyzed_at);assert.equal(db.prepare('SELECT count(*) AS n FROM rs_decisions').get().n,2);
});
test('an incomplete score and a future saved decision never manufacture filters-ready latency',t=>{
 const db=setup(t),event={id:'waiting',first_seen_at:'2026-11-09T12:00:00Z'},put=db.prepare('INSERT INTO rs_decisions(id,event_id,recorded_at,policy,payload) VALUES(?,?,?,?,?)');
 put.run('partial',event.id,'2026-11-09T12:00:02Z','frozen',JSON.stringify({financials:{score:null,signal_count:2}}));put.run('future',event.id,'2026-11-09T13:00:00Z','frozen',JSON.stringify({financials:{score:70,signal_count:3}}));
 const timing=decisionTiming(db,event,'2026-11-09T12:15:00Z');assert.equal(timing.receipt_to_analysis_seconds,2);assert.equal(timing.first_scored_at,null);assert.equal(timing.receipt_to_filters_seconds,null);
});
