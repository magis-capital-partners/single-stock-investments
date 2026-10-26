'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),R=require('./replay.cjs'),P=require('./portfolio.cjs');
const hash='a'.repeat(64);
function fixture({status='restricted',trades=[],markets=[],end=12000,ask=10.05,ask_size=100}={}){
 const events=[];
 for(let at=0;at<=end+4000;at+=500)events.push({type:'market',ts_ms:at,available_ms:at,venue:'XNAS',bid:10,ask,ask_size,tick:.01,grid_id:'fixture-grid',status,trading:true,feed_ok:true,liquidity_id:'book-1',book:{[ask]:ask_size}});
 events.push(...trades.map((x,i)=>({type:'trade',ts_ms:x.at,available_ms:x.at,venue:'XNAS',trade_id:'t'+i,price:10.02,size:1000,aggressor:'B',regular:true,...x})));
 for(const x of markets){const m=events.find(e=>e.type==='market'&&e.ts_ms===x.at);Object.assign(m,x);}
 events.sort((a,b)=>a.available_ms-b.available_ms||(a.type==='market'?-1:1));
 return {schema:'third_plus_execution_session.v1',date:'2026-01-02',event_id:'e1',issuer:'cik/1',open_ms:-59000,close_ms:300000,capture_start_ms:0,capture_end_ms:end+4000,evidence:Object.fromEntries(R.REQUIRED.map(k=>[k,true])),volume_scope:'direct_unique_venues',source_hashes:[hash],events,edge_per_share:1,route_rules:{initial_display_exception:true}};
}
const options={start_ms:1000,end_ms:12000,net_edge_per_share:1,latency_ms:500,policy:'E2'};
test('missing NBBO is unavailable evidence, never a zero-profit backtest',()=>{
 const s=fixture();s.evidence.consolidated_nbbo=false;const r=R.replay(s,options);assert.equal(r.status,'data_missing');assert.ok(r.gaps.includes('consolidated_nbbo'));assert.equal(r.filled_shares,undefined);
});
test('inside-price SSR order fills only from later eligible buyer flow',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2500,size:50}]});const r=R.replay(s,options);
 assert.equal(r.filled_shares,50);assert.equal(r.fills[0].price,10.01);assert.equal(r.journal.find(e=>e.type==='submit').quantity,100);assert.equal(r.fills[0].at_ms,2500);
});
test('the decision print cannot fill its own new order',()=>{
 const r=R.replay(fixture({trades:[{at:1500,size:1000}]}),options);assert.equal(r.filled_shares,0);assert.equal(r.children,1);
});
test('offer queue consumes flow ahead without cancellation credit',()=>{
 const s=fixture({ask_size:100,trades:[{at:1500,size:1000,price:10.05},{at:2500,size:80,price:10.05},{at:3000,size:50,price:10.05}]});
 for(const e of s.events)if(e.type==='market'&&e.ts_ms>2000)e.ask_size=0;
 const r=R.replay(s,{...options,policy:'E1'});assert.equal(r.filled_shares,30);
});
test('initially displayed above-bid order retains eligibility and priority on bid touch',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:3500,size:25,price:10.02}]});
 for(const e of s.events)if(e.type==='market'&&e.ts_ms>=2500)e.bid=10.01;
 const r=R.replay(s,options);assert.equal(r.filled_shares,25);assert.equal(r.journal.filter(e=>e.type==='submit').length,1);assert.ok(!r.journal.some(e=>e.type==='cancel_requested'&&e.reason==='price_test'));
});
test('E0 matches clear-status execution and skips restricted parents',()=>{
 const s=fixture({status:'restricted',trades:[{at:1500,size:1000},{at:2500,size:100}]});
 assert.equal(R.replay(s,{...options,policy:'E0'}).status,'ssr_skip');
 const clear=fixture({status:'clear',trades:[{at:1500,size:1000,price:10.05},{at:2500,size:200,price:10.05}]});
 const a=R.replay(clear,{...options,policy:'E0'}),b=R.replay(clear,{...options,policy:'E2'});assert.deepEqual(a.fills,b.fills);
});
test('unknown native route is withheld rather than treated as supported',()=>{
 assert.equal(R.replay(fixture(),{...options,policy:'E3'}).status,'route_unverified');
});
test('unknown aggressor, auction prints and duplicate trades never inflate passive fills',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2500,size:20,aggressor:'U'},{at:3000,size:1000,regular:false},{at:3500,size:20,trade_id:'duplicate'},{at:4000,size:20,trade_id:'duplicate'}]});
 const r=R.replay(s,options);assert.equal(r.filled_shares,20);assert.equal(r.observed_external_volume,1040);
});
test('cancel-race fills remain reserved until acknowledgement and are retained',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:12100,size:25}]});
 // A fresh market packet just before the deadline preserves feed health for the race print.
 s.events.push({...s.events.find(e=>e.type==='market'),ts_ms:11900,available_ms:11900});s.events.sort((a,b)=>a.available_ms-b.available_ms);
 const r=R.replay(s,options);assert.equal(r.filled_shares,25);assert.ok(r.journal.some(e=>e.type==='fill'&&e.pending_cancel));assert.equal(r.children,1);
});
test('halting cancels without extending the fixed deadline',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:3000,size:50}]});for(const e of s.events)if(e.type==='market'&&e.ts_ms>=2500)e.trading=false;
 const r=R.replay(s,options);assert.equal(r.filled_shares,0);assert.ok(r.journal.some(e=>e.type==='cancel_requested'&&e.reason==='invalid_market'));assert.equal(r.reason,'deadline');
});
test('stale feed cancels, but an unchanged price with healthy heartbeat remains valid',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:3500,size:50}]});
 s.events=s.events.filter(e=>e.type!=='market'||e.ts_ms<=1500);
 const r=R.replay(s,options);assert.equal(r.filled_shares,0);assert.ok(r.journal.some(e=>e.type==='cancel_requested'&&e.reason==='invalid_market'));
 assert.equal(R.replay(fixture({trades:[{at:1500,size:1000},{at:3500,size:50}]}),options).filled_shares,50);
});
test('verified-borrow mode does not substitute current inventory or conditional approval',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2500,size:50}]});
 assert.equal(R.replay(s,{...options,borrow_mode:'verified'}).filled_shares,0);
 s.borrow=[{available_ms:500,expires_ms:8000,quantity:40,confirmation:'fixture-confirmation'}];
 assert.equal(R.replay(s,{...options,borrow_mode:'verified'}).filled_shares,40);
});
test('parent share budget is frozen and cumulative/rolling volume never oversubscribed',()=>{
 const s=fixture({end:30000,trades:[{at:1500,size:100000},{at:2500,size:10000},{at:8000,size:10000},{at:14000,size:10000}]});
 for(const e of s.events)if(e.type==='market'&&e.ts_ms>=5000){e.bid=5;e.ask=5.05;e.book={'5.05':100};}
 const r=R.replay(s,{...options,end_ms:30000,target_usd:1000});assert.equal(r.target_shares,99);assert.ok(r.filled_shares<=99);
});
test('a cover cannot reuse unchanged displayed depth across heartbeats',()=>{
 const s=fixture({ask_size:20,trades:[{at:1500,size:10000}]});const r=R.replay(s,{...options,side:'buy',quantity:100});
 assert.equal(r.filled_shares,20);assert.ok(r.fees>0);assert.equal(r.fills[0].price,10.05);
});
test('fees are charged once per occupied child, including partial fills',()=>{
 const r=R.replay(fixture({trades:[{at:1500,size:1000},{at:2500,size:20},{at:3000,size:30}]}),options);
 assert.equal(r.fees,R.fee(50,10.01,'2026-01-02',true));
});
test('invalid clocks and unknown source provenance fail closed',()=>{
 const s=fixture();s.events[1].available_ms=-10;assert.throws(()=>R.replay(s,options),/clock/);
 const t=fixture();t.source_hashes=[];assert.equal(R.replay(t,options).status,'data_missing');
});
test('no whole-share budget and absent edge do not force completion',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2500,size:1000}]});
 assert.equal(R.replay(s,{...options,target_usd:1}).filled_shares,0);
 assert.equal(R.replay(s,{...options,net_edge_per_share:0}).filled_shares,0);
});
test('all latency stresses are deterministic and greater latency can miss flow',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:1900,size:30}]});
 const fast=R.replay(s,{...options,latency_ms:100}),slow=R.replay(s,{...options,latency_ms:2000});
 assert.equal(fast.filled_shares,30);assert.equal(slow.filled_shares,0);assert.deepEqual(fast,R.replay(s,{...options,latency_ms:100}));
});
test('portfolio refuses selected-sample P&L when any candidate entry path is unknown',()=>{
 const r=P.replayPortfolio({candidates:[{id:'e1',day:'2026-01-02',issuer:'cik/1'}]},new Map());
 assert.equal(r.status,'not_estimable');assert.equal(r.summary,null);assert.equal(r.audit[0].status,'execution_data_missing');
});
module.exports={fixture};

