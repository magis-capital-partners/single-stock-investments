import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter,openCheckpoint} from './reverse-split-live/checkpoint.mjs';
import {operationsChannel,operationsRefresher,operationsRefreshSettings,OPERATIONS_KEY,OPERATIONS_STAGING_KEY} from './reverse-split-live/operations-publication.mjs';
import {watchCollector} from './reverse-split-live/watch.mjs';
import {enqueue} from './reverse-split-live/worker.mjs';

const decode=bytes=>JSON.parse(new TextDecoder().decode(bytes));
const iso=ms=>new Date(ms).toISOString();
function markerDB(t){const db=new DatabaseSync(':memory:');db.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>db.close());return db;}
function storage(t){
  const remote=new DatabaseSync(':memory:');remote.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>remote.close());
  const adapter=localAdapter(remote),objects=new Map(),puts=[],counter={remote:0};
  const env={pending:[],controlDB:{prepare:sql=>{counter.remote++;return adapter.prepare(sql);},batch:async rows=>{counter.remote++;return adapter.batch(rows);}},
    EVIDENCE:{put:async(key,bytes,options={})=>{const copy=new Uint8Array(bytes);objects.set(key,copy);puts.push({key,urgent:options.urgent===true,bytes:copy});},get:async key=>objects.has(key)?{arrayBuffer:async()=>objects.get(key).slice().buffer}:null}};
  return {env,objects,puts,counter};
}
const operationPuts=puts=>puts.filter(p=>p.key===OPERATIONS_KEY).map(p=>({...decode(p.bytes),urgent:p.urgent}));

test('operations report does not replace the previous readable object before its receipt is saved', async t => {
  const {env,objects}=storage(t), channel=operationsChannel(env);
  const previous=Buffer.from('previous operations');
  objects.set(OPERATIONS_KEY,previous);
  const put=env.EVIDENCE.put;
  let release,entered;
  const gate=new Promise(resolve=>{release=resolve;});
  const waiting=new Promise(resolve=>{entered=resolve;});
  env.EVIDENCE.put=async(key,bytes,options)=>{
    if(key.includes('/operations-receipts/')){entered();await gate;}
    return put(key,bytes,options);
  };
  const at=new Date().toISOString();
  const send=channel.publish({text:JSON.stringify({state_at:at,generated_at:at}),stateAt:at,generatedAt:at});
  t.after(async()=>{release();await send.catch(()=>{});});
  await waiting;
  assert.equal(objects.get(OPERATIONS_KEY),previous);
  release();
  const {receipt}=await send;
  const latest=decode(objects.get(OPERATIONS_KEY));
  assert.equal(latest.publication.id,receipt.publication_id);
  assert.deepEqual(decode(objects.get(latest.publication.receipt_key)),receipt);
});

test('a blocked cleanup cannot hold the next durable checkpoint', async t => {
  const {env}=storage(t), cp=await openCheckpoint(env,{retainDurableBytes:true});
  let release,entered,third,fourth;
  const gate=new Promise(resolve=>{release=resolve;});
  const waiting=new Promise(resolve=>{entered=resolve;});
  env.EVIDENCE.delete=async()=>{entered();await gate;};
  t.after(async()=>{release();await Promise.allSettled([third,fourth]);await cp.flush();cp.close();});
  const save=()=>cp.save({publicationMode:'r2',checkpointOnly:true});
  await save();
  await save();
  third=save();
  await waiting;
  fourth=save();
  const result=await Promise.race([
    fourth,
    new Promise((_,reject)=>{const timer=setTimeout(()=>reject(new Error('checkpoint still waiting for cleanup')),250);timer.unref();}),
  ]);
  assert.equal(cp.durable().generation,result.generation);
});

test('a stalled checkpoint upload times out and the next queued save commits', async t => {
  const {env}=storage(t);
  const cp=await openCheckpoint(env,{retainDurableBytes:true,operationsOptions:{maxStateAgeMs:750}});
  t.after(()=>cp.close());
  const put=env.EVIDENCE.put;
  let stall=true;
  env.EVIDENCE.put=async(key,bytes,options)=>{
    if(stall&&key.startsWith('collector-state/checkpoints/')){
      stall=false;
      assert.ok(options.signal instanceof AbortSignal);
      await new Promise((_,reject)=>{
        const keepAlive=setTimeout(()=>reject(new Error('checkpoint timeout did not fire')),2000);
        options.signal.addEventListener('abort',()=>{
          clearTimeout(keepAlive);
          reject(options.signal.reason);
        },{once:true});
      });
    }
    return put(key,bytes,options);
  };
  const save=()=>cp.save({publicationMode:'r2',checkpointOnly:true});
  const stalled=save();
  const queued=save();
  await assert.rejects(stalled,{name:'TimeoutError'});
  const committed=await queued;
  assert.equal(cp.durable().generation,committed.generation);
});

