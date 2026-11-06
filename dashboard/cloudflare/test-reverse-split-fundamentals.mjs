import test from 'node:test';
import assert from 'node:assert/strict';
import {buildFinancialProfile,validateReviewedFacts,reconcileFacts} from './reverse-split-live/financials-core.mjs';
import {financialAPI} from './reverse-split-live/financials-api.mjs';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {localAdapter,openCheckpoint} from './reverse-split-live/checkpoint.mjs';
import {readSnapshotAPI} from './reverse-split-live/read-snapshot.mjs';
import {publishFinancialCoverage,harvestIssuer,nextFinancialJob} from './reverse-split-live/financials-harvest.mjs';
import {FinancialSources,hash} from './reverse-split-live/financials-io.mjs';
import {needsStartupReconciliation} from './reverse-split-live/watch.mjs';
import {captureReadSnapshot,publishReadSnapshot,trackCard} from './reverse-split-live/snapshot-publish.mjs';
const now='2026-11-05T17:00:00Z',cik='123';
const fact=(metric,value,start=null,end='2026-06-30',extra={})=>({metric,value,start,end,currency:'USD',cik,form:'6-K',filed:'2026-08-15',published_at:'2026-08-15T12:00:00Z',observed_at:now,source_url:'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/report.htm',source_sha256:'a'.repeat(64),locator:'Consolidated financial statements, row '+metric,kind:'html_table',confidence:'verified',scope:'consolidated',...extra});
const annual=(end='2026-06-30')=>[fact('net_income',-15,'2025-07-01',end),fact('cfo',-10,'2025-07-01',end),fact('cash',5,null,end),fact('total_assets',100,null,end),fact('stockholders_equity',-5,null,end),fact('long_term_debt',0,null,end),fact('current_debt',0,null,end)];

