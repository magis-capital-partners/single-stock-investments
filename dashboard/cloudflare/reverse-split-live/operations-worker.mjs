// Worker thread for operations-publication.mjs. It owns a read-only copy of the last
// committed checkpoint and evaluates operationalEvidence on it, off the collector's
// event loop. It never opens the live working database and makes no network call.
import {parentPort,workerData} from 'node:worker_threads';
import {DatabaseSync} from 'node:sqlite';
import {writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {operationalEvidence} from './operational-evidence.mjs';
import {operationsText,operationsDigest} from './operations-publication.mjs';
const GENERATION=/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
let db=null,file=null,generation=null;
function release(){try{db?.close();}finally{db=null;if(file)rmSync(file,{force:true});file=null;generation=null;}}
function load({generation:next,sha256,bytes}){
  if(!GENERATION.test(String(next)))throw new Error('Invalid checkpoint generation');
  const data=new Uint8Array(bytes);
  // Evaluate only the exact committed bytes: the receipt digest must match.
  if(operationsDigest(data)!==sha256)throw new Error('Committed checkpoint copy checksum mismatch');
  const path=join(workerData.dir,'durable-'+next+'.sqlite');let opened;
  try{writeFileSync(path,data);opened=new DatabaseSync(path,{readOnly:true});}catch(error){try{opened?.close();}finally{rmSync(path,{force:true});}throw error;}
  release();db=opened;file=path;generation=next;
}
parentPort.on('message',message=>{
  const {id,type}=message;
  try{
    if(type==='load'){load(message);parentPort.postMessage({id,ok:true,generation});}
    else if(type==='evaluate'){
      if(!db||message.generation!==generation)throw new Error('Committed checkpoint copy is not loaded');
      const text=operationsText(operationalEvidence(db,message.now),message.stateAt);
      parentPort.postMessage({id,ok:true,text,digest:operationsDigest(text)});
    }else if(type==='close'){release();parentPort.postMessage({id,ok:true});parentPort.close();}
    else throw new Error('Unknown operations worker request');
  }catch(error){parentPort.postMessage({id,ok:false,error:error.message});}
});