test('the next checkpoint recovers a pointer commit whose response was lost', async t => {
  const {env}=storage(t), cp=await openCheckpoint(env,{retainDurableBytes:true});
  t.after(()=>cp.close());
  const prepare=env.controlDB.prepare;
  const query="SELECT value FROM rs_state WHERE key='collector_checkpoint'";
  const remotePointer=async()=>JSON.parse((await prepare(query).first()).value);
  const save=()=>cp.save({publicationMode:'r2',checkpointOnly:true});
  const first=await save();
  let loseResponse=true;
  env.controlDB.prepare=(sql,options)=>{
    const statement=prepare(sql);
    if(!sql.startsWith("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_checkpoint'"))return statement;
    assert.ok(options.signal instanceof AbortSignal);
    return {bind(...args){
      const write=statement.bind(...args);
      return {async first(){
        const result=await write.first();
        if(loseResponse){
          loseResponse=false;
          throw new DOMException('Lost pointer response','TimeoutError');
        }
        return result;
      }};
    }};
  };
  await assert.rejects(save(),{name:'TimeoutError'});
  const committed=await remotePointer();
  assert.notEqual(committed.generation,first.generation);
  assert.equal(cp.durable().generation,first.generation);
  const latest=await save();
  assert.equal(latest.previous.generation,committed.generation);
  assert.equal((await remotePointer()).generation,latest.generation);
  assert.equal(cp.durable().generation,latest.generation);
});

test('freshness checkpoint upload bypasses background research object pacing',async t=>{
 const {env,puts}=storage(t),cp=await openCheckpoint(env,{retainDurableBytes:true});
 t.after(()=>cp.close());
 await cp.save({publicationMode:'r2',checkpointOnly:true});
 const upload=puts.find(p=>p.key.startsWith('collector-state/checkpoints/'));
 assert.equal(upload.urgent,true,'fresh state cannot sit behind queued financial/history object requests');
});

test('the actual full-checkpoint worker cannot publish an over-age report',async t=>{
 const {env,puts}=storage(t);let clock;const write=env.EVIDENCE.put;
 env.EVIDENCE.put=async(key,bytes,options)=>{if(key.startsWith('collector-state/checkpoints/'))clock=Date.now()+76000;return write(key,bytes,options);};
 const cp=await openCheckpoint(env,{operationsOptions:{clock:()=>clock??Date.now(),maxStateAgeMs:75000}});
 t.after(async()=>{await cp.flush();cp.close();});
 await cp.save({publicationMode:'r2',backgroundViews:true});await cp.flush();
 assert.equal(operationPuts(puts).length,0);
 assert.equal(env.publicationHealth.status,'retry_pending');
 assert.match(env.publicationHealth.error,/checkpoint_too_old/);
});

test('an uploading successor checkpoint does not remove the last committed bytes from the refresher',async t=>{
  const {env,puts}=storage(t);let clock;const cp=await openCheckpoint(env,{retainDurableBytes:true,operationsOptions:{clock:()=>clock??Date.now()}});
  let refresher,release,saving;const gate=new Promise(resolve=>{release=resolve;});
  t.after(async()=>{release();await saving?.catch(()=>{});await refresher?.close();await cp.flush();cp.close();});
  const first=await cp.save({publicationMode:'r2'}),put=env.EVIDENCE.put;
  let uploaded;const uploading=new Promise(resolve=>{uploaded=resolve;});
  env.EVIDENCE.put=async(key,bytes,options)=>{if(key.startsWith('collector-state/checkpoints/')){uploaded();await gate;}return put(key,bytes,options);};
  saving=cp.save({publicationMode:'r2',checkpointOnly:true});await uploading;
  clock=Date.parse(first.at)+31000;refresher=operationsRefresher({checkpoint:cp,clock:()=>clock});
  assert.equal((await refresher.refresh()).published,true,'the last durable copy must remain refreshable while the next upload waits');
  assert.equal(operationPuts(puts).at(-1).state_at,first.at);
  release();await saving;
});

