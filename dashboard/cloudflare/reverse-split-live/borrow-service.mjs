import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {digest,putState} from './shadow-service.mjs';
import {etDay} from './core.mjs';
import {at} from './shadow-core.mjs';
const run=promisify(execFile);
export async function pollIBKRBorrow(env,{now=new Date().toISOString(),fetchRows}={}){
  const events=(await env.DB.prepare('SELECT DISTINCT id AS event_id,ticker FROM rs_events WHERE ticker IS NOT NULL').all()).results;
  const tickers=[...new Set(events.map(e=>e.ticker))].filter(t=>/^[A-Z][A-Z0-9.-]{0,11}$/.test(t));if(!tickers.length)return;
  const get=async key=>JSON.parse((await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first())?.value||'null');
  const day=etDay(now),phaseAt=value=>{const time=new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));return time<'08:35'?'overnight':time<'16:15'?'day':'after_close';},phase=phaseAt(now);
  const last=await get('ibkr_borrow_poll'),active=(await env.DB.prepare("SELECT DISTINCT ticker FROM rs_execution_tracks WHERE state IN ('armed','partial_entry','open','exit_pending') UNION SELECT DISTINCT ticker FROM rs_shadow_tracks WHERE state IN ('armed','partial_entry','open','exit_pending')").all()).results.map(r=>r.ticker);
  const activeEvents=new Set((await env.DB.prepare("SELECT DISTINCT event_id FROM rs_execution_tracks WHERE state IN ('armed','partial_entry','open','exit_pending') UNION SELECT DISTINCT event_id FROM rs_shadow_tracks WHERE state IN ('armed','partial_entry','open','exit_pending')").all()).results.map(r=>r.event_id));
  const all=!last||last.day!==day||(last.phase||phaseAt(last.at))!==phase,newNames=tickers.filter(t=>!last?.tickers?.includes(t)),newActive=active.some(t=>!last?.active_tickers?.includes(t));
  if(!all&&!newNames.length&&!newActive&&(!active.length||at(now)-at(last.active_at||last.at)<300000))return;
  const wanted=all?tickers:tickers.filter(t=>newNames.includes(t)||active.includes(t));if(!wanted.length)return;
  const attempt=await get('ibkr_borrow_attempt');if(attempt&&at(now)-at(attempt)<60000)return;
  await putState(env,'ibkr_borrow_attempt',now,now);
  try{
    const result=fetchRows?await fetchRows(wanted):JSON.parse((await run(process.platform==='win32'?'python':'python3',[fileURLToPath(new URL('./public_borrow.py',import.meta.url)),'--tickers',wanted.join(',')],{timeout:25000,maxBuffer:3000000,windowsHide:true})).stdout);
    if(!result.as_of||at(result.as_of)>at(now)+2000||!Array.isArray(result.rows))throw new Error('Invalid public-file clock');
    const raw=JSON.stringify({...result,universe:wanted}),key='borrow-evidence/ibkr/'+await digest(raw)+'.json';
    await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
    let quoted=0,missing=0;
    for(const ticker of wanted){
      const row=result.rows.find(x=>x.ticker===ticker),valid=row&&Number.isFinite(row.apr)&&row.apr>=0&&Number.isInteger(row.available_shares)&&row.available_shares>=0;
      const observation={...(row||{}),ticker,broker:'IBKR',kind:'indicative',status:valid?'quoted':row?'rate_or_inventory_missing':'not_in_public_file',apr:valid?row.apr:null,available_shares:row?.available_shares??null,day:etDay(result.as_of),as_of:result.as_of,observed_at:result.observed_at,recorded_at:now,source_url:result.source_url,source_sha256:result.source_sha256,evidence_key:key,availability_only:true,locate_approved:false,actually_charged:false,rate_unit:'annual_fraction',source_rate_unit:'percent'};
      observation.id=await digest(ticker+':'+result.as_of+':'+result.source_sha256);
      await env.DB.prepare('INSERT OR IGNORE INTO rs_borrow_observations VALUES(?,?,?,?,?,?,?)').bind(observation.id,ticker,observation.day,observation.kind,result.as_of,result.observed_at,JSON.stringify(observation)).run();
      if(valid)quoted++;else missing++;
      for(const event of events.filter(e=>e.ticker===ticker&&activeEvents.has(e.event_id))){
        const e={...observation,id:await digest(event.event_id+':'+observation.id),kind:'public_borrow',event_id:event.event_id,valid_until:new Date(at(result.as_of)+1800000).toISOString()};
        await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(e.id,e.event_id,e.kind,e.observed_at,JSON.stringify(e)).run();
      }
    }
    await putState(env,'shadow_borrow_health',{status:at(now)-at(result.as_of)<=1800000?'available':'stale',broker:'IBKR',as_of:result.as_of,observed_at:result.observed_at,universe_size:tickers.length,checked:wanted.length,quoted,missing,scope:all?'complete_resolved_universe':newNames.length?'new_and_active_names':'active_names',locate_approved:false,actual_charges:'awaiting_IBKR_Flex_borrow_fee_details'},now);
    await putState(env,'ibkr_borrow_poll',{day,phase,at:all?now:last.at,active_at:now,active_tickers:active,tickers:all?tickers:[...new Set([...(last?.tickers||[]),...newNames])]},now);
  }catch{
    for(const ticker of wanted){const id=await digest('unavailable:'+ticker+':'+day+':'+now.slice(0,13));await env.DB.prepare('INSERT OR IGNORE INTO rs_borrow_observations VALUES(?,?,?,?,?,?,?)').bind(id,ticker,day,'coverage',null,now,JSON.stringify({id,ticker,broker:'IBKR',kind:'coverage',day,observed_at:now,status:'source_unavailable',apr:null,available_shares:null,locate_approved:false,actually_charged:false})).run();}
    await putState(env,'shadow_borrow_health',{status:'unavailable',broker:'IBKR',observed_at:now,checked:wanted.length,universe_size:tickers.length,message:'IBKR public file unavailable or failed validation; missing rates are never zero.'},now);
  }
}
