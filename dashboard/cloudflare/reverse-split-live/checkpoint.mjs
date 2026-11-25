// Local scan database. Each upload has a private, non-reused generation identity.
import {DatabaseSync} from 'node:sqlite';
import {createHash, randomUUID} from 'node:crypto';
import {mkdtempSync,readFileSync,writeFileSync,readdirSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname,basename} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';
import {sha} from './worker.mjs';
import {captureReadSnapshot,publishReadSnapshot} from './snapshot-publish.mjs';
import {createCheckpointCompressor,restoreCheckpoint} from './checkpoint-codec.mjs';
import {operationsChannel} from './operations-publication.mjs';
import {publishCheckpointSnapshot} from './snapshot-background.mjs';
const GENERATION_KEY=/^collector-state\/checkpoints\/([a-f0-9]{64})-([a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})\.sqlite(\.gz)?$/;
export function checkpointObjectKey(receipt){
 const key=receipt.key||`collector-state/slot${receipt.slot}.sqlite`;
 if(/^collector-state\/slot[01]\.sqlite(?:\.gz)?$/.test(key))return key;
 const match=GENERATION_KEY.exec(key),digest=receipt.compression?receipt.stored_sha256:receipt.sha256;
 if(!match||match[1]!==digest||match[2]!==receipt.generation||Boolean(match[3])!==Boolean(receipt.compression))throw new Error('Invalid checkpoint object identity');
 return key;
}
const previousReceipt=receipt=>receipt?Object.fromEntries(Object.entries(receipt).filter(([key])=>key!=='previous')):null;
function cleanup(dir){const target=realpathSync(dir),parent=realpathSync(tmpdir()),equal=(a,b)=>process.platform==='win32'?a.toLowerCase()===b.toLowerCase():a===b;if(!equal(dirname(target),parent)||!basename(target).startsWith('reverse-split-'))throw new Error('Unsafe collector temporary directory');rmSync(target,{recursive:true,force:true});}

async function confirmTimedOutUpload(env,key,body){
  const etag=createHash('md5').update(body).digest('hex');
  const deadline=AbortSignal.timeout(10500);
  // These are read-only probes of a never-reused key. A delayed original PUT
  // may finish, but sending a second large body would add another stall.
  for(const delay of [0,1800,2100,3500]){
    if(delay)await sleep(delay,undefined,{signal:deadline}).catch(()=>{});
    if(deadline.aborted)return false;
    env.assertCollectorLease?.();
    const signal=AbortSignal.any([deadline,AbortSignal.timeout(2200)]);
    const metadata=await env.EVIDENCE.stat(key,{signal}).catch(()=>null);
    if(metadata)return metadata.size===body.length&&metadata.etag===etag;
  }
  return false;
}

export function localAdapter(db){const make=(sql,args=[])=>({bind:(...values)=>make(sql,values),first:async()=>db.prepare(sql).get(...args)||null,all:async()=>({results:db.prepare(sql).all(...args)}),run:async()=>({meta:{changes:Number(db.prepare(sql).run(...args).changes)}})});return {prepare:sql=>make(sql),batch:async statements=>{db.exec('BEGIN');try{const rows=[];for(const s of statements)rows.push(await s.run());db.exec('COMMIT');return rows;}catch(e){db.exec('ROLLBACK');throw e;}}};}

