// Fixed reporting endpoints only. Credentials never enter URLs in logs or R2.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {digest,putState} from './shadow-service.mjs';
import {etDay} from './core.mjs';
const BASE='https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/';
export async function pollFlexBorrow(env,{now=new Date().toISOString(),token=process.env.IBKR_FLEX_BORROW_TOKEN,query=process.env.IBKR_FLEX_BORROW_QUERY_ID,fetcher=fetch}={}){
  const state=async key=>JSON.parse((await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first())?.value||'null');
  if(!token||!query){if(!await state('flex_borrow_health'))await putState(env,'flex_borrow_health',{status:'not_configured',observed_at:now,required_secrets:['IBKR_FLEX_BORROW_TOKEN','IBKR_FLEX_BORROW_QUERY_ID'],required_query_section:'Borrow Fee Details',shadow_positions_have_no_actual_charged_fee:true},now);return;}
  if(!/^\d+$/.test(query))throw new Error('Invalid Flex query identifier');
  const day=etDay(now),previous=await state('flex_borrow_poll');if(previous?.day===day&&(previous.status==='complete'||previous.attempts>=6||Date.parse(now)-Date.parse(previous.at)<3600000))return;
  const next={day,at:now,attempts:previous?.day===day?previous.attempts+1:1,status:'pending',reference:previous?.day===day?previous.reference:null};
  await putState(env,'flex_borrow_poll',next,now);
  async function request(endpoint,q){const url=new URL(BASE+endpoint);url.search=new URLSearchParams({t:token,q,v:'3'});const r=await fetcher(url,{redirect:'error',signal:AbortSignal.timeout(15000),headers:{'user-agent':'MagisReverseSplitBorrow/1.0'}});if(!r.ok)throw new Error('Flex report request failed');const bytes=new Uint8Array(await r.arrayBuffer());if(bytes.length>8000000)throw new Error('Flex report too large');return new TextDecoder().decode(bytes);}
  try{
    if(!next.reference){const response=await request('SendRequest',query),reference=/<ReferenceCode>(\d+)<\/ReferenceCode>/.exec(response)?.[1];if(!reference)throw new Error('Flex report not ready');next.reference=reference;await putState(env,'flex_borrow_poll',next,now);return;}
    const xml=await request('GetStatement',next.reference);
    const result=await new Promise((resolve,reject)=>{const child=spawn(process.platform==='win32'?'python':'python3',[fileURLToPath(new URL('./flex_borrow.py',import.meta.url))],{stdio:['pipe','pipe','ignore'],windowsHide:true});let output='';const timer=setTimeout(()=>{child.kill();reject(new Error('Flex normalization timeout'));},15000);child.stdout.on('data',b=>{output+=b;if(output.length>3000000)child.kill();});child.on('error',reject);child.on('exit',code=>{clearTimeout(timer);try{if(code!==0)throw new Error();resolve(JSON.parse(output));}catch{reject(new Error('Flex borrow report unavailable or schema invalid'));}});child.stdin.on('error',()=>{});child.stdin.end(xml);});
    const names=new Set((await env.DB.prepare('SELECT DISTINCT ticker FROM rs_events WHERE ticker IS NOT NULL').all()).results.map(r=>r.ticker));
    // Raw account statements are deliberately not archived. Keep only matching,
    // account-redacted, immutable borrow rows with a hash of the original report.
    const rows=result.rows.filter(r=>names.has(r.ticker));const raw=JSON.stringify({rows,source_sha256:result.source_sha256,observed_at:now}),key='borrow-evidence/ibkr-flex/'+await digest(raw)+'.json';await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
    for(const row of rows){const id=await digest(JSON.stringify(row));await env.DB.prepare('INSERT OR IGNORE INTO rs_borrow_observations VALUES(?,?,?,?,?,?,?)').bind(id,row.ticker,row.day,row.kind,row.as_of,row.observed_at,JSON.stringify({...row,id,evidence_key:key})).run();}
    next.status='complete';await putState(env,'flex_borrow_poll',next,now);await putState(env,'flex_borrow_health',{status:'available',observed_at:now,matching_charged_rows:rows.length,source_sha256:result.source_sha256,shadow_positions_have_no_actual_charged_fee:true},now);
  }catch{await putState(env,'flex_borrow_health',{status:'unavailable',observed_at:now,attempts:next.attempts,message:'Read-only Flex report unavailable, incomplete or schema not validated; no actual fees inferred.'},now);}
}
