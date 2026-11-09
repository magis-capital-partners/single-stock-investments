// Standby runners prepare dependencies while holding no feed or broker session.
export async function claimCollectorLease(remote,{owner,waitMs=0,clock=Date.now,sleep=ms=>new Promise(r=>setTimeout(r,ms)),shouldStop=()=>false,onWaiting=async()=>{}}){
 const start=clock(),deadline=start+Math.max(0,Math.min(1800000,waitMs));let attempts=0;
 await remote.prepare("INSERT OR IGNORE INTO rs_state(key,value,updated_at) VALUES('collector_lease','0',?)").bind(new Date(clock()).toISOString()).run();
 while(!shouldStop()){
  const now=clock(),lease=String(now+600000)+':'+owner,claimed=await remote.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_lease' AND CAST(value AS INTEGER)<=? RETURNING value").bind(lease,new Date(now).toISOString(),now).first();
  if(claimed)return {lease,waited_ms:clock()-start,attempts};
  attempts++;if(clock()>=deadline)return null;await onWaiting({at:new Date(clock()).toISOString(),attempts,waited_ms:clock()-start});await sleep(Math.min(5000,Math.max(1,deadline-clock())));
 }
 return null;
}