test('native repricer reacts at the venue, resets queue and respects original sell floor',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2600,size:40,price:9.99}]});
 s.native_repricing={verified:true,mode:'nasdaq_slide_down',minimum_sell_price:9.99,available_ms:0};
 for(const e of s.events)if(e.type==='market'&&e.ts_ms>=2500){e.bid=9.9;e.ask=10.05;e.book={'10.05':100};}
 const r=R.replay(s,{...options,policy:'E3'});
 assert.equal(r.filled_shares,40);assert.equal(r.fills[0].price,9.99);assert.ok(r.journal.some(e=>e.type==='native_reprice'&&e.at_ms===2500));
 assert.equal(r.journal.filter(e=>e.type==='submit').length,1);
});
test('without route support, a bid touch cancels instead of inventing initially displayed eligibility',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2700,size:50}]});s.route_rules.initial_display_exception=false;
 for(const e of s.events)if(e.type==='market'&&e.ts_ms>=2500)e.bid=10.01;
 const r=R.replay(s,options);assert.equal(r.filled_shares,0);assert.ok(r.journal.some(e=>e.type==='cancel_requested'&&e.reason==='price_test'));
});
test('unknown or future forecast updates cannot enter a decision',()=>{
 const s=fixture();s.events[0].net_edge_per_share=1;s.events[0].net_edge_available_ms=1;s.events[0].net_edge_source_sha256='a'.repeat(64);
 assert.throws(()=>R.replay(s,options),/Future or unproven edge/);
});
test('orders are rejected if the dated price grid changed before acknowledgement',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2500,size:50}]});
 for(const e of s.events)if(e.type==='market'&&e.ts_ms>=2000)e.tick=.05;
 const r=R.replay(s,options);assert.equal(r.filled_shares,0);assert.ok(r.journal.some(e=>e.type==='rejected'));
});

