// Node-only, explicitly pinned, read-only captures of public primary sources.
// A late archive repairs coverage, never the original news-to-trade clock.
import {readFileSync,realpathSync,existsSync} from 'node:fs';
import {dirname,resolve,relative,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import {sourceURL,enqueue,consume} from './worker.mjs';
import {publisherInventory} from './publisher-inventory.mjs';
import {publisherArchiveURL} from './publisher-recovery.mjs';
const digest=b=>createHash('sha256').update(b).digest('hex');
const encoded=value=>new TextEncoder().encode(JSON.stringify(value));
const clock=value=>{if(typeof value!=='string'||!Number.isFinite(Date.parse(value))||!/(?:Z|[+-]\d\d:\d\d)$/.test(value))throw new Error('Recovery capture clock missing');return Date.parse(value);};
export function openRecoveryBundle(file,{expectedSha256}={}){
 const bytes=readFileSync(file);if(bytes.length>2*1024*1024||!expectedSha256||digest(bytes)!==expectedSha256)throw new Error('Recovery manifest hash or size mismatch');
 const manifest=JSON.parse(bytes),root=realpathSync(dirname(file)),documents=new Map();
 if(manifest.schema!=='reverse_split_recovery_bundle.v1'||!Array.isArray(manifest.documents)||manifest.documents.length>2000)throw new Error('Unsupported recovery manifest');
 for(const row of manifest.documents){const url=sourceURL(row.url).href;if(documents.has(url)||!row.path||isAbsolute(row.path)||!/^([a-f0-9]{64})$/.test(row.sha256)||!Number.isInteger(row.bytes)||row.bytes<1||row.bytes>24*1024*1024)throw new Error('Invalid recovery document identity');clock(row.retrieved_at);documents.set(url,row);}
 const read=url=>{
  const row=documents.get(url);if(!row)return null;
  const path=realpathSync(resolve(root,row.path)),rel=relative(root,path);if(rel.startsWith('..')||isAbsolute(rel))throw new Error('Recovery path escapes bundle');
  const bytes=readFileSync(path);if(bytes.length!==row.bytes||digest(bytes)!==row.sha256)throw new Error('Recovery document hash or size mismatch');
  return {...row,bytes};
 };
 return {manifest,sha256:expectedSha256,read,fetchDocument:async(url,{maximum=24*1024*1024}={})=>{const u=sourceURL(url);if(u.search||!(u.hostname==='www.prnewswire.com'&&/\/news-releases\/.+\.html$/.test(u.pathname)||u.hostname==='www.sec.gov'&&u.pathname.startsWith('/Archives/edgar/data/')))return null;const doc=read(url);if(doc&&doc.bytes.length>maximum)throw new Error('Source exceeds document size limit');return doc;}};
}
const releaseId=value=>{const u=sourceURL(value);return u.hostname==='www.prnewswire.com'&&!u.search&&!u.hash?/\/news-releases\/.+-(\d{9,10})\.html$/.exec(u.pathname)?.[1]:null;};
function verifyArticle(bundle,item){
 const doc=bundle.read(item.url);if(!doc)throw new Error('Recovery article body missing');
 const text=new TextDecoder().decode(doc.bytes),canonical=[...text.matchAll(/<link\b[^>]*rel=["']canonical["'][^>]*href=["']([^"']+)/gi)].map(m=>m[1]),og=/<meta\b[^>]*property=["']og:url["'][^>]*content=["']([^"']+)/i.exec(text)?.[1],identity=canonical[0]||og;
 if(canonical.length>1||!identity||!releaseId(item.url)||releaseId(identity)!==releaseId(item.url))throw new Error('Recovery article identity mismatch');
 const dates=new Set([...text.matchAll(/"datePublished"\s*:\s*"([^"\r\n]+)"/g)].map(m=>m[1]));
 if(dates.size!==1||Math.floor(clock([...dates][0])/60000)!==Math.floor(clock(item.published_at)/60000)||!/<section\b[^>]*class=["'][^"']*\brelease-body\b/i.test(text))throw new Error('Recovery article publication or primary body mismatch');
 return doc;
}
async function archive(env,doc){
 env.assertCollectorLease?.();const key='documents/'+doc.sha256;await env.EVIDENCE.put(key,doc.bytes,{httpMetadata:{contentType:doc.content_type||'application/octet-stream'}});
 await env.DB.prepare('INSERT OR IGNORE INTO rs_documents(sha256,url,object_key,captured_at,bytes,content_type) VALUES(?,?,?,?,?,?)').bind(doc.sha256,doc.url,key,doc.retrieved_at,doc.bytes.length,doc.content_type||'application/octet-stream').run();return key;
}
export async function reconcileUnavailableFiling(env,bundle,{now=new Date().toISOString()}={}){
 // One reviewed stale reference, not a policy for suppressing arbitrary 404s.
 const oldId='history-filing:0001214659-24-016464',newId='history-filing:0001214659-24-016539',metadataURL='https://data.sec.gov/submissions/CIK0000896493.json';
 if(!bundle.manifest.reconcile_unavailable_filing)return {reconciled:0};
 const row=await env.DB.prepare('SELECT * FROM rs_jobs WHERE id=?').bind(oldId).first();if(!row||row.state==='superseded')return {reconciled:0};
 const later=await env.DB.prepare('SELECT * FROM rs_jobs WHERE id=?').bind(newId).first(),doc=bundle.read(metadataURL);if(!doc)throw new Error('Official submissions evidence missing');
 const sub=JSON.parse(new TextDecoder().decode(doc.bytes)),recent=sub.filings?.recent,p=JSON.parse(row.payload),q=later?JSON.parse(later.payload):{};
 const canonical=recent?.accessionNumber?.indexOf('0001214659-24-016539'),dates=recent?.filingDate||[];
 if(row.state!=='failed'||row.error!=='Source returned HTTP 404'||p.cik!=='896493'||p.accession!=='0001214659-24-016464'||p.published_at!=='2024-09-18T04:00:00.000Z'||String(Number(sub.cik))!=='896493'||!recent||recent.accessionNumber.includes(p.accession)||!(canonical>=0)||recent.filingDate[canonical]!=='2024-09-17'||recent.form[canonical]!=='8-K/A'||recent.primaryDocument[canonical]!=='o9172438ka2.htm'||!dates.some(d=>d<'2024-09-17')||!dates.some(d=>d>'2024-09-17')||recent.form.filter((f,i)=>f==='8-K/A'&&dates[i]==='2024-09-17').length!==1||later?.state!=='complete'||q.cik!==p.cik||q.accession!=='0001214659-24-016539'||q.published_at!==p.published_at)throw new Error('Unavailable filing reconciliation evidence or completed canonical job mismatch');
 const canonicalURL='https://www.sec.gov/Archives/edgar/data/896493/000121465924016539/0001214659-24-016539.txt';
 if(q.url!==canonicalURL)throw new Error('Canonical filing URL mismatch');
 const archived=await env.DB.prepare('SELECT sha256,object_key FROM rs_documents WHERE url=? ORDER BY captured_at DESC LIMIT 1').bind(canonicalURL).first();if(!archived)throw new Error('Completed canonical filing has no archived primary bytes');
 const metadataKey=await archive(env,doc),proof={schema:'reverse_split_unavailable_reference_reconciliation.v1',recorded_at:now,original_job:row,official_submissions:{url:metadataURL,sha256:doc.sha256,object_key:metadataKey},current_official_job:later,current_official_document:archived,action:'retire_unavailable_reference_current_official_same_day_amendment_already_processed',limitations:['Original unavailable accession bytes were not recovered.','This does not assert the unavailable submission and the current official amendment were byte-identical.','No historical signal, clock, fill or decision is changed.']};
 const bytes=encoded(proof),key='review/repairs/'+digest(bytes)+'.json';await env.EVIDENCE.put(key,bytes,{httpMetadata:{contentType:'application/json'}});env.assertCollectorLease?.();
 await env.DB.prepare("UPDATE rs_jobs SET state='superseded',error=?,updated_at=? WHERE id=? AND state='failed' AND updated_at=?").bind('Unavailable reference retained in '+key+'; current official amendment already archived and complete',now,row.id,row.updated_at).run();return {reconciled:1,proof:key};
}
export async function installRecoveryBundle(env,bundle,{now=new Date().toISOString()}={}){
 const marker='repair:public_capture:'+bundle.sha256;if(await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(marker).first())return {already_installed:true};
 env.assertCollectorLease?.();const input=bundle.manifest.publisher,plans=[];clock(now);
 if(input){
  if(input.source!=='prnewswire'||!Array.isArray(input.pages)||!input.pages.length||input.pages.length>120||!Array.isArray(input.gaps)||input.gaps.length>100)throw new Error('Invalid bounded recovery inventory');
  const pages=input.pages.map((p,i)=>{if(p.page!==i+1||p.url!==publisherArchiveURL(input.source,p.page,'2026-11-20'))throw new Error('Recovery pagination is not contiguous');const doc=bundle.read(p.url);if(!doc)throw new Error('Recovery inventory page missing');return {page:p.page,doc,items:publisherInventory(new TextDecoder().decode(doc.bytes),input.source,p.url)};});
  if(new Set(pages.map(p=>p.doc.sha256)).size!==pages.length)throw new Error('Recovery pagination repeated');
  for(let i=1;i<pages.length;i++)if(clock(pages[i].items[0].published_at)>clock(pages[i-1].items[0].published_at)||clock(pages[i].items.at(-1).published_at)>clock(pages[i-1].items.at(-1).published_at))throw new Error('Recovery pagination order changed');
  for(const wanted of input.gaps){
   const gap=await env.DB.prepare('SELECT * FROM rs_source_gaps WHERE id=?').bind(wanted.id).first();if(!gap||gap.source_id!==input.source||gap.start_at!==wanted.start_at||gap.end_at!==wanted.end_at)throw new Error('Recovery interval identity mismatch');if(gap.resolved_at)continue;
   const start=clock(gap.start_at)-60000,end=clock(gap.end_at)+60000,lower=pages.findIndex(p=>clock(p.items.at(-1).published_at)<start);
   if(clock(pages[0].items[0].published_at)<end-120000||lower<0||clock(pages[0].items[0].published_at)>clock(now)+2000)throw new Error('Recovery inventory did not cross both bounds');
   const used=pages.slice(0,lower+1),items=[...new Map(used.flatMap(p=>p.items).filter(r=>clock(r.published_at)>=start&&clock(r.published_at)<=end).map(r=>[r.url,r])).values()];for(const item of items)verifyArticle(bundle,item);
   const previous=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind('publisher_recovery:'+gap.id).first();plans.push({gap,used,items,previous:previous?JSON.parse(previous.value):null});
  }
  // All hashes, inventory bounds and required bodies validated before any state change.
  const unique=new Map(plans.flatMap(p=>p.used).map(p=>[p.doc.url,p]));for(const p of unique.values())await archive(env,p.doc);
  for(const plan of plans){
   const items=[];for(const item of plan.items){const job_id='publisher-article:v2:'+digest(item.url);await enqueue(env,'news',{...item,first_seen_at:now,discovery_path:'publisher_archive_catchup',publication_clock:'timestamp',recovery_gap_id:plan.gap.id,recovery_bundle_sha256:bundle.sha256},9,job_id);items.push({...item,job_id});}
   const state={version:'public_inventory.v2',page:plan.used.length+1,attempts:0,pages:plan.used.map(p=>({page:p.page,url:p.doc.url,sha256:p.doc.sha256,object_key:'documents/'+p.doc.sha256,newest:p.items[0].published_at,oldest:p.items.at(-1).published_at,count:p.items.length,observed_at:p.doc.retrieved_at})),items,upper_bound_observed:true,inventory_complete:true,coverage_complete:false,status:'awaiting_archived_article_analysis',pending_bodies:items.length,observed_at:now,next_attempt:now,previous_recovery:plan.previous,recovery_bundle_sha256:bundle.sha256};
   await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind('publisher_recovery:'+plan.gap.id,JSON.stringify(state),now).run();
  }
 }
 const reconciliation=await reconcileUnavailableFiling(env,bundle,{now});
 const proof={schema:'reverse_split_recovery_capture_install.v1',installed_at:now,manifest:bundle.manifest,manifest_sha256:bundle.sha256,gaps_still_require_archived_body_jobs:plans.map(p=>p.gap.id),...reconciliation},bytes=encoded(proof);await env.EVIDENCE.put('review/repairs/'+digest(bytes)+'.json',bytes,{httpMetadata:{contentType:'application/json'}});
 env.assertCollectorLease?.();await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(marker,JSON.stringify({at:now,gaps:plans.length,...reconciliation}),now).run();return {installed:true,gaps:plans.length,...reconciliation};
}

// The operator can deliver a completed immutable capture without another service
// restart. Only the current collector applies it, under its existing writer lease.
export async function installRequestedRecovery(env,{file=process.env.RS_RECOVERY_REQUEST,now=new Date().toISOString()}={}){
 if(!file||!existsSync(file))return {requested:false};const raw=readFileSync(file);if(raw.length>4096)throw new Error('Recovery request exceeds size limit');
 const request=JSON.parse(raw);if(request.schema!=='reverse_split_recovery_request.v1'||!isAbsolute(request.manifest)||!/^([a-f0-9]{64})$/.test(request.sha256))throw new Error('Invalid pinned recovery request');
 if(env.appliedRecoveryRequestSha===request.sha256)return {already_installed:true};
 const bundle=openRecoveryBundle(request.manifest,{expectedSha256:request.sha256}),result=await installRecoveryBundle(env,bundle,{now});
 env.recoveryBundle=bundle;env.recoveryDocument=bundle.fetchDocument;env.appliedRecoveryRequestSha=request.sha256;return result;
}

export async function drainRecoveryBodies(env,{maxJobs=4,maximumMs=3000,shouldStop=()=>false}={}){
 const pin=env.recoveryBundle?.sha256;if(!pin)return {jobs:0};const started=Date.now();let jobs=0;
 while(jobs<Math.min(4,Math.max(1,maxJobs))&&Date.now()-started<Math.min(5000,Math.max(1,maximumMs))&&!shouldStop()){
  env.assertCollectorLease?.();const at=Date.now();
  const urgent=await env.DB.prepare("SELECT id FROM rs_jobs WHERE priority>=10 AND kind IN ('filing','news') AND coalesce(json_extract(payload,'$.first_seen_at'),created_at)>=? AND ((state='pending' AND available_at<=?) OR (state IN ('queued','running') AND lease_until>?)) LIMIT 1").bind(new Date(at-900000).toISOString(),at,at).first();if(urgent)break;
  // The same in-process writer and existing token-checked job consumer. Never
  // share the main loop's outbound queue or open a second SQLite writer.
  const token=crypto.randomUUID(),row=await env.DB.prepare("UPDATE rs_jobs SET state='queued',token=?,lease_until=?,updated_at=? WHERE id=(SELECT id FROM rs_jobs WHERE state='pending' AND kind='news' AND priority<10 AND available_at<=? AND json_extract(payload,'$.recovery_bundle_sha256')=? ORDER BY created_at,id LIMIT 1) AND state='pending' RETURNING id").bind(token,at+600000,new Date(at).toISOString(),at,pin).first();if(!row)break;
  await consume({messages:[{body:{id:row.id,token},ack(){}}]},{...env,deadline:Date.now()+25000});jobs++;
 }
 return {jobs};
}
