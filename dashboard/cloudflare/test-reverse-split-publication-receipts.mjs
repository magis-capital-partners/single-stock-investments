import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {operationsChannel,OPERATIONS_KEY,OPERATIONS_STAGING_KEY} from './reverse-split-live/operations-publication.mjs';

const T=Date.parse('2026-11-23T14:30:00.000Z');
const iso=ms=>new Date(ms).toISOString();
const text=(state=T,generated=T)=>JSON.stringify({schema:'reverse_split_operations.v1',state_at:iso(state),generated_at:iso(generated),candidates:[]});

test('an upload acknowledged after the age deadline is recorded but cannot be accepted',async()=>{
 let now=T+65000;const objects=new Map(),audit=[];
 const env={RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'75',onOperationsAudit:r=>audit.push(r),EVIDENCE:{put:async(key,bytes)=>{objects.set(key,Buffer.from(bytes));if(key===OPERATIONS_STAGING_KEY)now+=11000;}}};
 const channel=operationsChannel(env,{clock:()=>now});
 const result=await channel.publish({text:text(T,T+64000),stateAt:iso(T),generatedAt:iso(T+64000)});
 assert.equal(result.published,false);assert.equal(result.reason,'state_too_old_at_ack');
 assert.equal(result.receipt.upload_completed_at,iso(T+76000));
 assert.equal(result.receipt.accepted,false);assert.equal(objects.has(OPERATIONS_KEY),false);assert.equal(audit[0].outcome,'state_too_old_at_ack');
});

test('full-checkpoint publication refuses state beyond the same configured 75s guard',async()=>{
 const writes=[];let now=T+76000;
 const env={RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'75',EVIDENCE:{put:async(key,bytes)=>writes.push({key,bytes})}};
 const channel=operationsChannel(env,{clock:()=>now});
 const result=await channel.publish({text:text(T,T+70000),stateAt:iso(T),generatedAt:iso(T+70000)});
 assert.equal(result.published,false,'an old full checkpoint must not bypass the refresher guard');
 assert.equal(result.reason,'paused_checkpoint_too_old');
 assert.equal(writes.length,0);
});

test('guard is rechecked after queue wait, before the actual object upload',async()=>{
 let now=T+65000,release,entered;const gate=new Promise(resolve=>{release=resolve;}),waiting=new Promise(resolve=>{entered=resolve;});
 const writes=[];let first=true;
 const env={RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'75',EVIDENCE:{put:async(key,bytes)=>{writes.push(key);if(key===OPERATIONS_KEY&&first){first=false;entered();await gate;}}}};
 const channel=operationsChannel(env,{clock:()=>now});
 const a=channel.publish({text:text(T,T+64000),stateAt:iso(T),generatedAt:iso(T+64000)});
 const b=channel.publish({text:text(T,T+65000),stateAt:iso(T),generatedAt:iso(T+65000)});
 await waiting;now=T+76000;release();await a;
 assert.equal((await b).published,false);
 assert.equal(writes.filter(k=>k===OPERATIONS_KEY).length,1,'the queued stale object is never uploaded');
});

test('upload completion is recorded after acknowledgement and bound to the exact report bytes',async()=>{
 let now=T+10000;const objects=new Map();
 const env={RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'75',EVIDENCE:{put:async(key,bytes)=>{objects.set(key,Buffer.from(bytes));now+=key===OPERATIONS_STAGING_KEY?2000:500;}}};
 const channel=operationsChannel(env,{clock:()=>now});
 const result=await channel.publish({text:text(),stateAt:iso(T),generatedAt:iso(T),kind:'full_checkpoint'});
 assert.equal(result.published,true);
 const body=objects.get(OPERATIONS_KEY),report=JSON.parse(body);
 assert.deepEqual(gunzipSync(objects.get(OPERATIONS_STAGING_KEY)),body);
 assert.ok(report.publication?.receipt_key,'report must identify its immutable upload receipt');
 const receipt=JSON.parse(objects.get(report.publication.receipt_key));
 assert.equal(receipt.publication_id,report.publication.id);
 assert.equal(receipt.report_sha256,createHash('sha256').update(body).digest('hex'));
 assert.equal(receipt.upload_started_at,iso(T+10000));
 assert.equal(receipt.upload_completed_at,iso(T+12000),'this is the ACK clock, not generation or PUT start');
 assert.equal(receipt.state_age_at_upload_completion_seconds,12);
 assert.equal(receipt.kind,'full_checkpoint');
 assert.equal(receipt.accepted,true);
});

test('a receipt that exhausts the age budget leaves the previous report visible',async()=>{
 let now=T+65000;
 const previous=Buffer.from(text(T,T+60000)),objects=new Map([[OPERATIONS_KEY,previous]]);
 const env={RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'75',EVIDENCE:{put:async(key,bytes)=>{
   objects.set(key,Buffer.from(bytes));
   if(key.includes('/operations-receipts/'))now=T+75001;
 }}};
 const channel=operationsChannel(env,{clock:()=>now});
 await assert.rejects(channel.publish({text:text(T,T+64000),stateAt:iso(T),generatedAt:iso(T+64000)}),/freshness budget expired/);
 assert.equal(objects.get(OPERATIONS_KEY),previous);
 assert.equal(channel.last(),null);
});
