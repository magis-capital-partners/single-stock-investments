import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {finishHandoff} from './reverse-split-live/handoff.mjs';
import {openCheckpoint,localAdapter} from './reverse-split-live/checkpoint.mjs';
import {publishReadSnapshot} from './reverse-split-live/snapshot-publish.mjs';

test('normal handoff evaluates quotes during slow cleanup and persists the final evaluation before closing',async()=>{
 let release,started,enabled=true,latest=null,saved=null;const draining=new Promise(r=>{started=r;}),wait=new Promise(r=>{release=r;}),order=[];
 const quote=value=>{if(enabled)latest=value;};
 const finishing=finishHandoff({keepQuotes:true,drain:async()=>{started();await wait;order.push('drained');},quiesce:async()=>{enabled=false;order.push('quiesced');},persist:async()=>{saved=latest;order.push('persisted');},close:async()=>{order.push('closed');}});
 await draining;quote({quote_at:'2026-11-09T15:34:59Z',evaluated_at:'2026-11-09T15:35:00Z'});assert.equal(saved,null);release();await finishing;
 assert.equal(saved.quote_at,'2026-11-09T15:34:59Z');assert.deepEqual(order,['drained','quiesced','persisted','closed']);quote(null);assert.equal(latest,saved);
});
test('a fatal or requested stop quiesces first while still preserving the final checkpoint',async()=>{
 const order=[];await finishHandoff({keepQuotes:false,quiesce:async()=>order.push('quiesce'),drain:async()=>order.push('drain'),persist:async()=>order.push('persist'),close:async()=>order.push('close')});assert.deepEqual(order,['quiesce','drain','persist','close']);
});
test('failed background cleanup cannot skip quiescence, final persistence or close',async()=>{
 const order=[];await assert.rejects(finishHandoff({keepQuotes:true,drain:async()=>{throw new Error('background failure');},quiesce:async()=>order.push('quiesce'),persist:async()=>order.push('persist'),close:async()=>order.push('close')}),/background failure/);assert.deepEqual(order,['quiesce','persist','close']);
});
test('checkpoint failure is reported and closes state before caller releases ownership',async()=>{
 let closed=false;await assert.rejects(finishHandoff({keepQuotes:true,drain:async()=>{},quiesce:async()=>{},persist:async()=>{throw new Error('checkpoint rejected');},close:async()=>{closed=true;}}),/checkpoint rejected/);assert.equal(closed,true);
});
test('final checkpoint restores late quote evidence without waiting for derived dashboard uploads',async t=>{
 const remote=new DatabaseSync(':memory:');remote.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>remote.close());
 const objects=new Map(),env={controlDB:localAdapter(remote),pending:[],EVIDENCE:{put:async(key,bytes)=>{assert.ok(!key.startsWith('collector-dashboard/'),'final persistence must not start another dashboard upload');objects.set(key,new Uint8Array(bytes));},get:async key=>objects.has(key)?{arrayBuffer:async()=>objects.get(key).slice().buffer}:null}};
 let checkpoint=await openCheckpoint(env);await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?)').bind('last-evaluated-quote',JSON.stringify({quote_at:'2026-11-09T15:35:00Z'}),'now').run();
 const receipt=await checkpoint.save({publicationMode:'r2',checkpointOnly:true});assert.ok(receipt.sha256);checkpoint.close();checkpoint=await openCheckpoint(env);
 try{assert.equal(JSON.parse((await env.DB.prepare("SELECT value FROM rs_state WHERE key='last-evaluated-quote'").first()).value).quote_at,'2026-11-09T15:35:00Z');assert.equal(objects.size,1);await assert.rejects(checkpoint.save({checkpointOnly:true}),/requires private R2/);}finally{checkpoint.close();}
});

test('yielding history completes current views and later resumes using durable object hashes',async t=>{
 const db=new DatabaseSync(':memory:');db.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>db.close());
 const writes=[],env={EVIDENCE:{put:async key=>writes.push(key)}},snapshot={at:'now',objects:['financial-needs.json','shadow.json','operations.json','execution.json','validation.json','history/page.json'].map(key=>({key,value:{version:1}})),borrow:[],envelope:{}};
 assert.equal((await publishReadSnapshot(env,db,snapshot,{shouldYield:()=>true})).complete,false);assert.equal(writes.length,5);assert.ok(!writes.some(k=>k.includes('history/')));
 assert.equal((await publishReadSnapshot(env,db,snapshot)).complete,true);assert.equal(writes.filter(k=>k.endsWith('/shadow.json')).length,1);assert.ok(writes.includes('collector-dashboard/history/page.json'));assert.ok(writes.includes('collector-dashboard/manifest.json'));
});

function backgroundFixture(t){
 const remote=new DatabaseSync(':memory:');remote.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>remote.close());const objects=new Map(),writes=[];let release,started;
 const gate=new Promise(r=>{release=r;}),blocked=new Promise(r=>{started=r;}),env={controlDB:localAdapter(remote),pending:[],EVIDENCE:{put:async(key,bytes)=>{if(key==='collector-dashboard/cards/shadow.json'&&!objects.has(key)){started();await gate;}writes.push({key,text:new TextDecoder().decode(bytes)});objects.set(key,new Uint8Array(bytes));},get:async key=>objects.has(key)?{arrayBuffer:async()=>objects.get(key).slice().buffer}:null}};
 return {env,objects,writes,blocked,release};
}
test('a newer durable snapshot publishes current state before the older historical backlog',async t=>{
 const {env,writes,blocked,release}=backgroundFixture(t),cp=await openCheckpoint(env);
 try{
  await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?)').bind('shadow_runtime',JSON.stringify({generation:'one'}),'now').run();await cp.save({publicationMode:'r2',backgroundViews:true});await blocked;
  await env.DB.prepare('UPDATE rs_state SET value=? WHERE key=?').bind(JSON.stringify({generation:'two'}),'shadow_runtime').run();await cp.save({publicationMode:'r2',backgroundViews:true});release();await cp.flush();
  const current=writes.findIndex(w=>w.key==='collector-dashboard/shadow.json'&&JSON.parse(w.text).runtime.generation==='two'),oldHistory=writes.findIndex(w=>w.key==='collector-dashboard/cards/execution.json');assert.ok(current>=0&&current<oldHistory);assert.equal(env.publicationHealth.history_complete,true);
 }finally{release();await cp.flush();cp.close();}
});
test('handoff flushing finishes current views and defers remaining derived history',async t=>{
 const {env,objects,blocked,release}=backgroundFixture(t),cp=await openCheckpoint(env);
 try{await cp.save({publicationMode:'r2',backgroundViews:true});await blocked;const flushing=cp.flush({handoff:true});release();await flushing;assert.ok(objects.has('collector-dashboard/validation.json'));assert.equal(objects.has('collector-dashboard/cards/execution.json'),false);assert.equal(env.publicationHealth.status,'current_published_history_pending');await cp.save({publicationMode:'r2',checkpointOnly:true});}finally{release();await cp.flush();cp.close();}
});
