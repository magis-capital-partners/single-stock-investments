// Bounded discovery from public publisher archives. Partial search never closes a gap.
import {plain} from './core.mjs';
import {publisherInventory} from './publisher-inventory.mjs';
export function publisherArchiveURL(source,page,day){
 if(!Number.isInteger(page)||page<1||page>120||!/^\d{4}-\d{2}-\d{2}$/.test(day))throw new Error('Invalid bounded archive request');
 if(source==='prnewswire')return `https://www.prnewswire.com/news-releases/news-releases-list/?page=${page}&pagesize=100`;
 if(source==='globenewswire')return `https://rss.globenewswire.com/en/search/date/${encodeURIComponent('['+day+' TO '+day+']')}/load/more?page=${page}&pageSize=50`;
 return null;
}
export function archiveCandidates(html,base){
 const origin=new URL(base).origin,rows=new Map();
 for(const m of html.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]{0,5000}?)<\/a>/gi)){
  let url;try{url=new URL(m[1].replaceAll('&amp;','&'),base);if(url.origin!==origin||url.search||!/(?:news-releases\/|news-release\/)/.test(url.pathname))continue;}catch{continue;}
  const title=plain(m[2]);if(/reverse.{0,30}split|share consolidation/i.test(title))rows.set(url.href,{url:url.href,title});
 }
 return [...rows.values()];
}
export async function recoverPublisherGaps(env,{fetchDocument,enqueue,hash,now=new Date().toISOString()}={}){
 const gaps=(await env.DB.prepare("SELECT * FROM rs_source_gaps WHERE resolved_at IS NULL AND source_id NOT LIKE 'sec-%' ORDER BY start_at").all()).results;
 for(const gap of gaps){
  const key='publisher_recovery:'+gap.id,old=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first(),previous=old?JSON.parse(old.value):null,state=previous?.version==='public_inventory.v2'?previous:{version:'public_inventory.v2',page:1,attempts:0,pages:[],items:[],previous_recovery:previous};
  if(Date.parse(state.next_attempt)>Date.parse(now))continue;
  if(state.inventory_complete){
   const pending=[];for(const item of state.items){const row=await env.DB.prepare('SELECT state,error FROM rs_jobs WHERE id=?').bind(item.job_id).first(),document=await env.DB.prepare('SELECT sha256,object_key FROM rs_documents WHERE url=? ORDER BY captured_at DESC LIMIT 1').bind(item.url).first();if(row?.state!=='complete'||!document)pending.push({url:item.url,state:row?.state||'missing',error:row?.error||'Original article archive required'});else Object.assign(item,{body_sha256:document.sha256,body_object_key:document.object_key});}
   state.pending_bodies=pending.length;state.status=pending.length?'awaiting_archived_article_analysis':'late_inventory_recovered';
   if(!pending.length){const proof={version:state.version,gap,observed_at:now,pages:state.pages,items:state.items,coverage_basis:'Unfiltered publisher inventory crossed both interval bounds; every interval article body job completed after archival.',limitations:['Minute publication clocks include a one-minute boundary overlap.','Public pagination cannot prove a deleted or unpublished article never existed.','Late recovery does not reconstruct original-clock fills or news-to-fill latency.']},bytes=new TextEncoder().encode(JSON.stringify(proof)),sha256=await hash(bytes),object_key='review/source-recovery/'+sha256+'.json';await env.EVIDENCE.put(object_key,bytes,{httpMetadata:{contentType:'application/json'}});state.coverage_complete=true;state.proof={sha256,object_key};await env.DB.prepare('UPDATE rs_source_gaps SET resolved_at=? WHERE id=? AND resolved_at IS NULL').bind(now,gap.id).run();}
   state.observed_at=now;await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(key,JSON.stringify(state),now).run();continue;
  }
  if(state.page>120){state.status='bounded_archive_exhausted';state.coverage_complete=false;state.observed_at=now;await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(key,JSON.stringify(state),now).run();continue;}
  const url=publisherArchiveURL(gap.source_id,state.page,gap.start_at.slice(0,10));if(!url)continue;
  try{const doc=await fetchDocument(url,{maximum:5*1024*1024}),raw=new TextDecoder().decode(doc.bytes),sha256=await hash(doc.bytes),object_key='documents/'+sha256;await env.EVIDENCE.put(object_key,doc.bytes,{httpMetadata:{contentType:doc.content_type}});
   let items;try{items=publisherInventory(raw,gap.source_id,url);}catch(error){for(const item of archiveCandidates(raw,url))await enqueue('news',{...item,first_seen_at:now,discovery_path:'publisher_archive_catchup',publication_clock:'unverified_archive',recovery_gap_id:gap.id},4,'news:'+await hash(item.url));throw error;}
   if(Date.parse(items[0].published_at)>Date.parse(now)+2000)throw new Error('Future publisher inventory');
   if(state.page===1){state.upper_bound_observed=Date.parse(items[0].published_at)>=Date.parse(gap.end_at)-60000;if(!state.upper_bound_observed)throw new Error('Publisher inventory does not reach interval end');}
   if(state.pages.some(p=>p.sha256===sha256))throw new Error('Publisher pagination repeated the same page');
   for(const item of items.filter(r=>Date.parse(r.published_at)>=Date.parse(gap.start_at)-60000&&Date.parse(r.published_at)<=Date.parse(gap.end_at)+60000)){
    const job_id='publisher-article:v2:'+await hash(item.url);await enqueue('news',{...item,first_seen_at:now,discovery_path:'publisher_archive_catchup',publication_clock:'timestamp',recovery_gap_id:gap.id},4,job_id);if(!state.items.some(r=>r.url===item.url))state.items.push({...item,job_id});
   }
   state.pages.push({page:state.page,url,sha256,object_key,newest:items[0].published_at,oldest:items.at(-1).published_at,count:items.length,observed_at:now});
   Object.assign(state,{page:state.page+1,attempts:0,status:'inventory_discovery',source_url:url,source_sha256:sha256,object_key,discovered:state.items.length,next_attempt:new Date(Date.parse(now)+1000).toISOString(),inventory_complete:state.upper_bound_observed&&Date.parse(items.at(-1).published_at)<Date.parse(gap.start_at)-60000,coverage_complete:false,error:null});
  }catch(error){state.attempts++;Object.assign(state,{status:'archive_unavailable',error:error.message,next_attempt:new Date(Date.parse(now)+Math.min(3600000,30000*2**Math.min(state.attempts,6))).toISOString(),coverage_complete:false});}
  state.observed_at=now;await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(key,JSON.stringify(state),now).run();
  if(env.deadline&&Date.now()+3000>=env.deadline)break;
 }
}
