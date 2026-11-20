import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {operationalEvidence} from './reverse-split-live/operational-evidence.mjs';

test('operations retain event-specific cohort order, delayed entry and expired open liabilities',t=>{
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());
 for(const name of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+name,import.meta.url),'utf8'));
 const now='2026-11-20T15:00:00.000Z',old='2026-11-19T15:00:00.000Z';
 for(const event of [{id:'open-old',first_seen_at:old},{id:'fresh',first_seen_at:'2026-11-20T14:59:00.000Z',result:'passes_screen'},{id:'unrelated',first_seen_at:old},{id:'retro-only',first_seen_at:old}]){
  const value={ticker:'SAME',...event};db.prepare('INSERT INTO rs_events(id,ticker,first_seen_at,result,payload) VALUES(?,?,?,?,?)').run(value.id,value.ticker,value.first_seen_at,value.result||'fails_screen',JSON.stringify(value));
 }
 const tracks=[
  {id:'other',event_id:'unrelated',policy_id:'capacity.v1',state:'rejected',entry_shares:0,remaining_shares:0},
  {id:'first',event_id:'open-old',policy_id:'capacity.v1',state:'open',entry_shares:4,remaining_shares:2},
  {id:'delayed',event_id:'open-old',policy_id:'capacity_delay30s.v1',state:'open',entry_shares:1,remaining_shares:1},
  {id:'second',event_id:'open-old',policy_id:'executable.v1',state:'rejected',entry_shares:0,remaining_shares:0},
  {id:'retro',event_id:'retro-only',policy_id:'capacity.v1',state:'retrospective',entry_shares:999,remaining_shares:999},
 ];
 for(const track of tracks){const value={ticker:'SAME',lane:'capacity',...track};db.prepare('INSERT INTO rs_execution_tracks(id,event_id,policy_id,ticker,state,updated_at,payload) VALUES(?,?,?,?,?,?,?)').run(value.id,value.event_id,value.policy_id,value.ticker,value.state,now,JSON.stringify(value));}
 const result=operationalEvidence(db,now),byId=new Map(result.candidates.map(candidate=>[candidate.id,candidate]));
 assert.deepEqual(byId.get('open-old').cohort_outcomes.map(row=>row.policy_id),['capacity.v1','executable.v1']);
 assert.equal(byId.get('open-old').entered,true);
 assert.deepEqual(byId.get('fresh').cohort_outcomes,[]);
 assert.equal(byId.get('unrelated').entered,false);
 assert.deepEqual(byId.get('retro-only').cohort_outcomes,[]);
 assert.equal(byId.get('retro-only').entered,false);
 assert.deepEqual(result.eligibility.map(row=>row.event_id).sort(),['fresh','open-old']);
 assert.deepEqual(result.open_liabilities.map(row=>row.id),['first','delayed']);
 assert.equal(result.distinct_entered_events,1);
 assert.equal(result.actual_broker_fills,0);
 assert.equal(result.broker_connections,0);
});
