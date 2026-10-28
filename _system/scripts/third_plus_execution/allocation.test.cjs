'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),A=require('./allocation.cjs');
const policy=id=>A.registry().find(p=>p.id===id),event=(id,signals={},i=30)=>({id,issuer:'cik/'+id,ticker:id,day:'2025-01-02',i,signals:{S7:'pass',burn:'pass',...signals},shock:2,risk_observations:20});
function fixture(){const days=['2025-01-02','2025-01-03','2025-01-06'],ctx={prices:{days,last:days.at(-1),point:()=>({open:10,close:10})},auction:()=>({open:10,close:10}),factor:()=>1};const get=(e,s,b)=>({id:e.id,ticker:e.ticker,issuer:e.issuer,day:e.day,budget:b,status:'filled',shock:2,entry:{filled_shares:b/10,notional:b,proxy:false,estimatedQuotes:0},costs:{fees:1,borrow:0,locate:0,impact:0},ready_day:'2025-01-06',close_day:'2025-01-03',daily:[{day:'2025-01-02',pnl:-1,change:-1,liability:b,margin:2*b,peak_liability:b,mark:10,factor:1,open:true},{day:'2025-01-03',pnl:100,change:101,liability:0,margin:0,peak_liability:b,mark:10,factor:1,open:false}]});return {ctx,get,days};}
test('related distress signals provide one grouped point and unknowns do not earn a bonus',()=>{
 const e=event('a',{burn:'pass',reported_runway:'pass',operating_loss:'pass',S3:'unknown',S4:'unknown',S5:'unknown',S6:'unknown'});
 assert.equal(A.scores(e).groups,1);assert.equal(A.scores(e).naive,3);assert.equal(A.desired([e],e,policy('group_size')).target,25000);assert.equal(A.desired([e],e,policy('naive_count')).target,100000);assert.equal(A.desired([e],e,policy('size_core')).target,25000);
});
test('shrinkage counts only distinct completed prior issuers, without future membership leakage',()=>{
 const e=event('now',{S3:'pass',S5:'pass'},100),p=policy('shrunk_core'),past=Array.from({length:10},(_,i)=>event('old'+i,{S3:'pass',S5:'pass'},10));
 assert.equal(A.desired(past,e,p).target,62500);assert.equal(A.desired([...past,...past,event('future',{S3:'pass',S5:'pass'},110),event('recent',{S3:'pass',S5:'pass'},90)],e,p).target,62500);
 assert.equal(A.desired([],e,p).target,25000);
});
test('ranking changes the scarce third slot using pre-entry signals only',()=>{
 const {ctx,get}=fixture(),events=[event('a'),event('b'),event('c'),event('d',{S3:'pass',S5:'pass'})];
 const base=A.simulate(ctx,events,policy('burn_100'),get,{budget:'original'}),rank=A.simulate(ctx,events,policy('rank_core'),get,{budget:'original'});
 assert.equal(base.audit.find(a=>a.id==='d').status,'name_limit');assert.equal(rank.audit.find(a=>a.id==='d').status,'filled');assert.equal(rank.audit.find(a=>a.id==='c').status,'name_limit');
});
test('later fill amounts and no-fills cannot free same-arrival slot or dollar reservations',()=>{
 const {ctx,get}=fixture(),events=[event('a'),event('b'),event('c'),event('d')],targets=[];
 const tiny=(e,s,b)=>{targets.push(b);const t=get(e,s,b);return e.id==='a'?{...t,status:'no_fill',entry:{filled_shares:0,notional:0},daily:[]}:t;};
 const r=A.simulate(ctx,events,policy('burn_100'),tiny,{budget:'matched'});assert.deepEqual(targets,[100000,100000,100000]);assert.equal(r.audit.find(a=>a.id==='d').status,'name_limit');
});
test('weighted daily allocations conserve the same intended pool and obey per-name caps',()=>{
 const x=A.waterfill([1,2,4],150000);assert.ok(Math.abs(x.reduce((a,b)=>a+b,0)-150000)<1e-8);assert.ok(x.every(v=>v<=100000));assert.deepEqual(A.waterfill([1],50000),[50000]);
 const {ctx,get}=fixture(),events=[event('a'),event('b',{S3:'pass'}),event('c',{S3:'pass',S5:'pass'})];
 for(const id of ['daily_uniform','daily_rank','daily_size','daily_both']){const r=A.simulate(ctx,events,policy(id),get,{budget:'original'});const total=r.audit.reduce((n,a)=>n+(a.target_usd||0),0);assert.ok(total<=150000&&total>=149700);}
});
test('morning admission uses known open and yesterday inventory, not today close',()=>{
 const {ctx,get}=fixture(),e=event('a'),t=get(e,'base',100000);const a=A.morning(ctx,t,'2025-01-03');ctx.auction=()=>({open:10,close:1000});ctx.prices.point=()=>({open:10,close:1000});assert.deepEqual(A.morning(ctx,t,'2025-01-03'),a);assert.equal(a.liability,100000);
});
test('squeeze risk ignores entry-day highs and removes reverse-split discontinuities',()=>{
 const days=['2025-01-02','2025-01-03','2025-01-06'],c={...event('a'),day:days[2]},ctx={prices:{days,index:new Map(days.map((d,i)=>[d,i])),point:(t,d)=>d===days[0]?{close:1,high:1}:{close:10,high:10}},factor:(t,a,b)=>b===days[1]?10:1};
 assert.equal(A.risk(ctx,c).shock,2);const point=ctx.prices.point;ctx.prices.point=(t,d)=>d===c.day?{close:1e6,high:1e6}:point(t,d);assert.equal(A.risk(ctx,c).shock,2);
});
test('risk overlay and sleeve loss budget cap requested dollars before execution',()=>{
 const {ctx,get}=fixture(),events=[{...event('a'),shock:8},{...event('b'),shock:2}];
 const r=A.simulate(ctx,events,policy('burn_risk'),get);assert.equal(r.audit.find(a=>a.id==='a').target_usd,25000);assert.equal(r.audit.find(a=>a.id==='b').target_usd,100000);
});
test('training excludes unfinished loan returns and insufficient issuer samples fall back',()=>{
 const run={positions:[{ready_day:'2024-12-31',id:'past'},{ready_day:'2025-01-02',id:'future'},{ready_day:null,id:'open'}],audit:[]};assert.deepEqual(A.completed(run,'2025-01-01').positions.map(x=>x.id),['past']);
 const p=policy('rank_core'),pair=n=>({base:{issuers:n,net_pnl:10000,max_drawdown_dollars:-1000},stress:{issuers:n,net_pnl:5000,max_drawdown_dollars:-2000}});
 assert.equal(A.choose({[p.id]:pair(19)},[p]).fallback,true);assert.equal(A.choose({[p.id]:pair(20)},[p]).selected,p.id);
});
test('issuer omissions rerun admissions and aggregate cash and monthly P&L reconcile',()=>{
 const {ctx,get}=fixture(),events=['a','b','c','d'].map(x=>event(x)),r=A.simulate(ctx,events,policy('burn_100'),get,{budget:'original',omit:new Set(['cik/a'])});
 assert.equal(r.audit.find(a=>a.id==='d').status,'filled');const x=A.aggregate(ctx,r).summary;assert.equal(x.entered,3);assert.equal(x.net_pnl,300);assert.equal(x.monthly.reduce((a,x)=>a+x[1],0),x.net_pnl);
});
