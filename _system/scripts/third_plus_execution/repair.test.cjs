'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const R=require('./bar_replay.cjs'),P=require('./venue_portfolio.cjs');
const I=require('./identity.cjs'),B=require('./benchmark.cjs');
function bars(){return {schema:'third_plus_bar_session.v2',event_id:'a',issuer:'cik/1',date:'2025-06-02',open_ms:0,close_ms:1000000,capture_start_ms:0,capture_end_ms:10000,source_hashes:['a'.repeat(64)],bars:[[0,10,10,10,10,1000],[1,10,10,10,10,1000],[2,12,12,12,12,1000]],quotes:[[0,10,10.02],[1,10,10.02],[2,12,12.02]],statuses:[],opening_restricted:0,quote_basis:'sampled_venue_quotes'};}
test('a buy limit cannot execute above its limit on a later rising bar',()=>{
 const s=bars(),x=R.replay(s,{side:'buy',policy:'E1',quantity:100,initial_price:10,start_ms:0,end_ms:4000});
 assert.ok(x.fills.every(f=>f.price<=10.02+1e-8),'The resting buy limit was 10.02');
});
test('missing quotes are unavailable evidence, never a made-up spread or a no-fill',()=>{
 const s=bars();s.quotes=[];s.quote_basis='lagged_bar_spread_proxy';
 const x=R.replay(s,{quantity:100,initial_price:10,start_ms:0,end_ms:4000});
 assert.equal(x.status,'data_missing');assert.ok(x.gaps.includes('quote_history'));
});
test('OHLC range crossing does not invent a uniform price-volume distribution',()=>{
 assert.equal(R.eligibleFraction([0,10,12,9,10,1000],11),0);
});
test('source-complete performance requires historical borrow and national prices',()=>{
 const s=bars(),days=[s.date],ctx={candidates:[{id:'a',issuer:'cik/1',ticker:'T',day:s.date}],prices:{days,index:new Map([[s.date,0]]),last:s.date,point:()=>({close:10})},factor:()=>1,settlement:d=>d};
 const x=P.replayPortfolio(ctx,new Map([['a',s]]),{engine:R,minutes:.05,evidence_mode:'verified'});
 assert.equal(x.summary,null);assert.ok(x.coverage[0].reasons.includes('borrow_history'));assert.ok(x.coverage[0].reasons.includes('national_prices'));
});
test('TNFA keeps its security through the sourced QCLS rename and price benchmark',()=>{
 const c={ticker:'TNFA',issuer:'cik/1321834',day:'2025-09-03'},days=['2025-09-03','2025-09-30'];
 assert.equal(I.resolve(c,'2025-09-24').ticker,'TNFA');assert.equal(I.resolve(c,'2025-09-25').ticker,'QCLS');
 assert.equal(I.resolve({...c,issuer:'cik/999'},'2025-09-25').ticker,'TNFA');
 const ctx={prices:{days,index:new Map([[days[0],0]])},factor:()=>1,auction:(t,d)=>({open:4,close:t==='QCLS'?3:undefined})};
 assert.equal(B.event(ctx,c,2).return_on_initial_gross,.25);
});
test('DBGI OTC period is not an empty Nasdaq session and later relisting is explicit',()=>{
 const c={ticker:'DBGI',issuer:'cik/1668010',day:'2024-12-16'};
 assert.equal(I.resolve(c,'2024-12-18').venue,'OTC');assert.equal(I.resolve(c,'2025-08-20').venue,'NASDAQ');
 assert.equal(I.resolve({...c,day:'2025-01-02'},'2025-01-03').venue,'OTC');
});
test('a missing live-position mark withholds the full return and later admissions',()=>{
 const days=['2026-01-05','2026-01-06','2026-01-07'],open=Date.parse(days[0]+'T14:30:00Z'),c={id:'a',ticker:'T',issuer:'cik/1',day:days[0]};
 const s={...bars(),date:days[0],event_id:'a',issuer:c.issuer,open_ms:open,close_ms:open+23400000,capture_start_ms:open,capture_end_ms:open+180000};
 const engine={gaps:()=>[],replay:()=>({status:'filled',filled_shares:10,notional:100,mean_fill:10,fees:1,children:1,fill_fraction:1,fills:[{at_ms:open+61000,quantity:10,price:10}]})};
 const ctx={candidates:[c,{...c,id:'b',ticker:'B',issuer:'cik/2',day:days[2]}],prices:{days,index:new Map(days.map((d,i)=>[d,i])),last:days[2],point:(t,d)=>d===days[1]?null:{close:10}},factor:()=>1,settlement:d=>d};
 const x=P.replayPortfolio(ctx,new Map([['a',s],['b',{...s,event_id:'b',issuer:'cik/2',date:days[2]}]]),{engine,minutes:1});
 assert.equal(x.summary,null);assert.deepEqual(x.daily,[]);assert.equal(x.positions.length,1);assert.equal(x.audit.find(x=>x.id==='b').status,'portfolio_path_unknown');
 assert.equal(x.missing_exits[0].reason,'price_history');
});
test('no-fill discovered at deadline does not retroactively free a morning parent slot',()=>{
 const day='2026-01-05',open=Date.parse(day+'T14:30:00Z'),candidates=Array.from({length:4},(_,i)=>({id:'e'+i,ticker:'T'+i,issuer:'cik/'+i,day}));
 const sessions=new Map(candidates.map(c=>[c.id,{...bars(),date:day,event_id:c.id,issuer:c.issuer,open_ms:open,close_ms:open+23400000}]));
 const engine={gaps:()=>[],replay:()=>({status:'no_fill',filled_shares:0,notional:0,fees:0,children:1,fills:[]})};
 const ctx={candidates,prices:{days:[day],index:new Map([[day,0]]),last:day,point:()=>({close:10})},factor:()=>1,settlement:d=>d};
 const x=P.replayPortfolio(ctx,sessions,{engine,minutes:1});
 assert.equal(x.positions.length,3);assert.equal(x.audit.filter(x=>x.status==='name_limit').length,1);
});
test('future entry proceeds cannot alter other parents morning risk budgets',()=>{
 const day='2026-01-05',open=Date.parse(day+'T14:30:00Z'),candidates=Array.from({length:2},(_,i)=>({id:'e'+i,ticker:'T'+i,issuer:'cik/'+i,day,entry_price:10}));
 const sessions=new Map(candidates.map(c=>[c.id,{...bars(),date:day,event_id:c.id,issuer:c.issuer,open_ms:open,close_ms:open+23400000}]));
 const budgets=[],engine={gaps:()=>[],replay:(s,o)=>{budgets.push(o.target_usd);return {status:'filled',filled_shares:1,notional:1,mean_fill:1,fees:0,children:1,fills:[]};}};
 const ctx={candidates,prices:{days:[day],index:new Map([[day,0]]),last:day,point:()=>({close:10})},factor:()=>1,settlement:d=>d};
 P.replayPortfolio(ctx,sessions,{engine,minutes:1,nav:100000,risk_limits:{per_name_fraction:.01,gross_fraction:1,squeeze_loss_fraction:2,margin_fraction:1}});
 assert.deepEqual(budgets,[1000,1000]);
});
test('a whole-share fractional cover retains the paid surplus as a real marked asset',()=>{
 const days=['2026-01-05','2026-01-06','2026-01-07'],c={id:'a',ticker:'T',issuer:'cik/1',day:days[0],entry_price:10};
 const sessions=new Map(days.map((d,i)=>[i?'a|'+d:'a',{...bars(),date:d,event_id:'a',issuer:c.issuer,open_ms:Date.parse(d+'T14:30:00Z'),close_ms:Date.parse(d+'T21:00:00Z')}]));
 const engine={gaps:()=>[],replay:(s,o)=>{const q=o.side==='buy'?o.quantity:3,price=o.side==='buy'?20:10;return {status:'filled',filled_shares:q,notional:q*price,mean_fill:price,fees:0,children:1,fill_fraction:1,fills:[{at_ms:Date.parse(s.date+'T15:00:00Z'),quantity:q,price}]};}};
 const ctx={candidates:[c],prices:{days,index:new Map(days.map((d,i)=>[d,i])),last:days[2],point:(t,d)=>({close:d===days[0]?10:20})},factor:(t,start,d)=>d===days[0]?1:2,settlement:d=>days[days.indexOf(d)+1]||'2026-01-08'};
 const x=P.replayPortfolio(ctx,sessions,{engine,minutes:1,horizon:2,borrow_apr:0});
 assert.equal(x.positions[0].units,0);assert.equal(x.summary.surplus_long_asset,10);assert.equal(x.summary.net_pnl,0);
});
module.exports={bars};
