import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomBytes} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter,openCheckpoint,checkpointObjectKey} from './reverse-split-live/checkpoint.mjs';
import {restoreCheckpoint} from './reverse-split-live/checkpoint-codec.mjs';

function fixture(t){
 const remote=new DatabaseSync(':memory:');remote.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>remote.close());
 const objects=new Map(),env={controlDB:localAdapter(remote),pending:[],CHECKPOINT_COMPRESSION:'gzip',EVIDENCE:{put:async(k,b)=>objects.set(k,Buffer.from(b)),get:async k=>objects.has(k)?{arrayBuffer:async()=>Uint8Array.from(objects.get(k)).buffer}:null}};
 return {remote,objects,env};
}
const save=cp=>cp.save({publicationMode:'r2',checkpointOnly:true});

test('changed-block checkpoints restore the exact newer SQLite state from one retained full checkpoint',async t=>{
 const {env,objects}=fixture(t);
 const cp=await openCheckpoint(env,{writeDeltas:true});t.after(()=>cp.close());
 await env.DB.prepare('CREATE TABLE checkpoint_fixture(id INTEGER PRIMARY KEY,data BLOB NOT NULL)').run();
 for(let id=1;id<=8;id++)await env.DB.prepare('INSERT INTO checkpoint_fixture VALUES(?,?)').bind(id,randomBytes(1024*1024)).run();
 const full=await save(cp);
 const changed=randomBytes(1024*1024);
 await env.DB.prepare('UPDATE checkpoint_fixture SET data=? WHERE id=2').bind(changed).run();
 const delta=await save(cp);
 assert.equal(delta.format,'sqlite_block_delta.v1');
 assert.equal(delta.base.key,full.key);
 assert.ok(delta.stored_bytes<full.stored_bytes/2);
 const restoredEnv={...env},restored=await openCheckpoint(restoredEnv);
 try{
  const row=await restoredEnv.DB.prepare('SELECT data FROM checkpoint_fixture WHERE id=2').first();
  assert.deepEqual(Buffer.from(row.data),changed);
  const legacy=await save(restored);
  assert.equal(legacy.format,undefined);
  await restoreCheckpoint(objects.get(legacy.key),legacy);
 }finally{restored.close();}
 const corrupt=Buffer.from(objects.get(delta.key));corrupt[0]^=1;objects.set(delta.key,corrupt);
 const corruptPointer={...env,controlDB:{prepare:()=>({first:async()=>({value:JSON.stringify(delta)})})}};
 await assert.rejects(openCheckpoint(corruptPointer),/checksum/);
});

test('checkpoint pruning keeps a full base while either retained generation depends on it',async t=>{
 const {env,objects}=fixture(t);
 env.EVIDENCE.delete=async key=>objects.delete(key);
 const cp=await openCheckpoint(env,{writeDeltas:true});t.after(()=>cp.close());
 await env.DB.prepare('CREATE TABLE checkpoint_fixture(id INTEGER PRIMARY KEY,data BLOB NOT NULL)').run();
 const insert=env.DB.prepare('INSERT INTO checkpoint_fixture VALUES(?,?)');
 const update=env.DB.prepare('UPDATE checkpoint_fixture SET data=? WHERE id=?');
 for(let id=1;id<=8;id++)await insert.bind(id,randomBytes(1024*1024)).run();
 const base=await save(cp);
 await update.bind(randomBytes(1024*1024),2).run();
 const first=await save(cp);
 await update.bind(randomBytes(1024*1024),2).run();
 const prior=await save(cp);
 assert.equal(prior.base.key,base.key);
 assert.ok(objects.has(base.key));
 for(let id=1;id<=8;id++)await update.bind(randomBytes(1024*1024),id).run();
 const next=await save(cp);
 assert.equal(next.format,undefined);
 assert.equal(next.previous.key,prior.key);
 assert.ok(objects.has(base.key));
 assert.equal(objects.has(first.key),false);
 await update.bind(randomBytes(1024*1024),2).run();
 const latest=await save(cp);
 assert.equal(latest.base.key,next.key);
 await new Promise(setImmediate);
 assert.equal(objects.has(base.key),false);
 assert.equal(objects.has(prior.key),false);
 assert.ok(objects.has(next.key));
 assert.ok(objects.has(latest.key));
});

