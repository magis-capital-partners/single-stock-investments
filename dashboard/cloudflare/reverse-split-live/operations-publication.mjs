// Node-only. Keeps collector-dashboard/operations.json fresh between checkpoints
// without publishing anything that is not already durable.
//
// A full save captures the views from the exact bytes it checkpoints and publishes
// them only after the checkpoint pointer commits. Between saves, the refresher
// re-evaluates operationalEvidence over a byte-identical copy of the LAST COMMITTED
// checkpoint. The next report can be prepared while storage runs, but can only
// publish once that exact generation commits. Every count, candidate and decision
// comes from durable state: a restart restores that generation or a newer one, so
// no published candidate can vanish or regress. Only clock-relative fields
// (`generated_at`, source/heartbeat ages, entry windows) move forward; `state_at`
// names the checkpoint the content came from. Evaluation runs on a worker thread,
// so it never blocks quote, exit or validation work, and it makes no database call.
import {Worker} from 'node:worker_threads';
import {createHash,randomUUID} from 'node:crypto';
import {mkdtempSync,rmSync,realpathSync,mkdirSync,appendFileSync,readFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname,basename} from 'node:path';
import {compressCheckpoint} from './checkpoint-codec.mjs';

export const OPERATIONS_KEY='collector-dashboard/operations.json';
export const OPERATIONS_STAGING_KEY='collector-dashboard/operations-upload.json.gz';
const MARKER='snapshot:operations.json',encoder=new TextEncoder();
export const operationsDigest=text=>createHash('sha256').update(text).digest('hex');
export const operationsText=(value,stateAt)=>JSON.stringify({...value,state_at:stateAt});
const clockOf=value=>{const ms=Date.parse(value);if(!Number.isFinite(ms))throw new Error('Operations publication requires ISO state and generation times');return ms;};

// RS_OPERATIONS_PUBLISH_SECONDS: refresh target while collecting (default 30; 0 disables).
// RS_OPERATIONS_MAX_STATE_AGE_SECONDS: stop refreshing once the last committed
// checkpoint is older than this (default and maximum 120), so a stalled checkpoint cannot be
// kept looking fresh; the executor's own 120-second rule then fails closed.
export function operationsRefreshSettings(source=process.env){
  const read=(name,fallback,min,max)=>{const raw=source?.[name];if(raw===undefined||raw===null||String(raw).trim()==='')return fallback;const n=Number(raw);if(!Number.isFinite(n)||n<0)return fallback;return n===0?0:Math.min(max,Math.max(min,n));};
  const interval=read('RS_OPERATIONS_PUBLISH_SECONDS',30,5,110),maxAge=read('RS_OPERATIONS_MAX_STATE_AGE_SECONDS',120,30,120)||120;
  return {intervalMs:interval*1000,maxStateAgeMs:maxAge*1000};
}

// The session's stage and publication P95s together consumed about 6.5s.
const publicationHeadroom=ageMs=>Math.min(8000,Math.floor(ageMs/8));

