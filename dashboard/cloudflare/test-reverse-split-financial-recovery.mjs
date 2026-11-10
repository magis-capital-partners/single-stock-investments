import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyAnnouncement} from './reverse-split-live/core.mjs';
import {nextFinancialJob} from './reverse-split-live/financials-harvest.mjs';
import {applyFinancialNeed,requestedFinancialSources} from './reverse-split-live/financials-harvest.mjs';
import {buildFinancialProfile} from './reverse-split-live/financials-core.mjs';
import {financialAssessment} from './reverse-split-live/financial-assessment.mjs';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {replayAnnouncement,sha} from './reverse-split-live/worker.mjs';

test('missing data, genuine financial rejection and excluded instruments are separate',()=>{
 assert.equal(financialAssessment({financials:{score:null,signal_count:2}}).status,'missing_data');
 assert.equal(financialAssessment({financials:{score:0,signal_count:3}}).status,'financial_rejection');
 assert.equal(financialAssessment({financials:{score:56.5,signal_count:3}}).data_ready,true);
 assert.equal(financialAssessment({financials:{score:75,signal_count:4}}).status,'meets_financial_filter');
 const adr={score:null,status:'instrument_not_in_operating_company_strategy',issuer_financials:{score:53,signal_count:5}};
 assert.equal(financialAssessment({financials:adr}).status,'instrument_excluded');
 assert.equal(financialAssessment({financials:{...adr,issuer_financials:{score:null,signal_count:2}}}).status,'missing_data');
});

test('an archived announcement repair appends a decision and retains original clocks and evidence',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
 const objects=new Map(),text='The Board approved a stock split ratio of 1-for-20 and maintained authorized shares. A certificate amendment was filed to effect the reverse stock split, effective November 12, 2026.',hash=await sha(text),first='2026-11-09T15:00:00Z';
 const original={id:'repair-test',ticker:'TEST',cik:'123',status:'authorization',ratio:20,effective_date:null,published_at:first,first_seen_at:first,sources:[{url:'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/report.htm',sha256:hash,representation:'original_release'}]};
 objects.set('documents/'+hash,new TextEncoder().encode(text));objects.set('sub',new TextEncoder().encode(JSON.stringify({cik:'123',tickers:['TEST'],filings:{recent:{}}})));
 const env={DB:localAdapter(db),scoreFinancialProfile:()=>({score:34,signal_count:5,status:'scored'}),EVIDENCE:{get:async k=>{const b=objects.get(k);return b?{arrayBuffer:async()=>b,json:async()=>JSON.parse(new TextDecoder().decode(b))}:null;},put:async(k,v)=>objects.set(k,v)}};
 db.prepare('INSERT INTO rs_events(id,cik,ticker,published_at,first_seen_at,payload) VALUES(?,?,?,?,?,?)').run(original.id,'123','TEST',first,first,JSON.stringify(original));
 db.prepare('INSERT INTO rs_issuers(cik,ticker,submissions_key,refreshed_at) VALUES(?,?,?,?)').run('123','TEST','sub',new Date().toISOString());
 db.prepare('INSERT INTO rs_decisions(id,event_id,recorded_at,policy,payload) VALUES(?,?,?,?,?)').run('original',original.id,first,'original-policy',JSON.stringify(original));
 const result=await replayAnnouncement(env,original.id);assert.equal(result.changed,true);
 const current=JSON.parse(db.prepare('SELECT payload FROM rs_events WHERE id=?').get(original.id).payload);
 assert.equal(current.status,'scheduled');assert.equal(current.first_seen_at,first);assert.equal(current.published_at,first);
 assert.deepEqual(JSON.parse(db.prepare("SELECT payload FROM rs_decisions WHERE id='original'").get().payload),original);
 assert.equal(db.prepare('SELECT count(*) AS n FROM rs_decisions').get().n,2);
 assert.deepEqual(JSON.parse(new TextDecoder().decode(objects.get(result.original_object_key))).original_event,original);
 current.status='cancelled';db.prepare('UPDATE rs_events SET payload=? WHERE id=?').run(JSON.stringify(current),original.id);assert.equal((await replayAnnouncement(env,original.id)).changed,false);
});

