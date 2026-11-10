import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {readFileSync,readdirSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {makeDatabentoMarket} from './reverse-split-live/databento-market.mjs';
import {SHADOW_POLICIES,quoteGate} from './reverse-split-live/shadow-core.mjs';
import {initializeShadow,enrollShadow,processShadowTrack,shadowTick} from './reverse-split-live/shadow-service.mjs';
const now='2026-11-04T15:00:00.000Z',mini=SHADOW_POLICIES.find(p=>p.id==='rs_immediate_mini.v1');
function transport(t){
  const child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();child.kill=()=>child.emit('exit',0);
  let launches=0,spawnArgs,commands='';child.stdin.on('data',chunk=>commands+=chunk.toString());
  const reference={health:{quote_access:'not_entitled'},identity:async()=>({cik:'123',security_id:'qa-identity',type:'CS',currency:'usd'}),quote:async()=>{throw new Error('NBBO not entitled');},news:async()=>[],actions:async()=>({records:[],complete:true})};
  const market=makeDatabentoMarket({key:'qa-key-never-forwarded',reference,clock:()=>now,spawnProcess:(...args)=>{launches++;spawnArgs=args;return child;}});
  t.after(()=>{market.close();child.emit('exit',0);});
  const send=row=>child.stdout.write(JSON.stringify(row)+'\n');
  return {market,child,send,reference,launches:()=>launches,commands:()=>commands,args:()=>spawnArgs};
}
function row(extra={}){return {kind:'quote',ticker:'QA',dataset:'EQUS.MINI',schema:'mbp-1',quote_at:now,observed_at:now,bid:10,ask:10.1,bid_size:1000,ask_size:2000,flags:0,ts_recv_ns:String(Date.parse(now)*1e6),...extra};}
function setup(t){const db=new DatabaseSync(':memory:');for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(x=>x.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));t.after(()=>db.close());return {db,env:{DB:localAdapter(db),SHADOW_ENABLED:'true'}};}
function event(id='qa'){return {id,cik:'123',ticker:'QA',company:'QA fixture',status:'scheduled',effective_date:'2026-11-20',first_seen_at:now,published_at:now,analyzed_at:now,ordinal_min:2,financials:{score:75,signal_count:3,period:'2026-06-30'},sources:[]};}

test('announcement observation peeks raw books before score eligibility and verifies identity without a second feed',async t=>{const x=transport(t);x.market.warm('QA');x.send(row());await new Promise(resolve=>setImmediate(resolve));assert.equal(x.market.peek('QA').bid_size,1000);assert.equal(x.market.peek('QA').identity_verified,false);await x.market.verifyIdentity('QA');assert.equal(x.market.peek('QA').identity_verified,true);assert.equal(x.market.peek('QA').cik,'123');assert.equal(x.launches(),1);});

