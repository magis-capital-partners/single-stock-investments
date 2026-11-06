import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {readAPI} from './reverse-split-live/worker.mjs';
import {captureReadSnapshot,publishReadSnapshot} from './reverse-split-live/snapshot-publish.mjs';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {ensureRemoteReadIndexes} from './reverse-split-live/read-indexes.mjs';
import {remoteEnvironment} from './reverse-split-live/collector.mjs';
import {monitor} from './reverse-split-live/review-monitor.mjs';

function setup(t){
 const db=new DatabaseSync(':memory:');for(const n of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+n,import.meta.url),'utf8'));t.after(()=>db.close());
 const objects=new Map(),env={DB:{prepare(){assert.fail('A committed dashboard view must not query D1, even when its daily allowance is exhausted');}},EVIDENCE:{get:async k=>objects.has(k)?{json:async()=>JSON.parse(objects.get(k))}:null,put:async(k,v)=>objects.set(k,typeof v==='string'?v:new TextDecoder().decode(v))}};return {db,objects,env};
}
test('the deployed snapshot remains readable during an account-wide D1 quota outage',async t=>{
 const {env,objects}=setup(t);objects.set('collector-dashboard/manifest.json',JSON.stringify({at:'2026-11-06T08:27:48Z'}));objects.set('collector-dashboard/shadow.json',JSON.stringify({runtime:{heartbeat_at:'2026-11-06T08:27:00Z',status:'running'}}));
 const response=await readAPI(new Request('https://internal/shadow'),env),d=await response.json();assert.equal(response.status,200);assert.equal(d.status,'stale');
});
test('historical per-policy pagination reads private snapshots and never scans D1',async t=>{
 const {db,env}=setup(t);const at='2026-11-06T08:00:00Z';
 for(let i=0;i<305;i++){const id=String(i).padStart(4,'0'),policy=i<303?'policy-A':'policy-B',track={id,event_id:'event-'+id,policy_id:policy,ticker:i===209?'FIND':'OTHER',cik:id,enrolled_at:at,state:'retrospective',reason:'historical'};db.prepare('INSERT INTO rs_shadow_tracks(id,event_id,policy_id,cik,ticker,enrolled_at,state,reason,updated_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?)').run(id,track.event_id,policy,id,track.ticker,at,track.state,track.reason,at,JSON.stringify(track));}
 await publishReadSnapshot(env,db,captureReadSnapshot(db));
 let before='',ids=[];do{const r=await readAPI(new Request('https://internal/shadow/tracks?policy=policy-A&limit=100'+(before?'&before='+encodeURIComponent(before):'')),env),d=await r.json();assert.equal(r.status,200);ids.push(...d.tracks.map(v=>v.id));before=d.next_cursor;}while(before);
 assert.equal(ids.length,303);assert.equal(new Set(ids).size,303);assert.equal(ids.at(-1),'0302');
 const result=await (await readAPI(new Request('https://internal/shadow/tracks?policy=policy-A&q=FIND&state=retrospective'),env)).json();assert.deepEqual(result.tracks.map(v=>v.id),['0209']);
});
test('an older snapshot explicitly reports unavailable history instead of querying the exhausted database',async t=>{
 const {env,objects}=setup(t);objects.set('collector-dashboard/manifest.json','{}');objects.set('collector-dashboard/cards/shadow.json','[]');
 const d=await (await readAPI(new Request('https://internal/shadow/tracks'),env)).json();assert.deepEqual(d.tracks,[]);assert.equal(d.historical_data_status,'awaiting_snapshot_rebuild');
});
test('the independent monitor records a quota outage without any D1 dependency',async t=>{const {env,objects}=setup(t);objects.set('collector-dashboard/shadow.json',JSON.stringify({runtime:{heartbeat_at:'2026-11-06T08:27:00Z',status:'running'},readiness:{generated_at:'2026-11-06T08:27:00Z',sources:[],jobs:[]}}));const result=await monitor(env);assert.equal(result.status,'needs_attention');assert.ok(result.problems.includes('collector_heartbeat_missing_or_older_than_three_minutes'));assert.ok(objects.has('review/monitor-latest.json'));});
test('a blocked push-time index migration is applied idempotently at the next collector start',async t=>{const {db}=setup(t);db.exec('DROP INDEX rs_shadow_state_policy_recent; DROP INDEX rs_shadow_policy_recent; DROP INDEX rs_execution_policy_id;');await ensureRemoteReadIndexes(localAdapter(db));await ensureRemoteReadIndexes(localAdapter(db));const plan=db.prepare("EXPLAIN QUERY PLAN SELECT payload FROM rs_shadow_tracks WHERE state='retrospective' AND (enrolled_at<? OR (enrolled_at=? AND id>?)) AND policy_id=? ORDER BY enrolled_at DESC,id LIMIT ?").all('9999','9999','','p',100);assert.ok(plan.some(r=>r.detail.includes('rs_shadow_state_policy_recent')));assert.ok(plan.every(r=>!r.detail.startsWith('SCAN')));});
test('the exact production quota response is explicit and is not blindly retried',async()=>{let calls=0;const env=remoteEnvironment({token:'test',account:'test',database:'test',bucket:'test',fetcher:async()=>{calls++;return Response.json({errors:[{code:7500,message:"Your account has exceeded D1's free tier daily row read limit."}]},{status:400});}});await assert.rejects(env.DB.prepare('SELECT value FROM rs_state').first(),/daily row-read allowance exhausted; resets at midnight UTC/);assert.equal(calls,1);});
