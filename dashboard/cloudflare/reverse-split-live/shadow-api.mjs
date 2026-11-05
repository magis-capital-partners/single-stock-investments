import {SHADOW_VERSION} from './shadow-core.mjs';
const parse=r=>JSON.parse(r.payload),json=(d,status=200)=>Response.json(d,{status,headers:{'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
export async function shadowAPI(url,env){
  const get=key=>env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first().then(r=>r?JSON.parse(r.value):null);
  const envelope={version:SHADOW_VERSION,research_only:true,authority:'none',execution_ready:false};
  if(url.pathname==='/shadow/executable')return json({...envelope,summary:await get('execution_summary'),daily:(await env.DB.prepare('SELECT payload FROM rs_execution_daily ORDER BY day DESC LIMIT 500').all()).results.map(parse)});
  if(url.pathname==='/shadow/validation')return json({...envelope,summary:await get('validation_summary'),plan:await get('validation_plan')});
  if(url.pathname==='/shadow/borrow'){
    const ticker=(url.searchParams.get('ticker')||'').toUpperCase(),before=(url.searchParams.get('before')||'9999').slice(0,300),limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||50));
    if(ticker&&!/^[A-Z][A-Z0-9.-]{0,11}$/.test(ticker))return json({error:'Invalid ticker'},400);
    let cursor=['9999',''];if(before!=='9999')try{cursor=JSON.parse(atob(before));if(!Array.isArray(cursor)||cursor.length!==2||cursor.some(x=>typeof x!=='string'))throw new Error();}catch{return json({error:'Invalid borrow cursor'},400);}
    const rows=(await env.DB.prepare('SELECT id,observed_at,payload FROM rs_borrow_observations WHERE (observed_at<? OR (observed_at=? AND id>?))'+(ticker?' AND ticker=?':'')+' ORDER BY observed_at DESC,id LIMIT ?').bind(cursor[0],cursor[0],cursor[1],...(ticker?[ticker]:[]),limit+1).all()).results;
    return json({...envelope,health:await get('shadow_borrow_health'),actual_charge_health:await get('flex_borrow_health'),observations:rows.slice(0,limit).map(parse),next_cursor:rows.length>limit?btoa(JSON.stringify([rows[limit-1].observed_at,rows[limit-1].id])):null});
  }
  if(url.pathname==='/shadow/executable/tracks'){
    const policy=(url.searchParams.get('policy')||'').slice(0,100),limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||50)),after=(url.searchParams.get('after')||'').slice(0,400),rows=(await env.DB.prepare("SELECT id,json_remove(payload,'$.book','$.fills','$.daily_marks') AS payload FROM rs_execution_tracks WHERE id>?"+(policy?' AND policy_id=?':'')+' ORDER BY id LIMIT ?').bind(after,...(policy?[policy]:[]),limit+1).all()).results;
    return json({...envelope,tracks:rows.slice(0,limit).map(parse),next_cursor:rows.length>limit?rows[limit-1].id:null});
  }
  if(url.pathname.startsWith('/shadow/executable/tracks/')){
    const id=decodeURIComponent(url.pathname.slice('/shadow/executable/tracks/'.length)),row=await env.DB.prepare("SELECT json_remove(payload,'$.book','$.fills','$.daily_marks') AS payload FROM rs_execution_tracks WHERE id=?").bind(id).first();if(!row)return json({error:'Executable shadow track not found'},404);
    const after=url.searchParams.get('after')||'';let cursor=['',''];if(after)try{cursor=JSON.parse(atob(after));if(!Array.isArray(cursor)||cursor.length!==2||cursor.some(x=>typeof x!=='string'))throw new Error();}catch{return json({error:'Invalid audit cursor'},400);}
    const records=(await env.DB.prepare('SELECT * FROM rs_execution_records WHERE track_id=? AND (recorded_at>? OR (recorded_at=? AND id>?)) ORDER BY recorded_at,id LIMIT 26').bind(id,cursor[0],cursor[0],cursor[1]).all()).results;
    return json({...envelope,track:parse(row),fills_in_audit_records:true,records:records.slice(0,25).map(r=>({...r,payload:parse(r)})),next_cursor:records.length>25?btoa(JSON.stringify([records[24].recorded_at,records[24].id])):null});
  }
  if(url.pathname==='/shadow'){
    const [summary,runtime,policies,daily]=await Promise.all([get('shadow_summary'),get('shadow_runtime'),env.DB.prepare('SELECT * FROM rs_shadow_policies ORDER BY registered_at,id').all(),env.DB.prepare('SELECT payload FROM rs_shadow_daily ORDER BY day DESC,policy_id LIMIT 1500').all()]);
    const [execution,validation,borrow,charged,borrowRows,executableTracks]=await Promise.all([get('execution_summary'),get('validation_summary'),get('shadow_borrow_health'),get('flex_borrow_health'),env.DB.prepare('SELECT payload FROM rs_borrow_observations ORDER BY observed_at DESC,id LIMIT 50').all(),env.DB.prepare("SELECT json_remove(payload,'$.book','$.fills','$.daily_marks') AS payload FROM rs_execution_tracks WHERE state<>'retrospective' ORDER BY updated_at DESC LIMIT 100").all()]);
    const fresh=runtime?.heartbeat_at&&Date.now()-Date.parse(runtime.heartbeat_at)<Math.max(90000,(runtime.interval_seconds||15)*6000);
    return json({version:SHADOW_VERSION,research_only:true,authority:'none',summary,runtime,policies:policies.results.map(r=>({...parse(r),registered_at:r.registered_at})),daily:daily.results.map(parse),execution,validation,borrow:{health:borrow,actual_charge_health:charged,observations:borrowRows.results.map(parse)},executable_tracks:executableTracks.results.map(parse),status:!runtime?'not_started':fresh?(summary?.market_data?.quote_access==='received'?'tracking':'tracking_signals'):'stale',execution_ready:false});
  }
  if(url.pathname==='/shadow/tracks'){
    const limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||50)),policy=(url.searchParams.get('policy')||'').slice(0,80),status=(url.searchParams.get('state')||'').slice(0,40),q=(url.searchParams.get('q')||'').slice(0,80).toUpperCase();let cursor=['9999',''];
    if(url.searchParams.has('before'))try{cursor=JSON.parse(atob(url.searchParams.get('before')));if(!Array.isArray(cursor)||cursor.length!==2||cursor.some(x=>typeof x!=='string'))throw new Error();}catch{return json({error:'Invalid shadow cursor'},400);}
    const sql='SELECT payload,enrolled_at,id FROM rs_shadow_tracks WHERE (enrolled_at<? OR (enrolled_at=? AND id>?))'+(policy?' AND policy_id=?':'')+(status?' AND state=?':'')+(q?" AND (UPPER(COALESCE(ticker,'')) LIKE ? OR UPPER(COALESCE(cik,'')) LIKE ?)":'')+' ORDER BY enrolled_at DESC,id LIMIT ?',params=[cursor[0],cursor[0],cursor[1],...(policy?[policy]:[]),...(status?[status]:[]),...(q?['%'+q+'%','%'+q+'%']:[]),limit+1],rows=(await env.DB.prepare(sql).bind(...params).all()).results,more=rows.length>limit;
    return json({version:SHADOW_VERSION,research_only:true,authority:'none',tracks:rows.slice(0,limit).map(parse),next_cursor:more?btoa(JSON.stringify([rows[limit-1].enrolled_at,rows[limit-1].id])):null});
  }
  if(url.pathname.startsWith('/shadow/tracks/')){
    const id=decodeURIComponent(url.pathname.slice('/shadow/tracks/'.length)),row=await env.DB.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(id).first();if(!row)return json({error:'Shadow record not found'},404);
    const before=(url.searchParams.get('before')||'').slice(0,300);let cursor=['',''];if(before)try{cursor=JSON.parse(atob(before));if(!Array.isArray(cursor)||cursor.length!==2||cursor.some(x=>typeof x!=='string'))throw new Error();}catch{return json({error:'Invalid audit cursor'},400);}
    const records=(await env.DB.prepare('SELECT * FROM rs_shadow_records WHERE track_id=? AND (recorded_at>? OR (recorded_at=? AND id>?)) ORDER BY recorded_at,id LIMIT 101').bind(id,cursor[0],cursor[0],cursor[1]).all()).results;
    const evidence=(await env.DB.prepare('SELECT payload FROM rs_shadow_evidence WHERE event_id=? ORDER BY observed_at DESC LIMIT 100').bind(parse(row).event_id).all()).results;
    return json({version:SHADOW_VERSION,research_only:true,authority:'none',track:parse(row),records:records.slice(0,100).map(r=>({...r,payload:parse(r)})),evidence:evidence.map(parse),next_cursor:records.length>100?btoa(JSON.stringify([records[99].recorded_at,records[99].id])):null});
  }
  return json({error:'Not found'},404);
}
