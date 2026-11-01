'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),R=require('./replay.cjs'),P=require('./portfolio.cjs');
const dayms=86400000,base=Date.parse('2026-01-05T14:31:00Z'),hash='a'.repeat(64);
function session({id='e1',date='2026-01-05',cover=false,price=10,depth=100,flow=1000,tradeFill=30}={}){
 const at=Date.parse(date+'T'+(cover?'19:30':'14:31')+':00Z'),end=at+(cover?75:1)*60000;
 const events=[];
 for(let ms=at;ms<=at+5000;ms+=500)events.push({type:'market',ts_ms:ms,available_ms:ms,venue:'XNAS',bid:price,ask:price+.05,ask_size:depth,tick:.01,grid_id:'fixture',status:cover?'unknown':'restricted',trading:true,feed_ok:true,liquidity_id:'one-book',book:{[price+.05]:depth}});
 events.push({type:'trade',ts_ms:at+500,available_ms:at+500,trade_id:'flow',venue:'XNAS',price:price+.02,size:flow,aggressor:'B',regular:true});
 if(!cover)events.push({type:'trade',ts_ms:at+1500,available_ms:at+1500,trade_id:'fill',venue:'XNAS',price:price+.02,size:tradeFill,aggressor:'B',regular:true});
 events.sort((a,b)=>a.available_ms-b.available_ms||(a.type==='market'?-1:1));
 return {schema:'third_plus_execution_session.v1',event_id:id,issuer:'cik/'+id,date,open_ms:Date.parse(date+'T14:30:00Z'),close_ms:Date.parse(date+'T21:00:00Z'),capture_start_ms:at-1000,capture_end_ms:end+5000,evidence:Object.fromEntries(R.REQUIRED.map(k=>[k,true])),source_hashes:[hash],volume_scope:'direct_unique_venues',edge_per_share:1,edge_available_ms:at-1000,edge_source_sha256:hash,route_rules:{initial_display_exception:true},events};
}
function fixture({n=1,horizon=2,split=1}={}){
 const days=['2026-01-05','2026-01-06','2026-01-07','2026-01-08'],index=new Map(days.map((d,i)=>[d,i]));
 const candidates=Array.from({length:n},(_,i)=>({id:'e'+(i+1),ticker:'T'+i,issuer:'cik/e'+(i+1),day:days[0]}));
 const ctx={first:days[0],candidates,prices:{days,index,last:days.at(-1),point:(ticker,d)=>({close:d===days[0]?10:8*split})},factor:(ticker,entry,d)=>d===days[0]?1:split,settlement:d=>new Date(Date.parse(d+'T12:00:00Z')+dayms).toISOString().slice(0,10)};
 const sessions=new Map(candidates.map(c=>[c.id,session({id:c.id})]));
 for(const c of candidates)for(const d of days.slice(1))sessions.set(c.id+'|'+d,session({id:c.id,date:d,cover:true,price:8*split,depth:d===days[1]?20:100}));
 return {ctx,sessions,o:{minutes:1,horizon,latency_ms:500}};
}
test('partial covers retain obligations and borrow until later loan return; cash reconciles',()=>{
 const {ctx,sessions,o}=fixture(),r=P.replayPortfolio(ctx,sessions,o);
 assert.equal(r.status,'conditional_simulation');assert.equal(r.summary.entered,1);
 assert.equal(r.positions[0].entry_units,30);assert.equal(r.positions[0].closed,'2026-01-07');assert.equal(r.positions[0].cover_replays[0].filled_shares,20);assert.equal(r.positions[0].cover_replays[1].filled_shares,10);
 assert.equal(r.summary.open_positions,0);assert.ok(r.summary.borrow_cost>0);assert.ok(r.summary.commissions_and_fees>2);
 assert.ok(Math.abs(r.summary.common_monthly.reduce((n,m)=>n+m.pnl,0)-r.summary.net_pnl)<1e-8);
 assert.ok(Math.abs(r.daily.at(-1).pnl-r.positions[0].pnl)<1e-8);
});
test('missing original exit data retains the liability and marks evidence incomplete',()=>{
 const {ctx,sessions,o}=fixture();sessions.delete('e1|2026-01-06');
 const r=P.replayPortfolio(ctx,sessions,o);assert.equal(r.status,'incomplete_exit_evidence');assert.equal(r.positions[0].closed,'2026-01-07');assert.equal(r.summary.missing_exit_sessions,1);assert.ok(r.missing_exits.some(e=>e.date==='2026-01-06'));
});
test('an immature position is admitted and marked without a fabricated future exit',()=>{
 const {ctx,sessions,o}=fixture({horizon:20}),r=P.replayPortfolio(ctx,sessions,o);
 assert.equal(r.summary.entered,1);assert.equal(r.summary.immature_positions,1);assert.equal(r.positions[0].planned_exit,null);assert.equal(r.summary.open_positions,1);assert.equal(r.summary.open_liability,240);
});
test('three issuer slots survive removal of modeled margin and sleeve admission limits',()=>{
 const {ctx,sessions,o}=fixture({n:4,horizon:20}),r=P.replayPortfolio(ctx,sessions,{...o,nav:100});
 assert.equal(r.summary.entered,3);assert.equal(r.audit.filter(e=>e.status==='name_limit').length,1);assert.equal(r.summary.margin_capacity_applied,false);assert.equal(r.summary.sleeve_cap_applied,false);
});
test('split units and fractional short liability remain unresolved rather than rounded closed',()=>{
 const {ctx,sessions,o}=fixture({split:100}),r=P.replayPortfolio(ctx,sessions,o);
 assert.equal(r.positions[0].units,30);assert.equal(r.positions[0].factor,100);assert.equal(r.summary.open_liability,240);assert.equal(r.positions[0].closed,undefined);
});
test('source identity mismatch blocks the entire selected portfolio, not only one sampled trade',()=>{
 const {ctx,sessions,o}=fixture({n:2});sessions.get('e2').issuer='different';
 const r=P.replayPortfolio(ctx,sessions,o);assert.equal(r.status,'not_estimable');assert.equal(r.summary,null);assert.equal(r.audit.find(x=>x.id==='e1').status,'portfolio_path_unknown');assert.ok(r.coverage.find(x=>x.id==='e2').reasons.includes('identity_join'));
});
test('paid no-fill locate expense remains in net performance and idle months are retained',()=>{
 const {ctx,sessions,o}=fixture();const s=sessions.get('e1');s.events=s.events.filter(e=>e.type!=='trade');s.locate_cost_usd=12;
 const r=P.replayPortfolio(ctx,sessions,o);assert.equal(r.summary.entered,0);assert.equal(r.summary.net_pnl,-12);assert.equal(r.summary.locate_cost,12);assert.equal(r.summary.common_monthly[0].pnl,-12);
});
test('higher financing assumptions change carry once without a duplicate flat execution debit',()=>{
 const {ctx,sessions,o}=fixture(),a=P.replayPortfolio(ctx,sessions,{...o,borrow_apr:.5}),b=P.replayPortfolio(ctx,sessions,{...o,borrow_apr:1.5});
 assert.ok(Math.abs(b.summary.borrow_cost-3*a.summary.borrow_cost)<1e-8);assert.ok(Math.abs(a.summary.net_pnl-b.summary.net_pnl-(b.summary.borrow_cost-a.summary.borrow_cost))<1e-8);
});
test('buyback does not require an SSR status or a positive short-entry edge forecast',()=>{
 const s=session({cover:true,price:8,depth:100});s.events.forEach(e=>{if(e.type==='market')e.net_edge_per_share=-10;e.net_edge_available_ms=e.available_ms;e.net_edge_source_sha256=hash;});
 const start=Date.parse('2026-01-05T19:30:00Z'),x=R.replay(s,{side:'buy',quantity:30,start_ms:start,end_ms:start+75*60000,net_edge_per_share:-5});
 assert.equal(x.filled_shares,30);
});
