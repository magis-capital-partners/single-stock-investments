import {readFileSync,writeFileSync,renameSync} from 'node:fs';
// Standby runners prepare dependencies while holding no feed or broker session.
// reclaimOwner: the owner id this host's previous collector process recorded
// (box R's RS_COLLECTOR_OWNER_FILE). A restarted process may take over that
// exact lease at once instead of waiting up to ten minutes for its own dead
// predecessor's lease to expire. Any other owner's unexpired lease is never
// displaced, and the predecessor's renew/save checks then fail and stop it.
const OWNER=/^[A-Za-z0-9-]{1,64}$/;
export async function claimCollectorLease(remote,{owner,reclaimOwner=null,waitMs=0,clock=Date.now,sleep=ms=>new Promise(r=>setTimeout(r,ms)),shouldStop=()=>false,onWaiting=async()=>{}}){
 const start=clock(),deadline=start+Math.max(0,Math.min(1800000,waitMs)),previous=typeof reclaimOwner==='string'&&OWNER.test(reclaimOwner)&&reclaimOwner!==owner?reclaimOwner:'';let attempts=0;
 await remote.prepare("INSERT OR IGNORE INTO rs_state(key,value,updated_at) VALUES('collector_lease','0',?)").bind(new Date(clock()).toISOString()).run();
 while(!shouldStop()){
  const now=clock(),lease=String(now+600000)+':'+owner,claimed=await remote.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_lease' AND (CAST(value AS INTEGER)<=? OR (?<>'' AND substr(value,instr(value,':')+1)=?)) RETURNING value").bind(lease,new Date(now).toISOString(),now,previous,previous).first();
  if(claimed)return {lease,waited_ms:clock()-start,attempts};
  attempts++;if(clock()>=deadline)return null;await onWaiting({at:new Date(clock()).toISOString(),attempts,waited_ms:clock()-start});await sleep(Math.min(5000,Math.max(1,deadline-clock())));
 }
 return null;
}
// The owner file is opt-in (unset on GitHub runners, which never restart in place).
export function readReclaimOwner(path){
 if(!path)return null;
 try{const value=readFileSync(path,'utf8').trim();return OWNER.test(value)?value:null;}catch{return null;}
}
export function recordOwner(path,owner){
 if(!path||!OWNER.test(String(owner||'')))return false;
 try{const temp=path+'.tmp';writeFileSync(temp,owner+'\n',{mode:0o600});renameSync(temp,path);return true;}
 catch(error){console.error(JSON.stringify({event:'collector_owner_file_unwritable',error:error.message}));return false;}
}