test('one live session uses secret environment only, preserves limited coverage and never falls back to history',async t=>{
  const x=transport(t);await assert.rejects(x.market.quote('QA',mini),/Waiting/);x.send(row());
  const q=await x.market.quote('QA',mini);assert.equal(q.bid_size,1000);assert.equal(q.consolidated,false);assert.equal(q.provider,'databento_mini');assert.equal(q.cik,'123');assert.equal(quoteGate(q,now,mini),null);assert.equal(quoteGate(q,now,SHADOW_POLICIES[0]),'live_consolidated_quote_required');
  await assert.rejects(x.market.quote('QA',SHADOW_POLICIES[0]),/NBBO not entitled/);assert.equal(x.launches(),1);assert.equal(x.commands().trim().split('\n').length,1);assert.ok(!JSON.stringify(x.args().slice(0,2)).includes('qa-key'));assert.ok(!JSON.stringify(x.market.health).includes('qa-key'));assert.equal(x.args()[2].env.DATABENTO_API_KEY,'qa-key-never-forwarded');assert.equal(x.market.activePolicy,mini.id);
});
test('disconnects, invalid books and old clocks invalidate cached Mini quotes',async t=>{
  const x=transport(t);await assert.rejects(x.market.quote('QA',mini));x.send(row());await x.market.quote('QA',mini);
  for(const change of [{flags:4},{quote_at:'2026-11-04T14:00:00Z'},{ask:9},{observed_at:'2026-11-04T15:02:00Z'}]){x.send(row(change));await assert.rejects(x.market.quote('QA',mini),/Waiting/);}
  x.send(row());x.send({kind:'health',status:'disconnected'});await assert.rejects(x.market.quote('QA',mini),/Waiting/);assert.equal(x.market.health.quote_access,'unavailable');
  x.send(row());x.send({kind:'invalidate',ticker:'QA'});await assert.rejects(x.market.quote('QA',mini));
  await assert.rejects(x.market.quote('BRK-B',mini),/explicit verification/);
});
test('latency samples retain earlier receipts rather than timing only the newest cached book',async t=>{const x=transport(t);await assert.rejects(x.market.quote('AAPL',mini));const early='2026-11-04T14:59:50.000Z';x.send(row({ticker:'AAPL',quote_at:early,observed_at:early}));x.send(row({ticker:'AAPL',quote_at:now,observed_at:now}));x.send(row({ticker:'AAPL',quote_at:now,observed_at:now}));assert.equal((await x.market.quote('AAPL',mini)).quote_at,now);const telemetry=x.market.drainTelemetry();assert.equal(telemetry.samples.length,2);assert.equal(telemetry.samples[0].observed_at,early);assert.equal(x.market.drainTelemetry().samples.length,0);assert.equal(x.launches(),1);});
test('new Mini registration does not rewrite the original policies or create backward fills',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');
  const originals=db.prepare("SELECT payload FROM rs_shadow_policies WHERE id NOT LIKE '%_mini.v1' ORDER BY id").all();assert.equal(originals.length,7);assert.ok(originals.every(r=>!JSON.parse(r.payload).quote_feed));
  db.prepare("DELETE FROM rs_shadow_policies WHERE id LIKE '%_mini.v1'").run();await initializeShadow(env,now);
  await enrollShadow(env,{...event(),first_seen_at:'2026-11-04T14:59:50Z'},now);
  const original=JSON.parse(db.prepare('SELECT payload FROM rs_shadow_tracks WHERE policy_id=?').get('rs_immediate.v1').payload),limited=JSON.parse(db.prepare('SELECT payload FROM rs_shadow_tracks WHERE policy_id=?').get(mini.id).payload);
  assert.equal(original.state,'armed');assert.equal(limited.state,'retrospective');assert.deepEqual(db.prepare("SELECT payload FROM rs_shadow_policies WHERE id NOT LIKE '%_mini.v1' ORDER BY id").all(),originals);
});
test('Mini quotes fill only their separately registered portfolio with coverage in the audit',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);
  const original=JSON.parse(db.prepare('SELECT payload FROM rs_shadow_tracks WHERE policy_id=?').get('rs_immediate.v1').payload),limited=JSON.parse(db.prepare('SELECT payload FROM rs_shadow_tracks WHERE policy_id=?').get(mini.id).payload);
  const q={...row(),id:'qa-quote',provider:'databento_mini',coverage:'selected_venues_not_sip_nbbo',consolidated:false,delayed:false,cik:'123',security_id:'qa-identity',type:'CS',currency:'usd'};
  await processShadowTrack(env,original,q,[original,limited],now);await processShadowTrack(env,limited,q,[original,limited],now);
  assert.equal(original.entry_shares,0);assert.equal(limited.entry_shares,50);assert.equal(limited.indicative,true);assert.equal(limited.quote_coverage,'selected_venues_not_sip_nbbo');assert.equal(limited.feasibility.broker_execution_verified,false);
});
test('collector quote cache keeps full-market and Mini sources separate for the same ticker',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);const feeds=[];
  env.market={health:{status:'available'},quote:async(ticker,p)=>{feeds.push(p.quote_feed||'consolidated');throw new Error('Offline fixture');}};
  await shadowTick(env,{now});assert.deepEqual(feeds.sort(),['consolidated','databento_mini']);assert.equal(db.prepare('SELECT sum(json_extract(payload,\'$.entry_shares\')) AS shares FROM rs_shadow_tracks').get().shares,0);
});
test('a still-fresh cached quote received before the entry or exit clock cannot create a fill',async t=>{
  const {db,env}=setup(t);await initializeShadow(env,'2026-11-04T14:00:00Z');await enrollShadow(env,event(),now);
  const x=JSON.parse(db.prepare('SELECT payload FROM rs_shadow_tracks WHERE policy_id=?').get(mini.id).payload);
  const q={...row(),id:'before',provider:'databento_mini',coverage:'selected_venues_not_sip_nbbo',consolidated:false,delayed:false,cik:'123',security_id:'qa-identity',type:'CS',currency:'usd',observed_at:'2026-11-04T14:59:59.999Z'};
  await processShadowTrack(env,x,q,[x],now);assert.equal(x.entry_shares,0);assert.equal(x.reason,'quote_received_before_entry_clock');
  await processShadowTrack(env,x,{...q,id:'after',observed_at:now},[x],now);assert.equal(x.entry_shares,50);
  const exit='2026-11-10T20:59:30.000Z',early={...q,id:'early-cover',quote_at:exit,observed_at:'2026-11-10T20:59:29.999Z'};
  await processShadowTrack(env,x,early,[x],exit);assert.equal(x.remaining_shares,50);assert.equal(x.reason,'waiting_for_post_exit_quote');
  await processShadowTrack(env,x,{...early,id:'cover',observed_at:exit},[x],exit);assert.equal(x.remaining_shares,0);assert.equal(x.state,'closed');
});
