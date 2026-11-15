import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter,openCheckpoint,checkpointObjectKey} from './reverse-split-live/checkpoint.mjs';
import {restoreCheckpoint} from './reverse-split-live/checkpoint-codec.mjs';

function fixture(t){
 const remote=new DatabaseSync(':memory:');remote.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>remote.close());
 const objects=new Map(),env={controlDB:localAdapter(remote),pending:[],CHECKPOINT_COMPRESSION:'gzip',EVIDENCE:{put:async(k,b)=>objects.set(k,Buffer.from(b)),get:async k=>objects.has(k)?{arrayBuffer:async()=>Uint8Array.from(objects.get(k)).buffer}:null}};
 return {remote,objects,env};
}
const save=cp=>cp.save({publicationMode:'r2',checkpointOnly:true});

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