test('known borrow expiry cancels early enough to include acknowledgement latency',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:3000,size:10},{at:3300,size:10}]});
 s.borrow=[{available_ms:500,expires_ms:3200,quantity:100,confirmation:'fixture'}];
 const r=R.replay(s,{...options,borrow_mode:'verified'});
 assert.equal(r.filled_shares,10);assert.equal(r.borrow_exceptions,0);
 assert.ok(r.journal.some(e=>e.type==='cancel_requested'&&e.reason==='borrow_expiring'&&e.at_ms===2700));
});
test('borrow revocation race retains actual short quantity and flags evidence failure',()=>{
 const s=fixture({trades:[{at:1500,size:1000},{at:2800,size:10}]});
 s.borrow=[{available_ms:500,expires_ms:8000,quantity:100,confirmation:'fixture'},{available_ms:2700,expires_ms:8000,quantity:0,confirmation:'revoked'}];
 const r=R.replay(s,{...options,borrow_mode:'verified'});assert.equal(r.filled_shares,10);assert.equal(r.borrow_exceptions,1);assert.ok(r.journal.some(e=>e.type==='fill'&&e.pending_cancel));
});
test('literal parent-dollar cap also binds when the sell offer exceeds the arrival midpoint',()=>{
 const s=fixture({ask:20,ask_size:0,trades:[{at:1500,size:1000,price:20},{at:2500,size:100,price:20}]});
 const r=R.replay(s,{...options,policy:'E1',target_usd:100});assert.equal(r.target_shares,6);assert.equal(r.filled_shares,5);assert.equal(r.notional,100);
});