// The only writer of operations.json for a checkpoint: full snapshots and refreshes
// share one queue, so two puts are never in flight for the key and the published
// state never moves back to an older checkpoint.
export function operationsChannel(env,{db=null,clock=Date.now,maxStateAgeMs=operationsRefreshSettings({...process.env,...env}).maxStateAgeMs}={}){
  let tail=Promise.resolve(),last=null;
  maxStateAgeMs=Math.min(120000,Math.max(1000,maxStateAgeMs));
  const minimumHeadroomMs=publicationHeadroom(maxStateAgeMs);
  const auditDir=env.RS_OPERATIONS_AUDIT_DIR||process.env.RS_OPERATIONS_AUDIT_DIR;
  const record=row=>{env.onOperationsAudit?.(row);if(auditDir){mkdirSync(auditDir,{recursive:true});appendFileSync(join(auditDir,row.at.slice(0,10)+'.jsonl'),JSON.stringify(row)+'\n',{flush:true});}};
  const readMarker=()=>db?db.prepare('SELECT value FROM rs_state WHERE key=?').get(MARKER)?.value??null:null;
  const writeMarker=(digest,at)=>{db?.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(MARKER,digest,at);};
  return {
    last:()=>last,
    record,
    async archiveAudit(day=new Date(clock()).toISOString().slice(0,10)){
      if(!auditDir)return;
      const path=join(auditDir,day+'.jsonl');if(!existsSync(path))return;
      const data=readFileSync(path);if(data.length>32000000)throw new Error('Operations audit exceeded its daily bound');
      await env.EVIDENCE.put('collector-dashboard/operations-audit/'+day+'.jsonl',data,{httpMetadata:{contentType:'application/x-ndjson'}});
    },
    idle:()=>tail.catch(()=>{}),
    publish({text,digest=null,stateAt,generatedAt,urgent=false,kind=urgent?'refresh':'full_checkpoint',renderMode=null}){
      const queuedAt=clock();
      const task=tail.catch(()=>{}).then(async()=>{
        const state=clockOf(stateAt),generated=clockOf(generatedAt),seen={state,generated,stateAt,generatedAt};
        if(last&&(state<last.state||(state===last.state&&generated<=last.generated)))return {published:false,reason:'superseded'};
        env.assertCollectorLease?.();
        const started=clock(),at=new Date(started).toISOString();
        const remainingAtStart=maxStateAgeMs-(started-state);
        let reason=null;
        if(remainingAtStart<0)reason='paused_checkpoint_too_old';
        else if(state-started>2000||generated-started>2000)reason='future_source_clock';
        else if(remainingAtStart<minimumHeadroomMs)reason='insufficient_publication_headroom';
        if(reason){
          record({event:'publication_refused',at,reason,kind,state_at:stateAt,generated_at:generatedAt,queue_wait_ms:started-queuedAt,max_state_age_seconds:maxStateAgeMs/1000});
          return {published:false,reason};
        }
        const hash=digest||operationsDigest(text);
        if(readMarker()===hash){last=seen;return {published:false,reason:'unchanged'};}
        const id=randomUUID(),receiptKey='collector-dashboard/operations-receipts/'+at.slice(0,10)+'/'+id+'.json';
        const content=JSON.stringify({...JSON.parse(text),publication:{id,receipt_key:receiptKey,upload_started_at:at}}),reportHash=operationsDigest(content);
        const receipt={schema:'rs_operations_publication_receipt.v1',publication_id:id,report_sha256:reportHash,report_bytes:Buffer.byteLength(content),state_at:stateAt,generated_at:generatedAt,kind,queued_at:new Date(queuedAt).toISOString(),upload_started_at:at,upload_completed_at:null,accepted:false,max_state_age_seconds:maxStateAgeMs/1000,publish_interval_seconds:operationsRefreshSettings().intervalMs/1000,pipeline_commit:process.env.RS_PIPELINE_COMMIT||null};
        if(renderMode)receipt.render_mode=renderMode;
        const bytes=encoder.encode(content);
        const remaining=()=>maxStateAgeMs-(clock()-state);
        const write=async(key,body,contentType)=>{
          env.assertCollectorLease?.();
          const budget=Math.min(15000,remaining());
          if(budget<=0)throw new Error('Operations publication freshness budget expired');
          await env.EVIDENCE.put(key,body,{httpMetadata:{contentType},urgent:true,signal:AbortSignal.timeout(budget)});
        };
        try{
          // Stage the complete report in a private, reusable slot. The receipt
          // timestamps the acknowledged upload of this exact report (gzip on
          // the wire), and binds the original bytes delivered to readers.
          const staged=await compressCheckpoint(bytes);
          receipt.upload_started_at=new Date(clock()).toISOString();
          receipt.visibility_mode='after_receipt';
          await write(OPERATIONS_STAGING_KEY,staged.stored,'application/gzip');
          const completed=clock();receipt.upload_completed_at=new Date(completed).toISOString();
          receipt.state_age_at_upload_completion_seconds=(completed-state)/1000;
          receipt.accepted=completed>=Date.parse(receipt.upload_started_at)&&completed-state>=-2000&&completed-state<=maxStateAgeMs;
          receipt.outcome=receipt.accepted?'acknowledged':'state_too_old_at_ack';
        }catch(error){
          receipt.outcome='upload_outcome_unknown';receipt.error_type=error.name;
          record({event:'publication_upload',at:new Date(clock()).toISOString(),...receipt});
          throw error;
        }
        record({event:'publication_upload',at:receipt.upload_completed_at,...receipt});
        if(!receipt.accepted)return {published:false,reason:'state_too_old_at_ack',receipt};
        try{
          await write(receiptKey,encoder.encode(JSON.stringify(receipt)),'application/json');
        }catch(error){record({event:'receipt_archive_failed',at:new Date(clock()).toISOString(),publication_id:id,report_sha256:reportHash,error_type:error.name});throw error;}
        // Preserve the existing report key and JSON format. A reader can only
        // see these new bytes after the corresponding receipt is durable.
        try{
          await write(OPERATIONS_KEY,bytes,'application/json');
        }catch(error){record({event:'publication_visibility_failed',at:new Date(clock()).toISOString(),publication_id:id,report_sha256:reportHash,error_type:error.name});throw error;}
        const visibleAt=clock();
        record({event:'publication_visible',at:new Date(visibleAt).toISOString(),publication_id:id,report_sha256:reportHash,state_age_at_visibility_ack_seconds:(visibleAt-state)/1000});
        last={...seen,visibleAt,uploadCompletedAt:receipt.upload_completed_at,receiptKey,reportHash};
        writeMarker(hash,generatedAt);return {published:true,receipt};
      });
      tail=task;return task;
    },
  };
}