test('selected implementation is not a proposal merely because authorized shares are mentioned',()=>{
 const p=classifyAnnouncement('The Board approved a stock split ratio of 1-for-20 and maintained authorized shares. A certificate amendment was filed to effect the reverse stock split, effective November 12, 2026.',{published_at:'2026-11-10T13:00:00Z',form:'8-K'});
 assert.equal(p.status,'scheduled');assert.equal(p.ratio,20);assert.equal(p.effective_date,'2026-11-12');
});
test('approved hundred-for-one consolidation with a shall-take-effect date is extracted',()=>{
 const p=classifyAnnouncement('All resolutions passed. As an ordinary resolution, to approve a share consolidation at one hundred (100)-for-one (1), which shall take effect on November 19, 2026.',{published_at:'2026-11-10T13:00:00Z',form:'6-K'});
 assert.equal(p.status,'scheduled');assert.equal(p.ratio,100);assert.equal(p.effective_date,'2026-11-19');
});
test('conditional proposals and discretionary ratio ranges remain non-qualifying',()=>{
 for(const text of ['A proposed reverse stock split of 1-for-20 would be effective November 19, 2026, subject to shareholder approval.','Shareholders approved a reverse stock split range between 1-for-10 and 1-for-100; the board may select a ratio later.'])assert.notEqual(classifyAnnouncement(text,{published_at:'2026-11-10T13:00:00Z',form:'6-K'}).status,'scheduled');
});
test('a new live financial need is not starved by unseen bulk-universe seeds and still respects backoff',()=>{
 const jobs={LICN:{cik:'1876766',priority:200,last_attempt:'2026-11-09',last_signal:'new-primary-disclosure',next_attempt:0},bulk:{cik:'123',priority:200,next_attempt:0}};
 assert.equal(nextFinancialJob(jobs,100).cik,'1876766');jobs.LICN.next_attempt=200;assert.equal(nextFinancialJob(jobs,100).cik,'123');
});
test('older dashboard needs cannot overwrite a newer reviewed request or reset its retry clock repeatedly',()=>{
 const queue={jobs:{'1780652':{cik:'1780652',priority:50,next_attempt:123}}},old=JSON.stringify({first_seen_at:'2026-11-10T12:48:52Z'}),review=JSON.stringify({request_kind:'reviewed_primary_recovery',repair_requested_at:'2026-11-10T17:40:00Z'});
 assert.equal(applyFinancialNeed(queue,'1780652',old),true);assert.equal(applyFinancialNeed(queue,'1780652',review),true);assert.equal(queue.jobs['1780652'].priority,2000);queue.jobs['1780652'].next_attempt=999;assert.equal(applyFinancialNeed(queue,'1780652',old),false);assert.equal(applyFinancialNeed(queue,'1780652',review),false);assert.equal(queue.jobs['1780652'].next_attempt,999);
 assert.equal(applyFinancialNeed(queue,'1780652',JSON.stringify({first_seen_at:'2026-11-10T18:00:00Z'})),true);
});
test('reviewed financial batches preserve requested order and bind issuer, accession, source digest and disclosure clock',()=>{
 const source={cik:'1780652',accession:'0001104659-26-107048',url:'https://www.sec.gov/Archives/edgar/data/1780652/000110465926107048/0001104659-26-107048.txt',source_sha256:'a'.repeat(64),form:'6-K',filed:'2026-09-11',published_at:'2026-09-12T04:00:00Z'},second={...source,accession:'0001104659-25-087782',url:'https://www.sec.gov/Archives/edgar/data/1780652/000110465925087782/0001104659-25-087782.txt'};
 assert.deepEqual(requestedFinancialSources({sources:[source,second]},'1780652').map(r=>r.accession),[source.accession,second.accession]);
 for(const wrong of [{...source,cik:'123'},{...source,url:source.url.replace('/1780652/','/123/')},{...source,source_sha256:null},{...source,published_at:'unknown'}])assert.throws(()=>requestedFinancialSources({sources:[wrong]},'1780652'),/identity|provenance/);
 assert.throws(()=>requestedFinancialSources({sources:Array(9).fill(source)},'1780652'),/count/);
});
test('a primary consolidated total can resolve an API concept-priority ambiguity only with matching filed tagged evidence',()=>{
 const cik='1876766',annual={start:'2025-01-01',end:'2025-12-31',form:'20-F',filed:'2026-04-28'};
 const raw={cik,facts:{'us-gaap':{
  Revenues:{units:{USD:[{...annual,val:809000}]}},
  RevenueFromContractWithCustomerIncludingAssessedTax:{units:{USD:[{...annual,val:24518000}]}}
 }}};
 const fact={cik,metric:'revenues',value:24518000,start:annual.start,end:annual.end,currency:'USD',form:'20-F',filed:annual.filed,published_at:'2026-04-28T12:00:00Z',observed_at:'2026-11-10T14:00:00Z',source_url:'https://www.sec.gov/Archives/edgar/data/1876766/report.htm',source_sha256:'a'.repeat(64),locator:'Consolidated statement of operations, Total revenues',original_label:'Total revenues',kind:'html_table',scope:'consolidated',confidence:'verified',statement_total:true};
 const p=buildFinancialProfile({cik,companyfacts:raw,facts:[fact],as_of:'2026-11-10T15:00:00Z'});assert.equal(p.coverage.metrics.revenues.value,24518000);assert.equal(p.coverage.conflicts.length,0);
 const wrong=buildFinancialProfile({cik,companyfacts:raw,facts:[{...fact,value:999999}],as_of:'2026-11-10T15:00:00Z'});assert.ok(wrong.coverage.conflicts.length);
});

