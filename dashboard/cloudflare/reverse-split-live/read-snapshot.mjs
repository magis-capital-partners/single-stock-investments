// Worker-compatible bounded reads of the current committed research snapshot.
const json=(v,status=200)=>Response.json(v,{status,headers:{'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
const envelope={version:'reverse_split_shadow.v1',research_only:true,authority:'none',execution_ready:false,publication_mode:'private_snapshot'};
async function read(env,key){const o=await env.EVIDENCE.get('collector-dashboard/'+key);return o?await o.json():null;}
async function keyId(value){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(v=>v.toString(16).padStart(2,'0')).join('');}
const pair=(a,b)=>a[0]===b[0]?(a[1]<b[1]?-1:a[1]>b[1]?1:0):a[0]<b[0]?-1:1;
function cursor(value,initial){if(!value)return initial;const r=JSON.parse(atob(value));if(!Array.isArray(r)||r.length!==2||r.some(v=>typeof v!=='string'))throw new Error('Invalid cursor');return r;}
export async function readSnapshotAPI(url,env){
  if(url.pathname.startsWith('/shadow/announcement-quotes/')){
    const sha=url.pathname.slice('/shadow/announcement-quotes/'.length);if(!/^[a-f0-9]{64}$/.test(sha))return json({error:'Invalid quote archive'},400);
    const object=await env.EVIDENCE.get('announcement-quotes/'+sha+'.json');if(!object)return json({error:'Quote archive not found'},404);
    return new Response(object.body||await object.arrayBuffer(),{headers:{'content-type':'application/json','content-disposition':`attachment; filename="announcement-quotes-${sha}.json"`,'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
  }
  if(url.pathname==='/shadow/review-monitor'){const object=await env.EVIDENCE.get('review/monitor-latest.json');return object?json(await object.json()):json({error:'Independent review check has not run'},503);}
  const path=url.pathname,staticPaths={'/shadow':'shadow.json','/shadow/executable':'execution.json','/shadow/readiness':'readiness.json','/shadow/operations':'operations.json','/shadow/validation':'validation.json','/health':'health.json','/':'health.json'};
  if(path==='/shadow/validation'&&url.searchParams.has('run')){
    const id=url.searchParams.get('run');if(!/^rs_live_path_\d{4}-\d{2}-\d{2}\.v\d+$/.test(id||''))return json({error:'Invalid validation run'},400);
    const history=await env.EVIDENCE.get('validation/history-latest.json'),entry=history?(await history.json()).runs.find(r=>r.id===id):null;if(!entry||!/^validation\/results\/rs_live_path_[a-zA-Z0-9_.-]+-[a-f0-9]{64}\.json$/.test(entry.key))return json({error:'Archived validation run not found'},404);
    const object=await env.EVIDENCE.get(entry.key);if(!object)return json({error:'Archived validation data unavailable'},404);
    return new Response(object.body||await object.arrayBuffer(),{headers:{'content-type':'application/json','content-disposition':`attachment; filename="${id}.json"`,'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
  }
  if(path==='/shadow/operations'){const object=await env.EVIDENCE.get('collector-dashboard/operations.json');if(!object)return json({error:'Detailed readiness snapshot is not yet published'},503);return new Response(object.body||await object.arrayBuffer(),{headers:{'content-type':'application/json','cache-control':'no-store, private','x-content-type-options':'nosniff'}});}
  if(staticPaths[path]){const data=await read(env,staticPaths[path]);if(!data)return json({error:'Committed snapshot is not yet available'},503);if(path==='/shadow'){const runtime=await read(env,'runtime.json');if(runtime)data.runtime=runtime;const r=data.runtime,fresh=r?.heartbeat_at&&Date.now()-Date.parse(r.heartbeat_at)<180000;data.status=!fresh?'stale':r.status==='running'?(r.market_data?.quote_access==='received'?'tracking':'tracking_signals'):r.status;}return json(data);}
  if(path==='/events'){
    let before;try{before=cursor(url.searchParams.get('before'),['9999','']);}catch{return json({error:'Invalid event cursor'},400);}
    const limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||50)),q=(url.searchParams.get('q')||'').toUpperCase(),result=url.searchParams.get('result')||'';
    const rows=(await read(env,'events.json')||[]).filter(r=>(r.first_seen_at<before[0]||(r.first_seen_at===before[0]&&r.id>before[1]))&&(!result||r.result===result)&&(!q||[r.ticker,r.cik,r.company].some(v=>String(v||'').toUpperCase().includes(q))));
    return json({events:rows.slice(0,limit),policy:{id:'reverse_split_live.v1',research_only:true,authority:'none'},next_cursor:rows.length>limit?btoa(JSON.stringify([rows[limit-1].first_seen_at,rows[limit-1].id])):null,publication_mode:'private_snapshot'});
  }
  if(path.startsWith('/events/')){const value=await read(env,'events/'+await keyId(decodeURIComponent(path.slice(8)))+'.json');return value?json(value):null;}
  if(path==='/shadow/borrow'){
    const ticker=(url.searchParams.get('ticker')||'').toUpperCase(),limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||50));if(ticker&&!/^[A-Z][A-Z0-9.-]{0,11}$/.test(ticker))return json({error:'Invalid ticker'},400);
    let before;try{before=cursor(url.searchParams.get('before'),['9999','']);}catch{return json({error:'Invalid borrow cursor'},400);}
    const manifest=await read(env,'manifest.json');if(!manifest)return json({error:'Snapshot unavailable'},503);
    const days=manifest.days.filter(d=>d<=before[0].slice(0,10)),selected=days.slice(0,3);let rows=[];
    for(const day of selected)rows.push(...(await read(env,'borrow/'+day+'.json')||[]).filter(r=>(r.observed_at<before[0]||(r.observed_at===before[0]&&r.id>before[1]))&&(!ticker||r.ticker===ticker)));
    let next=null;if(rows.length>limit)next=btoa(JSON.stringify([rows[limit-1].observed_at,rows[limit-1].id]));else if(days.length>selected.length)next=btoa(JSON.stringify([selected.at(-1)+'T00:00:00','']));
    return json({...envelope,health:manifest.borrow_health,actual_charge_health:manifest.flex,observations:rows.slice(0,limit),next_cursor:next});
  }
  const executable=path.startsWith('/shadow/executable/tracks'),base=executable?'/shadow/executable/tracks':'/shadow/tracks';
  if(path!==base&&!path.startsWith(base+'/'))return null;
  if(path.startsWith(base+'/')){
    const trackId=decodeURIComponent(path.slice(base.length+1)),data=await read(env,'tracks/'+(executable?'execution/':'shadow/')+await keyId(trackId)+'.json');if(!data)return null;
    let after;try{after=cursor(url.searchParams.get(executable?'after':'before'),['','']);}catch{return json({error:'Invalid audit cursor'},400);}
    const limit=executable?25:100,pages=(data.record_index||[]).filter(p=>pair(p.last,after)>0);let all=data.records||[];
    if(pages.length){all=[];for(const page of pages.slice(0,2))all.push(...await read(env,page.key));}
    const records=all.filter(r=>pair([r.recorded_at,r.id],after)>0),more=records.length>limit||pages.length>2;
    return json({...envelope,track:data.track,records:records.slice(0,limit),evidence:data.evidence,fills_in_audit_records:executable,next_cursor:more&&records.length?btoa(JSON.stringify([records[Math.min(limit,records.length)-1].recorded_at,records[Math.min(limit,records.length)-1].id])):null});
  }
  const policy=(url.searchParams.get('policy')||'').slice(0,100),limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||50)),state=url.searchParams.get('state')||'',q=(url.searchParams.get('q')||'').toUpperCase();
  let before;try{before=cursor(url.searchParams.get('before'),['9999','']);}catch{return json({error:'Invalid shadow cursor'},400);}
  const cardKey='cards/'+(executable?'execution':'shadow'),afterId=(url.searchParams.get('after')||'').slice(0,400),index=await read(env,cardKey+(policy?'/policy/'+await keyId(policy):'')+'/index.json');
  const matchesCursor=r=>executable?r.id>afterId:r.enrolled_at<before[0]||(r.enrolled_at===before[0]&&r.id>before[1]);
  if(index?.schema==='reverse_split_track_pages.v1'){
    const pages=index.pages.filter(p=>matchesCursor(p.last)&&(!state||p.states.includes(state))&&(!q||p.lookup.some(v=>v.includes(q))));let rows=[],more=false;
    for(let n=0;n<pages.length;n++){
      const page=pages[n];if(!/^cards\/(?:shadow|execution)\/pages\/[a-f0-9]{64}\.json$/.test(page.key))return json({error:'Invalid private track page'},503);
      const items=await read(env,page.key);if(!Array.isArray(items))return json({error:'Committed track page unavailable'},503);
      rows.push(...items.filter(r=>matchesCursor(r)&&(!policy||r.policy_id===policy)&&(!state||r.state===state)&&(!q||[r.ticker,r.cik].some(v=>String(v||'').toUpperCase().includes(q)))));
      if(rows.length>limit){more=true;break;}if(rows.length===limit&&n<pages.length-1){more=true;break;}
    }
    const last=rows[Math.min(limit,rows.length)-1];return json({...envelope,tracks:rows.slice(0,limit),historical_data_status:'included',next_cursor:more&&last?(executable?last.id:btoa(JSON.stringify([last.enrolled_at,last.id]))):null});
  }
  const policyCards=policy?await read(env,cardKey+'/policy/'+await keyId(policy)+'.json'):null;
  const live=(policyCards||await read(env,cardKey+'.json')||[]).filter(r=>(!policy||r.policy_id===policy)&&(!state||r.state===state)&&(!q||[r.ticker,r.cik].some(v=>String(v||'').toUpperCase().includes(q))));
  // Older snapshots have only forward cards. Report this explicitly until the
  // next collector publication adds history; never silently fall back to a scan.
  const filtered=live.filter(r=>(!state||r.state===state)&&(!q||[r.ticker,r.cik].some(v=>String(v||'').toUpperCase().includes(q)))&&matchesCursor(r));
  filtered.sort(executable?(a,b)=>a.id<b.id?-1:a.id>b.id?1:0:(a,b)=>a.enrolled_at===b.enrolled_at?(a.id<b.id?-1:1):a.enrolled_at>b.enrolled_at?-1:1);
  return json({...envelope,tracks:filtered.slice(0,limit),historical_data_status:'awaiting_snapshot_rebuild',next_cursor:filtered.length>limit?(executable?filtered[limit-1].id:btoa(JSON.stringify([filtered[limit-1].enrolled_at,filtered[limit-1].id]))):null});
}