// retainDurableBytes: keep the last committed checkpoint's bytes (one generation)
// for the operations refresh, which evaluates only already-durable state.
export async function openCheckpoint(env,{retainDurableBytes=false,operationsOptions={},publishOperationsFromFull=true,prepareOperations=null}={}){
  const remote=env.controlDB,dir=mkdtempSync(join(tmpdir(),'reverse-split-')),file=join(dir,'research.sqlite');let db,receipt,receiptValue,publicationTask=null,latestSnapshot=null,deferDerived=false,saving=Promise.resolve(),durable=null,refreshPointer=false,pruneTask=null;
  const pruneQueue=new Set(),pruneStop=new AbortController();
  // Large checkpoint blobs have a different latency budget from D1 pointer updates.
  const uploadTimeoutMs=Math.max(250,Math.min(35000,Math.floor((operationsOptions.maxStateAgeMs??75000)/2)));
  const pointerTimeoutMs=Math.min(5000,uploadTimeoutMs);
  const readPointer=()=>remote.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'",{signal:AbortSignal.timeout(pointerTimeoutMs)}).first();
  try{
    receiptValue=(await readPointer())?.value??null;receipt=JSON.parse(receiptValue||'null');
    if(receipt){const object=await env.EVIDENCE.get(checkpointObjectKey(receipt));if(!object)throw new Error('Committed collector checkpoint is unavailable');const bytes=await restoreCheckpoint(new Uint8Array(await object.arrayBuffer()),receipt);writeFileSync(file,bytes);}
    // synchronous=OFF: this file is a working copy restored from the committed R2
    // checkpoint on every start, so an fsync per write buys no durability.
    db=new DatabaseSync(file);db.exec('PRAGMA journal_mode=DELETE');db.exec('PRAGMA synchronous=OFF');for(const name of readdirSync(new URL('./migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./migrations/'+name,import.meta.url),'utf8'));
    env.DB=localAdapter(db);
    const bootstrap=readFileSync(new URL('./bootstrap.json',import.meta.url)),bootstrapHash=await sha(bootstrap);
    if(!db.prepare("SELECT value FROM rs_state WHERE key='prior_history_bootstrap'").get()||db.prepare("SELECT value FROM rs_state WHERE key='prior_history_bootstrap'").get().value!==bootstrapHash){
      const data=JSON.parse(bootstrap);if(data.schema!=='reverse_split_prior_history.v1')throw new Error('Unexpected historical action seed');
      db.exec('BEGIN');try{for(const r of data.records){if(!r.verified||!r.cik||!r.effective_date||!r.known_at||!r.source_url?.startsWith('https://'))throw new Error('Unbound historical action');db.prepare('INSERT OR IGNORE INTO rs_history(id,cik,effective_date,known_at,verified,payload) VALUES(?,?,?,?,1,?)').run(r.cik+':'+r.effective_date,r.cik,r.effective_date,r.known_at,JSON.stringify(r));}db.prepare("INSERT INTO rs_state(key,value,updated_at) VALUES('prior_history_bootstrap',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").run(bootstrapHash,new Date().toISOString());db.exec('COMMIT');}catch(e){db.exec('ROLLBACK');throw e;}
    }
  }catch(e){db?.close();cleanup(dir);throw e;}
  const operations=operationsChannel(env,{db,...operationsOptions});
  const compressCheckpoint=createCheckpointCompressor();
  async function commitPointer(next,at){
    env.assertCollectorLease?.();
    const value=JSON.stringify(next),lease=env.collectorLeaseOwner?" AND EXISTS(SELECT 1 FROM rs_state WHERE key='collector_lease' AND substr(value,instr(value,':')+1)=? AND CAST(value AS INTEGER)>?)":'',args=env.collectorLeaseOwner?[env.collectorLeaseOwner,Date.now()+30000]:[];
    const options={signal:AbortSignal.timeout(pointerTimeoutMs)};
    try{
      const ok=receiptValue===null
        ?await remote.prepare("INSERT INTO rs_state(key,value,updated_at) SELECT 'collector_checkpoint',?,? WHERE NOT EXISTS(SELECT 1 FROM rs_state WHERE key='collector_checkpoint')"+lease+" ON CONFLICT(key) DO NOTHING RETURNING key",options).bind(value,at,...args).first()
        :await remote.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_checkpoint' AND value=?"+lease+" RETURNING key",options).bind(value,at,receiptValue,...args).first();
      if(!ok)throw new Error('Collector lease lost or checkpoint superseded before checkpoint commit; original evidence preserved');
      receipt=next;receiptValue=value;
    }catch(error){
      // The server may have committed despite a timeout. Reload the current
      // pointer before the next compare-and-swap; never promote an assumed ACK.
      refreshPointer=true;
      throw error;
    }
  }
  function pruneCheckpoint(key){
    pruneQueue.add(key);
    if(pruneTask)return;
    pruneTask=Promise.resolve().then(async()=>{
      try{
        while(pruneQueue.size&&!pruneStop.signal.aborted){
          const obsolete=pruneQueue.values().next().value;
          pruneQueue.delete(obsolete);
          try{
            env.assertCollectorLease?.();
            await env.EVIDENCE.delete(obsolete,{signal:AbortSignal.any([pruneStop.signal,AbortSignal.timeout(5000)])});
          }catch(error){
            if(!pruneStop.signal.aborted)console.error(JSON.stringify({event:'checkpoint_prune_deferred',key:obsolete,error:error.message}));
          }
        }
      }finally{pruneTask=null;}
    });
  }
  async function storeCheckpoint(bytes,at,{compressed=false,onCommittedBytes=null,onCommitted=null}={}){
    env.assertCollectorLease?.();
    if(refreshPointer){
      receiptValue=(await readPointer())?.value??null;
      receipt=JSON.parse(receiptValue||'null');
      if(receipt)checkpointObjectKey(receipt);
      refreshPointer=false;
    }
    const preparationStarted=Date.now();
    const parent=receipt,encoded=compressed?await compressCheckpoint(bytes):null;
    const compressionCompleted=Date.now();
    // Use the native incremental hash to avoid the Web Crypto input copy for a large SQLite image.
    const generation=randomUUID(),digest=createHash('sha256').update(bytes).digest('hex'),key=`collector-state/checkpoints/${encoded?.stored_sha256||digest}-${generation}.sqlite`+(encoded?'.gz':'');
    const next={slot:parent?.slot===0?1:0,sha256:digest,bytes:bytes.length,at,key,generation};
    if(encoded)Object.assign(next,{compression:encoded.compression,stored_bytes:encoded.stored_bytes,stored_sha256:encoded.stored_sha256});
    if(parent)next.previous=previousReceipt(parent);
    env.assertCollectorLease?.();
    const body=encoded?.stored||bytes;
    let uploadCompleted,uploadTimeoutAt=null;
    if(retainDurableBytes&&prepareOperations){
      try{prepareOperations({receipt:next,bytes});}
      catch(error){console.error(JSON.stringify({event:'operations_preparation_deferred',error:error.message}));}
    }
    const uploadStarted=Date.now();
    try{
      try{
        await env.EVIDENCE.put(key,body,{httpMetadata:{contentType:encoded?'application/gzip':'application/vnd.sqlite3'},urgent:true,signal:AbortSignal.timeout(uploadTimeoutMs)});
      }catch(error){
        if(!['TimeoutError','AbortError'].includes(error.name)||!env.EVIDENCE.stat)throw error;
        uploadTimeoutAt=Date.now();
        if(!await confirmTimedOutUpload(env,key,body))throw error;
      }
      uploadCompleted=Date.now();
      await commitPointer(next,at);
    }catch(error){
      operations.record({event:'checkpoint_failed',at:new Date().toISOString(),state_at:at,generation,phase:uploadCompleted?'pointer':'upload',error_type:error.name});
      throw error;
    }
    operations.record({event:'checkpoint_committed',at:new Date().toISOString(),state_at:at,generation,upload_started_at:new Date(uploadStarted).toISOString(),upload_completed_at:new Date(uploadCompleted).toISOString(),upload_confirmation:uploadTimeoutAt===null?'put_response':'storage_metadata',upload_timeout_at:uploadTimeoutAt===null?null:new Date(uploadTimeoutAt).toISOString(),compression_ms:compressionCompleted-preparationStarted,hash_and_key_ms:uploadStarted-compressionCompleted,stored_bytes:body.length,compressed_blocks:encoded?.compressed_blocks??0,reused_compression_blocks:encoded?.reused_compression_blocks??0});
    onCommitted?.(next);
    onCommittedBytes?.(encoded?.stored||bytes);
    // Keep two committed generations. Legacy slots, review archives and uncertain
    // failed uploads are never deleted here. A late PUT cannot target a newer key.
    const obsolete=parent?.previous?.key;
    if(obsolete&&GENERATION_KEY.test(obsolete)&&obsolete!==key&&obsolete!==parent.key&&env.EVIDENCE.delete){
      pruneCheckpoint(obsolete);
    }
    return next;
  }
  async function publishSnapshot(snapshot,options){
    const result=snapshot.receipt?await publishCheckpointSnapshot(env,db,snapshot,{...options,operations,publishOperations:publishOperationsFromFull}):await publishReadSnapshot(env,db,snapshot,{...options,operations});
    const at=result.at||snapshot.at;
    if(!env.snapshotActivated){await remote.prepare("INSERT INTO rs_state VALUES('collector_publication','r2',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").bind(at).run();env.snapshotActivated=true;}
    env.publicationHealth={status:result.complete?'published':'current_published_history_pending',snapshot_at:at,history_complete:result.complete};
  }
  function queueSnapshot(snapshot){
    latestSnapshot=snapshot;
    if(!publicationTask)publicationTask=(async()=>{while(latestSnapshot){const current=latestSnapshot;latestSnapshot=null;await publishSnapshot(current,{shouldYield:()=>deferDerived||Boolean(latestSnapshot)});}})().catch(e=>{env.publicationHealth={status:'retry_pending',error:e.message};console.error(JSON.stringify({event:'snapshot_publication_retry',error:e.message}));}).finally(()=>{publicationTask=null;});
  }
  async function saveInternal({publicationMode='d1',backgroundViews=false,checkpointOnly=false}={}){
      if(checkpointOnly&&publicationMode!=='r2')throw new Error('Checkpoint-only handoff requires private R2 publication');
      for(const p of env.pending.splice(0))await env.DB.prepare("UPDATE rs_jobs SET state='pending',token=NULL WHERE id=? AND token=? AND state='queued'").bind(p.id,p.token).run();
      const at=new Date().toISOString(),jobs=db.prepare('SELECT state,count(*) AS count,min(created_at) AS oldest FROM rs_jobs GROUP BY state').all();
      db.prepare("INSERT INTO rs_state(key,value,updated_at) VALUES('collector_job_counts',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").run(JSON.stringify(jobs),at);
      if(publicationMode==='r2'){
        // Capture without yielding: every displayed fill belongs to these exact durable bytes.
        // Retain the previous committed bytes until the successor commits: the
        // refresher must remain usable while a large upload is in flight.
        const started=Date.now(),snapshot=checkpointOnly||backgroundViews?null:captureReadSnapshot(db),bytes=readFileSync(file),captured=Date.now();let stored=null;
        const next=await storeCheckpoint(bytes,at,{compressed:env.CHECKPOINT_COMPRESSION==='gzip',onCommittedBytes:backgroundViews&&!checkpointOnly?value=>{stored=value;}:null,onCommitted:retainDurableBytes?committed=>{durable={generation:committed.generation,at:committed.at,sha256:committed.sha256,bytes};}:null});
        env.checkpointHealth={state_at:at,bytes:bytes.length,stored_bytes:next.stored_bytes||bytes.length,capture_ms:captured-started,store_ms:Date.now()-captured,total_ms:Date.now()-started};
        // These bytes became durable when the pointer committed; the refresh reads nothing newer.
        if(snapshot)snapshot.stateAt=next.at;
        if(backgroundViews&&!checkpointOnly)queueSnapshot({stored,receipt:next});
        else if(snapshot)await publishSnapshot(snapshot);
        return next;
      }
      const publications=[];
      const backgroundDue=Date.now()-Number(db.prepare("SELECT value FROM rs_state WHERE key='source_publication_at'").get()?.value||0)>=300000;
      async function changed(kind,id,payload,statement){if(kind==='source'&&!backgroundDue)return;const hash=await sha(payload),key='published:'+kind+':'+id,old=db.prepare('SELECT value FROM rs_state WHERE key=?').get(key)?.value;if(old!==hash)publications.push({key,hash,statement});}
      for(const r of db.prepare('SELECT * FROM rs_sources').all())await changed('source',r.id,JSON.stringify(r),remote.prepare('INSERT INTO rs_sources(id,kind,url,last_attempt,last_success,watermark,status,error,failures,next_attempt,coverage_gap,items) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=excluded.last_success,watermark=excluded.watermark,status=excluded.status,error=excluded.error,failures=excluded.failures,next_attempt=excluded.next_attempt,coverage_gap=excluded.coverage_gap,items=excluded.items').bind(...['id','kind','url','last_attempt','last_success','watermark','status','error','failures','next_attempt','coverage_gap','items'].map(k=>r[k])));
      for(const r of db.prepare('SELECT * FROM rs_events').all())await changed('event',r.id,r.payload,remote.prepare('INSERT INTO rs_events(id,cik,ticker,company,effective_date,published_at,first_seen_at,analyzed_at,result,score,ordinal_min,revision,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,company=excluded.company,effective_date=excluded.effective_date,published_at=excluded.published_at,analyzed_at=excluded.analyzed_at,result=excluded.result,score=excluded.score,ordinal_min=excluded.ordinal_min,revision=excluded.revision,payload=json_set(excluded.payload,\'$.first_seen_at\',rs_events.first_seen_at) WHERE rs_events.payload<>excluded.payload').bind(...['id','cik','ticker','company','effective_date','published_at','first_seen_at','analyzed_at','result','score','ordinal_min','revision','payload'].map(k=>r[k])));
      for(const r of db.prepare('SELECT * FROM rs_decisions').all())await changed('decision',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_decisions(id,event_id,recorded_at,policy,payload) VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.recorded_at,r.policy,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_alerts').all())await changed('alert',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_alerts(id,event_id,created_at,kind,payload) VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.created_at,r.kind,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_policies').all())await changed('shadow-policy',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_policies VALUES(?,?,?)').bind(r.id,r.registered_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_tracks').all())await changed('shadow-track',r.id,r.payload,remote.prepare('INSERT INTO rs_shadow_tracks(id,event_id,policy_id,cik,ticker,enrolled_at,signal_at,due_at,state,reason,updated_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,signal_at=excluded.signal_at,due_at=excluded.due_at,state=excluded.state,reason=excluded.reason,updated_at=excluded.updated_at,payload=excluded.payload').bind(...['id','event_id','policy_id','cik','ticker','enrolled_at','signal_at','due_at','state','reason','updated_at','payload'].map(k=>r[k])));
      for(const r of db.prepare('SELECT * FROM rs_shadow_records').all())await changed('shadow-record',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_records VALUES(?,?,?,?,?,?)').bind(r.id,r.track_id,r.event_id,r.kind,r.recorded_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_quotes').all())await changed('shadow-quote',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_quotes VALUES(?,?,?,?,?)').bind(r.id,r.ticker,r.quote_at,r.observed_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_evidence').all())await changed('shadow-evidence',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.kind,r.observed_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_daily').all())await changed('shadow-day',r.id,r.payload,remote.prepare('INSERT INTO rs_shadow_daily VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').bind(r.id,r.policy_id,r.day,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_execution_policies').all())await changed('execution-policy',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_execution_policies VALUES(?,?,?)').bind(r.id,r.registered_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_execution_tracks').all())await changed('execution-track',r.id,r.payload,remote.prepare('INSERT INTO rs_execution_tracks VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,state=excluded.state,updated_at=excluded.updated_at,payload=excluded.payload').bind(r.id,r.event_id,r.policy_id,r.ticker,r.state,r.updated_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_execution_daily').all())await changed('execution-day',r.id,r.payload,remote.prepare('INSERT INTO rs_execution_daily VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').bind(r.id,r.policy_id,r.day,r.payload));
      const cursors=[];
      for(const [table,fields] of [['rs_execution_records',['id','track_id','recorded_at','kind','payload']],['rs_borrow_observations',['id','ticker','day','kind','as_of','observed_at','payload']]]){
        const key='publication_cursor:'+table,last=Number(db.prepare('SELECT value FROM rs_state WHERE key=?').get(key)?.value||0),rows=db.prepare(`SELECT rowid AS sequence,* FROM ${table} WHERE rowid>? ORDER BY rowid`).all(last);
        for(const r of rows)publications.push({statement:remote.prepare(`INSERT OR IGNORE INTO ${table} VALUES(${fields.map(()=>'?').join(',')})`).bind(...fields.map(k=>r[k]))});
        if(rows.length)cursors.push({key,value:String(rows.at(-1).sequence)});
      }
      const keys=['last_tick','last_completed_tick','service_mode','last_reconciliation','reconciliation_error','collector_job_counts','last_collector_run','shadow_started_at','shadow_summary','execution_summary','validation_plan','validation_summary','shadow_borrow_health','flex_borrow_health'];
      const routineKeys=['last_tick','last_completed_tick','collector_job_counts'];
      const stateRows=db.prepare('SELECT * FROM rs_state').all().filter(r=>keys.includes(r.key)&&(backgroundDue||!routineKeys.includes(r.key))),states=[];
      for(const r of stateRows){const key='published:state:'+r.key,hash=await sha(JSON.stringify([r.value,r.updated_at]));if(db.prepare('SELECT value FROM rs_state WHERE key=?').get(key)?.value!==hash)states.push({r,key,hash});}
      const next=await storeCheckpoint(readFileSync(file),at);
      // The committed checkpoint is authoritative before any dashboard publication.
      // A failed publication retries from that checkpoint and cannot erase a simulated fill.
      for(let i=0;i<publications.length;i+=60){const group=publications.slice(i,i+60);await remote.batch(group.map(p=>p.statement));for(const p of group)if(p.key)db.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(p.key,p.hash,at);}
      for(const {key,value} of cursors)db.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(key,value,at);
      if(backgroundDue)db.prepare("INSERT INTO rs_state VALUES('source_publication_at',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").run(String(Date.now()),at);
      if(states.length){await remote.batch(states.map(({r})=>remote.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(r.key,r.value,r.updated_at)));for(const {key,hash} of states)db.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(key,hash,at);}
      return next;
  }
  return {
    save(options){const task=saving.catch(()=>{}).then(()=>saveInternal(options));saving=task;return task;},
    changedSince(at){return Boolean(db.prepare('SELECT id FROM rs_events WHERE analyzed_at>? LIMIT 1').get(at));},
    operations,
    durable(){return durable&&{generation:durable.generation,at:durable.at,sha256:durable.sha256};},
    takeDurableBytes(generation){if(durable?.generation!==generation||!durable.bytes)return null;const bytes=durable.bytes;durable.bytes=null;return bytes;},
    async flush({handoff=false}={}){if(handoff)deferDerived=true;if(publicationTask)await publicationTask;},
    close(){pruneStop.abort();pruneQueue.clear();db.close();cleanup(dir);},
  };
}