import {retainFinancialProfile,MAX_RETAINED_FINANCIAL_PROFILES,installFinancialImport} from './reverse-split-live/financials-import.mjs';
test('broad imports retain bounded raw filings while compact scores and version receipts survive eviction',()=>{
 const env={};installFinancialImport(env);
 for(let i=0;i<MAX_RETAINED_FINANCIAL_PROFILES*5;i++){const id=String(i);retainFinancialProfile(env,id,{profile:{version:id},raw:{large:'primary history'},facts:[]});env.financialProfileVersions.set(id,id);env.financialScoreCache.set(id,{schema:'test'});}
 assert.equal(env.financialProfiles.size,MAX_RETAINED_FINANCIAL_PROFILES);assert.equal(env.financialProfiles.has('0'),false);assert.equal(env.financialProfileVersions.get('0'),'0');assert.ok(env.financialScoreCache.has('0'));
});

import {FINANCIAL_EVIDENCE_REVISION} from './reverse-split-live/financials-import.mjs';
import {FINANCIAL_VERSION} from './reverse-split-live/financials-core.mjs';
test('handoffs cannot reuse an old numeric score under a newly repaired evidence calculation',async t=>{
 const db=new DatabaseSync(':memory:');db.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT)');t.after(()=>db.close());const now=new Date().toISOString(),saved={schema:FINANCIAL_VERSION,cik:'1876766',computed_at:now,score:{score:66.7,period:new Date(Date.now()-120*86400000).toISOString().slice(0,10),source_profile_version:'a'.repeat(64)}};
 db.prepare('INSERT INTO rs_state VALUES(?,?,?)').run('financial_score_cache:1876766',JSON.stringify(saved),now);const env={DB:localAdapter(db)};installFinancialImport(env);await env.restoreFinancialScores();assert.equal(env.scoreFinancialProfile('1876766',now),null);assert.equal(env.financialProfileVersions.has('1876766'),false);assert.deepEqual(JSON.parse(db.prepare('SELECT value FROM rs_state').get().value),saved);
 saved.calculation_revision=FINANCIAL_EVIDENCE_REVISION;saved.score.score=75;db.prepare('UPDATE rs_state SET value=?').run(JSON.stringify(saved));await env.restoreFinancialScores();assert.equal(env.scoreFinancialProfile('1876766',now).score,75);assert.equal(env.financialProfileVersions.get('1876766'),'a'.repeat(64));
});
