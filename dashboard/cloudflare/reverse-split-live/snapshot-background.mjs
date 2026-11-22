// One streamed page at a time returns to the existing leased R2 writer. Large
// SQL reads and JSON encoding never run on the collector's event loop.
import {Worker} from 'node:worker_threads';
import {mkdtempSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname,basename} from 'node:path';

function cleanup(dir){
  const target=realpathSync(dir),parent=realpathSync(tmpdir());
  const same=(a,b)=>process.platform==='win32'?a.toLowerCase()===b.toLowerCase():a===b;
  if(!same(dirname(target),parent)||!basename(target).startsWith('reverse-split-snapshot-'))throw new Error('Unsafe snapshot worker directory');
  rmSync(target,{recursive:true,force:true});
}
export async function publishCheckpointSnapshot(env,db,{stored,receipt},{shouldYield=()=>false,operations=null,timeoutMs=180000}={}){
  const dir=mkdtempSync(join(tmpdir(),'reverse-split-snapshot-'));
  const worker=new Worker(new URL('./snapshot-worker.mjs',import.meta.url),{workerData:{dir}});
  let pending=Promise.resolve(),settled=false,timer;
  try{
    return await new Promise((resolve,reject)=>{
      const fail=error=>{if(!settled){settled=true;clearTimeout(timer);reject(error);}};
      timer=setTimeout(()=>fail(new Error('Background dashboard publication timed out')),timeoutMs);
      worker.on('error',fail);
      worker.on('exit',code=>{if(!settled)fail(new Error('Snapshot worker exited before completion ('+code+')'));});
      worker.on('message',message=>{
        if(message.type==='failure'){fail(new Error(message.error));return;}
        if(message.type==='done'){if(!settled){settled=true;clearTimeout(timer);resolve({complete:message.complete,at:message.at});}return;}
        if(message.type!=='object'||settled)return;
        pending=pending.then(async()=>{
          if(settled)return;
          if(!message.core&&shouldYield()){worker.postMessage({type:'ack',id:message.id,stop:true});return;}
          env.assertCollectorLease?.();
          const bytes=new Uint8Array(message.bytes),marker='snapshot:'+message.key;
          if(operations&&message.key==='operations.json'){
            const published=await operations.publish({text:new TextDecoder().decode(bytes),digest:message.digest,stateAt:message.stateAt,generatedAt:message.generatedAt,urgent:message.urgent===true,kind:'full_checkpoint'});
            if(!published.published&&!['superseded','unchanged'].includes(published.reason))throw new Error('Operations publication refused: '+published.reason);
          }else if(db.prepare('SELECT value FROM rs_state WHERE key=?').get(marker)?.value!==message.digest){
            await env.EVIDENCE.put('collector-dashboard/'+message.key,bytes,{httpMetadata:{contentType:'application/json'}});
            db.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(marker,message.digest,receipt.at);
          }
          worker.postMessage({type:'ack',id:message.id,stop:false});
        }).catch(fail);
      });
      const input=Uint8Array.from(stored);
      worker.postMessage({type:'start',stored:input.buffer,receipt},[input.buffer]);
    });
  }finally{
    clearTimeout(timer);await pending.catch(()=>{});await worker.terminate().catch(()=>{});cleanup(dir);
  }
}
