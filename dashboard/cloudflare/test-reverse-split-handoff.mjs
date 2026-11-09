import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {finishHandoff} from './reverse-split-live/handoff.mjs';
import {openCheckpoint,localAdapter} from './reverse-split-live/checkpoint.mjs';

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