function removeScratch(dir){
  if(!dir)return;const target=realpathSync(dir),parent=realpathSync(tmpdir()),same=(a,b)=>process.platform==='win32'?a.toLowerCase()===b.toLowerCase():a===b;
  if(!same(dirname(target),parent)||!basename(target).startsWith('reverse-split-operations-'))throw new Error('Unsafe operations refresh directory');
  rmSync(target,{recursive:true,force:true});
}

function operationsWorker(workerURL,timeoutMs){
  const waiting=new Map();
  let worker=null,dir=null,sequence=0,closed=false,closing=null,stopping=Promise.resolve();
  function settle(error){for(const [id,w] of waiting){clearTimeout(w.timer);waiting.delete(id);w.reject(error);}}
  function stopWorker(){
    if(!worker&&!dir)return stopping;
    const current=worker,scratch=dir;worker=null;dir=null;
    stopping=(async()=>{
      if(current){current.removeAllListeners();current.on('error',()=>{});await current.terminate().catch(()=>{});}
      try{removeScratch(scratch);}catch(error){console.error(JSON.stringify({event:'operations_refresh_cleanup_deferred',error:error.message}));}
    })();
    return stopping;
  }
  function start(){
    dir=mkdtempSync(join(tmpdir(),'reverse-split-operations-'));
    const current=new Worker(workerURL,{workerData:{dir}});worker=current;current.unref();
    current.on('message',m=>{const w=waiting.get(m.id);if(!w)return;clearTimeout(w.timer);waiting.delete(m.id);if(m.ok)w.resolve(m);else w.reject(new Error(m.error||'Operations evaluation failed'));});
    const fail=error=>{if(worker!==current)return;settle(error);stopWorker();};
    current.on('error',fail);current.on('exit',code=>fail(new Error('Operations evaluation worker exited ('+code+')')));
  }
  function call(message,{transfer=[],timeout=timeoutMs}={}){
    if(closed)return Promise.reject(new Error('Operations worker closed'));
    if(!worker)start();const current=worker,id=++sequence;current.ref();
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{waiting.delete(id);reject(new Error('Operations evaluation timed out'));if(worker===current){settle(new Error('Operations evaluation worker stopped'));stopWorker();}},timeout);
      waiting.set(id,{resolve,reject,timer});try{current.postMessage({...message,id},transfer);}catch(error){clearTimeout(timer);waiting.delete(id);reject(error);}
    }).finally(()=>{if(!waiting.size&&worker===current)current.unref();});
  }
  function close(){
    if(closing)return closing;
    const leave=worker&&!waiting.size?call({type:'close'},{timeout:2500}):Promise.resolve();
    closed=true;
    closing=leave.catch(()=>{}).then(()=>{settle(new Error('Operations worker closed'));return stopWorker();});
    return closing;
  }
  return {call,alive:()=>worker!==null,close};
}