test('background dashboard history is captured off the collector thread',async t=>{
  const {env,objects}=storage(t),cp=await openCheckpoint(env,{retainDurableBytes:true});
  t.after(async()=>{await cp.flush();cp.close();});
  const prepare=DatabaseSync.prototype.prepare;
  t.mock.method(DatabaseSync.prototype,'prepare',function(sql){
    if(sql.startsWith('SELECT payload FROM rs_shadow_tracks ORDER BY'))throw new Error('expensive dashboard history queried on collector thread');
    return prepare.call(this,sql);
  });
  const receipt=await cp.save({publicationMode:'r2',backgroundViews:true});
  await cp.flush();
  assert.ok(objects.has('collector-dashboard/shadow.json'));
  assert.equal(decode(objects.get(OPERATIONS_KEY)).state_at,receipt.at);
});

test('durable operations publish urgently before a blocked dashboard page',async t=>{
  const {env,objects,puts}=storage(t),cp=await openCheckpoint(env,{retainDurableBytes:true});
  let release,blocked;const gate=new Promise(resolve=>{release=resolve;}),waiting=new Promise(resolve=>{blocked=resolve;});
  const put=env.EVIDENCE.put;
  env.EVIDENCE.put=async(key,bytes,options)=>{if(key==='collector-dashboard/financial-needs.json'){blocked();await gate;}return put(key,bytes,options);};
  t.after(async()=>{release();await cp.flush();cp.close();});
  const receipt=await cp.save({publicationMode:'r2',backgroundViews:true});
  await waiting;
  const visible=objects.get(OPERATIONS_KEY),first=puts.find(row=>row.key===OPERATIONS_KEY||row.key==='collector-dashboard/financial-needs.json');
  release();await cp.flush();
  assert.ok(visible,'operations must already be available while a large dashboard page waits');
  assert.equal(decode(visible).state_at,receipt.at);
  assert.equal(first.urgent,true);
  assert.equal(first.key,OPERATIONS_KEY);
});
async function addEvent(env,id,firstSeen){
  const payload={id,cik:'1'+id.length,ticker:'QA'+id.slice(-2).toUpperCase(),company:'Synthetic '+id,status:'scheduled',result:'passes_screen',first_seen_at:firstSeen,published_at:firstSeen,analyzed_at:firstSeen,sources:[]};
  await env.DB.prepare('INSERT INTO rs_events(id,cik,ticker,company,first_seen_at,published_at,analyzed_at,result,payload) VALUES(?,?,?,?,?,?,?,?,?)').bind(id,payload.cik,payload.ticker,payload.company,firstSeen,firstSeen,firstSeen,payload.result,JSON.stringify(payload)).run();
}

test('refresh interval defaults to 30 s, is configurable, and 0 disables it',()=>{
  assert.deepEqual(operationsRefreshSettings({}),{intervalMs:30000,maxStateAgeMs:120000});
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_PUBLISH_SECONDS:'15'}).intervalMs,15000);
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_PUBLISH_SECONDS:'0'}).intervalMs,0);
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_PUBLISH_SECONDS:'1'}).intervalMs,5000);
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_PUBLISH_SECONDS:'500'}).intervalMs,110000);
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_PUBLISH_SECONDS:'soon'}).intervalMs,30000);
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'240'}).maxStateAgeMs,120000);
  assert.equal(operationsRefreshSettings({RS_OPERATIONS_MAX_STATE_AGE_SECONDS:'0'}).maxStateAgeMs,120000);
});

