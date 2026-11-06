import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {remoteEnvironment,isolatedWriteFailure,safeContentType,cloudflareErrorDetail} from './reverse-split-live/collector.mjs';
import {runFinancialHarvest} from './reverse-split-live/financials-harvest.mjs';
import {isSourceCooldown} from './reverse-split-live/financials-io.mjs';
import {recoverWatch} from './reverse-split-live/recovery.mjs';

const TOKEN='fixture-secret-token';
const D1_DAILY_LIMIT={result:[],success:false,errors:[{code:7500,message:"Your account has exceeded D1's free tier daily row read limit. Upgrade to a paid plan or wait until tomorrow (midnight UTC) to continue."}],messages:[]};
const remote=fetcher=>remoteEnvironment({token:TOKEN,account:'acct',database:'db',bucket:'bucket',evidenceInterval:0,fetcher});

test('D1 rejections report status, service, request path and the Cloudflare error without credentials',async()=>{
  const env=remote(async()=>Response.json(D1_DAILY_LIMIT,{status:400}));
  const error=await env.DB.prepare('SELECT 1').first().then(()=>null,e=>e);
  assert.match(error.message,/^Research storage HTTP 400 from D1 POST \/d1\/database\/db\/query: 7500 Your account has exceeded D1's free tier daily row read limit/);
  assert.equal(error.httpStatus,400);assert.equal(error.service,'D1');assert.equal(error.cloudflareCode,7500);
  assert.equal(error.message.includes(TOKEN),false);assert.equal(error.message.includes('acct'),false);
  // A storage 400/403 must never be mistaken for an SEC source cooldown or terminal 404.
  assert.equal('status' in error,false);assert.equal(isSourceCooldown(error),false);
  assert.equal(isolatedWriteFailure(error),false);
});

test('R2 write rejections name the object path, bound the body snippet and redact echoed tokens',async()=>{
  const env=remote(async()=>new Response(`<Error>bad request ${TOKEN} `+'x'.repeat(1000)+'</Error>',{status:400}));
  const error=await env.EVIDENCE.put('financials/queue.json',new Uint8Array([1])).then(()=>null,e=>e);
  assert.match(error.message,/^Research storage HTTP 400 from R2 PUT \/r2\/buckets\/bucket\/objects\/financials\/queue\.json: <Error>bad request \[redacted\] x+…$/);
  assert.ok(error.message.length<450);assert.equal(error.message.includes(TOKEN),false);
  assert.equal(isolatedWriteFailure(error),true);
  const denied=await remote(async()=>Response.json({success:false,errors:[{code:10000,message:'Authentication error'}]},{status:403})).EVIDENCE.put('k',new Uint8Array()).then(()=>null,e=>e);
  assert.match(denied.message,/HTTP 403 from R2 PUT .*: 10000 Authentication error$/);assert.equal(isolatedWriteFailure(denied),false);
});

test('D1 statement failures inside a successful envelope carry the per-statement error',async()=>{
  const env=remote(async()=>Response.json({success:true,errors:[],result:[{success:false,error:'D1_ERROR: no such table: rs_missing'}]}));
  await assert.rejects(env.DB.prepare('SELECT * FROM rs_missing').all(),{name:'ResearchStorageError',message:'Research database query failed: D1_ERROR: no such table: rs_missing'});
  assert.equal(cloudflareErrorDetail(''),'');
});

test('transient storage failures keep the recovery classification',async()=>{
  const env=remote(async()=>Response.json({success:false,errors:[{code:10001,message:'Internal error'}]},{status:503}));
  const error=await env.EVIDENCE.get('k').then(()=>null,e=>e);let calls=0,now=0;
  await assert.rejects(recoverWatch(async()=>{calls++;throw error;},{maximumMs:100000,clock:()=>now,pause:async ms=>{now+=ms;},report:()=>{}}),/HTTP 503 from R2 GET/);
  assert.equal(calls,3);
});

test('object puts send only a well-formed single media type',async()=>{
  const sent=[],env=remote(async(url,options)=>{sent.push(options.headers['content-type']);return new Response(null,{status:200});});
  for(const value of ['application/json','text/html; charset=UTF-8','application/pdf;name="10-K report.pdf"',undefined,'','text/html, text/plain','text/html\r\nx-injected: 1','<!DOCTYPE html>','a/'+'b'.repeat(300)])await env.EVIDENCE.put('k',new Uint8Array(),{httpMetadata:{contentType:value}});
  assert.deepEqual(sent,['application/json','text/html; charset=UTF-8','application/pdf;name="10-K report.pdf"',...Array(6).fill('application/octet-stream')]);
  assert.equal(safeContentType('  image/png  '),'image/png');
});

function storageFixture(t,{rejectPut=()=>false}={}){
  const db=new DatabaseSync(':memory:');t.after(()=>db.close());
  for(const name of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+name,import.meta.url),'utf8'));
  const objects=new Map(),puts=[];
  const run=({sql,params=[]})=>({success:true,results:db.prepare(sql).all(...params),meta:{rows_read:0,rows_written:0}});
  const env=remote(async(url,options)=>{
    const path=new URL(url).pathname.replace(/^\/client\/v4\/accounts\/acct/,'');
    if(path==='/d1/database/db/query'){const body=JSON.parse(options.body);return Response.json({success:true,result:body.batch?body.batch.map(run):[run(body)]});}
    const key=decodeURIComponent(path.replace('/r2/buckets/bucket/objects/',''));
    if(options.method==='PUT'){puts.push(key);if(rejectPut(key,puts))return Response.json({success:false,errors:[{code:10020,message:'Invalid object write'}]},{status:400});objects.set(key,new Uint8Array(await new Response(options.body).arrayBuffer()));return new Response(null,{status:200});}
    return objects.has(key)?new Response(objects.get(key)):new Response('',{status:404});
  });
  return {db,env,objects,puts};
}

