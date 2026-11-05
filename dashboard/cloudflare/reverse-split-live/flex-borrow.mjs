// Fixed reporting endpoints only. Credentials never enter URLs in logs or R2.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {digest,putState} from './shadow-service.mjs';
import {etDay} from './core.mjs';
import {sessions,at} from './shadow-core.mjs';
const BASE='https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/';
const REPORT_URLS=new Set([BASE+'GetStatement','https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement']);
export async function pollFlexBorrow(env,{now=new Date().toISOString(),token=process.env.IBKR_FLEX_BORROW_TOKEN,query=process.env.IBKR_FLEX_BORROW_QUERY_ID,fetcher=fetch,normalizeReport}={}){
  const state=async key=>JSON.parse((await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first())?.value||'null');
  if(!token||!query){if(!await state('flex_borrow_health'))await putState(env,'flex_borrow_health',{status:'not_configured',observed_at:now,required_secrets:['IBKR_FLEX_BORROW_TOKEN','IBKR_FLEX_BORROW_QUERY_ID'],required_query_section:'Borrow Fee Details',shadow_positions_have_no_actual_charged_fee:true},now);return;}
  if(!/^\d+$/.test(query))throw new Error('Invalid Flex query identifier');
  const time=new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(now));
  if(time<'08:35'){const health=await state('flex_borrow_health');if(!health||health.status==='not_configured')await putState(env,'flex_borrow_health',{status:'configured_waiting_daily_window',observed_at:now,next_daily_window:'08:35 America/New_York',shadow_positions_have_no_actual_charged_fee:true},now);return;}
  const day=etDay(now),previous=await state('flex_borrow_poll');if(previous?.day===day&&(previous.status==='complete'||previous.attempts>=12||Date.parse(now)<Date.parse(previous.next_attempt_at||previous.at)))return;
  const next={day,at:now,attempts:previous?.day===day?previous.attempts+1:1,status:'pending',reference:previous?.day===day?previous.reference:null,report_url:previous?.day===day&&REPORT_URLS.has(previous.report_url)?previous.report_url:BASE+'GetStatement'};
  next.next_attempt_at=new Date(at(now)+60000).toISOString();
  await putState(env,'flex_borrow_poll',next,now);
  async function request(endpoint,q){const url=new URL(endpoint==='GetStatement'?next.report_url:BASE+endpoint);url.search=new URLSearchParams({t:token,q,v:'3'});const r=await fetcher(url,{redirect:'error',signal:AbortSignal.timeout(120000),headers:{'user-agent':'MagisReverseSplitBorrow/1.0'}});if(!r.ok)throw new Error('Flex report request failed');const chunks=[],reader=r.body.getReader();let length=0;for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>128000000){await reader.cancel();throw new Error('Flex report too large');}chunks.push(value);}const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}return new TextDecoder().decode(bytes);}
  try{
    if(!next.reference){const response=await request('SendRequest',query),reference=/<ReferenceCode>(\d+)<\/ReferenceCode>/.exec(response)?.[1],reportURL=/<url>([^<]+)<\/url>/.exec(response)?.[1];if(!reference)throw new Error('Flex report not ready');if(reportURL&&!REPORT_URLS.has(reportURL))throw new Error('Unsupported reporting endpoint');next.reference=reference;next.report_url=reportURL||BASE+'GetStatement';await putState(env,'flex_borrow_poll',next,now);return;}
    const xml=await request('GetStatement',next.reference);
    const errorCode=/<ErrorCode>(\d+)<\/ErrorCode>/.exec(xml.slice(0,10000))?.[1];
    if(errorCode){
      if(['1020','1017'].includes(errorCode))next.reference=null;
      if(errorCode==='1018')next.next_attempt_at=new Date(at(now)+300000).toISOString();
      await putState(env,'flex_borrow_poll',next,now);await putState(env,'flex_borrow_health',{status:['1019','1009','1018'].includes(errorCode)?'report_pending':'unavailable',observed_at:now,attempts:next.attempts,next_attempt_at:next.next_attempt_at,provider_code:errorCode,shadow_positions_have_no_actual_charged_fee:true},now);return;
    }
    const names=new Set((await env.DB.prepare('SELECT DISTINCT ticker FROM rs_events WHERE ticker IS NOT NULL').all()).results.map(r=>r.ticker));
    const result=normalizeReport?await normalizeReport(xml,[...names]):await new Promise((resolve,reject)=>{const child=spawn(process.platform==='win32'?'python':'python3',[fileURLToPath(new URL('./flex_borrow.py',import.meta.url)),'--tickers',[...names].join(',')],{stdio:['pipe','pipe','ignore'],windowsHide:true});let output='';const timer=setTimeout(()=>{child.kill();reject(new Error('Flex normalization timeout'));},60000);child.stdout.on('data',b=>{output+=b;if(output.length>16000000)child.kill();});child.on('error',reject);child.on('exit',code=>{clearTimeout(timer);try{if(code!==0)throw new Error();resolve(JSON.parse(output));}catch{reject(new Error('Flex borrow report unavailable or schema invalid'));}});child.stdin.on('error',()=>{});child.stdin.end(xml);});
    // Raw account statements are deliberately not archived. Keep only matching,
    // account-redacted, immutable borrow rows with a hash of the original report.
    const rows=result.rows.filter(r=>names.has(r.ticker));const raw=JSON.stringify({rows,source_sha256:result.source_sha256,report_to_date:result.report_to_date,observed_at:now}),key='borrow-evidence/ibkr-flex/'+await digest(raw)+'.json';await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
    let added=0;for(const row of rows){if(!/^[a-f0-9]{64}$/.test(row.observation_key||''))throw new Error('Stable Flex observation identity required');const id=row.observation_key,{components,...canonical}=row;added+=Number((await env.DB.prepare('INSERT OR IGNORE INTO rs_borrow_observations VALUES(?,?,?,?,?,?,?)').bind(id,row.ticker,row.day,row.kind,row.as_of,row.observed_at,JSON.stringify({...canonical,id,evidence_key:key})).run()).meta?.changes||0);}
    const expected=sessions.filter(s=>at(s.close)<at(now)).at(-1)?.day,stale=expected&&result.report_to_date<expected;
    next.status=stale?'stale_report':'complete';if(stale){next.reference=null;next.next_attempt_at=new Date(at(now)+3600000).toISOString();}
    await putState(env,'flex_borrow_poll',next,now);await putState(env,'flex_borrow_health',{status:stale?'stale_report':'available',observed_at:now,matching_charged_rows:rows.length,new_charged_rows:added,report_to_date:result.report_to_date,expected_completed_session:expected,lookback_days:result.lookback_days,source_sha256:result.source_sha256,shadow_positions_have_no_actual_charged_fee:true},now);
  }catch{await putState(env,'flex_borrow_health',{status:'unavailable',observed_at:now,attempts:next.attempts,message:'Read-only Flex report unavailable, incomplete or schema not validated; no actual fees inferred.'},now);}
}