test('the operations channel never regresses state, skips unchanged content and asserts the lease before a put',async t=>{
  const db=markerDB(t),puts=[];let leaseLost=false;
  const env={assertCollectorLease:()=>{if(leaseLost)throw new Error('Collector lease expired');},EVIDENCE:{put:async(key,bytes,options)=>puts.push({key,urgent:options.urgent===true,body:key===OPERATIONS_STAGING_KEY?null:decode(bytes)})}};
  const channel=operationsChannel(env,{db,clock:()=>Date.parse('2026-11-19T15:01:35.000Z')}),T=Date.parse('2026-11-19T15:00:00.000Z'),text=(state,generated)=>JSON.stringify({state_at:iso(state),generated_at:iso(generated)});
  const send=(state,generated,urgent=false)=>channel.publish({text:text(state,generated),stateAt:iso(state),generatedAt:iso(generated),urgent});
  assert.equal((await send(T,T)).published,true);
  assert.equal((await send(T,T+30000,true)).published,true,'a refresh of the same checkpoint at a later time publishes');
  assert.equal((await send(T,T+15000)).reason,'superseded','the same checkpoint at an older time never overwrites');
  assert.equal((await send(T-60000,T+60000,true)).reason,'superseded','an older checkpoint never overwrites newer state');
  assert.equal((await send(T+20000,T+20000)).published,true,'a newer checkpoint wins even with an earlier generated_at');
  assert.equal((await channel.publish({text:text(T+20000,T+20000),stateAt:iso(T+20000),generatedAt:iso(T+50000)})).reason,'unchanged','identical bytes are not re-put');
  leaseLost=true;await assert.rejects(send(T+90000,T+90000),/lease expired/);
  assert.deepEqual(puts.filter(p=>p.key===OPERATIONS_KEY).map(p=>[p.body.state_at,p.body.generated_at,p.urgent]),[[iso(T),iso(T),true],[iso(T),iso(T+30000),true],[iso(T+20000),iso(T+20000),true]]);
  assert.equal(db.prepare("SELECT value FROM rs_state WHERE key='snapshot:operations.json'").get().value.length,64);
});

test('channel puts are serialized: a refresh and a checkpoint publication are never in flight together',async t=>{
  let inFlight=0,most=0,release;const gate=new Promise(r=>{release=r;}),order=[];
  const env={EVIDENCE:{put:async(key,bytes)=>{if(key!==OPERATIONS_KEY)return;inFlight++;most=Math.max(most,inFlight);const body=decode(bytes);if(order.length===0)await gate;order.push(body.generated_at);inFlight--;}}};
  const channel=operationsChannel(env,{db:markerDB(t),clock:()=>Date.parse('2026-11-19T15:00:30.000Z')}),T=Date.parse('2026-11-19T15:00:00.000Z');
  const first=channel.publish({text:JSON.stringify({generated_at:iso(T)}),stateAt:iso(T),generatedAt:iso(T)}),second=channel.publish({text:JSON.stringify({generated_at:iso(T+30000)}),stateAt:iso(T),generatedAt:iso(T+30000),urgent:true});
  await new Promise(r=>setTimeout(r,20));assert.equal(order.length,0);release();await Promise.all([first,second]);
  assert.equal(most,1);assert.deepEqual(order,[iso(T),iso(T+30000)]);
});

test('a refresh publishes the last committed checkpoint re-evaluated now, never uncommitted live rows, with no database call',async t=>{
  const {env,objects,puts,counter}=storage(t),start=Date.now();
  let clock;let cp=await openCheckpoint(env,{retainDurableBytes:true,operationsOptions:{clock:()=>clock??Date.now()}});
  let refresher;t.after(async()=>{await refresher?.close();cp?.close();});
  await addEvent(env,'qa-durable-01',iso(start-60000));
  const receipt=await cp.save({publicationMode:'r2'});
  const atCheckpoint=operationPuts(puts);assert.equal(atCheckpoint.length,1);assert.equal(atCheckpoint[0].state_at,receipt.at);assert.equal(atCheckpoint[0].urgent,true);assert.equal(atCheckpoint[0].candidate_count,1);
  await addEvent(env,'qa-live-only-02',iso(start-30000));
  clock=Date.parse(receipt.at)+40000;
  refresher=operationsRefresher({checkpoint:cp,intervalMs:30000,maxStateAgeMs:180000,clock:()=>clock});
  assert.equal(refresher.due(),true);
  counter.remote=0;const result=await refresher.refresh();assert.equal(result.published,true);assert.equal(counter.remote,0,'a refresh makes no remote database read or write');
  const refreshed=operationPuts(puts).at(-1);
  assert.equal(refreshed.generated_at,iso(clock));assert.equal(refreshed.state_at,receipt.at);assert.equal(refreshed.urgent,true);
  assert.deepEqual(refreshed.candidates.map(c=>c.id),['qa-durable-01'],'the uncommitted live row is not published');
  assert.equal(refresher.due(),false,'just published');clock+=29500;assert.equal(refresher.due(),true,'due again one tick before the 30-second target');
  const second=await refresher.refresh();assert.equal(second.published,true);assert.equal(operationPuts(puts).at(-1).generated_at,iso(clock));
  assert.equal(refresher.health().published,2);assert.equal(refresher.health().last_state_at,receipt.at);
  // A successor restores this generation: every refreshed candidate is still there.
  const published=decode(objects.get(OPERATIONS_KEY));await refresher.close();refresher=null;cp.close();cp=await openCheckpoint(env);
  const restored=(await env.DB.prepare('SELECT id FROM rs_events ORDER BY id').all()).results.map(r=>r.id);
  for(const c of published.candidates)assert.ok(restored.includes(c.id));assert.ok(!restored.includes('qa-live-only-02'));
});