test('an upcoming company refresh precedes the historical baseline queue while backoff is respected',()=>{
  const jobs={old:{cik:'old',priority:50,last_attempt:'2026-11-01',next_attempt:0},unseen:{cik:'unseen',priority:200,next_attempt:0},upcoming:{cik:'upcoming',priority:1000,last_attempt:'2026-11-05',next_attempt:0}};
  assert.equal(nextFinancialJob(jobs,100).cik,'upcoming');jobs.upcoming.next_attempt=200;assert.equal(nextFinancialJob(jobs,100).cik,'unseen');jobs.unseen.next_attempt=200;assert.equal(nextFinancialJob(jobs,100).cik,'old');
});
test('a long research pause queues filing reconciliation while ordinary handoffs do not',()=>{assert.equal(needsStartupReconciliation('2026-11-05T14:11:00Z',Date.parse(now)),true);assert.equal(needsStartupReconciliation('2026-11-05T16:55:00Z',Date.parse(now)),false);assert.equal(needsStartupReconciliation(null,Date.parse(now)),false);});
test('verified filing inputs recover a score without inventing absent debt or historical entry clocks',()=>{
  const p=buildFinancialProfile({cik,company:'Example Research Ltd',companyfacts:{cik,facts:{}},facts:annual(),as_of:now});
  assert.equal(p.policy_financials.signal_count,3);assert.equal(p.policy_financials.score,68.8);
  assert.equal(p.coverage.status,'current');assert.equal(p.observed_at,now);assert.equal(p.coverage.metrics.revenues.status,'not_recovered');
  const early=buildFinancialProfile({cik,companyfacts:{cik,facts:{}},facts:annual(),as_of:'2026-11-05T16:00:00Z'});assert.equal(early.policy_financials.score,null);
});
test('complete old statements remain separately available but cannot pass the current freshness gate',()=>{
  const facts=annual('2025-12-31').map(r=>({...r,start:r.start?'2025-01-01':null,filed:'2026-03-15',published_at:'2026-03-15T12:00:00Z'}));
  const p=buildFinancialProfile({cik,companyfacts:{cik,facts:{}},facts,as_of:now});assert.equal(p.policy_financials.score,null);assert.equal(p.coverage.status,'stale');assert.equal(p.coverage.available_score,68.8);
});
test('funds and conflicting numeric disclosures remain non-eligible',()=>{
  const fund=buildFinancialProfile({cik,companyfacts:{cik,facts:{}},facts:annual(),as_of:now,instrument:{type:'ETF'}});assert.equal(fund.coverage.status,'not_applicable');assert.equal(fund.policy_financials.score,null);
  const conflict=buildFinancialProfile({cik,companyfacts:{cik,facts:{}},facts:[...annual(),fact('cash',500)],as_of:now});assert.equal(conflict.coverage.status,'needs_review');assert.equal(conflict.policy_financials.score,null);assert.ok(conflict.coverage.conflicts.length);
});
test('registered tag priorities distinguish total debt and parent equity; note tables cannot replace tagged facts',()=>{
  const rows=[fact('long_term_debt',100,null,undefined,{kind:'inline_xbrl',original_tag:'us-gaap:LongTermDebtNoncurrent'}),fact('long_term_debt',120,null,undefined,{kind:'inline_xbrl',original_tag:'us-gaap:LongTermDebt'}),fact('long_term_debt',1,null,undefined,{kind:'html_table'})];
  const r=reconcileFacts(rows);assert.equal(r.facts[0].value,100);assert.equal(r.conflicts.length,0);
});
test('a review must refer to a captured source and explicit finite values',()=>{
  const sources=[{sha256:'a'.repeat(64),url:'https://www.sec.gov/Archives/edgar/data/123/a/report.htm',published_at:'2026-08-15T12:00:00Z',form:'6-K',filed:'2026-08-15'}];
  assert.throws(()=>validateReviewedFacts({cik,facts:[fact('cash',5,{})],reason:'checked'},[],now),/source/i);
  assert.throws(()=>validateReviewedFacts({cik,facts:[{...fact('cash',5),value:null}],reason:'checked'},sources,now),/numeric|finite/i);
  assert.throws(()=>validateReviewedFacts({cik,facts:[{...fact('cash',5),end:'2026-02-31'}],reason:'checked'},sources,now),/periods/i);
});
function setup(t){const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(x=>x.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());const objects=new Map(),EVIDENCE={put:async(k,v)=>objects.set(k,typeof v==='string'?new TextEncoder().encode(v):new Uint8Array(v)),get:async k=>{const v=objects.get(k);return v?{json:async()=>JSON.parse(new TextDecoder().decode(v)),arrayBuffer:async()=>v,body:v}:null;}};return {db,objects,env:{DB:localAdapter(db),EVIDENCE}};}

test('a source cooldown carries a future retry time without making a network request',async t=>{
  const {env}=setup(t),client=new FinancialSources(env),until=Date.now()+300000;client.cooldown=until;
  await assert.rejects(client.get('https://data.sec.gov/submissions/CIK0000000123.json'),e=>e.code==='FINANCIAL_SOURCE_COOLDOWN'&&e.retryAt===until);assert.equal(client.requests,0);
});

test('a source cooldown stops the visit without failing every remaining document',async t=>{
  const {env}=setup(t),until=Date.now()+300000;let calls=0;const client={cooldown:0,get:async url=>{
    if(url.includes('/Archives/')){calls++;client.cooldown=until;throw Object.assign(new Error('Financial source is in backoff'),{code:'FINANCIAL_SOURCE_COOLDOWN',retryAt:until});}
    return {bytes:Buffer.from(JSON.stringify(url.includes('/submissions/')?{cik:123,name:'Example Research Ltd',filings:{recent:{form:['10-Q','10-Q'],filingDate:['2026-08-15','2026-05-15'],accessionNumber:['0000000123-26-000001','0000000123-26-000002']}}}:{cik:123,facts:{}})),url,sha256:'a'.repeat(64),captured_at:now};
  }};const result=await harvestIssuer(env,{cik:'123'},{client,maximumDocuments:8}),work=await(await env.EVIDENCE.get('financials/work/123.json')).json();assert.equal(calls,1);assert.equal(result.complete,false);assert.equal(result.profile.collection.remaining_documents,2);assert.ok(result.next_attempt>=until);assert.equal(Object.keys(work.errors).length,1);assert.equal(Object.values(work.errors)[0].terminal,false);assert.equal(Object.values(work.errors)[0].attempts,0);
});

