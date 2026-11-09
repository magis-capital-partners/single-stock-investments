#!/usr/bin/env node
// Independent, read-only public-document harvest. No broker, quote or NY4 access.
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';
import {appendFileSync,readFileSync} from 'node:fs';
import {remoteEnvironment,isolatedWriteFailure} from './collector.mjs';
import {FinancialSources,extractFiling,hash,primaryURL,isSourceCooldown} from './financials-io.mjs';
import {buildFinancialProfile,FINANCIAL_VERSION} from './financials-core.mjs';
import {etDay} from './core.mjs';
import {seedPreparedNeeds} from './financial-preparation.mjs';
import {loadFilingDocuments} from './filing-documents.mjs';
const now=()=>new Date().toISOString(),bytes=v=>new TextEncoder().encode(JSON.stringify(v));
const PARSER_HASH=hash(Buffer.concat(['fundamental_filing.py','filing-documents.mjs'].map(n=>readFileSync(new URL('./'+n,import.meta.url)))));
const coverageCard=p=>({cik:p.cik,ticker:p.ticker,company:p.company,observed_at:p.observed_at,version:p.version,status:p.coverage.status,period:p.coverage.period,age_days:p.coverage.age_days,score:p.policy_financials.score,available_score:p.coverage.available_score,signal_count:p.coverage.signal_count,verified_inputs:p.coverage.verified_inputs,required_inputs:p.coverage.required_inputs,collection_status:p.collection.status,pending_documents:p.collection.remaining_documents,conflicts:p.coverage.conflicts.length});
async function coverageCache(env){if(env.financialCoverageCards)return env.financialCoverageCards;const manifest=await read(env,'financials/manifest-latest.json');env.financialCoverageCards=new Map((manifest?.cards||[]).map(r=>[r.cik,r]));if(manifest&&!manifest.cards)for(const r of manifest.profiles||[]){const p=await read(env,`financials/profiles/${r.cik}/latest.json`);if(p)env.financialCoverageCards.set(r.cik,coverageCard(p));}return env.financialCoverageCards;}
const REPORT_FORMS=new Set(['10-K','10-K/A','10-Q','10-Q/A','20-F','20-F/A','40-F','40-F/A','6-K','6-K/A','8-K','8-K/A']);
export const nextFinancialJob=(jobs,at=Date.now())=>Object.values(jobs).filter(j=>Number(j.next_attempt||0)<=at).sort((a,b)=>Number(b.priority>=1000)-Number(a.priority>=1000)||Number(!b.last_attempt)-Number(!a.last_attempt)||b.priority-a.priority||String(a.last_attempt||'').localeCompare(String(b.last_attempt||'')))[0];
async function read(env,key,fallback=null){const o=await env.EVIDENCE.get(key);return o?await o.json():fallback;}
async function put(env,key,value){await env.EVIDENCE.put(key,bytes(value),{httpMetadata:{contentType:'application/json'}});}
function filingRows(sub,cik){const recent=sub.filings?.recent||sub,rows=[];for(let i=0;i<(recent.form||[]).length;i++){
  const form=recent.form[i],filed=recent.filingDate[i],acc=recent.accessionNumber[i];if(!REPORT_FORMS.has(form)||!/^\d{10}-\d{2}-\d{6}$/.test(acc||'')||!filed)continue;
  rows.push({form,filed,published_at:recent.acceptanceDateTime?.[i]||filed+'T23:59:59Z',report_end:recent.reportDate?.[i]||null,accession:acc,url:`https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${acc.replaceAll('-','')}/${acc}.txt`});
}return rows;}
async function vendorMeta(env,ticker,cik){
  const key=process.env.POLYGON_API_KEY||process.env.MASSIVE_API_KEY;if(!key||!ticker||!/^[A-Z][A-Z0-9.-]{0,11}$/.test(ticker))return null;
  const saved=await read(env,'financials/vendor-meta/'+ticker+'.json');if(saved&&Date.now()-Date.parse(saved.checked_at)<86400000)return saved;
  try{const response=await fetch('https://api.massive.com/v3/reference/tickers/'+encodeURIComponent(ticker),{headers:{authorization:'Bearer '+key},redirect:'error',signal:AbortSignal.timeout(8000)});if(!response.ok){await response.body?.cancel();return null;}const raw=await response.text();if(raw.length>300000)throw new Error();const r=JSON.parse(raw).results;if(!r||String(Number(r.cik))!==String(Number(cik)))return null;const result={cik:String(Number(cik)),type:r.type,homepage_url:r.homepage_url||null,checked_at:now(),source_url:'https://api.massive.com/v3/reference/tickers/'+ticker};await put(env,'financials/vendor-meta/'+ticker+'.json',result);return result;}catch{return null;}
}
async function vendorComparison(env,ticker){
  const key=process.env.POLYGON_API_KEY||process.env.MASSIVE_API_KEY;if(!key||!ticker)return {status:'not_configured'};
  const health=await read(env,'financials/vendor-health.json');if(health?.day===etDay(now())&&['not_entitled','rate_limited'].includes(health.status))return health;
  const rows=[];for(const statement of ['income-statements','balance-sheets','cash-flow-statements']){
    try{const url='https://api.massive.com/stocks/financials/v1/'+statement+'?tickers='+encodeURIComponent(ticker)+'&timeframe=annual&limit=3';const response=await fetch(url,{headers:{authorization:'Bearer '+key},redirect:'error',signal:AbortSignal.timeout(8000)});
      if(!response.ok){await response.body?.cancel();const status=[401,403].includes(response.status)?'not_entitled':response.status===429?'rate_limited':'unavailable';const result={day:etDay(now()),status,checked_at:now(),http_status:response.status,admitted_to_strategy:false};await put(env,'financials/vendor-health.json',result);return result;}
      const text=await response.text();if(text.length>1000000)throw new Error();const body=JSON.parse(text);rows.push({statement,records:body.results||[]});
    }catch{return {status:'unavailable',admitted_to_strategy:false};}
  }
  // Vendor zeros/restated history are comparison evidence, not filed zero facts.
  return {status:'available',checked_at:now(),admitted_to_strategy:false,missing_values_may_be_zero:true,statements:rows};
}
async function discoverIR(client,homepage,company){
  if(!homepage)return [];
  let home;try{home=new URL(homepage);primaryURL(home.href,[home.origin]);}catch{return [];}
  const out=[],seen=new Set(),pages=[home.href];
  for(let n=0;n<Math.min(pages.length,4);n++){
    const url=pages[n];if(seen.has(url))continue;seen.add(url);let doc;try{doc=await client.get(url,{origins:[new URL(url).origin],mutable:true,maximum:5000000});}catch{continue;}
    const text=doc.bytes.toString('utf8');
    for(const m of text.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]{0,700}?)<\/a>/gi)){
      let u;try{u=new URL(m[1].replaceAll('&amp;','&'),url);if(u.protocol!=='https:')continue;}catch{continue;}
      const label=m[2].replace(/<[^>]+>/g,' '),description=label+' '+u.pathname;
      if(/annual.{0,30}report|interim.{0,30}(?:report|result)|financial.{0,30}(?:statement|result|report)|quarter.{0,30}(?:report|result)|earnings.{0,20}release/i.test(description))out.push({url:u.href,form:'IR_RELEASE',filed:etDay(now()),published_at:now(),publication_basis:'first_observed_conservative',trusted_parent:url,origins:[u.origin]});
      else if(/investor.{0,20}relation|investors/i.test(description)&&pages.length<4&&u.hostname.replace(/^www\./,'')===home.hostname.replace(/^www\./,''))pages.push(u.href);
    }
  }
  return out.slice(0,12);
}
async function discoverReports(client,cik,sub){
  const cutoff=new Date(Date.now()-3*366*86400000).toISOString().slice(0,10),rows=filingRows(sub,cik);
  for(const f of (sub.filings?.files||[]).filter(x=>x.filingTo>=cutoff).slice(0,4))try{const doc=await client.get('https://data.sec.gov/submissions/'+f.name);rows.push(...filingRows(JSON.parse(doc.bytes),cik));}catch{}
  // Financial-text search finds foreign-interim exhibits among numerous 6-Ks.
  if(rows.some(r=>r.form.startsWith('6-K')))try{
    const url=new URL('https://efts.sec.gov/LATEST/search-index');url.search=new URLSearchParams({dateRange:'custom',startdt:cutoff,enddt:etDay(now()),ciks:String(Number(cik)),forms:'6-K',q:'"cash flows"',from:'0',size:'40'});
    const doc=await client.get(url.href,{mutable:true});for(const hit of JSON.parse(doc.bytes).hits?.hits||[]){const s=hit._source||{},acc=s.adsh||String(hit._id||'').split(':')[0],filed=s.file_date;if(/^\d{10}-\d{2}-\d{6}$/.test(acc)&&filed)rows.push({form:'6-K',filed,published_at:filed+'T23:59:59Z',report_end:s.period_of_report||null,accession:acc,financial_match:true,url:`https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${acc.replaceAll('-','')}/${acc}.txt`});}
  }catch{}
  const unique=new Map();for(const r of rows.filter(r=>r.filed>=cutoff))if(!unique.has(r.url)||r.financial_match)unique.set(r.url,r);
  return [...unique.values()].sort((a,b)=>Number(!!b.financial_match)-Number(!!a.financial_match)||Number(!b.form.startsWith('6-K')&&!b.form.startsWith('8-K'))-Number(!a.form.startsWith('6-K')&&!a.form.startsWith('8-K'))||b.filed.localeCompare(a.filed)).slice(0,120);
}
export async function harvestIssuer(env,job,{client=new FinancialSources(env),maximumDocuments=8,offline=false,extract=extractFiling}={}){
  const cik=String(Number(job.cik)),key='financials/work/'+cik+'.json',work=await read(env,key,{facts:[],sources:[],processed:{},candidates:[],issues:[],errors:{}});work.errors||={};
  if(work.parser_hash!==PARSER_HASH){Object.assign(work,{facts:[],processed:{},candidates:[],issues:[],errors:{},parser_hash:PARSER_HASH});}
  // Repair only documents that the earlier cooldown handling parked by mistake.
  for(const error of Object.values(work.errors))if(error.terminal&&isSourceCooldown(error)){error.terminal=false;error.attempts=0;error.next_attempt=0;}
  const subDoc=await client.get(`https://data.sec.gov/submissions/CIK${cik.padStart(10,'0')}.json`,{mutable:true}),sub=JSON.parse(subDoc.bytes);if(String(Number(sub.cik))!==cik)throw new Error('Financial issuer submissions mismatch');
  let companyDoc=null,companyfacts={cik,facts:{}};try{companyDoc=await client.get(`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik.padStart(10,'0')}.json`,{mutable:true});companyfacts=JSON.parse(companyDoc.bytes);if(String(Number(companyfacts.cik))!==cik)throw new Error('Financial Company Facts identity mismatch');}catch(e){companyDoc=null;companyfacts={cik,facts:{}};work.issues.push({reason:'companyfacts_unavailable_primary_filing_fallback',message:e.message});}
  let instrument=await vendorMeta(env,job.ticker,cik);const name=sub.name||job.company;
  if(!instrument&&/^(?:ProShares Trust|iShares Trust|Direxion Shares ETF|ETF Series Solutions|Exchange Traded Concepts Trust)\b/i.test(name||''))instrument={type:'FUND',source_url:`https://data.sec.gov/submissions/CIK${cik.padStart(10,'0')}.json`,basis:'verified_registered_fund_issuer_name'};
  const current=buildFinancialProfile({cik,companyfacts,as_of:now()});const currency=current.coverage.metrics.total_assets.currency||current.coverage.metrics.revenues.currency;
  const deferDiscovery=maximumDocuments===0&&(!instrument?.type||instrument.type==='CS');
  let reports=maximumDocuments===0?[]:[...await discoverReports(client,cik,sub),...(work.discovered||[])],processed=0;
  if(instrument?.type&&instrument.type!=='CS')reports=[];
  if(maximumDocuments>0&&(reports.length<5||current.coverage.status!=='current'))reports.push(...await discoverIR(client,instrument?.homepage_url,name));
  const requests=job.last_signal||(await env.DB.prepare("SELECT value FROM rs_state WHERE key=?").bind('financial_need:'+cik).first())?.value;
  if(requests)try{const signal=JSON.parse(requests);if(signal.url&&!reports.some(r=>r.url===signal.url))reports.unshift(signal);}catch{}
  for(const source of reports){
    if(work.processed[source.url]||work.errors[source.url]?.terminal||work.errors[source.url]?.next_attempt>Date.now())continue;if(processed>=maximumDocuments)break;processed++;
    try{
      let doc;if(source.source_sha256)doc={bytes:Buffer.from(await(await env.EVIDENCE.get('documents/'+source.source_sha256)).arrayBuffer()),sha256:source.source_sha256,url:source.url};else if(source.accession&&/\.txt$/i.test(source.url)){const loaded=await loadFilingDocuments(env,{...source,cik},async(url,opts={})=>{try{const d=await client.get(url,{origins:source.origins||[],maximum:opts.maximum||24000000});return {...d,content_type:d.content_type||'application/octet-stream'};}catch(e){if(/Financial document size limit/.test(e.message))throw new Error('Source exceeds document size limit');throw e;}});doc=loaded.documents[0];for(const extra of loaded.documents.slice(1)){if(!reports.some(r=>r.url===extra.url)){const attachment={...source,url:extra.url,source_sha256:extra.sha256,form:extra.form||'EX-99',trusted_parent:source.url};reports.push(attachment);(work.discovered||=[]).push(attachment);}}}else doc=await client.get(source.url,{origins:source.origins||[],maximum:24000000});
      // Retain the captured document for owner review even if extraction fails.
      work.sources.push({sha256:doc.sha256,url:source.url,form:source.form,filed:source.filed,published_at:source.published_at,publication_basis:source.publication_basis||'SEC_disclosure',parent:source.trusted_parent||null});
      const parsedKey='financials/parsed/'+doc.sha256+'-'+cik+'-'+PARSER_HASH+'.json';let parsed=await read(env,parsedKey);
      const meta={...source,cik,company:name,require_table_identity:true,require_company_identity:source.form==='IR_RELEASE'||doc.bytes.subarray(0,5).toString()==='%PDF-',currency_hint:currency,source_url:source.url,source_sha256:doc.sha256,observed_at:now()};
      if(!parsed){parsed=await extract(doc.bytes,meta);await put(env,parsedKey,parsed);}
      // PDF exhibits may be separate files in the same SEC accession. Keep the
      // parent's CIK and disclosure clock; never follow an arbitrary document URL.
      if(source.accession){for(const m of doc.bytes.toString('utf8').matchAll(/<FILENAME>\s*([^\s<>]+\.pdf)\b/gi)){
        if(!/^[a-zA-Z0-9._-]+\.pdf$/i.test(m[1]))continue;const url=new URL(m[1],source.url).href;
        if(!reports.some(r=>r.url===url)){const attachment={...source,url,source_sha256:undefined,form:'EX-99.PDF',trusted_parent:source.url};reports.push(attachment);(work.discovered||=[]).push(attachment);}
      }}
      work.facts.push(...parsed.facts);work.candidates.push(...parsed.candidates.map(r=>({...r,source_sha256:doc.sha256,source_url:source.url})));work.issues.push(...parsed.issues.map(r=>({...r,source_sha256:doc.sha256})));work.processed[source.url]={sha256:doc.sha256,at:now()};delete work.errors[source.url];
    }catch(e){const cooldown=isSourceCooldown(e),attempt=(work.errors[source.url]?.attempts||0)+(cooldown?0:1);work.errors[source.url]={attempts:attempt,next_attempt:Math.max(Number(e.retryAt)||0,Date.now()+Math.min(86400000,60000*2**Math.min(attempt,10))),terminal:!cooldown&&(e.status===404||attempt>=3),reason:e.message};work.issues.push({source_url:source.url,reason:e.message,at:now()});if(cooldown)break;}
  }
  const reviews=(await env.DB.prepare("SELECT value FROM rs_state WHERE key>=? AND key<? LIMIT 100").bind('financial_review:'+cik+':','financial_review:'+cik+';').all()).results;
  for(const row of reviews)try{const review=JSON.parse(row.value),document=await read(env,review.object_key);if(document?.facts)work.facts.push(...document.facts);}catch{}
  work.facts=[...new Map(work.facts.map(r=>[hash(JSON.stringify(r)),r])).values()];work.sources=[...new Map(work.sources.map(r=>[r.sha256,r])).values()];work.candidates=work.candidates.slice(-100);work.issues=work.issues.slice(-200);
  const remaining=deferDiscovery?1:reports.filter(r=>!work.processed[r.url]&&!work.errors[r.url]?.terminal).length,profile=buildFinancialProfile({cik,ticker:job.ticker,company:name,companyfacts,facts:work.facts,sources:[...(companyDoc?[{sha256:companyDoc.sha256,url:companyDoc.url,form:'SEC_COMPANYFACTS',published_at:companyDoc.captured_at,filed:etDay(companyDoc.captured_at)}]:[]),...work.sources],as_of:now(),instrument,errors:work.issues});
  profile.collection={status:deferDiscovery?'queued_for_filing_search':remaining?'in_progress':Object.keys(work.errors).length?'searched_with_errors':'searched',discovery_pending:deferDiscovery,remaining_documents:remaining,searched_documents:Object.keys(work.processed).length,candidates:work.candidates,issues:work.issues,api_source_sha256:companyDoc?.sha256||null};
  profile.coverage.recovery_plan=Object.entries(profile.coverage.metrics).filter(([,r])=>['not_recovered','insufficient_history'].includes(r.status)).map(([metric,r])=>({metric,reason:r.status,next_step:remaining?'pending_primary_document_extraction':'source_review_required',future_zeros_forbidden:true}));
  profile.coverage.sources_searched=Object.keys(work.processed).length;profile.coverage.pending_documents=remaining;
  const vendorKey='financials/vendor-comparison/'+cik+'.json';if(!await read(env,vendorKey)&&job.ticker)await put(env,vendorKey,await vendorComparison(env,job.ticker));profile.vendor_comparison_key=vendorKey;
  const material={...profile,observed_at:undefined,policy_financials:{...profile.policy_financials,cutoff:undefined},collection:{...profile.collection,issues:profile.collection.issues.map(({at,...r})=>r)}};
  await env.assertFinancialLease?.();
  profile.version=hash(JSON.stringify(material));const factsKey='financials/facts/'+cik+'/'+profile.version+'.json',ledger={schema:FINANCIAL_VERSION,cik,observed_at:profile.observed_at,facts:profile.facts,source_profile_version:profile.version};await put(env,factsKey,ledger);
  const {facts,...compact}=profile;compact.facts_object_key=factsKey;compact.facts_sha256=hash(JSON.stringify(ledger));await put(env,'financials/profiles/'+cik+'/'+profile.version+'.json',compact);await put(env,'financials/profiles/'+cik+'/latest.json',compact);await put(env,key,work);(await coverageCache(env)).set(cik,coverageCard(compact));
  return {profile:compact,complete:remaining===0,processed,next_attempt:Math.max(Number(client.cooldown)||0,Math.min(...Object.values(work.errors).filter(e=>!e.terminal).map(e=>e.next_attempt),Date.now()+60000))};
}
export async function publishFinancialCoverage(env,queue){
  const cards=[...(await coverageCache(env)).values()].filter(p=>queue.jobs[p.cik]).sort((a,b)=>b.observed_at.localeCompare(a.observed_at)),counts={};for(const p of cards)counts[p.status]=(counts[p.status]||0)+1;
  const summary={schema:FINANCIAL_VERSION,generated_at:now(),issuers:Object.keys(queue.jobs).length,processed:cards.length,pending:Object.values(queue.jobs).filter(j=>!j.complete).length,prepared_seed:queue.prepared_seed||null,status_counts:counts,eligible_issuer_scope:'Operating-company strategy; non-CS instruments separately classified',broker_connections:0,orders:0,source_policy:'Verified primary disclosures with original availability clocks; no imputed missing zeros'};
  const pages=[];for(let i=0;i<cards.length;i+=50){const page={schema:FINANCIAL_VERSION,profiles:cards.slice(i,i+50),next_cursor:i+50<cards.length?String(i+50):null,summary},key='financials/pages/'+hash(JSON.stringify(page))+'.json';await put(env,key,page);pages.push(key);}
  const manifest={...summary,pages,cards,profiles:cards.map(p=>({cik:p.cik,version:p.version,observed_at:p.observed_at}))};await env.assertFinancialLease?.();await put(env,'financials/manifest-latest.json',manifest);return manifest;
}
export async function runFinancialHarvest(env,{maximumMs=270*60000,maxIssuers=500,maximumDocuments=8,offline=false}={}){
  const start=Date.now(),owner=crypto.randomUUID(),leaseKey='financial_harvest_lease';let lease=String(Date.now()+600000)+':'+owner;
  await env.DB.prepare("INSERT OR IGNORE INTO rs_state VALUES(?,?,?)").bind(leaseKey,'0',now()).run();
  if(!await env.DB.prepare('UPDATE rs_state SET value=?,updated_at=? WHERE key=? AND CAST(value AS INTEGER)<=? RETURNING value').bind(lease,now(),leaseKey,Date.now()).first())return {skipped:true};
  const queue=await read(env,'financials/queue.json',{jobs:{}}),client=new FinancialSources(env,{offline});let handled=0,lastSeed=0,stop=false,leaseError=null,renewing=Promise.resolve();const signal=()=>{stop=true;};process.once('SIGTERM',signal);process.once('SIGINT',signal);
  const renew=()=>{renewing=renewing.then(async()=>{const next=String(Date.now()+600000)+':'+owner;if(!await env.DB.prepare('UPDATE rs_state SET value=?,updated_at=? WHERE key=? AND value=? RETURNING value').bind(next,now(),leaseKey,lease).first())throw new Error('Financial harvest lease lost');lease=next;}).catch(e=>{leaseError=e;stop=true;});return renewing;};
  // queue.json and the coverage manifest are rewritten every iteration, so one rejected object write waits for the next pass.
  let deferredWrites=0;const deferrable=async(stage,write)=>{try{await write();deferredWrites=0;}catch(e){if(!isolatedWriteFailure(e)||++deferredWrites>=5)throw e;console.error(JSON.stringify({event:'financial_harvest_write_deferred',stage,error:e.message,consecutive:deferredWrites}));}};
  const timer=setInterval(renew,120000);env.assertFinancialLease=async()=>{await renewing;if(leaseError)throw leaseError;const row=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(leaseKey).first();if(row?.value?.split(':').at(-1)!==owner||Number(row.value.split(':')[0])<=Date.now())throw new Error('Financial harvest lease lost');};
  try{while(!stop&&Date.now()-start<maximumMs&&handled<maxIssuers){
    if(Date.now()-lastSeed>60000){const remote=(await env.DB.prepare('SELECT cik,ticker,company,payload,analyzed_at FROM rs_events WHERE cik IS NOT NULL').all()).results,live=await read(env,'collector-dashboard/events.json',[]);for(const r of [...remote,...live.filter(e=>e.cik).map(e=>({...e,payload:JSON.stringify(e)}))]){const event=JSON.parse(r.payload),cik=String(Number(r.cik)),priority=event.status==='scheduled'?1000:event.result==='needs_review'?200:50;const old=queue.jobs[cik]||{cik,attempts:0,next_attempt:0};queue.jobs[cik]={...old,ticker:r.ticker||old.ticker,company:r.company||old.company,priority:Math.max(old.priority||0,priority)};}
      const signals=(await env.DB.prepare("SELECT key,value FROM rs_state WHERE key>='financial_need:' AND key<'financial_need;' LIMIT 1000").all()).results;for(const r of signals){const cik=r.key.split(':')[1],j=queue.jobs[cik];if(j&&j.last_signal!==r.value){j.next_attempt=0;j.last_signal=r.value;}}
      const snapshot=await read(env,'collector-dashboard/financial-needs.json',[]);for(const r of snapshot){const cik=r.key.split(':')[1],j=queue.jobs[cik];if(j&&j.last_signal!==r.value){j.next_attempt=0;j.last_signal=r.value;}}
      await seedPreparedNeeds(env,queue);lastSeed=Date.now();}
    if(Number(lease.split(':')[0])-Date.now()<480000)await renew();if(leaseError)throw leaseError;
    const job=nextFinancialJob(queue.jobs);
    if(!job){await new Promise(r=>setTimeout(r,10000));continue;}
    const firstPass=!job.last_attempt;job.last_attempt=now();handled++;
    try{const result=await harvestIssuer(env,job,{client,maximumDocuments:firstPass&&job.priority<1000?0:maximumDocuments,offline});job.complete=result.complete;job.next_attempt=result.complete?Date.now()+3600000:result.next_attempt;job.error=null;job.attempts=0;console.log(JSON.stringify({event:'financial_profile',cik:job.cik,ticker:job.ticker,status:result.profile.coverage.status,score:result.profile.policy_financials.score,remaining:result.profile.collection.remaining_documents}));}
    catch(e){const cooldown=isSourceCooldown(e);if(!cooldown)job.attempts++;job.complete=false;job.error=e.message;job.next_attempt=cooldown?Math.max(Number(e.retryAt)||0,Date.now()+300000):Date.now()+Math.min(86400000,60000*2**Math.min(job.attempts,10));console.log(JSON.stringify({event:'financial_harvest_retry',cik:job.cik,error:e.message,retry_at:new Date(job.next_attempt).toISOString()}));}
    await deferrable('queue',()=>put(env,'financials/queue.json',queue));if(handled%5===0||job.priority>=1000)await deferrable('coverage',()=>publishFinancialCoverage(env,queue));
  }await deferrable('coverage',()=>publishFinancialCoverage(env,queue));return {handled,requests:client.requests,continue:!stop,broker_connections:0};}
  finally{clearInterval(timer);await renewing;process.removeListener('SIGTERM',signal);process.removeListener('SIGINT',signal);try{await env.assertFinancialLease();await put(env,'financials/queue.json',queue);}finally{await env.DB.prepare("UPDATE rs_state SET value='0',updated_at=? WHERE key=? AND value=?").bind(now(),leaseKey,lease).run();delete env.assertFinancialLease;}}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  const {values}=parseArgs({options:{'run-minutes':{type:'string',default:'270'},'max-issuers':{type:'string',default:'500'},'max-documents':{type:'string',default:'8'},offline:{type:'boolean',default:false}}});
  const env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:'e1cac493b315c8fd7398500dd1bfd687',database:'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:'single-stock-reverse-splits-evidence',evidenceInterval:1000});
  try{const result=await runFinancialHarvest(env,{maximumMs:Math.min(270,Number(values['run-minutes']))*60000,maxIssuers:Math.min(5000,Number(values['max-issuers'])),maximumDocuments:Math.min(20,Number(values['max-documents'])),offline:values.offline});if(process.env.GITHUB_OUTPUT)appendFileSync(process.env.GITHUB_OUTPUT,'continue='+!!result.continue+'\n');console.log(JSON.stringify(result));}catch(e){console.error(JSON.stringify({event:'financial_harvest_failed',error:e.message}));process.exitCode=1;}
}