export function operationsRefresher({checkpoint,intervalMs=30000,maxStateAgeMs=120000,clock=Date.now,timeoutMs=60000,workerURL=new URL('./operations-worker.mjs',import.meta.url)}={}){
  if(!checkpoint?.operations||!checkpoint.durable)throw new Error('Operations refresh requires a durable-checkpoint publisher');
  const channel=checkpoint.operations,tickMs=Math.max(250,Math.min(1000,Math.floor(intervalMs/4)));
  const workBudget=state=>Math.min(timeoutMs,maxStateAgeMs-(clock()-state)-publicationHeadroom(maxStateAgeMs));
  const newWorker=()=>operationsWorker(workerURL,timeoutMs);
  let active=newWorker(),prepared=null,loaded=null,running=null,closed=false,retryAt=0;
  let attemptedGeneration=null,exhaustedGeneration=null;
  const health={status:'waiting_for_checkpoint',interval_seconds:intervalMs/1000,max_state_age_seconds:maxStateAgeMs/1000,refreshes:0,published:0,skipped:{},last_generated_at:null,last_state_at:null,last_published_at:null,last_error:null};

  async function prepare({receipt,bytes}){
    const state=clockOf(receipt.at),generation=receipt.generation;
    if(closed||workBudget(state)<=0)return false;
    // A successor may begin saving just as the previous checkpoint commits.
    // Give the refresher a chance to take the committed report first.
    const obsolete=prepared;
    if(obsolete&&checkpoint.durable()?.generation===obsolete.generation)return false;
    const entry={generation,worker:newWorker()};
    prepared=entry;
    entry.ready=(async()=>{
      if(obsolete)await obsolete.worker.close();
      const shared=bytes.buffer instanceof SharedArrayBuffer;
      const buffer=shared?bytes.buffer:Uint8Array.from(bytes).buffer;
      const loadBudget=workBudget(state);
      if(loadBudget<=0)return null;
      await entry.worker.call({type:'load',generation,sha256:receipt.sha256,bytes:buffer},{transfer:shared?[]:[buffer],timeout:loadBudget});
      const evaluateBudget=workBudget(state);
      if(evaluateBudget<=0)return null;
      const now=new Date(clock()).toISOString();
      const evaluated=await entry.worker.call({type:'evaluate',generation,now,stateAt:receipt.at},{timeout:evaluateBudget});
      return {evaluated,now};
    })().catch(error=>{
      if(prepared===entry&&!closed)console.error(JSON.stringify({event:'operations_preparation_deferred',error:error.message}));
      return null;
    });
    return Boolean(await entry.ready);
  }
  const count=reason=>{health.skipped[reason]=(health.skipped[reason]||0)+1;};
  let lastSkip='';
  const skip=reason=>{count(reason);health.status=reason;const key=reason+':'+checkpoint.durable()?.generation;if(key!==lastSkip){lastSkip=key;channel.record?.({event:'refresh_refused',at:new Date(clock()).toISOString(),reason,state_at:checkpoint.durable()?.at||null,max_state_age_seconds:maxStateAgeMs/1000});}return {published:false,reason};};
  async function refreshOnce(){
    const durable=checkpoint.durable();if(!durable)return skip('waiting_for_checkpoint');
    attemptedGeneration=durable.generation;
    const state=clockOf(durable.at);
    const remaining=()=>maxStateAgeMs-(clock()-state);
    const outOfTime=()=>{
      exhaustedGeneration=durable.generation;
      return skip(remaining()<0?'paused_checkpoint_too_old':'insufficient_publication_headroom');
    };
    if(workBudget(state)<=0)return outOfTime();
    const last=channel.last();if(last&&state<last.state)return skip('superseded');
    let now,evaluated,renderMode='after_commit';
    if(prepared?.generation===durable.generation){
      const entry=prepared;
      prepared=null;
      const result=await entry.ready;
      if(result&&entry.worker.alive()){
        await active.close();
        active=entry.worker;
        loaded=durable.generation;
        checkpoint.takeDurableBytes(durable.generation);
        ({evaluated,now}=result);
        renderMode='prepared_during_upload';
      }else await entry.worker.close();
    }
    if(!evaluated){
      if(!active.alive()||loaded!==durable.generation){
        const loadBudget=workBudget(state);
        if(loadBudget<=0)return outOfTime();
        const bytes=checkpoint.takeDurableBytes(durable.generation);if(!bytes)return skip('checkpoint_copy_unavailable');
        // The captured image is shared read-only or transferred once after commit.
        const owned=bytes.byteOffset===0&&bytes.byteLength===bytes.buffer.byteLength?bytes:new Uint8Array(bytes);
        const transfer=owned.buffer instanceof SharedArrayBuffer?[]:[owned.buffer];
        loaded=null;await active.call({type:'load',generation:durable.generation,sha256:durable.sha256,bytes:owned.buffer},{transfer,timeout:loadBudget});loaded=durable.generation;
      }
      const evaluateBudget=workBudget(state);
      if(evaluateBudget<=0)return outOfTime();
      now=new Date(clock()).toISOString();
      evaluated=await active.call({type:'evaluate',generation:durable.generation,now,stateAt:durable.at},{timeout:evaluateBudget});
    }
    // Keep the last verified report readable. If its replacement checkpoint
    // committed during this repeated refresh, give the write slot to that one.
    if(channel.last()?.state===state&&Date.parse(checkpoint.durable()?.at)-state>=intervalMs)return skip('superseded');
    if(remaining()<publicationHeadroom(maxStateAgeMs))return outOfTime();
    const result=await channel.publish({text:evaluated.text,digest:evaluated.digest,stateAt:durable.at,generatedAt:now,urgent:true,renderMode});
    if(result.reason==='insufficient_publication_headroom'||result.reason==='paused_checkpoint_too_old'){
      exhaustedGeneration=durable.generation;
    }
    health.refreshes++;if(result.published){health.published++;health.last_published_at=result.receipt?.upload_completed_at||new Date(clock()).toISOString();}else count(result.reason);
    Object.assign(health,{status:'refreshing',last_generated_at:now,last_state_at:durable.at,last_error:null});return result;
  }
  return {
    tickMs,
    prepare,
    due(nowMs=clock()){
      const durable=checkpoint.durable(),last=channel.last();
      if(closed||running||!durable||durable.generation===exhaustedGeneration)return false;
      // A new committed generation can use its own budget immediately. Backoff
      // from an older report must never hold it until its publish slot expires.
      if(durable.generation!==attemptedGeneration&&(!last||Date.parse(durable.at)>last.state))return true;
      return nowMs>=retryAt&&(!last||nowMs-(last.visibleAt??last.generated)>=intervalMs-tickMs);
    },
    refresh(){
      if(closed)return Promise.resolve({published:false,reason:'closed'});if(running)return running;
      running=refreshOnce().catch(error=>{retryAt=clock()+Math.min(intervalMs,15000);health.status='retry_pending';health.last_error=error.message;throw error;}).finally(()=>{running=null;});return running;
    },
    health:()=>({...health,skipped:{...health.skipped}}),
    async close(){closed=true;if(running)await running.catch(()=>{});await channel.idle();await Promise.all([active.close(),prepared?.worker.close()]);},
  };
}