test('documents parked by the old cooldown bug are reopened and can be extracted',async t=>{
  const {env}=setup(t),url='https://www.sec.gov/Archives/edgar/data/123/000000012326000001/0000000123-26-000001.txt',parser_hash=hash(readFileSync(new URL('./reverse-split-live/fundamental_filing.py',import.meta.url))),work={parser_hash,facts:[],sources:[],processed:{},candidates:[],issues:[],errors:{[url]:{attempts:3,terminal:true,next_attempt:Date.now()+86400000,reason:'Financial source is in backoff'}}};await env.EVIDENCE.put('financials/work/123.json',JSON.stringify(work));let extracted=0;
  const client={get:async target=>({bytes:Buffer.from(JSON.stringify(target.includes('/submissions/')?{cik:123,name:'Example Research Ltd',filings:{recent:{form:['10-Q'],filingDate:['2026-08-15'],accessionNumber:['0000000123-26-000001']}}}:{cik:123,facts:{}})),url:target,sha256:'b'.repeat(64),captured_at:now})};const result=await harvestIssuer(env,{cik:'123'},{client,extract:async()=>{extracted++;return {facts:[],candidates:[],issues:[]};}});assert.equal(extracted,1);assert.equal(result.profile.collection.searched_documents,1);assert.equal(result.complete,true);
});
test('private snapshot publication keeps full local research running with no event-table writes',async t=>{
  const {db,env,objects}=setup(t);env.controlDB=env.DB;env.pending=[];const checkpoint=await openCheckpoint(env);t.after(()=>checkpoint.close());
  await env.DB.prepare('INSERT INTO rs_events(id,cik,first_seen_at,payload) VALUES(?,?,?,?)').bind('qa-current','123',now,JSON.stringify({id:'qa-current',cik:'123',first_seen_at:now,result:'needs_review'})).run();
  const put=env.EVIDENCE.put;env.EVIDENCE.put=async(k,v)=>{if(k.startsWith('collector-dashboard/'))assert.ok(db.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").get(),'checkpoint commits before any view');await put(k,v);};
  await checkpoint.save({publicationMode:'r2'});assert.equal(db.prepare('SELECT count(*) AS n FROM rs_events').get().n,0);assert.equal(db.prepare("SELECT value FROM rs_state WHERE key='collector_publication'").get().value,'r2');assert.ok(objects.has('collector-dashboard/events.json'));
  env.DB=env.controlDB;const response=await readSnapshotAPI(new URL('https://internal/events'),env);assert.equal((await response.json()).events[0].id,'qa-current');
});
test('losing the collector lease cannot commit a checkpoint or publish a new view',async t=>{
  const {db,env,objects}=setup(t);env.controlDB=env.DB;env.pending=[];env.collectorLeaseOwner='qa-old-owner';db.prepare('INSERT INTO rs_state VALUES(?,?,?)').run('collector_lease',String(Date.now()+600000)+':qa-new-owner',now);
  const checkpoint=await openCheckpoint(env);t.after(()=>checkpoint.close());await assert.rejects(checkpoint.save({publicationMode:'r2'}),/lease lost/);assert.equal(db.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").get(),undefined);assert.equal(objects.has('collector-dashboard/shadow.json'),false);
});
test('coverage publication uses the cached cards instead of rereading every issuer on every update',async t=>{
  const {env}=setup(t),queue={jobs:Object.fromEntries(Array.from({length:200},(_,i)=>[String(i+1),{cik:String(i+1)}]))};let reads=0;env.EVIDENCE.get=async()=>{reads++;return null;};env.financialCoverageCards=new Map([['123',{cik:'123',version:'a'.repeat(64),status:'stale',observed_at:now}]]);const result=await publishFinancialCoverage(env,queue);assert.equal(result.processed,1);assert.equal(result.issuers,200);assert.equal(reads,0);
});
test('a malformed Company Facts response does not poison the primary-filing fallback ledger',async t=>{
  const {env}=setup(t),client={get:async url=>({bytes:Buffer.from(url.includes('/submissions/')?JSON.stringify({cik:123,name:'Example Research Ltd',filings:{recent:{form:[]}}}):'<html>upstream unavailable</html>'),url,sha256:'a'.repeat(64),captured_at:now})};const result=await harvestIssuer(env,{cik:'123',ticker:null},{client,maximumDocuments:0});assert.equal(result.profile.collection.api_source_sha256,null);assert.equal(result.profile.policy_financials.score,null);assert.equal(result.profile.cik,'123');
});

test('an extraction failure retains the captured filing for owner review without admitting any facts',async t=>{
  const {env}=setup(t),url='https://www.sec.gov/Archives/edgar/data/123/000000012326000001/0000000123-26-000001.txt',client={get:async target=>({bytes:Buffer.from(JSON.stringify(target.includes('/submissions/')?{cik:123,name:'Example Research Ltd',filings:{recent:{form:['10-Q'],filingDate:['2026-08-15'],accessionNumber:['0000000123-26-000001']}}}:{cik:123,facts:{}})),url:target,sha256:target===url?'b'.repeat(64):'a'.repeat(64),captured_at:now})};
  const result=await harvestIssuer(env,{cik:'123'},{client,maximumDocuments:1,extract:async()=>{throw new Error('Document needs manual extraction');}});
  assert.ok(result.profile.sources.some(s=>s.url===url&&s.sha256==='b'.repeat(64)));assert.equal(result.profile.policy_financials.score,null);assert.equal(result.profile.collection.searched_documents,0);assert.equal(result.profile.collection.remaining_documents,1);assert.ok(result.profile.collection.issues.some(s=>s.reason==='Document needs manual extraction'));
});
test('slow derived dashboard writes do not block the durable collector checkpoint or quote loop',async t=>{
  const {db,env}=setup(t);env.controlDB=env.DB;env.pending=[];const checkpoint=await openCheckpoint(env);let release,started=false;const wait=new Promise(r=>{release=r;}),put=env.EVIDENCE.put;env.EVIDENCE.put=async(k,v)=>{if(k.startsWith('collector-dashboard/')&&!started){started=true;await wait;}await put(k,v);};
  try{await checkpoint.save({publicationMode:'r2',backgroundViews:true});assert.ok(db.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").get());assert.equal(started,true);await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?)').bind('qa-quote-loop','still_running',now).run();assert.equal((await env.DB.prepare("SELECT value FROM rs_state WHERE key='qa-quote-loop'").first()).value,'still_running');}finally{release();await checkpoint.flush();checkpoint.close();}
});
test('snapshot history pagination reaches beyond the first page and paused runtime is never tracking',async t=>{
  const {db,env}=setup(t);for(let i=0;i<5;i++){const id='qa-'+i,payload={id,policy_id:'p',state:'retrospective',enrolled_at:now};db.prepare('INSERT INTO rs_execution_tracks VALUES(?,?,?,?,?,?,?)').run(id,id,'p','QA','retrospective',now,JSON.stringify(payload));}
  let after='',ids=[];for(let i=0;i<4;i++){const r=await readSnapshotAPI(new URL('https://internal/shadow/executable/tracks?limit=2&after='+after),env),b=await r.json();ids.push(...b.tracks.map(r=>r.id));if(!b.next_cursor)break;after=b.next_cursor;}assert.equal(new Set(ids).size,5);
  await env.EVIDENCE.put('collector-dashboard/shadow.json',JSON.stringify({runtime:{status:'running'},status:'tracking'}));db.prepare('INSERT INTO rs_state VALUES(?,?,?)').run('shadow_runtime',JSON.stringify({status:'paused_budget',heartbeat_at:new Date().toISOString()}),now);const r=await readSnapshotAPI(new URL('https://internal/shadow'),env);assert.equal((await r.json()).status,'paused_budget');
});
test('compact policy cards keep full fills and bounded audit pages available in the separate detail',async t=>{
  const {db,env}=setup(t),track={id:'qa-fills',event_id:'qa',policy_id:'p',cik:'123',ticker:'QA',state:'open',enrolled_at:now,updated_at:now,entry_shares:1,fills:[{side:'short',shares:1,price:10}],decision_snapshot:{score:70,sources:[{large:'evidence'}]}};
  db.prepare('INSERT INTO rs_shadow_tracks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').run(track.id,'qa','p','123','QA',now,now,now,'open','qa',now,JSON.stringify(track));
  for(let i=0;i<105;i++)db.prepare('INSERT INTO rs_shadow_records VALUES(?,?,?,?,?,?)').run(String(i).padStart(3,'0'),track.id,'qa','mark',now,JSON.stringify({reason:'qa'}));
  const card=trackCard(track);assert.equal(card.fills,undefined);assert.equal(card.decision_snapshot.sources,undefined);await publishReadSnapshot(env,db,captureReadSnapshot(db));
  const first=await(await readSnapshotAPI(new URL('https://internal/shadow/tracks/qa-fills'),env)).json();assert.equal(first.track.fills.length,1);assert.equal(first.records.length,100);assert.ok(first.next_cursor);const second=await(await readSnapshotAPI(new URL('https://internal/shadow/tracks/qa-fills?before='+first.next_cursor),env)).json();assert.equal(second.records.length,5);assert.equal(second.next_cursor,null);
});
test('reviews require a verified owner, current source version and captured document; retries are idempotent',async t=>{
  const {db,env}=setup(t),source={sha256:'a'.repeat(64),url:'https://www.sec.gov/Archives/edgar/data/123/a/report.htm',published_at:'2026-08-15T12:00:00Z',form:'6-K',filed:'2026-08-15'},profile={version:'v1',sources:[source]};await env.EVIDENCE.put('financials/profiles/123/latest.json',JSON.stringify(profile));
  const input={cik,profile_version:'v1',reason:'Checked source row',facts:[fact('cash',5)]},req=(owner=true,body=input)=>new Request('https://internal/fundamentals/reviews',{method:'POST',headers:{'content-type':'application/json',...(owner?{'x-verified-owner':'qa-owner'}:{})},body:JSON.stringify(body)});
  assert.equal((await financialAPI(req(false),env)).status,403);assert.equal((await financialAPI(req(true,{...input,profile_version:'old'}),env)).status,409);
  assert.equal((await financialAPI(req(),env)).status,200);const retry=await financialAPI(req(),env);assert.equal((await retry.json()).status,'already_saved');assert.equal(db.prepare("SELECT count(*) AS n FROM rs_state WHERE key LIKE 'financial_review:%'").get().n,1);
  const unicode={...input,reason:'Checked caf\u00e9 source \u20ac row'},encoded=new TextEncoder().encode(JSON.stringify(unicode)),split=encoded.indexOf(0xc3)+1,stream=new ReadableStream({start(c){c.enqueue(encoded.slice(0,split));c.enqueue(encoded.slice(split));c.close();}}),response=await financialAPI(new Request('https://internal/fundamentals/reviews',{method:'POST',headers:{'x-verified-owner':'qa-owner'},body:stream,duplex:'half'}),env),saved=await response.json();assert.equal(response.status,200);assert.equal(JSON.parse(new TextDecoder().decode((await env.EVIDENCE.get(`financials/reviews/${cik}/${saved.id}.json`)).body)).reason,unicode.reason);
  assert.equal((await financialAPI(new Request('https://internal/fundamentals/123/source/'+'b'.repeat(64)),env)).status,404);
});
