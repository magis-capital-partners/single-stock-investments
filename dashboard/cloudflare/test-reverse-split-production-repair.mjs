import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {classifyAnnouncement} from './reverse-split-live/core.mjs';
import {recordEvent} from './reverse-split-live/worker.mjs';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {makeDatabentoMarket} from './reverse-split-live/databento-market.mjs';
import {EXECUTION_POLICIES,DELAY_EXECUTION_POLICIES,BROAD_EXECUTION_POLICIES,brokerGates} from './reverse-split-live/execution-core.mjs';
import {signalGate} from './reverse-split-live/shadow-core.mjs';
import {initializeExecution,enrollExecution} from './reverse-split-live/execution-service.mjs';
import {financialDisclosureGap} from './reverse-split-live/disclosure-gaps.mjs';
import {financialAssessment} from './reverse-split-live/financial-assessment.mjs';
import {repairNewsBindingFailures,consume,SOURCES,sha,replayAnnouncement} from './reverse-split-live/worker.mjs';
import {installFinancialImport} from './reverse-split-live/financials-import.mjs';
import {FINANCIAL_VERSION} from './reverse-split-live/financials-core.mjs';

test('broader portfolios differ only by explicit threshold and comparison identity',()=>{
 const originals=[...EXECUTION_POLICIES,...DELAY_EXECUTION_POLICIES];assert.equal(BROAD_EXECUTION_POLICIES.length,32);
 for(const broad of BROAD_EXECUTION_POLICIES){const original=originals.find(p=>p.id===broad.threshold_comparison_parent),{id,label,minimum_score,threshold_group,threshold_comparison_parent,...rest}=broad;assert.deepEqual({...rest,id:original.id,label:original.label,minimum_score:60},original);assert.equal(minimum_score,0);assert.equal(threshold_group,'all_scoreable');}
 const now='2026-11-11T15:00:00Z',e={ticker:'QA',cik:'123',status:'scheduled',ordinal_min:2,effective_date:'2026-11-20',financials:{score:34,signal_count:5,period:'2026-06-30'}};
 assert.equal(signalGate(e,EXECUTION_POLICIES[0],now).reason,'score_below_threshold');assert.equal(signalGate(e,BROAD_EXECUTION_POLICIES[0],now).state,'eligible');
 for(const f of [{score:null,signal_count:5,period:'2026-06-30'},{score:34,signal_count:2,period:'2026-06-30'},{score:34,signal_count:5,period:'2025-09-30'}])for(const p of [EXECUTION_POLICIES[0],BROAD_EXECUTION_POLICIES[0]])assert.equal(signalGate({...e,financials:f},p,now).state,'waiting');
 assert.ok(brokerGates([],now).reasons.includes('ibkr_locate_approval_missing'));
});

test('new portfolio registration preserves originals and cannot backdate old detections',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());const env={DB:localAdapter(db)};
 await initializeExecution(env,'2026-11-11T20:00:00Z');const e={id:'old',first_seen_at:'2026-11-11T19:00:00Z',cik:'123',ticker:'QA',company:'QA'};await enrollExecution(env,e,'2026-11-11T20:00:01Z');
 for(const row of db.prepare('SELECT payload FROM rs_execution_tracks').all()){const track=JSON.parse(row.payload);assert.equal(track.state,'retrospective');assert.equal(track.entry_shares,0);}
 for(const p of EXECUTION_POLICIES)assert.deepEqual(JSON.parse(db.prepare('SELECT payload FROM rs_execution_policies WHERE id=?').get(p.id).payload),p);
});

test('source-backed delinquency is a data gap, never a financial fact or low-score rejection',()=>{
 const gap=financialDisclosureGap(new TextEncoder().encode('The Company has not timely filed its Annual Report on Form 10-K for 2025 and Quarterly Reports for March and June 2026.'),{url:'https://www.sec.gov/Archives/example.htm',sha256:'a'.repeat(64),published_at:'2026-10-09T13:30:12Z'},'2026-11-11T20:00:00Z');assert.ok(gap);assert.equal(gap.financial_facts_created,false);
 const missing=financialAssessment({financials:{score:null,signal_count:0,period:'2025-09-30',disclosure_gaps:[gap]}});assert.equal(missing.status,'missing_data');assert.match(missing.reason,/overdue/);assert.equal(financialAssessment({financials:{score:34,signal_count:5,disclosure_gaps:[gap]}}).status,'financial_rejection');
});

