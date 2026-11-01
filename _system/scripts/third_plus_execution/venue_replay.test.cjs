'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const R=require('./venue_replay.cjs'),P=require('./venue_portfolio.cjs');
function fixture(){
 const events=[];
 for(const t of [0,1000,2000,3000,4000])events.push({type:'market',ts_ms:t,available_ms:t,venue:'XNAS',bid:10,ask:10.04,ask_size:100,ask_capacity:100,tick:.01,grid_id:'dated-test',status:'restricted',trading:true,feed_ok:true,liquidity_id:'unchanged',book:{'10.04':100}});
 events.push({type:'trade',ts_ms:1500,available_ms:1500,venue:'XNAS',trade_id:'budget',price:10.04,size:1000,aggressor:'B',regular:true});
 events.push({type:'trade',ts_ms:2500,available_ms:2500,venue:'XNAS',trade_id:'fill',price:10.04,size:30,aggressor:'B',regular:true});
 events.sort((a,b)=>a.available_ms-b.available_ms);
 return {schema:'third_plus_venue_session.v2',date:'2026-01-05',event_id:'a',issuer:'cik/1',open_ms:-59000,close_ms:300000,capture_start_ms:0,capture_end_ms:10000,continuity_mode:'complete_capture',volume_scope:'single_venue',source_hashes:['a'.repeat(64)],evidence:Object.fromEntries(R.REQUIRED.map(k=>[k,true])),events,route_rules:{initial_display_exception:true}};
}
const o={start_ms:1000,end_ms:4000,policy:'E2',latency_ms:100,edge_filter:false};
test('every SSR name can reach an attempt without inventing a positive forecast or NBBO certification',()=>{
 const s=fixture(),x=R.replay(s,o);assert.equal(x.filled_shares,30);assert.equal(s.evidence.consolidated_nbbo,undefined);assert.equal(x.fills[0].at_ms,2500);
});
test('no eligible buying flow produces an honest no-fill',()=>{
 const s=fixture();s.events=s.events.filter(e=>e.type!=='trade'||e.trade_id==='budget');assert.equal(R.replay(s,o).filled_shares,0);
});
test('partial historical capture stays missing, never a forced fill',()=>{
 const s=fixture();s.capture_end_ms=2000;assert.equal(R.replay(s,o).status,'data_missing');
});
test('fixed-window execution is optional; an explicitly requested edge filter still fails closed',()=>{
 assert.equal(R.replay(fixture(),{...o,edge_filter:true}).filled_shares,0);
});
test('complete capture can retain a quiet quote; missing capture cannot',()=>{
 const s=fixture();s.events=s.events.filter(e=>e.type==='trade'||e.ts_ms===0);assert.equal(R.replay(s,o).filled_shares,30);
});
test('inside orders obey dated increments and target/flow reservations',()=>{
 const x=R.replay(fixture(),o);assert.equal(x.fills[0].price,10.01);assert.ok(x.filled_shares<=Math.floor(x.observed_external_volume*.1));
});
test('unknown native handling cannot be silently enabled',()=>{
 assert.equal(R.replay(fixture(),{...o,policy:'E3'}).status,'route_unverified');
});
module.exports={fixture,o};
