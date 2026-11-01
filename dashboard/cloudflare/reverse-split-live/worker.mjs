import {POLICY,DAY,etDay,iso,dateOnlyAvailable,plain,parseFeed,classifyAnnouncement,scoreFundamentals,screen} from './core.mjs';

const stamp=()=>new Date().toISOString(),sleep=ms=>new Promise(r=>setTimeout(r,ms));
const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
const log=(event,fields={})=>console.log(JSON.stringify({event,...fields}));
export const SOURCES=[
  ...['8-K','6-K','10-Q','10-K','20-F','40-F'].map(form=>({id:'sec-'+form,kind:'sec',form,url:`https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=${form}&owner=exclude&count=100&output=atom`})),
  {id:'prnewswire',kind:'news',url:'https://www.prnewswire.com/rss/news-releases-list.rss'},
  {id:'globenewswire',kind:'news',url:'https://www.globenewswire.com/RssFeed/subjectcode/13-Change%20in%20Share%20Capital/feedTitle/GlobeNewswire%20-%20Change%20in%20Share%20Capital'},
];
const SEC_HOSTS=new Set(['www.sec.gov','data.sec.gov','efts.sec.gov']);
const NEWS_HOSTS=new Set(['www.prnewswire.com','www.globenewswire.com']);
export function sourceURL(value){const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.port||(!SEC_HOSTS.has(u.hostname)&&!NEWS_HOSTS.has(u.hostname)))throw new Error('Unsupported source URL');return u;}
export async function sha(value){const bytes=typeof value==='string'?new TextEncoder().encode(value):value;return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export async function boundedBody(response,maximum){
  if(Number(response.headers.get('content-length'))>maximum)throw new Error('Source exceeds document size limit');
  if(!response.body)return new Uint8Array();
  const reader=response.body.getReader(),chunks=[];let size=0;
  try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>maximum)throw new Error('Source exceeds document size limit');chunks.push(value);}}catch(e){await reader.cancel().catch(()=>{});throw e;}
  const bytes=new Uint8Array(size);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length;}return bytes;
}
async function state(env,key,value){if(value===undefined)return env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first().then(r=>r?.value);await env.DB.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(key,String(value),stamp()).run();}
export async function limitedFetch(env,value,{maximum=24*1024*1024,redirects=0}={}){
  const url=sourceURL(value),sec=SEC_HOSTS.has(url.hostname);
  if(env.deadline&&Date.now()>=env.deadline)throw new Error('Collector source deadline reached; work will retry');
  if(sec){
    if(Number(await state(env,'sec_cooldown'))>Date.now())throw new Error('SEC access is in backoff');
    await env.DB.prepare("INSERT OR IGNORE INTO rs_state(key,value,updated_at) VALUES('sec_slot','0',?)").bind(stamp()).run();
    let slot=false;
    for(let i=0;i<12&&!slot;i++){const now=Date.now();slot=await env.DB.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='sec_slot' AND CAST(value AS INTEGER)<=? RETURNING value").bind(String(now+650),stamp(),now).first();if(!slot)await sleep(250);}
    if(!slot)throw new Error('SEC request budget occupied');
  }
  const remaining=env.deadline?env.deadline-Date.now():18000;
  if(remaining<=0)throw new Error('Collector source deadline reached; work will retry');
  const response=await fetch(url,{redirect:'manual',headers:{'user-agent':env.SEC_USER_AGENT,'accept':'application/atom+xml, application/rss+xml, application/json, text/html, text/plain, */*'},signal:AbortSignal.timeout(Math.min(18000,remaining))});
  if(response.status>=300&&response.status<400){await response.body?.cancel();if(redirects>=3)throw new Error('Source redirect limit');const next=new URL(response.headers.get('location'),url);sourceURL(next);return limitedFetch(env,next.href,{maximum,redirects:redirects+1});}
  if(!response.ok){await response.body?.cancel();if(sec&&[403,429].includes(response.status))await state(env,'sec_cooldown',Date.now()+Math.min(3600000,Math.max(300000,Number(response.headers.get('retry-after')||0)*1000)));throw new Error(`Source returned HTTP ${response.status}`);}
  return {bytes:await boundedBody(response,maximum),content_type:response.headers.get('content-type')||'',url:url.href};
}
async function archive(env,doc){const hash=await sha(doc.bytes),key='documents/'+hash;await env.EVIDENCE.put(key,doc.bytes,{httpMetadata:{contentType:doc.content_type},customMetadata:{source_url:doc.url,captured_at:stamp()}});await env.DB.prepare('INSERT OR IGNORE INTO rs_documents(sha256,url,object_key,captured_at,bytes,content_type) VALUES(?,?,?,?,?,?)').bind(hash,doc.url,key,stamp(),doc.bytes.length,doc.content_type).run();return {hash,key,text:new TextDecoder().decode(doc.bytes)};}
export async function enqueue(env,kind,payload,priority=0,id=null){const now=stamp();id ||= await sha(kind+':'+JSON.stringify(payload));await env.DB.prepare('INSERT OR IGNORE INTO rs_jobs(id,kind,payload,priority,created_at,updated_at) VALUES(?,?,?,?,?,?)').bind(id,kind,JSON.stringify(payload),priority,now,now).run();return id;}
async function addFiling(env,item,priority){
  if(!item.cik||!/^\d{10}-\d{2}-\d{6}$/.test(item.accession||''))return;
  const first=stamp(),url=`https://www.sec.gov/Archives/edgar/data/${Number(item.cik)}/${item.accession.replaceAll('-','')}/${item.accession}.txt`;
  await env.DB.prepare('INSERT OR IGNORE INTO rs_filings(accession,cik,form,published_at,first_seen_at,source_url) VALUES(?,?,?,?,?,?)').bind(item.accession,item.cik,item.form||null,item.published_at,first,url).run();
  await enqueue(env,'filing',{...item,url,first_seen_at:first},priority,'filing:'+item.accession);
}
async function addFilings(env,items,priority){
  const now=stamp(),statements=[];
  for(const item of items){if(!item.cik||!/^\d{10}-\d{2}-\d{6}$/.test(item.accession||''))continue;
    const url=`https://www.sec.gov/Archives/edgar/data/${Number(item.cik)}/${item.accession.replaceAll('-','')}/${item.accession}.txt`,payload={...item,url,first_seen_at:now};
    statements.push(env.DB.prepare('INSERT OR IGNORE INTO rs_filings(accession,cik,form,published_at,first_seen_at,source_url) VALUES(?,?,?,?,?,?)').bind(item.accession,item.cik,item.form||null,item.published_at,now,url),env.DB.prepare('INSERT OR IGNORE INTO rs_jobs(id,kind,payload,priority,created_at,updated_at) VALUES(?,?,?,?,?,?)').bind('filing:'+item.accession,'filing',JSON.stringify(payload),priority,now,now));
  }
  for(let i=0;i<statements.length;i+=80)await env.DB.batch(statements.slice(i,i+80));
}
async function poll(env,source){
  await env.DB.prepare('INSERT OR IGNORE INTO rs_sources(id,kind,url) VALUES(?,?,?)').bind(source.id,source.kind,source.url).run();
  const saved=await env.DB.prepare('SELECT * FROM rs_sources WHERE id=?').bind(source.id).first();
  if(saved.next_attempt>Date.now())return;
  try{
    let count=0,complete=false,newest=null,oldest=null;
    const cutoff=saved.watermark||new Date(Date.now()-3*DAY).toISOString();
    for(let page=0;page<(source.kind==='sec'?4:1);page++){
      const url=source.url+(page?'&start='+page*100:''),doc=await limitedFetch(env,url,{maximum:3*1024*1024}),items=parseFeed(new TextDecoder().decode(doc.bytes),source.id);
      oldest=items.map(x=>x.published_at).filter(Boolean).sort()[0]||oldest;
      if(page===0)newest=items.map(x=>x.published_at).filter(Boolean).sort().at(-1)||null;
      const selected=[];
      for(const item of items){
        if(item.published_at&&item.published_at<cutoff){complete=true;continue;}
        count++;
        if(source.kind==='sec')selected.push({...item,form:item.form||source.form});
        else if(/reverse.{0,20}split|share consolidation/i.test(item.title))await enqueue(env,'news',{...item,first_seen_at:stamp()},12,'news:'+await sha(item.url));
      }
      if(selected.length)await addFilings(env,selected,source.form.startsWith('10-')?5:10);
      if(items.length<100||source.kind!=='sec')complete=true;
      if(complete)break;
    }
    if(!complete&&oldest)await env.DB.prepare('INSERT OR IGNORE INTO rs_source_gaps(id,source_id,start_at,end_at,created_at) VALUES(?,?,?,?,?)').bind(source.id+':'+cutoff,source.id,cutoff,oldest,stamp()).run();
    const gap=await env.DB.prepare('SELECT id FROM rs_source_gaps WHERE source_id=? AND resolved_at IS NULL LIMIT 1').bind(source.id).first();
    await env.DB.prepare("UPDATE rs_sources SET last_attempt=?,last_success=?,watermark=?,status=?,error=NULL,failures=0,next_attempt=0,coverage_gap=?,items=? WHERE id=?").bind(stamp(),stamp(),newest||saved.watermark,gap?'catching_up':'healthy',gap?1:0,count,source.id).run();
  }catch(e){const failures=saved.failures+1;await env.DB.prepare("UPDATE rs_sources SET last_attempt=?,status='degraded',error=?,failures=?,next_attempt=? WHERE id=?").bind(stamp(),e.message,failures,Date.now()+Math.min(3600000,30000*2**Math.min(failures,7)),source.id).run();log('source_failure',{source:source.id,error:e.message});}
}
export async function dispatch(env){
  const now=Date.now();
  await env.DB.prepare("UPDATE rs_jobs SET state='pending',token=NULL WHERE state IN ('queued','running') AND lease_until<? AND attempts<6").bind(now).run();
  await env.DB.prepare("UPDATE rs_jobs SET state='failed',error=COALESCE(error,'Lease expired after retry limit') WHERE state IN ('queued','running') AND lease_until<? AND attempts>=6").bind(now).run();
  const rows=(await env.DB.prepare("SELECT id FROM rs_jobs WHERE state='pending' AND available_at<=? ORDER BY priority DESC,json_extract(payload,'$.published_at') DESC,created_at LIMIT ?").bind(now,Math.min(40,Math.max(1,env.MAX_DISPATCH||40))).all()).results;
  for(const r of rows){const token=crypto.randomUUID(),claimed=await env.DB.prepare("UPDATE rs_jobs SET state='queued',token=?,lease_until=?,updated_at=? WHERE id=? AND state='pending' RETURNING id").bind(token,now+600000,stamp(),r.id).first();if(!claimed)continue;
    try{await env.JOBS.send({id:r.id,token});}catch(e){await env.DB.prepare("UPDATE rs_jobs SET state='pending',token=NULL,error=?,available_at=? WHERE id=? AND token=?").bind(e.message,now+60000,r.id,token).run();throw e;}
  }
}
async function issuer(env,cik,{refresh=false}={}){
  let row=await env.DB.prepare('SELECT * FROM rs_issuers WHERE cik=?').bind(cik).first();
  if(row?.submissions_key&&!refresh&&Date.now()-Date.parse(row.refreshed_at)<6*3600000){const obj=await env.EVIDENCE.get(row.submissions_key);if(obj)return {row,submissions:await obj.json()};}
  const doc=await archive(env,await limitedFetch(env,`https://data.sec.gov/submissions/CIK${cik.padStart(10,'0')}.json`)),submissions=JSON.parse(doc.text);
  if(String(Number(submissions.cik))!==cik)throw new Error('SEC issuer metadata identity mismatch');
  await env.DB.prepare('INSERT INTO rs_issuers(cik,ticker,company,submissions_key,refreshed_at) VALUES(?,?,?,?,?) ON CONFLICT(cik) DO UPDATE SET ticker=excluded.ticker,company=excluded.company,submissions_key=excluded.submissions_key,refreshed_at=excluded.refreshed_at').bind(cik,submissions.tickers?.length===1?submissions.tickers[0]:null,submissions.name,doc.key,stamp()).run();
  row=await env.DB.prepare('SELECT * FROM rs_issuers WHERE cik=?').bind(cik).first();return {row,submissions};
}
async function financials(env,cik,cutoff,refresh=false){
  const row=await env.DB.prepare('SELECT * FROM rs_issuers WHERE cik=?').bind(cik).first();let raw,hash;
  if(!refresh&&row?.cache_key&&Date.now()-Date.parse(row.facts_captured_at)<6*3600000){const object=await env.EVIDENCE.get(row.cache_key);if(object){raw=await object.json();hash=row.cache_key.split('/').at(-1);}}
  if(!raw){const doc=await archive(env,await limitedFetch(env,`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik.padStart(10,'0')}.json`));raw=JSON.parse(doc.text);if(String(Number(raw.cik))!==cik)throw new Error('Companyfacts issuer identity mismatch');hash=doc.hash;await env.DB.prepare('UPDATE rs_issuers SET cache_key=?,facts_captured_at=? WHERE cik=?').bind(doc.key,stamp(),cik).run();}
  return {...scoreFundamentals(raw,cutoff,cik),source_sha256:hash,source_url:`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik.padStart(10,'0')}.json`};
}
export async function recordEvent(env,event,{refresh=false}={}){
  let previous;
  if(event.cik){previous=await env.DB.prepare('SELECT * FROM rs_events WHERE cik=? AND effective_date=? ORDER BY first_seen_at LIMIT 1').bind(event.cik,event.effective_date).first();
    const changedSchedule=(event.sources||[]).some(s=>/\/A$/.test(s.form||''))||(event.evidence||[]).some(t=>/postpon|reschedul|amend.{0,50}(?:effective|split)|changed.{0,50}(?:effective|split)/i.test(t));
    if(!previous&&(event.status==='cancelled'||changedSchedule)){const possible=(await env.DB.prepare("SELECT * FROM rs_events WHERE cik=? AND first_seen_at>=? AND effective_date>=? ORDER BY first_seen_at DESC LIMIT 3").bind(event.cik,new Date(Date.now()-30*DAY).toISOString(),etDay(Date.now())).all()).results;if(possible.length===1)previous=possible[0];else if(possible.length>1){event.related_event_ids=possible.map(r=>r.id);event.status='needs_review';event.reason='Multiple outstanding issuer actions; amendment linkage is unresolved';}}
  }
  previous ||= await env.DB.prepare('SELECT * FROM rs_events WHERE id=?').bind(event.id).first();
  if(previous){const old=JSON.parse(previous.payload),latest=old.latest_publication_at||old.published_at,older=event.published_at&&latest&&(event.published_at<latest||(old.status==='cancelled'&&event.published_at<=latest));event={...old,...event,...(older?{status:old.status,reason:old.reason,ratio:old.ratio,effective_date:old.effective_date}:{}),id:previous.id,first_seen_at:old.first_seen_at,published_at:[old.published_at,event.published_at].filter(Boolean).sort()[0]||null,latest_publication_at:[latest,event.published_at].filter(Boolean).sort().at(-1)||null,sources:[...(old.sources||[]),...(event.sources||[])].filter((r,i,a)=>a.findIndex(x=>x.url===r.url&&x.sha256===r.sha256)===i)};}
  const now=stamp();
  // Persist detection before external enrichment: even an outage cannot hide a company.
  await env.DB.prepare("INSERT INTO rs_events(id,cik,ticker,company,effective_date,published_at,first_seen_at,payload) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET effective_date=excluded.effective_date,payload=excluded.payload,revision=rs_events.revision+1").bind(event.id,event.cik||null,event.ticker||null,event.company||null,event.effective_date,event.published_at,event.first_seen_at,JSON.stringify(event)).run();
  let f={score:null,status:'issuer_identity_unresolved',signals:{},evidence:[]},prior=[],metadataError=null;
  if(event.cik){try{const {row,submissions}=await issuer(env,event.cik);event.company ||= row.company;event.ticker ||= row.ticker;event.multiple_securities=(submissions.tickers||[]).length>1;f=await financials(env,event.cik,now,refresh);prior=(await env.DB.prepare('SELECT payload FROM rs_history WHERE cik=? AND effective_date<?').bind(event.cik,etDay(now)).all()).results.map(r=>JSON.parse(r.payload));await enqueue(env,'history',{cik:event.cik},3,'history:'+event.cik+':'+etDay(now));}catch(e){metadataError=e.message;f={...f,status:'financial_source_unavailable',error:e.message};}}
  const decision=screen(event,f,prior,now);if(event.multiple_securities){decision.result='needs_review';decision.checks.security={state:'unknown',reason:'Multiple issuer securities require instrument reconciliation'};}
  const payload={...event,financials:f,...decision,analyzed_at:now,metadata_error:metadataError,latency_seconds:Math.max(0,(Date.parse(now)-Date.parse(event.first_seen_at))/1000),source_delay_seconds:event.published_at?Math.max(0,(Date.parse(event.first_seen_at)-Date.parse(event.published_at))/1000):null};
  const id=await sha(event.id+':'+now+':'+JSON.stringify(payload));
  await env.DB.batch([
    env.DB.prepare('UPDATE rs_events SET ticker=?,company=?,analyzed_at=?,result=?,score=?,ordinal_min=?,payload=? WHERE id=?').bind(event.ticker||null,event.company||null,now,decision.result,f.score,decision.ordinal_min,JSON.stringify(payload),event.id),
    env.DB.prepare('INSERT OR IGNORE INTO rs_decisions(id,event_id,recorded_at,policy,payload) VALUES(?,?,?,?,?)').bind(id,event.id,now,POLICY.id,JSON.stringify(payload)),
  ]);
  if(decision.result==='passes_screen')await env.DB.prepare('INSERT OR IGNORE INTO rs_alerts(id,event_id,created_at,kind,payload) VALUES(?,?,?,?,?)').bind(POLICY.id+':'+event.id,event.id,now,'research_screen_pass',JSON.stringify({ticker:event.ticker,score:f.score,ordinal_min:decision.ordinal_min,execution_ready:false})).run();
  if(metadataError)await enqueue(env,'rescore',{id:event.id,refresh:true},8,'retry-score:'+event.id+':'+Math.floor(Date.now()/3600000));
  return payload;
}
function filingText(raw){const docs=[...raw.matchAll(/<DOCUMENT>([\s\S]*?)<\/DOCUMENT>/gi)];if(!docs.length)return raw;return docs.map(x=>x[1]).filter(t=>/<TYPE>\s*(?:8-K|6-K|10-[KQ]|20-F|40-F|EX-99)/i.test(t)).join('\n');}
async function filingJob(env,p){
  const row=await env.DB.prepare('SELECT * FROM rs_filings WHERE accession=?').bind(p.accession).first();
  if(row?.state==='complete')return;
  const downloaded=await limitedFetch(env,p.url),raw=new TextDecoder().decode(downloaded.bytes);
  const bound=/ACCESSION NUMBER:\s*([\d-]+)/i.exec(raw)?.[1];if(bound&&bound!==p.accession)throw new Error('Filing accession mismatch');
  const parsed=classifyAnnouncement(filingText(raw),{published_at:p.published_at||p.first_seen_at,form:p.form});
  const source=parsed?await archive(env,downloaded):{hash:await sha(downloaded.bytes)};
  let event=null;
  if(parsed){const ticker=/<ix:nonNumeric[^>]*name=["']dei:TradingSymbol["'][^>]*>([^<]+)/i.exec(raw)?.[1]?.trim();
    event=await recordEvent(env,{...parsed,id:'sec:'+p.accession,cik:p.cik,ticker:ticker||null,company:/COMPANY CONFORMED NAME:\s*([^\r\n]+)/i.exec(raw)?.[1]?.trim()||null,published_at:p.published_at,first_seen_at:row?.first_seen_at||p.first_seen_at,sources:[{url:p.url,sha256:source.hash,accession:p.accession,form:p.form}],clock_basis:'SEC feed publication; separately recorded first observation'});
  }
  if(/^10-[KQ]|20-F|40-F/.test(p.form||'')){
    const active=(await env.DB.prepare('SELECT id FROM rs_events WHERE cik=? AND effective_date>=?').bind(p.cik,etDay(Date.now())).all()).results;
    for(const e of active)await enqueue(env,'rescore',{id:e.id,refresh:true},7,'financial-update:'+p.accession+':'+e.id);
  }
  await env.DB.prepare("UPDATE rs_filings SET state='complete',source_sha256=?,event_id=? WHERE accession=?").bind(source.hash,event?.id||null,p.accession).run();
}
async function tickerCIK(env,ticker){
  let key=await state(env,'ticker_map_key'),at=await state(env,'ticker_map_at'),raw;
  if(key&&Date.now()-Date.parse(at)<DAY){const obj=await env.EVIDENCE.get(key);if(obj)raw=await obj.json();}
  if(!raw){const source=await archive(env,await limitedFetch(env,'https://www.sec.gov/files/company_tickers.json',{maximum:5*1024*1024}));raw=JSON.parse(source.text);await state(env,'ticker_map_key',source.key);await state(env,'ticker_map_at',stamp());}
  const matches=Object.values(raw).filter(x=>x.ticker===ticker);return matches.length===1?String(Number(matches[0].cik_str)):null;
}
async function newsJob(env,p){
  const source=await archive(env,await limitedFetch(env,p.url,{maximum:5*1024*1024})),parsed=classifyAnnouncement(source.text,{published_at:p.published_at});if(!parsed)return;
  const text=plain(source.text),ticker=/\b(?:NASDAQ|NYSE(?:\s+AMERICAN)?|OTCQ[BX])\s*[:：]\s*([A-Z][A-Z0-9.-]{0,11})\b/i.exec(text)?.[1]?.toUpperCase();let cik=null;
  if(ticker)try{cik=await tickerCIK(env,ticker);}catch(e){log('news_identity_pending',{ticker,error:e.message});}
  await recordEvent(env,{...parsed,id:'news:'+await sha(p.url),cik,ticker:ticker||null,company:p.title,published_at:p.published_at,first_seen_at:p.first_seen_at||stamp(),sources:[{url:p.url,sha256:source.hash}],clock_basis:'Publisher feed timestamp; separately recorded first observation'});
}
async function historyJob(env,p){
  const url=`https://efts.sec.gov/LATEST/search-index?q=${encodeURIComponent('"reverse stock split" OR "reverse split" OR "share consolidation"')}&ciks=${p.cik}&forms=8-K,6-K&dateRange=custom&startdt=${new Date(Date.now()-10*365*DAY).toISOString().slice(0,10)}&enddt=${etDay(Date.now())}&from=0&size=30`;
  const doc=await limitedFetch(env,url,{maximum:5*1024*1024}),result=JSON.parse(new TextDecoder().decode(doc.bytes)),hits=result.hits?.hits||[];
  await env.DB.prepare('UPDATE rs_issuers SET history_status=? WHERE cik=?').bind((result.hits?.total?.value||0)>30?'partial':'search_complete',p.cik).run();
  for(const h of hits){const s=h._source||{},acc=s.adsh||/^(\d{10}-\d{2}-\d{6})/.exec(h._id||'')?.[1];if(!acc)continue;const payload={cik:p.cik,accession:acc,published_at:s.file_date?dateOnlyAvailable(s.file_date):null,url:`https://www.sec.gov/Archives/edgar/data/${p.cik}/${acc.replaceAll('-','')}/${acc}.txt`};await enqueue(env,'history_filing',payload,2,'history-filing:'+acc);}
}
async function historyFiling(env,p){
  const source=await archive(env,await limitedFetch(env,p.url)),text=plain(filingText(source.text));
  // Only an explicit completed action, with a single bound date, establishes a prior split.
  const clauses=text.split('\n').filter(x=>/reverse.{0,20}split|share consolidation/i.test(x));
  const dates=[];
  for(const line of clauses){const m=/(?:became effective|was effective|effected|completed|implemented)[^\n]{0,120}?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2})/i.exec(line);if(m){const day=iso(m[1])?.slice(0,10);if(day&&day<etDay(Date.now())&&p.published_at&&day<=etDay(p.published_at))dates.push(day);}}
  if(new Set(dates).size===1){const d=dates[0],record={cik:p.cik,effective_date:d,known_at:p.published_at,verified:true,source_url:p.url,source_sha256:source.hash,verification:'explicit_completed_primary_clause'};await env.DB.prepare('INSERT OR IGNORE INTO rs_history(id,cik,effective_date,known_at,verified,payload) VALUES(?,?,?,?,1,?)').bind(p.cik+':'+d,p.cik,d,p.published_at,JSON.stringify(record)).run();
    for(const r of (await env.DB.prepare('SELECT id FROM rs_events WHERE cik=? AND effective_date>=?').bind(p.cik,etDay(Date.now())).all()).results)await enqueue(env,'rescore',{id:r.id},7,'history-rescore:'+p.accession+':'+r.id);
  }
}
async function reconcile(env){
  for(let ago=1;ago<=7;ago++){
    const day=new Date(Date.now()-ago*DAY).toISOString().slice(0,10),d=new Date(day+'T12:00:00Z');if([0,6].includes(d.getUTCDay()))continue;
    const id='reconcile:'+day;if(await state(env,id))continue;
    const url=`https://www.sec.gov/Archives/edgar/daily-index/${d.getUTCFullYear()}/QTR${Math.floor(d.getUTCMonth()/3)+1}/master.${day.replaceAll('-','')}.idx`;
    try{const doc=await limitedFetch(env,url,{maximum:12*1024*1024}),text=new TextDecoder().decode(doc.bytes);if(!text.includes('CIK|Company Name|Form Type|Date Filed|Filename'))throw new Error('Invalid daily index');let count=0;
      const found=[];for(const line of text.split('\n')){const [cik,,form,filed,path]=line.trim().split('|');if(!/^\d+$/.test(cik||'')||!['8-K','8-K/A','6-K','6-K/A','10-Q','10-Q/A','10-K','10-K/A','20-F','40-F'].includes(form))continue;const accession=/(\d{10}-\d{2}-\d{6})/.exec(path||'')?.[1];if(accession){found.push({cik:String(Number(cik)),accession,form,published_at:dateOnlyAvailable(filed)});count++;}}await addFilings(env,found,1);
      await state(env,id,JSON.stringify({at:stamp(),filings:count}));await state(env,'last_reconciliation',stamp());
    }catch(e){await state(env,'reconciliation_error',JSON.stringify({day,error:e.message,at:stamp()}));log('reconciliation_failure',{day,error:e.message});}
  }
  for(const gap of (await env.DB.prepare('SELECT * FROM rs_source_gaps WHERE resolved_at IS NULL').all()).results){let covered=true;for(let t=Date.parse(gap.start_at.slice(0,10)+'T12:00:00Z');t<=Date.parse(gap.end_at.slice(0,10)+'T12:00:00Z');t+=DAY){const d=new Date(t);if([0,6].includes(d.getUTCDay()))continue;if(!await state(env,'reconcile:'+d.toISOString().slice(0,10)))covered=false;}if(covered)await env.DB.prepare('UPDATE rs_source_gaps SET resolved_at=? WHERE id=?').bind(stamp(),gap.id).run();}
}
export async function consume(batch,env){
  for(const message of batch.messages){const {id,token}=message.body||{},now=Date.now();const row=await env.DB.prepare("UPDATE rs_jobs SET state='running',attempts=attempts+1,lease_until=?,updated_at=? WHERE id=? AND token=? AND state='queued' RETURNING *").bind(now+600000,stamp(),id,token).first();if(!row){message.ack();continue;}
    try{const p=JSON.parse(row.payload);if(row.kind==='filing')await filingJob(env,p);else if(row.kind==='news')await newsJob(env,p);else if(row.kind==='history')await historyJob(env,p);else if(row.kind==='history_filing')await historyFiling(env,p);else if(row.kind==='rescore'){const e=await env.DB.prepare('SELECT payload FROM rs_events WHERE id=?').bind(p.id).first();if(e){const result=await recordEvent(env,JSON.parse(e.payload),p);if(result.metadata_error)throw new Error(result.metadata_error);}}else if(row.kind==='reconcile')await reconcile(env);else throw new Error('Unsupported job kind');
      await env.DB.prepare("UPDATE rs_jobs SET state='complete',error=NULL,updated_at=? WHERE id=? AND token=?").bind(stamp(),id,token).run();message.ack();
    }catch(e){const delay=Math.min(3600000,30000*2**Math.min(row.attempts,7));await env.DB.prepare('UPDATE rs_jobs SET state=?,error=?,available_at=?,updated_at=? WHERE id=? AND token=?').bind(row.attempts>=6?'failed':'pending',e.message,Date.now()+delay,stamp(),id,token).run();log('job_failure',{id,kind:row.kind,error:e.message,attempt:row.attempts});message.ack();}
  }
}
export async function scheduled(event,env){
  if(env.ENABLED!=='true'){await state(env,'service_mode','paused');return;}
  await state(env,'last_tick',stamp());await state(env,'service_mode',env.COLLECTOR_MODE||'research_monitor');
  for(const source of SOURCES)await poll(env,source);
  if(await state(env,'daily_rescore')!==etDay(Date.now())){for(const e of (await env.DB.prepare("SELECT id FROM rs_events WHERE first_seen_at>=? AND result IN ('passes_screen','needs_review') ORDER BY first_seen_at DESC LIMIT 300").bind(new Date(Date.now()-30*DAY).toISOString()).all()).results)await enqueue(env,'rescore',{id:e.id},6,'daily-rescore:'+etDay(Date.now())+':'+e.id);await state(env,'daily_rescore',etDay(Date.now()));}
  if(event.cron==='17 8 * * *')await enqueue(env,'reconcile',{day:etDay(Date.now())},1,'daily-reconcile:'+etDay(Date.now()));
  await dispatch(env);await state(env,'last_completed_tick',stamp());
}
export async function readAPI(request,env){
  if(request.method!=='GET')return json({error:'Read-only research service'},405);
  const url=new URL(request.url);
  if(url.pathname==='/events'){
    const limit=Math.max(1,Math.min(100,Number(url.searchParams.get('limit'))||50)),filter=url.searchParams.get('result'),query=(url.searchParams.get('q')||'').slice(0,80).toUpperCase();let cursor=['9999',''];
    if(url.searchParams.has('before')){try{cursor=JSON.parse(atob(url.searchParams.get('before')));if(!Array.isArray(cursor)||cursor.length!==2||cursor.some(x=>typeof x!=='string'))throw new Error();}catch{return json({error:'Invalid announcement cursor'},400);}}
    const sql='SELECT * FROM rs_events WHERE (first_seen_at<? OR (first_seen_at=? AND id>?))'+(filter?' AND result=?':'')+(query?" AND (UPPER(COALESCE(ticker,'')) LIKE ? OR UPPER(COALESCE(company,'')) LIKE ? OR cik=?)":'')+' ORDER BY first_seen_at DESC,id LIMIT ?';
    const binds=[cursor[0],cursor[0],cursor[1],...(filter?[filter]:[]),...(query?['%'+query+'%','%'+query+'%',query]:[]),limit+1];const rows=(await env.DB.prepare(sql).bind(...binds).all()).results,more=rows.length>limit;
    return json({policy:POLICY,generated_at:stamp(),events:rows.slice(0,limit).map(r=>JSON.parse(r.payload)),next_cursor:more?btoa(JSON.stringify([rows[limit-1].first_seen_at,rows[limit-1].id])):null});
  }
  if(url.pathname.startsWith('/events/')){const id=decodeURIComponent(url.pathname.slice(8)),row=await env.DB.prepare('SELECT payload FROM rs_events WHERE id=?').bind(id).first();if(!row)return json({error:'Announcement not found'},404);const decisions=(await env.DB.prepare('SELECT id,recorded_at,policy,payload FROM rs_decisions WHERE event_id=? ORDER BY recorded_at DESC LIMIT 30').bind(id).all()).results;return json({event:JSON.parse(row.payload),decisions:decisions.map(r=>({...r,payload:JSON.parse(r.payload)}))});}
  if(url.pathname==='/health'){
    const [sources,jobs,states,counts,alerts]=await Promise.all([env.DB.prepare('SELECT * FROM rs_sources').all(),env.DB.prepare("SELECT state,count(*) AS count,min(created_at) AS oldest FROM rs_jobs GROUP BY state").all(),env.DB.prepare("SELECT key,value,updated_at FROM rs_state WHERE key IN ('last_tick','last_completed_tick','service_mode','last_reconciliation','reconciliation_error','sec_cooldown')").all(),env.DB.prepare('SELECT result,count(*) AS count FROM rs_events GROUP BY result').all(),env.DB.prepare('SELECT * FROM rs_alerts ORDER BY created_at DESC LIMIT 20').all()]);
    const values=Object.fromEntries(states.results.map(r=>[r.key,r.value])),cadence=Number(env.EXPECTED_CADENCE_SECONDS)||60,fresh=values.last_completed_tick&&Date.now()-Date.parse(values.last_completed_tick)<Math.max(180000,cadence*2500),externalJobs=await state(env,'collector_job_counts');
    if(externalJobs)jobs.results=JSON.parse(externalJobs);
    return json({policy:POLICY,generated_at:stamp(),status:values.service_mode==='paused'?'paused':!fresh?'stale':sources.results.some(r=>r.status!=='healthy'||r.coverage_gap)||jobs.results.some(r=>r.state==='failed')?'degraded':'healthy',state:values,sources:sources.results,jobs:jobs.results,counts:counts.results,alerts:alerts.results.map(r=>({...r,payload:JSON.parse(r.payload)})),scope:'SEC issuer filings plus configured public press-release feeds. Public feed coverage is not a complete global announcement service.',expected_cadence_seconds:cadence,schedule_note:cadence>=300?'GitHub schedule: five minutes plus runner delays; not a guaranteed arrival time.':'Independent collector cadence; upstream publication delays still apply.',execution_ready:false});
  }
  return json({error:'Not found'},404);
}
export default {fetch:readAPI,scheduled,queue:consume};