test('exact failed news jobs are archived before a one-time retry',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
 const columns=db.prepare('PRAGMA table_info(rs_jobs)').all().map(c=>c.name);assert.ok(columns.includes('error'));
 db.prepare("INSERT INTO rs_jobs(id,kind,payload,state,priority,created_at,updated_at,available_at,attempts,error) VALUES('news:qa','news','{}','failed',15,'2026-11-11','2026-11-11',0,6,'Provided value cannot be bound to SQLite parameter 2')").run();let archive;
 const env={DB:localAdapter(db),EVIDENCE:{put:async(k,b)=>{assert.equal(db.prepare("SELECT state FROM rs_jobs WHERE id='news:qa'").get().state,'failed');archive=JSON.parse(new TextDecoder().decode(b));}}};await repairNewsBindingFailures(env);assert.equal(archive.original_jobs[0].attempts,6);assert.equal(db.prepare("SELECT state FROM rs_jobs WHERE id='news:qa'").get().state,'pending');await repairNewsBindingFailures(env);
});

test('publisher-blocked news completes detection while its incomplete primary body stays blocked',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
 const publisher=SOURCES.find(s=>s.id==='businesswire'),p={title:'QA announces reverse stock split',excerpt:'QA (NASDAQ: QA) announced a reverse stock split. The final date remains unresolved.',url:'https://www.businesswire.com/news/home/qa',primary_publisher:publisher.id,primary_feed_url:publisher.url,published_at:'2026-11-11T14:00:00Z',first_seen_at:'2026-11-11T14:05:00Z'};
 db.prepare("INSERT INTO rs_jobs(id,kind,payload,state,priority,created_at,updated_at,token) VALUES('news:qa','news',?,'queued',15,'2026-11-11','2026-11-11','test-token')").run(JSON.stringify(p));const objects=new Map(),env={DB:localAdapter(db),SEC_USER_AGENT:'offline-test',EVIDENCE:{put:async(k,b)=>objects.set(k,b),get:async()=>null}};
 const old=globalThis.fetch;globalThis.fetch=async u=>String(u).endsWith('company_tickers.json')?Response.json({0:{cik_str:123,ticker:'QA'}}):new Response('blocked',{status:403});t.after(()=>globalThis.fetch=old);
 await consume({messages:[{body:{id:'news:qa',token:'test-token'},ack(){}}]},env);assert.equal(db.prepare("SELECT state FROM rs_jobs WHERE id='news:qa'").get().state,'complete');const e=JSON.parse(db.prepare('SELECT payload FROM rs_events').get().payload);assert.equal(e.cik,'123');assert.equal(e.primary_content_complete,false);assert.equal(e.status,'needs_review');assert.equal(e.first_seen_at,p.first_seen_at);
});

test('reviewed filing-gap evidence is checksum-bound and does not manufacture a current score',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
 const cik='123',version='a'.repeat(64),ledger={schema:FINANCIAL_VERSION,cik,source_profile_version:version,facts:[]},factsKey='financials/facts/'+cik+'/'+version+'.json',profile={schema:FINANCIAL_VERSION,cik,version,facts_object_key:factsKey,facts_sha256:await sha(JSON.stringify(ledger)),sources:[],collection:{api_source_sha256:null},coverage:{instrument:{type:'CS'}}};
 const bytes=new TextEncoder().encode('The issuer has not timely filed its Annual Report on Form 10-K for 2025.'),digest=await sha(bytes),source={cik,url:'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/a.htm',sha256:digest,published_at:'2026-10-09T13:30:00Z'};db.prepare('INSERT INTO rs_state VALUES(?,?,?)').run('reviewed_disclosure_source:'+cik,JSON.stringify(source),new Date().toISOString());
 const objects=new Map([['financials/profiles/'+cik+'/latest.json',JSON.stringify(profile)],[factsKey,JSON.stringify(ledger)],['documents/'+digest,bytes]]),env={DB:localAdapter(db),EVIDENCE:{get:async k=>objects.has(k)?{json:async()=>JSON.parse(objects.get(k)),arrayBuffer:async()=>objects.get(k).slice().buffer}:null}};installFinancialImport(env);await env.ensureFinancialProfile(cik);const score=env.scoreFinancialProfile(cik,new Date().toISOString());assert.equal(score.score,null);assert.equal(score.disclosure_gaps[0].source_sha256,digest);
 objects.set('documents/'+digest,new Uint8Array([1,2,3]));const corrupt={...env};installFinancialImport(corrupt);await assert.rejects(corrupt.ensureFinancialProfile(cik),/checksum/);
});

