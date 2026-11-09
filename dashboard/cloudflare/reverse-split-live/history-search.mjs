import {etDay} from './core.mjs';
export const HISTORY_SEARCH_VERSION='history_cik.2026-11-09.v2';
export function historySearchURL(cik,{offset=0,start,end}={}){
 if(!/^\d{1,10}$/.test(String(cik))||!Number(cik)||!Number.isInteger(offset)||offset<0||offset>9900||offset%100||![start,end].every(d=>/^\d{4}-\d{2}-\d{2}$/.test(d||'')))throw new Error('Invalid bounded history search');
 const query='"reverse stock split" OR "reverse share split" OR "reverse split" OR "share consolidation"';
 return 'https://efts.sec.gov/LATEST/search-index?'+new URLSearchParams({q:query,ciks:String(cik).padStart(10,'0'),forms:'8-K,6-K',dateRange:'custom',startdt:start,enddt:end,from:String(offset),size:'100'});
}
export function historySearchPage(result,cik,{offset=0,end}={}){
 const total=result?.hits?.total,hits=result?.hits?.hits;if(!Number.isInteger(total?.value)||total.value<0||!['eq','gte'].includes(total.relation)||!Array.isArray(hits)||hits.length>100||(!hits.length&&total.value>offset))throw new Error('Incomplete or malformed SEC history inventory');
 const unique=new Map();for(const hit of hits){const source=hit._source,accession=source?.adsh;if(!Array.isArray(source?.ciks)||!source.ciks.some(v=>String(Number(v))===String(Number(cik)))||!/^\d{10}-\d{2}-\d{6}$/.test(accession||'')||!/^\d{4}-\d{2}-\d{2}$/.test(source.file_date||'')||source.file_date>end)throw new Error('SEC history hit issuer, accession or clock mismatch');unique.set(accession,{accession,filed:source.file_date});}
 const next=offset+hits.length,complete=total.relation==='eq'&&next>=total.value;if(!complete&&hits.length<100)throw new Error('Incomplete SEC history page');
 return {filings:[...unique.values()],total:total.value,next:complete||next>=10000?null:next,complete};
}
export async function queueHistorySearch(env,event,enqueue,now=new Date().toISOString()){
 const urgent=Date.parse(now)-Date.parse(event.first_seen_at)>=0&&Date.parse(now)-Date.parse(event.first_seen_at)<900000,day=etDay(now),id='history:v2:'+event.cik+':'+day+':0';
 await enqueue('history',{cik:event.cik,urgent},urgent?12:3,id);
 if(urgent){await env.DB.prepare("UPDATE rs_jobs SET priority=max(priority,12),payload=? WHERE id=? AND state='pending'").bind(JSON.stringify({cik:event.cik,urgent:true}),id).run();await env.DB.prepare("UPDATE rs_jobs SET priority=max(priority,11) WHERE kind='history_filing' AND state='pending' AND json_extract(payload,'$.cik')=?").bind(event.cik).run();}
}
export async function recoverHistorySearch(env,{enqueue,hash,now=new Date().toISOString()}={}){
 const marker='repair:'+HISTORY_SEARCH_VERSION;if(await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(marker).first())return {queued:0};
 const issuers=(await env.DB.prepare('SELECT DISTINCT i.cik,i.history_status FROM rs_issuers i JOIN rs_events e ON e.cik=i.cik ORDER BY i.cik LIMIT 20001').all()).results;
 const originals=(await env.DB.prepare("SELECT * FROM rs_jobs WHERE kind='history' ORDER BY created_at,id LIMIT 20001").all()).results;if(issuers.length>20000||originals.length>20000)throw new Error('History repair exceeds bounded archive size');
 const raw=JSON.stringify({schema:'reverse_split_history_repair.v1',version:HISTORY_SEARCH_VERSION,at:now,original_issuer_states:issuers,original_jobs:originals,reason:'SEC full-text search requires ten-digit CIKs; original unpadded searches could falsely return zero hits',historical_decisions_unchanged:true,not_original_clock_fills:true}),key='review/repairs/'+await hash(raw)+'.json';await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
 for(const row of issuers)await enqueue('history',{cik:row.cik},3,'history:v2:'+row.cik+':'+etDay(now)+':0');
 await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(marker,JSON.stringify({at:now,queued:issuers.length,originals:key,not_original_clock_fills:true}),now).run();return {queued:issuers.length};
}
