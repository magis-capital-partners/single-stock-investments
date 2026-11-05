import {SHADOW_VERSION} from './shadow-core.mjs';
const parse=r=>JSON.parse(r.payload),json=(d,status=200)=>Response.json(d,{status,headers:{'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
export async function shadowAPI(url,env){
  const get=key=>env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first().then(r=>r?JSON.parse(r.value):null);
  if(url.pathname==='/shadow'){
    const [summary,runtime,policies,daily]=await Promise.all([get('shadow_summary'),get('shadow_runtime'),env.DB.prepare('SELECT * FROM rs_shadow_policies ORDER BY registered_at,id').all(),env.DB.prepare('SELECT payload FROM rs_shadow_daily ORDER BY day DESC,policy_id LIMIT 1500').all()]);
    const fresh=runtime?.heartbeat_at&&Date.now()-Date.parse(runtime.heartbeat_at)<Math.max(90000,(runtime.interval_seconds||15)*6000);
    return json({version:SHADOW_VERSION,research_only:true,authority:'none',summary,runtime,policies:policies.results.map(r=>({...parse(r),registered_at:r.registered_at})),daily:daily.results.map(parse),status:!runtime?'not_started':fresh?(summary?.market_data?.quote_access==='received'?'tracking':'tracking_signals'):'stale',execution_ready:false});
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