test('financial harvest defers one rejected queue write and still publishes coverage',async t=>{
  let rejected=0;const {env,objects,puts}=storageFixture(t,{rejectPut:key=>key==='financials/queue.json'&&!rejected++});
  objects.set('financials/queue.json',new TextEncoder().encode(JSON.stringify({jobs:{'1':{cik:'1',ticker:'ABC',priority:50,attempts:0,next_attempt:0}}})));
  const logs=[];t.mock.method(console,'error',line=>logs.push(JSON.parse(line)));t.mock.method(console,'log',()=>{});
  const result=await runFinancialHarvest(env,{maxIssuers:1,offline:true});
  assert.equal(result.handled,1);
  assert.deepEqual(logs.map(r=>[r.event,r.stage,r.consecutive]),[['financial_harvest_write_deferred','queue',1]]);
  assert.match(logs[0].error,/HTTP 400 from R2 PUT \/r2\/buckets\/bucket\/objects\/financials\/queue\.json: 10020 Invalid object write/);
  assert.ok(puts.includes('financials/manifest-latest.json'));
  assert.equal(JSON.parse(new TextDecoder().decode(objects.get('financials/queue.json'))).jobs['1'].error,'Financial source is not cached');
});

test('financial harvest stops after repeated rejected writes rather than spinning silently',async t=>{
  const {env,objects}=storageFixture(t,{rejectPut:key=>key==='financials/queue.json'||key.startsWith('financials/pages/')||key==='financials/manifest-latest.json'});
  objects.set('financials/queue.json',new TextEncoder().encode(JSON.stringify({jobs:Object.fromEntries(Array.from({length:6},(_,i)=>[String(i+1),{cik:String(i+1),priority:50,attempts:0,next_attempt:0}]))})));
  t.mock.method(console,'error',()=>{});t.mock.method(console,'log',()=>{});
  await assert.rejects(runFinancialHarvest(env,{maxIssuers:6,offline:true}),/HTTP 400 from R2 PUT/);
});

test('financial harvest never defers D1 control-plane failures',async t=>{
  const env=remote(async()=>Response.json(D1_DAILY_LIMIT,{status:400}));
  await assert.rejects(runFinancialHarvest(env,{maxIssuers:1,offline:true}),/HTTP 400 from D1 POST \/d1\/database\/db\/query: 7500 Your account has exceeded D1's free tier daily row read limit/);
});
