// Incremental broad queue seeding; expensive extraction stays in the financial lane.
import {createHash} from 'node:crypto';
export async function seedPreparedNeeds(env,queue,{pagesPerPass=4}={}){
 const read=async key=>{const o=await env.EVIDENCE.get(key);return o?o.json():null;},manifest=await read('prepared/manifest-latest.json');if(!manifest?.pages)return;
 // Listed issuers and normalized coverage pages can change before the SEC bulk ZIP does.
 const generation=createHash('sha256').update(JSON.stringify({source:manifest.summary?.source_archive_sha256,pages:manifest.pages})).digest('hex');
 if(queue.prepared_seed?.generation!==generation)queue.prepared_seed={generation,page:0,classified:0,queued:0};
 const seed=queue.prepared_seed,end=Math.min(manifest.pages.length,seed.page+pagesPerPass);
 for(;seed.page<end;seed.page++){
  const page=await read(manifest.pages[seed.page]);if(!page?.companies)throw new Error('Prepared coverage page unavailable; queue cursor preserved');
  for(const c of page.companies){seed.classified++;if(c.status==='current'||c.status==='not_applicable')continue;const cik=String(Number(c.cik)),old=queue.jobs[cik];if(!old){queue.jobs[cik]={cik,ticker:c.tickers?.length===1?c.tickers[0]:null,company:c.company,attempts:0,next_attempt:0,priority:c.status==='insufficient_components'?20:10,prepared_status:c.status,origin:'prepared_universe'};seed.queued++;}}
 }
 seed.complete=seed.page===manifest.pages.length;seed.updated_at=new Date().toISOString();return seed;
}