test('a lost upload response can commit once the original object is visible and its size and ETag match',async t=>{
 const {env,objects,remote}=fixture(t),audit=[];
 env.onOperationsAudit=row=>audit.push(row);
 const cp=await openCheckpoint(env,{retainDurableBytes:true});t.after(()=>cp.close());
 const baseline=await save(cp),put=env.EVIDENCE.put;
 let checks=0;
 env.EVIDENCE.put=async(k,b)=>{await put(k,b);throw new DOMException('PUT response timed out','TimeoutError');};
 env.EVIDENCE.stat=async(key,{signal})=>{
  assert.equal(signal.aborted,false);
  assert.equal(JSON.parse(remote.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").get().value).key,baseline.key);
  if(++checks===1)return null;
  const body=objects.get(key);
  return {size:body.length,etag:createHash('md5').update(body).digest('hex')};
 };
 const receipt=await save(cp);
 assert.equal(checks,2);
 assert.equal(cp.durable().generation,receipt.generation);
 await restoreCheckpoint(objects.get(receipt.key),receipt);
 assert.equal(audit.at(-1).upload_confirmation,'storage_metadata');
 assert.ok(audit.at(-1).upload_timeout_at<=audit.at(-1).upload_completed_at);
});

test('a same-size checkpoint object with a different ETag cannot recover an unconfirmed upload',async t=>{
 const {env,objects}=fixture(t),cp=await openCheckpoint(env,{retainDurableBytes:true});t.after(()=>cp.close());
 const baseline=await save(cp),put=env.EVIDENCE.put;
 env.EVIDENCE.put=async(k,b)=>{await put(k,b);throw new DOMException('PUT response timed out','TimeoutError');};
 env.EVIDENCE.stat=async key=>({size:objects.get(key).length,etag:'0'.repeat(32)});
 await assert.rejects(save(cp),/PUT response timed out/);
 assert.equal(cp.durable().generation,baseline.generation);
});

test('late upload from the previous owner cannot invalidate the committed compressed checkpoint',async t=>{
 const remote=new DatabaseSync(':memory:');
 remote.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');
 t.after(()=>remote.close());
 const objects=new Map(),storage={put:async(k,b)=>objects.set(k,Buffer.from(b)),get:async k=>objects.has(k)?{arrayBuffer:async()=>Uint8Array.from(objects.get(k)).buffer}:null};
 let owner='previous',hold=false,release,arrived;
 const blocked=new Promise(r=>{release=r;}),uploadStarted=new Promise(r=>{arrived=r;});
 const lease=()=>remote.prepare("INSERT INTO rs_state VALUES('collector_lease',?,'now') ON CONFLICT(key) DO UPDATE SET value=excluded.value").run(String(Date.now()+600000)+':'+owner);
 const environment=name=>({controlDB:localAdapter(remote),pending:[],CHECKPOINT_COMPRESSION:'gzip',collectorLeaseOwner:name,assertCollectorLease(){if(owner!==name)throw new Error('Collector lease lost');},EVIDENCE:name==='previous'?{...storage,put:async(k,b)=>{if(hold&&k.startsWith('collector-state/')){arrived();await blocked;}return storage.put(k,b);}}:storage});
 lease();const oldEnv=environment('previous'),old=await openCheckpoint(oldEnv);t.after(()=>old.close());
 await old.save({publicationMode:'r2',checkpointOnly:true});
 await oldEnv.DB.prepare("INSERT INTO rs_state VALUES('owned-research','previous','now')").run();
 hold=true;const lateSave=old.save({publicationMode:'r2',checkpointOnly:true});
 await uploadStarted;owner='successor';lease();
 const newEnv=environment('successor'),successor=await openCheckpoint(newEnv);t.after(()=>successor.close());
 await newEnv.DB.prepare("INSERT INTO rs_state VALUES('owned-research','successor','now')").run();
 await successor.save({publicationMode:'r2',checkpointOnly:true});
 release();await assert.rejects(lateSave,/lease lost/);
 await assert.doesNotReject(async()=>{
  const restoredEnv=environment('successor'),restored=await openCheckpoint(restoredEnv);
  try{assert.equal((await restoredEnv.DB.prepare("SELECT value FROM rs_state WHERE key='owned-research'").first()).value,'successor');}finally{restored.close();}
 });
});

test('overlapping saves from one checkpoint handle serialize upload and receipt commitment',async t=>{
 const {env,objects}=fixture(t),cp=await openCheckpoint(env);t.after(()=>cp.close());
 let entered,release,calls=0;const started=new Promise(r=>{entered=r;}),blocked=new Promise(r=>{release=r;}),put=env.EVIDENCE.put;
 env.EVIDENCE.put=async(k,b)=>{calls++;if(calls===1){entered();await blocked;}return put(k,b);};
 const first=save(cp);await started;const second=save(cp);await new Promise(setImmediate);assert.equal(calls,1);
 await env.DB.prepare("INSERT INTO rs_state VALUES('late-record','retained','now')").run();release();
 const receipts=await Promise.all([first,second]);assert.notEqual(receipts[0].key,receipts[1].key);
 for(const receipt of receipts)await restoreCheckpoint(objects.get(receipt.key),receipt);
 const restoredEnv={...env},restored=await openCheckpoint(restoredEnv);try{assert.equal((await restoredEnv.DB.prepare("SELECT value FROM rs_state WHERE key='late-record'").first()).value,'retained');}finally{restored.close();}
});

test('a timed-out PUT completing after the final save cannot replace that final checkpoint',async t=>{
 const {env,objects}=fixture(t),cp=await openCheckpoint(env);t.after(()=>cp.close());await save(cp);
 const put=env.EVIDENCE.put;let late;
 env.EVIDENCE.put=async(k,b)=>{late={key:k,bytes:Buffer.from(b)};throw new Error('upload aborted before response');};
 await env.DB.prepare("INSERT INTO rs_state VALUES('runtime-phase','starting','now')").run();await assert.rejects(save(cp),/upload aborted/);
 env.EVIDENCE.put=put;await env.DB.prepare("UPDATE rs_state SET value='stopped' WHERE key='runtime-phase'").run();const final=await save(cp);
 // The remote server may finish a timed-out request after its caller rejected.
 await put(late.key,late.bytes);await restoreCheckpoint(objects.get(final.key),final);assert.notEqual(late.key,final.key);
 const restoredEnv={...env},restored=await openCheckpoint(restoredEnv);try{assert.equal((await restoredEnv.DB.prepare("SELECT value FROM rs_state WHERE key='runtime-phase'").first()).value,'stopped');}finally{restored.close();}
});

test('a stale parent receipt cannot replace a newer committed checkpoint even under the same owner',async t=>{
 const {env}=fixture(t),initial=await openCheckpoint(env);await save(initial);initial.close();
 const oldEnv={...env},newEnv={...env},old=await openCheckpoint(oldEnv),current=await openCheckpoint(newEnv);t.after(()=>old.close());t.after(()=>current.close());
 await newEnv.DB.prepare("INSERT INTO rs_state VALUES('new-owner-evidence','retained','now')").run();const committed=await save(current);
 await assert.rejects(save(old),/superseded/);
 const pointer=JSON.parse((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").first()).value);assert.equal(pointer.key,committed.key);
 const restoredEnv={...env},restored=await openCheckpoint(restoredEnv);try{assert.equal((await restoredEnv.DB.prepare("SELECT value FROM rs_state WHERE key='new-owner-evidence'").first()).value,'retained');}finally{restored.close();}
});

test('normal retention keeps two committed generations and never deletes legacy slots or review evidence',async t=>{
 const {env,objects}=fixture(t),deleted=[];objects.set('collector-state/slot0.sqlite.gz',Buffer.from('preserved original'));objects.set('review/recovery-inputs/original.sqlite.gz',Buffer.from('preserved archive'));
 env.EVIDENCE.delete=async key=>{const current=JSON.parse((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").first()).value);assert.notEqual(key,current.key);assert.notEqual(key,current.previous?.key);deleted.push(key);objects.delete(key);};
 const cp=await openCheckpoint(env);t.after(()=>cp.close());let receipt;
 for(let i=0;i<6;i++){await env.DB.prepare("INSERT INTO rs_state VALUES(?,?,'now')").bind('generation-evidence:'+i,String(i)).run();receipt=await save(cp);}
 assert.equal(objects.size,4);assert.equal(deleted.length,4);assert.ok(deleted.every(k=>k.startsWith('collector-state/checkpoints/')));assert.ok(objects.has(receipt.key));assert.ok(objects.has(receipt.previous.key));assert.equal(receipt.previous.previous,undefined);
 await restoreCheckpoint(objects.get(receipt.key),receipt);await restoreCheckpoint(objects.get(receipt.previous.key),receipt.previous);
});

test('generation keys must bind both their digest and generation to the receipt',()=>{
 const generation='12345678-1234-4234-8234-123456789abc',stored_sha256='a'.repeat(64),key=`collector-state/checkpoints/${stored_sha256}-${generation}.sqlite.gz`,receipt={key,generation,stored_sha256,compression:'gzip'};
 assert.equal(checkpointObjectKey(receipt),key);assert.throws(()=>checkpointObjectKey({...receipt,stored_sha256:'b'.repeat(64)}),/identity/);assert.throws(()=>checkpointObjectKey({...receipt,generation:'invalid'}),/identity/);assert.throws(()=>checkpointObjectKey({...receipt,key:'review/private-original.json'}),/identity/);
 assert.equal(checkpointObjectKey({slot:1}),'collector-state/slot1.sqlite');
});

test('committed operations bytes become available before slow obsolete-object cleanup',async t=>{
 const {env}=fixture(t),cp=await openCheckpoint(env,{retainDurableBytes:true});t.after(()=>cp.close());await save(cp);await save(cp);const old=cp.durable().generation;
 let arrived,release;const entered=new Promise(r=>{arrived=r;}),blocked=new Promise(r=>{release=r;});env.EVIDENCE.delete=async()=>{arrived();await blocked;};
 const pending=save(cp);await entered;
 try{const receipt=JSON.parse((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").first()).value);assert.notEqual(cp.durable().generation,old);assert.equal(cp.durable().generation,receipt.generation);}finally{release();await pending;}
});
