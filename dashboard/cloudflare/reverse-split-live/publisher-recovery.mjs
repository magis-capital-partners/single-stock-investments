// Bounded discovery from public publisher archives. Partial search never closes a gap.
import {plain} from './core.mjs';
export function publisherArchiveURL(source,page,day){
 if(!Number.isInteger(page)||page<1||page>20||!/^\d{4}-\d{2}-\d{2}$/.test(day))throw new Error('Invalid bounded archive request');
 if(source==='prnewswire')return `https://www.prnewswire.com/news-releases/news-releases-list/?page=${page}&pagesize=100`;
 if(source==='globenewswire')return `https://www.globenewswire.com/NewsRoom?date=${day}&page=${page}`;
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
  const key='publisher_recovery:'+gap.id,old=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first(),state=old?JSON.parse(old.value):{page:1,attempts:0};
  if(Date.parse(state.next_attempt)>Date.parse(now)||state.page>20)continue;
  const url=publisherArchiveURL(gap.source_id,state.page,gap.start_at.slice(0,10));if(!url)continue;
  try{const doc=await fetchDocument(url,{maximum:5*1024*1024}),raw=new TextDecoder().decode(doc.bytes),items=archiveCandidates(raw,url),sha256=await hash(doc.bytes),object_key='documents/'+sha256;await env.EVIDENCE.put(object_key,doc.bytes,{httpMetadata:{contentType:doc.content_type}});
   for(const item of items)await enqueue('news',{...item,first_seen_at:now,discovery_path:'publisher_archive_catchup',publication_clock:'unverified_archive',recovery_gap_id:gap.id},4,'news:'+await hash(item.url));
   Object.assign(state,{page:state.page+1,attempts:0,status:'partial_archive_discovery',source_url:url,source_sha256:sha256,object_key,discovered:items.length,next_attempt:new Date(Date.parse(now)+3600000).toISOString(),coverage_complete:false});
  }catch(error){state.attempts++;Object.assign(state,{status:'archive_unavailable',error:error.message,next_attempt:new Date(Date.parse(now)+Math.min(86400000,3600000*2**Math.min(state.attempts,4))).toISOString(),coverage_complete:false});}
  state.observed_at=now;await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(key,JSON.stringify(state),now).run();
  if(env.deadline&&Date.now()+3000>=env.deadline)break;
 }
}
