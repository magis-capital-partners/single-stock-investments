// Capture and encode expensive historical dashboard pages outside the collector.
// Input is a checksum-bound committed checkpoint, never the live working file.
import {parentPort,workerData} from 'node:worker_threads';
import {DatabaseSync} from 'node:sqlite';
import {writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {restoreCheckpoint} from './checkpoint-codec.mjs';
import {captureReadSnapshot} from './snapshot-publish.mjs';
import {operationalEvidence} from './operational-evidence.mjs';

const waiting=new Map(),encoder=new TextEncoder();let sequence=0;
function send(object,receipt,core=false,urgent=false){
  const value=object.key==='operations.json'?{...object.value,state_at:receipt.at}:object.value;
  const bytes=encoder.encode(JSON.stringify(value)),digest=createHash('sha256').update(bytes).digest('hex'),id=++sequence;
  return new Promise(resolve=>{waiting.set(id,resolve);parentPort.postMessage({type:'object',id,key:object.key,bytes:bytes.buffer,digest,core,urgent,stateAt:receipt.at,generatedAt:value?.generated_at},[bytes.buffer]);});
}
async function run(message){
  const file=join(workerData.dir,'snapshot.sqlite');let db,raw;
  try{
    if(!message.path){
      raw=await restoreCheckpoint(new Uint8Array(message.stored),message.receipt);
      message.stored=null;writeFileSync(file,raw);raw=null;
    }
    db=new DatabaseSync(message.path||file,{readOnly:true});
    // Without a separate refresher, hand off operations before dashboard
    // pages. Otherwise compute only the dashboard's compact operations view.
    const receipt=message.receipt, publishOperations=message.publishOperations!==false;
    const operations=operationalEvidence(db,undefined,{includeCandidates:publishOperations});
    if(publishOperations)await send({key:'operations.json',value:operations},receipt,true,true);
    const snapshot=captureReadSnapshot(db,{operations});
    for(let i=0;i<snapshot.objects.length;i++){
      const object=snapshot.objects[i];snapshot.objects[i]=null;
      if(object.key==='operations.json')continue;
      if((await send(object,receipt,i<5)).stop){parentPort.postMessage({type:'done',complete:false,at:snapshot.at});return;}
    }
    const days={};for(const row of snapshot.borrow)(days[row.observed_at.slice(0,10)]||=[]).push(row);
    snapshot.borrow=[];
    for(const [day,observations] of Object.entries(days)){
      if((await send({key:'borrow/'+day+'.json',value:observations},receipt)).stop){parentPort.postMessage({type:'done',complete:false,at:snapshot.at});return;}
    }
    const result=await send({key:'manifest.json',value:{at:snapshot.at,days:Object.keys(days).sort().reverse(),borrow_health:snapshot.borrowHealth,flex:snapshot.flex,envelope:snapshot.envelope}},receipt);
    parentPort.postMessage({type:'done',complete:!result.stop,at:snapshot.at});
  }catch(error){parentPort.postMessage({type:'failure',error:error.message});}
  finally{db?.close();rmSync(file,{force:true});}
}
parentPort.on('message',message=>{
  if(message.type==='ack'){const resolve=waiting.get(message.id);waiting.delete(message.id);resolve?.(message);}
  else if(message.type==='start')run(message);
});