test('a newer checkpoint is reloaded, and refresh pauses once the committed checkpoint is too old',async t=>{
  const {env,puts}=storage(t),start=Date.now();let clock;const cp=await openCheckpoint(env,{retainDurableBytes:true,operationsOptions:{clock:()=>clock??Date.now()}});let refresher;t.after(async()=>{await refresher?.close();cp.close();});
  await addEvent(env,'qa-first-01',iso(start-60000));const first=await cp.save({publicationMode:'r2'});
  clock=Date.parse(first.at)+35000;refresher=operationsRefresher({checkpoint:cp,intervalMs:30000,maxStateAgeMs:120000,clock:()=>clock});
  assert.equal((await refresher.refresh()).published,true);assert.equal(operationPuts(puts).at(-1).candidate_count,1);
  await addEvent(env,'qa-second-02',iso(start-30000));const second=await cp.save({publicationMode:'r2'});assert.notEqual(second.generation,first.generation);
  clock=Math.max(clock,Date.parse(second.at))+31000;assert.equal((await refresher.refresh()).published,true);
  const latest=operationPuts(puts).at(-1);assert.equal(latest.state_at,second.at);assert.equal(latest.candidate_count,2);
  const before=puts.length;clock=Date.parse(second.at)+121000;
  assert.deepEqual(await refresher.refresh(),{published:false,reason:'paused_checkpoint_too_old'});assert.equal(puts.length,before);assert.equal(refresher.health().status,'paused_checkpoint_too_old');
});

test('refresh evaluates only bytes matching the committed receipt, backs off after failure and fails closed on a lost lease',async t=>{
  const puts=[];let leaseLost=false;const env={assertCollectorLease:()=>{if(leaseLost)throw new Error('Collector lease lost');},EVIDENCE:{put:async key=>puts.push(key)}};
  const invalid={generation:randomUUID(),at:new Date().toISOString(),sha256:'0'.repeat(64)};
  const fake={operations:operationsChannel(env),durable:()=>invalid,takeDurableBytes:()=>new Uint8Array([1,2,3])};
  const refresher=operationsRefresher({checkpoint:fake});t.after(()=>refresher.close());
  await assert.rejects(refresher.refresh(),/checksum mismatch/);assert.equal(puts.length,0);assert.equal(refresher.health().status,'retry_pending');
  assert.equal(refresher.due(),false,'a failed refresh backs off instead of retrying every tick');
  const {env:real,puts:realPuts}=storage(t);const cp=await openCheckpoint(real,{retainDurableBytes:true});let leased;t.after(async()=>{await leased?.close();cp.close();});
  real.assertCollectorLease=()=>{if(leaseLost)throw new Error('Collector lease lost');};const receipt=await cp.save({publicationMode:'r2'});
  leased=operationsRefresher({checkpoint:cp,clock:()=>Date.parse(receipt.at)+31000});leaseLost=true;const count=realPuts.length;
  await assert.rejects(leased.refresh(),/lease lost/);assert.equal(realPuts.length,count);
});

