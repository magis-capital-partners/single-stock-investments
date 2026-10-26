'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),R=require('./bar_replay.cjs'),P=require('./venue_portfolio.cjs');
const Study=require('./venue_study.cjs');
function fixture({day='2026-01-05',id='a',cover=false}={}){
 const open=Date.parse(day+'T14:30:00Z'),close=Date.parse(day+'T21:00:00Z'),start=cover?close-90*60000:open+60000;
 const bars=Array.from({length:80},(_,i)=>[(start-1000+i*1000)/1000,10,10.10,9.98,10,1000]);
 return {schema:'third_plus_bar_session.v2',event_id:id,issuer:'cik/'+id,date:day,open_ms:open,close_ms:close,capture_start_ms:start-1000,capture_end_ms:cover?close-15*60000+5000:start+65000,
 source_hashes:['a'.repeat(64)],opening_restricted:1,quote_basis:'lagged_bar_spread_proxy',bars,quotes:[],statuses:[],_results:new Map()};
}
function options(s,x={}){return {start_ms:s.open_ms+60000,end_ms:s.open_ms+120000,initial_price:10,target_usd:100000,policy:'E2',...x};}
test('SSR names receive causal partial-fill attempts while matched skip remains a control',()=>{
 const s=fixture(),x=R.replay(s,options(s));assert.ok(x.children>0);assert.ok(x.filled_shares>0);assert.ok(x.fill_fraction<1);assert.equal(x.evidence,'one_second_bar_fill_sensitivity');assert.equal(R.replay(s,options(s,{policy:'E0'})).filled_shares,0);
});
test('future volume after the fixed deadline cannot fund opening orders',()=>{
 const s=fixture(),a=R.replay(s,options(s));s._results.clear();s.bars.push([(s.open_ms+300000)/1000,10,100,1,10,100000000]);const b=R.replay(s,options(s));assert.deepEqual(a.fills,b.fills);
});
test('no trading flow is an honest no-fill, never a forced trade',()=>{
 const s=fixture();s.bars=s.bars.map(b=>[...b.slice(0,5),0]);const x=R.replay(s,options(s));assert.equal(x.filled_shares,0);assert.equal(x.children,0);
});
test('missing source capture and verified-borrow requests stay unavailable',()=>{
 const s=fixture();s.capture_end_ms=s.open_ms+65000;assert.equal(R.replay(s,options(s)).status,'data_missing');
 assert.equal(R.replay(fixture(),options(fixture(),{borrow_mode:'verified'})).status,'data_missing');
});
test('a parent never exceeds its fixed shares or dollar ceiling',()=>{
 const s=fixture(),x=R.replay(s,options(s,{target_usd:1500}));assert.ok(x.notional<=1500+1e-6);assert.ok(x.filled_shares<=x.target_shares);
});

test('a rising restricted bid blocks a working short during cancellation latency',()=>{
 const s=fixture(),start=s.open_ms+60000;
 // The child was priced using the earlier quote. Later bars cross it, but the
 // current bid now makes that working price ineligible even before cancellation.
 s.quotes=[[start/1000,10,10.02],[(start+1000)/1000,12,12.02]];
 s.bars=s.bars.slice(0,3).map((b,i)=>i<2?b:[b[0],12,12.1,11.9,12,1000]);
 const x=R.replay(s,options(s));assert.ok(x.children>0);assert.equal(x.filled_shares,0);
});
test('different capture assumptions are retained without selecting the winner',()=>{
 const s=fixture(),a=R.replay(s,options(s,{capture:.25})),b=R.replay(s,options(s,{capture:.75}));assert.ok(a.filled_shares<=b.filled_shares);
});
test('an unfilled opportunity never becomes an open residual position',()=>{
 const x=Study.summarizeOpportunity({id:'a'},{status:'no_fill',entry:{children:1,filled_shares:0,notional:0}},{entry_units:0,deadline:10,last_calendar_index:20},'ssr_rejected');assert.equal(x.exit_status,'no_position');
});
test('long entry windows respect actual early closes',()=>{
 const open=Date.parse('2026-11-27T14:30:00Z'),close=Date.parse('2026-11-27T18:00:00Z');assert.equal(P.entryWindow({open_ms:open,close_ms:close},240)[1],close-15*60000);
});
test('bar accounting retains residuals and separates independent opportunities from account slots',()=>{
 const days=['2026-01-05','2026-01-06','2026-01-07'],index=new Map(days.map((d,i)=>[d,i]));
 const candidates=Array.from({length:4},(_,i)=>({id:'e'+i,issuer:'cik/e'+i,ticker:'T'+i,day:days[0],entry_price:10}));
 const sessions=new Map();for(const c of candidates){sessions.set(c.id,fixture({id:c.id}));for(const day of days.slice(1))sessions.set(c.id+'|'+day,fixture({id:c.id,day,cover:true}));}
 const ctx={candidates,first:days[0],prices:{days,index,last:days.at(-1),point:()=>({close:10})},factor:()=>1,settlement:d=>d,auction:()=>({open:10})};
 const o={engine:R,minutes:1,horizon:2,impact_bps:10};
 const account=P.replayPortfolio(ctx,sessions,o),independent=P.replayPortfolio(ctx,sessions,{...o,independent_events:true,maximum_names:1000});
 assert.equal(account.summary.entered,3);assert.equal(independent.summary.entered,4);assert.ok(account.audit.some(a=>a.status==='name_limit'));
 assert.ok(Math.abs(independent.positions.reduce((n,p)=>n+p.pnl,0)-independent.summary.net_pnl)<1e-6);
 assert.ok(Math.abs(independent.summary.common_monthly.reduce((n,m)=>n+m.pnl,0)-independent.summary.net_pnl)<1e-6);
});
module.exports={fixture,options};