test('an amendment repair uses its current publication while retaining original detection clocks',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
 const bytes=new TextEncoder().encode('The Board approved a stock split ratio of 1-for-20. The Reverse Stock Split will be effective on November 13, 2026, and the Certificate of Amendment will be effective on November 12, 2026.'),hash=await sha(bytes),event={id:'amended',cik:null,ticker:null,status:'needs_review',effective_date:null,published_at:'2026-11-10T13:00:00Z',latest_publication_at:'2026-11-11T13:00:00Z',first_seen_at:'2026-11-10T13:00:01Z',sources:[{url:'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/a.txt',sha256:'b'.repeat(64),representation:'complete_submission',form:'8-K'},{url:'https://www.sec.gov/Archives/edgar/data/123/000000012326000002/a.txt',sha256:hash,representation:'complete_submission',form:'8-K/A'}]};
 db.prepare('INSERT INTO rs_events(id,first_seen_at,payload) VALUES(?,?,?)').run(event.id,event.first_seen_at,JSON.stringify(event));const env={DB:localAdapter(db),EVIDENCE:{get:async k=>k==='documents/'+hash?{arrayBuffer:async()=>bytes.slice().buffer}:null,put:async()=>{}}};await replayAnnouncement(env,event.id);const current=JSON.parse(db.prepare('SELECT payload FROM rs_events').get().payload);assert.equal(current.status,'scheduled');assert.equal(current.effective_date,'2026-11-13');assert.equal(current.legal_effective_date,'2026-11-12');assert.equal(current.published_at,event.published_at);assert.equal(current.first_seen_at,event.first_seen_at);assert.equal(current.sources.length,2);
});

test('a detected issuer announcement with unresolved terms persists before enrichment',async t=>{
 const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
 const event={id:'publisher-unresolved',cik:'123',ticker:'QA',company:'QA',status:'needs_review',published_at:'2026-11-11T14:00:00Z',first_seen_at:'2026-11-11T14:05:02.319Z',sources:[]};let detected=0;
 const env={DB:localAdapter(db),onAnnouncementDetection:async()=>detected++,EVIDENCE:{get:async()=>null},SEC_USER_AGENT:'offline-test',fetch:async()=>{throw new Error('offline');}};
 const before=globalThis.fetch;globalThis.fetch=async()=>{throw new Error('offline');};t.after(()=>{globalThis.fetch=before;});
 await recordEvent(env,event);assert.ok(db.prepare('SELECT id FROM rs_events WHERE id=?').get(event.id));assert.ok(detected>0);
});

test('selected action keeps separate legal and split-adjusted trading dates',()=>{
 const text='The Board approved a reverse stock split of 1-for-40. The Reverse Stock Split is expected to become effective on November 20, 2026. The shares are expected to begin trading on a split-adjusted basis on November 23, 2026, subject to NYSE American approval.';
 const result=classifyAnnouncement(text,{published_at:'2026-11-11T17:30:00Z'});
 assert.equal(result.status,'scheduled');assert.equal(result.ratio,40);assert.equal(result.effective_date,'2026-11-20');assert.equal(result.trading_date,'2026-11-23');
});