function collectorEnv(t){
  const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(x=>x.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());
  const env={DB:localAdapter(db),SHADOW_ENABLED:'true'};env.controlDB=env.DB;env.pending=[];env.usage={rows_read:0,rows_written:0};env.JOBS={send:async body=>env.pending.push(body)};env.ENABLED='true';env.SEC_USER_AGENT='Synthetic offline test';env.market={health:{status:'not_configured'},quote:async()=>{throw new Error('No ticker in this test');}};
  return env;
}
test('the continuous collector refreshes operations between checkpoints and stops before releasing its lease',async t=>{
  const env=collectorEnv(t),objects=new Map(),writes=[],audit=[];
  env.onOperationsAudit=row=>audit.push(row);
  env.EVIDENCE={put:async(k,b,o={})=>{const lease=(await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='collector_lease'").first())?.value;writes.push({key:k,urgent:o.urgent===true,leased:lease&&lease!=='0',bytes:new Uint8Array(b)});objects.set(k,new Uint8Array(b));},get:async k=>objects.has(k)?{arrayBuffer:async()=>objects.get(k).slice().buffer}:null};
  const old=globalThis.fetch;globalThis.fetch=async()=>new Response('<feed></feed>');t.after(()=>{globalThis.fetch=old;});
  let stopped=false;const result=await watchCollector(env,{maximumMs:20000,operations:{intervalMs:1000,maxStateAgeMs:60000},shouldStop:()=>stopped,sleep:async()=>{await new Promise(r=>setTimeout(r,3200));stopped=true;}});
  assert.equal(result.ticks,1);
  const ops=writes.filter(w=>w.key===OPERATIONS_KEY),refreshes=ops.filter(w=>w.urgent).map(w=>decode(w.bytes));
  assert.ok(refreshes.length>=2,`expected refreshes between checkpoints, saw ${refreshes.length}`);
  assert.equal(new Set(refreshes.map(r=>r.state_at)).size,1,'all refreshes re-evaluate the one checkpoint taken at start; none checkpoints');
  for(const r of refreshes)assert.ok(Date.parse(r.generated_at)>=Date.parse(r.state_at));
  for(let i=1;i<refreshes.length;i++)assert.ok(Date.parse(refreshes[i].generated_at)-Date.parse(refreshes[i-1].generated_at)<=2500,'consecutive refreshes stay near the target');
  assert.ok(ops.every(w=>w.leased),'no operations put after the lease is released');
  assert.ok(!audit.some(row=>row.event==='publication_upload'&&row.kind==='full_checkpoint'),'dashboard must not compete for the report upload queue');
  const runtime=JSON.parse((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='shadow_runtime'").first()).value);
  assert.equal(runtime.status,'handoff');assert.ok(runtime.operations_publication.published>=2);assert.equal(runtime.operations_publication.interval_seconds,1);
  assert.equal((await env.controlDB.prepare("SELECT value FROM rs_state WHERE key='collector_lease'").first()).value,'0');
});

test('slow pre-job imports cannot consume the entire source-processing budget',async t=>{
 const env=collectorEnv(t),objects=new Map(),remote=env.controlDB;let seeded=false;
 const delayed=statement=>({...statement,bind:(...args)=>delayed(statement.bind(...args)),all:async()=>{await new Promise(r=>setTimeout(r,1100));return statement.all();}});
 env.controlDB={...remote,prepare:sql=>sql.startsWith('SELECT payload FROM rs_shadow_evidence WHERE kind IN')?delayed(remote.prepare(sql)):remote.prepare(sql)};
 env.EVIDENCE={put:async(k,b)=>{objects.set(k,new Uint8Array(b));if(k==='collector-dashboard/runtime.json'&&!seeded){seeded=true;const at=new Date().toISOString();await enqueue(env,'news',{url:'https://www.prnewswire.com/news-releases/ordinary-302900002.html',published_at:at,first_seen_at:at},15,'slow-loop-source');}},get:async k=>objects.has(k)?{arrayBuffer:async()=>objects.get(k).slice().buffer}:null};
 const previous=globalThis.fetch;t.after(()=>globalThis.fetch=previous);globalThis.fetch=async value=>new Response(String(value).endsWith('.html')?'<html><article>Ordinary source body</article></html>':'<feed></feed>');
 let stopped=false;const result=await watchCollector(env,{maximumMs:20000,operations:{intervalMs:0,maxStateAgeMs:60000},shouldStop:()=>stopped,sleep:async()=>{stopped=true;}});
 assert.equal(result.ticks,1);const cp=await openCheckpoint(env);try{assert.equal((await env.DB.prepare("SELECT state FROM rs_jobs WHERE id='slow-loop-source'").first()).state,'complete','The queued source must be analyzed even when imports took longer than one second');}finally{cp.close();}
});


test('a large successor checkpoint reuses unchanged compressed blocks and restores the exact database',async t=>{
  const {env,objects}=storage(t);const audit=[];env.onOperationsAudit=row=>audit.push(row);
  const cp=await openCheckpoint(env);t.after(()=>cp.close());env.CHECKPOINT_COMPRESSION='gzip';
  await env.DB.prepare('CREATE TABLE large_fixture(payload BLOB)').run();
  await env.DB.prepare('INSERT INTO large_fixture VALUES(?)').bind(new Uint8Array(20*1024*1024).fill(61)).run();
  const first=await cp.save({publicationMode:'r2',checkpointOnly:true});
  await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?)').bind('reuse-test','new','2026-11-24T00:00:00Z').run();
  const second=await cp.save({publicationMode:'r2',checkpointOnly:true});
  const rows=audit.filter(x=>x.event==='checkpoint_committed');
  assert.ok(rows[1].reused_compression_blocks>=1,'mutating a small row must not compress every database block again');
  assert.ok(rows[1].compressed_blocks<rows[0].compressed_blocks);
  assert.ok(objects.get(second.key));assert.notEqual(first.sha256,second.sha256);
  const recoveryEnv={...env};const recovered=await openCheckpoint(recoveryEnv);t.after(()=>recovered.close());
  assert.equal((await recoveryEnv.DB.prepare("SELECT value FROM rs_state WHERE key='reuse-test'").first()).value,'new');
  assert.equal((await recoveryEnv.DB.prepare('SELECT length(payload) AS bytes FROM large_fixture').first()).bytes,20*1024*1024);
  assert.equal(second.compression,'gzip','rollback readers can still open ordinary gzip checkpoints');
});

test('a fresh checkpoint can publish during the backoff of a failed older checkpoint',async t=>{
  const {env,puts}=storage(t);let clock;const cp=await openCheckpoint(env,{retainDurableBytes:true,operationsOptions:{clock:()=>clock??Date.now(),maxStateAgeMs:75000}});
  let refresher;t.after(async()=>{await refresher?.close();cp.close();});
  const first=await cp.save({publicationMode:'r2',checkpointOnly:true});
  clock=Date.parse(first.at)+30000;
  const put=env.EVIDENCE.put;
  env.EVIDENCE.put=async(key,...args)=>{if(key===OPERATIONS_STAGING_KEY)throw new Error('publication transport failed');return put(key,...args);};
  refresher=operationsRefresher({checkpoint:cp,intervalMs:10000,maxStateAgeMs:75000,clock:()=>clock});
  await assert.rejects(refresher.refresh(),/publication transport failed/);
  assert.equal(refresher.due(),false);
  env.EVIDENCE.put=put;
  const next=await cp.save({publicationMode:'r2',checkpointOnly:true});
  clock+=1000;
  assert.equal(refresher.due(),true,'newly committed evidence must not inherit a previous generation’s upload backoff');
  assert.equal((await refresher.refresh()).published,true);
  assert.equal(operationPuts(puts).at(-1).state_at,next.at);
});

test('a publication with insufficient time for all three writes does not start a doomed upload',async t=>{
 const {env,puts}=storage(t);const T=Date.parse('2026-11-24T14:30:00Z');
 const channel=operationsChannel(env,{clock:()=>T+70000,maxStateAgeMs:75000});
 const at=iso(T),generated=iso(T+70000),result=await channel.publish({text:JSON.stringify({state_at:at,generated_at:generated}),stateAt:at,generatedAt:generated});
 assert.equal(result.reason,'insufficient_publication_headroom');
 assert.equal(puts.length,0);
});


test('an expired publication budget avoids opening a large committed database',async t=>{
 const {env}=storage(t),cp=await openCheckpoint(env,{retainDurableBytes:true});let refresher;t.after(async()=>{await refresher?.close();cp.close();});
 const receipt=await cp.save({publicationMode:'r2',checkpointOnly:true});
 const clock=()=>Date.parse(receipt.at)+70000;
 let loads=0;
 const checkpoint={...cp,takeDurableBytes(generation){loads++;return cp.takeDurableBytes(generation);}};
 refresher=operationsRefresher({checkpoint,clock,maxStateAgeMs:75000});
 const result=await refresher.refresh();
 assert.equal(loads,0,'loading bytes is wasted if all report writes cannot fit in the remaining age budget');
 assert.equal(result.reason,'insufficient_publication_headroom');
 assert.equal(refresher.due(),false,'wait for the next committed generation');
});
