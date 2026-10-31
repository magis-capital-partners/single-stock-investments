'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),E=require('./assumed_backtest.cjs');
function fixture(){
 const days=['2026-01-02','2026-01-05','2026-01-06','2026-01-07','2026-01-08','2026-01-09','2026-01-12','2026-01-13'];
 const ctx={prices:{days,last:days.at(-1),index:new Map(days.map((d,i)=>[d,i])),point:()=>({open:10,high:10,close:10})},factor:()=>1,auction:()=>({open:10,close:10}),settlement:d=>days[days.indexOf(d)+1]||'2026-01-14'};
 const c={id:'a',ticker:'TEST',issuer:'cik/999',day:days[0],entry_price:10,adv_shares:234000};return {ctx,c,days};
}
test('missing quotes, venue capture and lending history still produce full numeric assumed results',()=>{
 const {ctx,c}=fixture(),t=E.trade(ctx,new Map(),c,{horizon:2});
 assert.equal(t.status,'filled');assert.equal(t.entry.proxy,true);assert.equal(t.close_day,'2026-01-05');assert.ok(Number.isFinite(t.net_pnl));assert.ok(t.costs.borrow>0);assert.equal(t.open_liability,0);
 const p=E.portfolio(ctx,[t]);assert.equal(p.entered,1);assert.ok(Math.abs(p.monthly.reduce((a,x)=>a+x[1],0)-p.net_pnl)<1e-8);assert.ok(Math.abs(p.gross_before_costs-p.net_pnl-Object.values(p.costs).reduce((a,x)=>a+x,0))<1e-8);
});
test('borrow starts at sale settlement, charges weekends and ends at cover settlement',()=>{
 const {ctx,c}=fixture(),t=E.trade(ctx,new Map(),c,{horizon:6}),expected=t.entry.filled_shares*11*.5/360*7;
 assert.equal(t.close_day,'2026-01-09');assert.ok(Math.abs(t.costs.borrow-expected)<1e-8);
 const entryPnl=t.entry.notional-t.entry.filled_shares*10-t.entry.fees-t.costs.locate-t.entry.notional*.001;
 assert.ok(Math.abs(t.daily[0].change-entryPnl)<1e-8,'No borrow charge before sale settlement');
});
test('unavailable daily prices close at a declared adverse estimate rather than freezing slots',()=>{
 const {ctx,c}=fixture();ctx.prices.point=()=>null;ctx.auction=()=>({});
 const t=E.trade(ctx,new Map(),c,{horizon:2});assert.equal(t.close_day,'2026-01-05');assert.ok(t.proxy_exit);assert.ok(t.proxy_marks>=2);assert.ok(t.net_pnl<0);
 const p=E.portfolio(ctx,[t,{...t,id:'b',issuer:'cik/998',day:'2026-01-06'}],{maximum_names:1});assert.equal(p.entered,2);
});
test('final-day volume and close cannot change the morning target or entry',()=>{
 const {ctx,c}=fixture(),a=E.trade(ctx,new Map(),c,{horizon:2});ctx.prices.point=()=>({open:10,high:100,close:100,volume:1e12});ctx.auction=()=>({close:100});
 const b=E.trade(ctx,new Map(),c,{horizon:2});assert.deepEqual(a.entry,b.entry);assert.notEqual(a.net_pnl,b.net_pnl);
});
test('eventual no-fills keep all same-day parent reservations',()=>{
 const {ctx,c}=fixture(),ts=Array.from({length:4},(_,i)=>E.trade(ctx,new Map(),{...c,id:'e'+i,issuer:'cik/'+i},{policy:'E1',horizon:2})),p=E.portfolio(ctx,ts);
 assert.equal(p.attempted,3);assert.equal(p.entered,0);assert.equal(p.no_fill,3);assert.equal(p.name_limit,1);assert.equal(E.portfolio(ctx,ts,{independent:true}).attempted,4);
});
test('fills obey buy limits, dollar caps and participation, and SSR names can trade',()=>{
 const date='2026-01-02',open=E.clock(date,9,30),bars=Array.from({length:180},(_,i)=>[(open+i*1000)/1000,10,10.01,9.99,10,1000]);
 const s={open_ms:open,close_ms:open+23400000,opening_restricted:1,bars,quotes:[],statuses:[]};
 const x=E.execute(s,date,10,10000,{minutes:1});assert.ok(x.filled_shares>0);assert.ok(x.notional<=100000);assert.ok(x.filled_shares<=60000*.1);
 assert.equal(E.execute(s,date,10,10000,{minutes:1,policy:'E0'}).status,'ssr_skip');
 const buy=E.execute(null,date,10,234000,{side:'buy',quantity:100});assert.equal(buy.filled_shares,100);assert.ok(buy.fills.every(f=>f.price<=f.limit_price));
});
test('recent positions remain marked open and future events stay in the audit',()=>{
 const {ctx,c}=fixture(),t=E.trade(ctx,new Map(),{...c,day:ctx.prices.last});assert.ok(t.immature);assert.equal(t.close_day,null);assert.ok(t.open_liability>0);
 const future=E.trade(ctx,new Map(),{...c,day:null});assert.equal(future.status,'not_yet_eligible');assert.equal(E.portfolio(ctx,[future]).decisions[0].status,'not_yet_eligible');
});
test('an SSR transition after partial execution retains one filled position rather than a second skip',()=>{
 const date='2026-01-02',open=E.clock(date,9,30),s={open_ms:open,close_ms:open+23400000,opening_restricted:0,bars:Array.from({length:180},(_,i)=>[(open+i*1000)/1000,10,10,10,10,1000]),quotes:[],statuses:[{available_ms:open+90000,restricted:'Y'}]};
 const x=E.execute(s,date,10,10000,{minutes:1,policy:'E0'});assert.ok(x.filled_shares>0);assert.equal(x.status,'filled');
});
test('estimated external flow cannot trade through a captured halt',()=>{
 const date='2026-01-02',open=E.clock(date,9,30),s={open_ms:open,close_ms:open+23400000,bars:[],statuses:[{available_ms:open,trading:'N'}]};
 assert.equal(E.execute(s,date,10,234000,{minutes:1}).filled_shares,0);
});
test('split-adjusted liabilities and paid fractional overbuy reconcile',()=>{
 const {ctx,c}=fixture();ctx.factor=(t,a,b)=>b>c.day?3:1;ctx.prices.point=(t,d)=>({open:d===c.day?10:30,high:d===c.day?10:30,close:d===c.day?10:30});ctx.auction=(t,d)=>({close:d===c.day?10:30});
 const t=E.trade(ctx,new Map(),c,{horizon:2});assert.equal(t.open_liability,0);assert.ok(Number.isFinite(t.net_pnl));assert.ok(t.net_pnl<0);assert.ok(Math.abs(t.net_pnl)<t.entry.notional*.1);
});