test('a legal afternoon effective time does not hide the next trading date or exchange condition',()=>{
 const result=classifyAnnouncement('The board approved a 1-for-19 reverse stock split. The Reverse Split will legally take effect at 4:01 p.m. Eastern Time, on November 12, 2026. The common stock will open for trading on November 13, 2026, on a split-adjusted basis.',{published_at:'2026-11-11T14:00:00Z'});assert.equal(result.ratio,19);assert.equal(result.legal_effective_date,'2026-11-12');assert.equal(result.trading_date,'2026-11-13');
 const conditional=classifyAnnouncement('The board approved a 1-for-40 reverse stock split. The reverse stock split is effective on November 20, 2026, subject to NYSE American approval.',{published_at:'2026-11-11T17:30:00Z'});assert.ok(conditional.implementation_conditions.length);assert.equal(signalGate({...conditional,cik:'123',ticker:'QA',ordinal_min:2},BROAD_EXECUTION_POLICIES[0],'2026-11-11T18:00:00Z').reason,'implementation_conditions_unresolved');
});

test('an old-shares-for-new-shares selected ratio overrides an earlier authorization range',()=>{
 const text='Shareholders approved a consolidation range of 2 to 1000 shares. The Company will implement a share consolidation of eight (8) ordinary shares into one (1) ordinary share, effective on November 16, 2026. Its prior 25-for-1 reverse stock split took effect September 17, 2026.';
 const result=classifyAnnouncement(text,{published_at:'2026-11-10T15:00:01Z'});
 assert.equal(result.status,'scheduled');assert.equal(result.ratio,8);assert.equal(result.effective_date,'2026-11-16');
});

test('a stopped quote helper is restarted and all selected subscriptions are restored',t=>{
 let now='2026-11-11T15:00:00Z';const children=[];
 const market=makeDatabentoMarket({key:'offline-test',clock:()=>now,reference:{identity:async()=>({})},spawnProcess:()=>{const c=new EventEmitter();c.stdin=new PassThrough();c.stdout=new PassThrough();c.stderr=new PassThrough();c.kill=()=>{};c.commands='';c.stdin.on('data',b=>c.commands+=b.toString());children.push(c);return c;}});t.after(()=>market.close());
 market.warm('QA');assert.equal(children.length,1);children[0].emit('exit',3);children[0].emit('close',3);now='2026-11-11T15:00:05Z';market.warm('QA');assert.equal(children.length,2);assert.match(children[1].commands,/QA/);
});

test('verified raw-symbol mapping can identify a common share without inventing a FIGI',async t=>{
 const now='2026-11-11T15:00:00Z';let c;
 const market=makeDatabentoMarket({key:'offline-test',clock:()=>now,reference:{health:{quote_access:'not_entitled'},identity:async ticker=>({ticker,cik:'123',type:'CS',currency:'usd',active:true,security_id:null,source_url:'https://api.massive.com/v3/reference/tickers/QA',observed_at:now})},spawnProcess:()=>{c=new EventEmitter();c.stdin=new PassThrough();c.stdout=new PassThrough();c.stderr=new PassThrough();c.kill=()=>{};return c;}});t.after(()=>market.close());
 market.warm('QA');await market.verifyIdentity('QA');const row={kind:'quote',ticker:'QA',dataset:'EQUS.MINI',schema:'mbp-1',quote_at:now,observed_at:now,bid:10,ask:10.1,bid_size:100,ask_size:200,flags:0,instrument_id:12345,mapping_verified:true,raw_symbol:'QA'};
 c.stdout.write(JSON.stringify({...row,mapping_verified:false})+'\n');await assert.rejects(market.quote('QA',{quote_feed:'databento_mini'}),/identity/);
 c.stdout.write(JSON.stringify(row)+'\n');const q=await market.quote('QA',{quote_feed:'databento_mini'});assert.equal(q.security_id,'databento:EQUS.MINI:12345');assert.equal(q.identity_basis,'exact_reference_ticker_CIK_type_and_live_raw_mapping');assert.equal(q.cik,'123');
});
