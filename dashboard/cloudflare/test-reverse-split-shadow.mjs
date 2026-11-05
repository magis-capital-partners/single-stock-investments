import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter,openCheckpoint} from './reverse-split-live/checkpoint.mjs';
import {SHADOW_POLICIES,plannedEntry,plannedExit,sessionAt,quoteGate,signalGate,entryCapacity,validateEvidence,feasibility} from './reverse-split-live/shadow-core.mjs';
import {initializeShadow,enrollShadow,processShadowTrack,shadowTick,summarizeShadow} from './reverse-split-live/shadow-service.mjs';
import {makeMarketData} from './reverse-split-live/market-data.mjs';
import {readAPI,limitedFetch} from './reverse-split-live/worker.mjs';
import {onRequestGet} from '../functions/api/v1/reverse-splits/[[path]].js';
import {watchCollector} from './reverse-split-live/watch.mjs';
const now='2026-11-04T15:00:00.000Z',primary=SHADOW_POLICIES[0];
function setup(t){const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(x=>x.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());const env={DB:localAdapter(db),SHADOW_ENABLED:'true'};return {db,env};}
function event(overrides={}){return {id:'qa-shadow-event',cik:'123',ticker:'QATEST',company:'Synthetic unit-test issuer',status:'scheduled',ratio:20,effective_date:'2026-11-20',published_at:'2026-11-04T14:59:30.000Z',first_seen_at:'2026-11-04T14:59:40.000Z',analyzed_at:now,ordinal_min:2,financials:{score:75,signal_count:3,period:'2026-06-30',signals:{cash_burn:{score:1},leverage:{score:1},revenue_turn:{score:.5}}},sources:[{url:'https://www.sec.gov/test',sha256:'test-only'}],...overrides};}
function quote(overrides={}){return {id:'q1',ticker:'QATEST',cik:'123',security_id:'test-figi',type:'CS',currency:'usd',bid:10,ask:10.1,bid_size:100000,ask_size:100000,quote_at:now,observed_at:now,consolidated:true,delayed:false,provider:'test',source_url:'https://example.test/quote',...overrides};}
const track=(db,id='rs_immediate.v1:qa-shadow-event')=>JSON.parse(db.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').get(id).payload);

test('immediate entry has no five-minute delay; comparison clocks respect holidays, early closes and DST',()=>{
  assert.equal(plannedEntry(event(),primary,now),now);
  assert.equal(plannedEntry(event(),SHADOW_POLICIES[1],now),'2026-11-04T15:05:00.000Z');
  assert.equal(plannedEntry(event(),primary,'2026-11-04T22:00:00Z'),'2026-11-05T14:30:00Z');
  assert.equal(sessionAt('2026-11-26T16:00:00Z'),null);
  assert.equal(sessionAt('2026-11-27T18:00:00Z'),null);
  assert.equal(plannedEntry(event(),primary,'2026-11-27T19:00:00Z'),'2026-11-30T14:30:00Z');
  assert.equal(plannedExit(now,5),'2026-11-10T21:00:00Z');
  assert.equal(plannedEntry(event(),primary,'2026-03-06T22:00:00Z'),'2026-03-09T13:30:00Z');
});
test('financial coverage, freshness and repeat gates fail closed; controls keep their own versions',()=>{
  assert.equal(signalGate(event(),primary,now).state,'eligible');
  assert.equal(signalGate(event({ordinal_min:1}),primary,now).state,'waiting');
  assert.equal(signalGate(event({financials:{score:70,signal_count:2,period:'2026-06-30'}}),primary,now).state,'waiting');
  assert.equal(signalGate(event({financials:{score:59,signal_count:3,period:'2026-06-30'}}),primary,now).state,'rejected');
  assert.equal(signalGate(event({financials:{score:70,signal_count:3,period:'2025-06-30'}}),primary,now).state,'waiting');
  assert.equal(SHADOW_POLICIES.at(-2).minimum_score,0);
  assert.ok(SHADOW_POLICIES.every(p=>p.authority==='none'&&p.research_only));
});
test('a fresh consolidated quote is required; delayed, crossed, future and old quotes cannot fill',()=>{
  assert.equal(quoteGate(quote(),now,primary),null);
  for(const change of [{delayed:true},{consolidated:false},{ask:9},{quote_at:'2026-11-04T14:59:30Z'},{quote_at:'2026-11-04T15:01:00Z'},{bid_size:0}])assert.ok(quoteGate(quote(change),now,primary));
});
test('forward enrollment preserves every decision and never fills pre-registration detections',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);assert.equal(track(db).state,'armed');assert.equal(track(db).due_at,now);
  const snapshots=db.prepare('SELECT count(*) AS n FROM rs_shadow_records').get().n;await enrollShadow(env,event(),now);assert.equal(db.prepare('SELECT count(*) AS n FROM rs_shadow_records').get().n,snapshots);
  await enrollShadow(env,event({id:'old',first_seen_at:'2026-11-03T14:00:00Z'}),now);assert.equal(track(db,'rs_immediate.v1:old').state,'retrospective');
  await enrollShadow(env,event({id:'low',financials:{score:40,signal_count:3,period:'2026-06-30'}}),now);assert.equal(track(db,'rs_immediate.v1:low').state,'rejected');
  assert.equal(db.prepare('SELECT count(*) AS n FROM rs_shadow_tracks').get().n,3*SHADOW_POLICIES.length);
});
test('registered policies cannot be silently edited or reused with new parameters',async t=>{const {db,env}=setup(t);await initializeShadow(env,now);db.prepare("UPDATE rs_shadow_policies SET payload='{}' WHERE id=?").run(primary.id);await assert.rejects(initializeShadow(env,now),/new version/);});
test('simulated short uses bid, cover uses ask, fees and carry reduce profit; duplicate quotes cannot refill',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);let x=track(db);await processShadowTrack(env,x,quote(),[x],now);assert.equal(x.entry_shares,250);assert.equal(x.entry_price,9.99);assert.equal(x.feasibility.state,'unverified');assert.ok(x.net_pnl<0);
  const fills=x.fills.length;await processShadowTrack(env,x,quote(),[x],now);assert.equal(x.fills.length,fills);
  const exit='2026-11-10T20:59:30.000Z';await processShadowTrack(env,x,quote({id:'exit',bid:8,ask:8.1,quote_at:exit,observed_at:exit}),[x],exit);assert.equal(x.state,'closed');assert.equal(x.remaining_shares,0);assert.equal(x.fills.at(-1).price,8.1*1.001);assert.ok(x.borrow_cost>0);assert.ok(x.commissions>=2);assert.ok(x.net_pnl>0);assert.equal(x.feasibility.broker_execution_verified,false);
});
test('capacity reserves a squeeze budget and does not reuse another issuer slot or displayed depth',()=>{
  const x={id:'x',policy_id:primary.id,cik:'123',entry_shares:0,remaining_shares:0};assert.equal(entryCapacity(x,quote({bid_size:100}),primary,[]).shares,5);
  assert.equal(entryCapacity(x,quote(),primary,[{...x,id:'other',remaining_shares:1,mark_price:10}]).shares,0);
  const peers=['1','2','3'].map(cik=>({...x,id:cik,cik,remaining_shares:1,mark_price:10}));assert.equal(entryCapacity(x,quote(),primary,peers).shares,0);
});
test('missing exit quotes retain the liability and carry; split uncertainty never manufactures a gain',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event({effective_date:'2026-11-06'}),now);let x=track(db);await processShadowTrack(env,x,quote(),[x],now);const shares=x.remaining_shares;
  await processShadowTrack(env,x,null,[x],'2026-11-06T15:00:00Z');assert.equal(x.remaining_shares,shares);assert.equal(x.action_unresolved,true);assert.equal(x.net_pnl,null);
  const at='2026-11-06T15:01:00Z',q=quote({id:'post',bid:200,ask:202,quote_at:at,observed_at:at}),actions={complete:true,records:[{id:'a',ticker:'QATEST',execution_date:'2026-11-06',split_from:20,split_to:1}]};await processShadowTrack(env,x,q,[x],at,actions);assert.equal(x.remaining_shares,shares/20);assert.ok(x.net_pnl<0);
  await processShadowTrack(env,x,q,[x],at,{...actions,records:[{...actions.records[0],id:'duplicate-source'}]});assert.equal(x.remaining_shares,shares/20);
});
test('expired entries are recorded as missed without requesting an earlier fill',async t=>{const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);const x=track(db);await processShadowTrack(env,x,quote(),[x],'2026-11-04T15:16:00Z');assert.equal(x.state,'missed');assert.equal(x.entry_shares,0);});
test('new quote timestamps alone do not replenish consumed displayed depth',async t=>{const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);const x=track(db);await processShadowTrack(env,x,quote({bid_size:2000}),[x],now);assert.equal(x.entry_shares,100);await processShadowTrack(env,x,quote({id:'new-timestamp',bid_size:2000}),[x],now);assert.equal(x.entry_shares,100);await processShadowTrack(env,x,quote({id:'larger-displayed-size',bid_size:3000}),[x],now);assert.equal(x.entry_shares,150);});
test('known short-sale restrictions or explicit borrow denials block adding a simulated short',async t=>{const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);const evidence={id:'restricted',event_id:'qa-shadow-event',kind:'ssr',observed_at:now,valid_until:'2026-11-05T22:00:00Z',restricted:true};db.prepare('INSERT INTO rs_shadow_evidence VALUES(?,?,?,?,?)').run(evidence.id,evidence.event_id,evidence.kind,evidence.observed_at,JSON.stringify(evidence));const x=track(db);await processShadowTrack(env,x,quote(),[x],now);assert.equal(x.entry_shares,0);assert.equal(x.reason,'short_sale_restriction_active');});
test('owner-supplied evidence must have source, reference, valid clocks and sufficient size',()=>{
  const base={event_id:'x',source_url:'https://broker.example/evidence',reference:'test',observed_at:now,valid_until:'2026-11-04T16:00:00Z'};
  const locate=validateEvidence({...base,kind:'locate',approved:true,shares:100,apr:.5},now);assert.throws(()=>validateEvidence({...locate,observed_at:'2027-01-01'},now));assert.throws(()=>validateEvidence({...locate,source_url:''},now));
  assert.equal(feasibility([locate],now,100,10).state,'unverified');
  const ssr={...base,kind:'ssr',restricted:false},margin={...base,kind:'margin',approved:true,available_notional:1000};assert.equal(feasibility([locate,ssr,margin],now,100,10).state,'supplied_evidence_supports_size');assert.equal(feasibility([locate,{...ssr,restricted:true},margin],now,100,10).state,'unverified');
});
test('market adapter preserves share sizes, nanosecond quote clocks, identity and secret-free errors',async()=>{
  const seen=[],market=makeMarketData({key:'secret-test-only',clock:()=>now,fetcher:async(url,options)=>{seen.push({url:String(url),headers:options.headers});return String(url).includes('/reference/tickers/')?Response.json({results:{cik:'0000000123',share_class_figi:'test',type:'CS',currency_name:'usd'}}):Response.json({status:'OK',results:{t:Date.parse(now)*1e6,p:10,P:10.1,s:123,S:456}});}});
  const q=await market.quote('QATEST');assert.equal(q.bid_size,123);assert.equal(q.cik,'123');assert.equal(q.quote_at,now);assert.ok(seen.every(r=>!r.url.includes('secret')));assert.ok(seen.every(r=>r.headers.authorization==='Bearer secret-test-only'));
  const denied=makeMarketData({key:'secret',fetcher:async()=>new Response('secret vendor error',{status:403})});await assert.rejects(denied.quote('QATEST'),/HTTP 403/);assert.ok(!JSON.stringify(denied.health).includes('secret'));
});
test('a blocked GlobeNewswire article uses its official RSS host without broadening source access',async t=>{const old=globalThis.fetch,urls=[];globalThis.fetch=async value=>{urls.push(String(value));return new Response(urls.length===1?'blocked':'primary document',{status:urls.length===1?403:200});};t.after(()=>{globalThis.fetch=old;});const doc=await limitedFetch({},'https://www.globenewswire.com/news-release/example.html');assert.equal(new TextDecoder().decode(doc.bytes),'primary document');assert.equal(urls[1],'https://rss.globenewswire.com/news-release/example.html');});
test('shadow API has bounded pagination, private viewer access and a complete audit route',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);await summarizeShadow(env,now);
  const summary=await(await readAPI(new Request('https://internal/shadow'),env)).json();assert.equal(summary.authority,'none');assert.equal(summary.policies.length,SHADOW_POLICIES.length);
  let cursor,ids=[];for(let i=0;i<SHADOW_POLICIES.length;i++){const q=new URL('https://internal/shadow/tracks?limit=1');if(cursor)q.searchParams.set('before',cursor);const r=await(await readAPI(new Request(q),env)).json();ids.push(r.tracks[0].id);cursor=r.next_cursor;}assert.equal(new Set(ids).size,SHADOW_POLICIES.length);assert.equal(cursor,null);
  const detail=await(await readAPI(new Request('https://internal/shadow/tracks/'+encodeURIComponent(ids[0])),env)).json();assert.ok(detail.records.length>=2);
  assert.equal((await readAPI(new Request('https://internal/shadow',{method:'POST'}),env)).status,405);
  let forwarded;const response=await onRequestGet({request:new Request('https://dash/api/v1/reverse-splits/shadow/tracks'),data:{humanViewer:{role:'owner'}},env:{REVERSE_SPLITS:{fetch:async r=>{forwarded=r.url;return Response.json({});}}}});assert.equal(response.status,200);assert.equal(forwarded,'https://reverse-split.internal/shadow/tracks');
  assert.equal((await onRequestGet({request:new Request('https://dash/api/v1/reverse-splits/shadow'),data:{humanViewer:{role:'member'}},env:{}})).status,403);
});
test('shadow decisions and positions survive atomic checkpoint publication and restore',async t=>{
  const {env}=setup(t);env.controlDB=env.DB;env.pending=[];const objects=new Map();env.EVIDENCE={put:async(k,b)=>objects.set(k,new Uint8Array(b)),get:async k=>objects.has(k)?{arrayBuffer:async()=>objects.get(k).slice().buffer}:null};let checkpoint=await openCheckpoint(env);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);let x=JSON.parse((await env.DB.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(primary.id+':qa-shadow-event').first()).payload);await processShadowTrack(env,x,quote(),[x],now);await checkpoint.save();checkpoint.close();
  checkpoint=await openCheckpoint(env);const restored=JSON.parse((await env.DB.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(x.id).first()).payload);assert.equal(restored.entry_shares,x.entry_shares);assert.equal(restored.fills.length,1);assert.ok((await env.controlDB.prepare('SELECT id FROM rs_shadow_tracks WHERE id=?').bind(x.id).first()).id);checkpoint.close();
});
test('a failed dashboard publication cannot roll back a committed simulated position',async t=>{
  const {env}=setup(t);const original=env.DB;let fail=false;env.controlDB={...original,batch:async rows=>{if(fail)throw new Error('publication interrupted');return original.batch(rows);}};env.pending=[];const objects=new Map();env.EVIDENCE={put:async(k,b)=>objects.set(k,new Uint8Array(b)),get:async k=>objects.has(k)?{arrayBuffer:async()=>objects.get(k).slice().buffer}:null};let cp=await openCheckpoint(env);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);let x=JSON.parse((await env.DB.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(primary.id+':qa-shadow-event').first()).payload);await processShadowTrack(env,x,quote(),[x],now);fail=true;await assert.rejects(cp.save(),/publication interrupted/);cp.close();fail=false;cp=await openCheckpoint(env);x=JSON.parse((await env.DB.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(x.id).first()).payload);assert.equal(x.entry_shares,250);await cp.save();cp.close();assert.equal(JSON.parse((await original.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(x.id).first()).payload).entry_shares,250);
});
test('continuous collector runs bounded ticks, releases its lease and publishes its heartbeat without broker access',async t=>{
  const {env}=setup(t);env.controlDB=env.DB;env.pending=[];env.usage={rows_read:0,rows_written:0};env.JOBS={send:async body=>env.pending.push(body)};env.ENABLED='true';env.SEC_USER_AGENT='Synthetic offline test';env.market={health:{status:'not_configured'},quote:async()=>{throw new Error('No ticker in this test');}};
  const objects=new Map();env.EVIDENCE={put:async(k,b)=>objects.set(k,new Uint8Array(b)),get:async k=>objects.has(k)?{arrayBuffer:async()=>objects.get(k).slice().buffer}:null};
  const old=globalThis.fetch;globalThis.fetch=async()=>new Response('<feed></feed>');t.after(()=>{globalThis.fetch=old;});let stopChecks=0;const result=await watchCollector(env,{maximumMs:20000,shouldStop:()=>stopChecks++>=1,sleep:async()=>{}});assert.equal(result.ticks,1);assert.equal((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='collector_lease'").first()).value,'0');const runtime=JSON.parse((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='shadow_runtime'").first()).value);assert.equal(runtime.status,'handoff');assert.equal(runtime.broker_connections,0);
});
