// Public index parsing, independent of transport. Original disclosure clocks stay intact.
const forms=new Set(['8-K','8-K/A','6-K','6-K/A','10-Q','10-Q/A','10-K','10-K/A','20-F','20-F/A','40-F','40-F/A']);
export function parseDailyIndex(text,day){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!/^\s*CIK\s*\|\s*Company Name\s*\|\s*Form Type\s*\|\s*Date Filed\s*\|\s*File\s*Name\s*$/im.test(text))throw new Error('Invalid daily index: expected SEC pipe-delimited header');
 const rows=[];
 for(const line of text.split('\n')){const [cik,,form,rawDate,path]=line.trim().split('|'),filed=/^\d{8}$/.test(rawDate||'')?rawDate.slice(0,4)+'-'+rawDate.slice(4,6)+'-'+rawDate.slice(6):rawDate;if(!/^\d+$/.test(cik||'')||!forms.has(form)||filed!==day)continue;const match=/^edgar\/data\/\d+\/(\d{10}-\d{2}-\d{6})\.txt$/.exec(path||'');if(!match)continue;rows.push({cik:String(Number(cik)),accession:match[1],form,filed});}
 return rows;
}
export const repairedJobError=e=>/Filing index document identity or format is unsupported|Official filing index lacks an unambiguous primary report|Source exceeds document size limit|Announcement PDF requires verified readable text/.test(e||'');
export async function recoverReaderFailures(env,{version='document_readers.2026-11-09.v1',eligible=repairedJobError,hash,now=new Date().toISOString()}={}){
 const marker='repair:'+version;if(await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(marker).first())return {retried:0};
 const rows=(await env.DB.prepare("SELECT * FROM rs_jobs WHERE state='failed'").all()).results.filter(r=>['filing','history_filing'].includes(r.kind)&&eligible(r.error,r));
 for(const row of rows){const raw=JSON.stringify({schema:'reverse_split_repair_record.v1',version,recorded_at:now,original_job:row,action:'bounded_retry_after_reader_repair',historical_decisions_unchanged:true}),key='review/repairs/'+await hash(raw)+'.json';await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});await env.DB.prepare("UPDATE rs_jobs SET state='pending',attempts=0,token=NULL,lease_until=0,available_at=?,updated_at=? WHERE id=? AND state='failed' AND updated_at=?").bind(Date.now(),now,row.id,row.updated_at).run();}
 const rescoring=(await env.DB.prepare("SELECT * FROM rs_jobs WHERE kind='rescore' AND state='failed' AND error='Source returned HTTP 404'").all()).results;
 for(const row of rescoring){let payload;try{payload=JSON.parse(row.payload);}catch{continue;}const latest=await env.DB.prepare('SELECT payload,analyzed_at FROM rs_events WHERE id=?').bind(payload.id).first();if(!latest||latest.analyzed_at<=row.updated_at)continue;const event=JSON.parse(latest.payload);if(event.metadata_error||!event.financials?.source_sha256)continue;
  const raw=JSON.stringify({schema:'reverse_split_repair_record.v1',version,recorded_at:now,original_job:row,action:'superseded_by_later_source_recovery',later_analysis_at:latest.analyzed_at,source_sha256:event.financials.source_sha256,historical_decisions_unchanged:true});await env.EVIDENCE.put('review/repairs/'+await hash(raw)+'.json',new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});await env.DB.prepare("UPDATE rs_jobs SET state='complete',error=NULL,updated_at=? WHERE id=? AND state='failed' AND updated_at=?").bind(now,row.id,row.updated_at).run();
 }
 await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(marker,JSON.stringify({at:now,retried:rows.length,originals:'review/repairs/',not_original_clock_fills:true}),now).run();return {retried:rows.length};
}
