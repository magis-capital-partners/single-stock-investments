import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {digest,putState} from './shadow-service.mjs';
const run=promisify(execFile);
export async function pollPublicBorrow(env){
  const events=(await env.DB.prepare("SELECT DISTINCT event_id,ticker FROM rs_shadow_tracks WHERE ticker IS NOT NULL AND state IN ('armed','partial_entry','open','exit_pending') LIMIT 100").all()).results;
  if(!events.length)return;
  const tickers=[...new Set(events.map(e=>e.ticker))].filter(t=>/^[A-Z][A-Z0-9.-]{0,11}$/.test(t));if(!tickers.length)return;
  try{
    const {stdout}=await run(process.platform==='win32'?'python':'python3',[fileURLToPath(new URL('./public_borrow.py',import.meta.url)),'--tickers',tickers.join(',')],{timeout:25000,maxBuffer:1000000,windowsHide:true}),result=JSON.parse(stdout),key='borrow-evidence/'+await digest(stdout)+'.json';
    await env.EVIDENCE.put(key,new TextEncoder().encode(stdout),{httpMetadata:{contentType:'application/json'}});
    for(const e of events){const r=result.rows.find(x=>x.ticker===e.ticker),observation={...r,kind:'public_borrow',event_id:e.event_id,ticker:e.ticker,observed_at:result.observed_at,as_of:result.as_of,valid_until:new Date(Date.parse(result.as_of)+1800000).toISOString(),source_url:result.source_url,source_sha256:result.source_sha256,evidence_key:key,availability_only:true,locate_approved:false,not_in_public_file:!r},id=await digest(e.event_id+':'+JSON.stringify(observation));observation.id=id;await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(id,e.event_id,'public_borrow',result.observed_at,JSON.stringify(observation)).run();}
    await putState(env,'shadow_borrow_health',{status:'available',as_of:result.as_of,observed_at:result.observed_at,tickers:tickers.length,locate_approved:false});
  }catch{await putState(env,'shadow_borrow_health',{status:'unavailable',observed_at:new Date().toISOString(),message:'Public borrow file could not be validated; locate remains unverified.'});}
}
