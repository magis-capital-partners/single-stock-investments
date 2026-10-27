'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),S=require('./announcement_study.cjs');
const E=require('./assumed_backtest.cjs');
function fixture(){
 const days=['2023-01-03','2023-01-04','2023-01-05','2023-01-06','2023-01-09','2023-01-10','2023-01-11','2023-01-12','2023-01-13','2023-01-17','2023-01-18','2023-01-19','2023-01-20','2023-01-23','2023-01-24','2023-01-25','2023-01-26','2023-01-27','2023-01-30','2023-01-31','2023-02-01','2023-02-02','2023-02-03','2023-02-06','2023-02-07'];
 const data=new Map(days.map(day=>[day,{open:10,high:12,low:8,close:10,volume:100000}]));
 return {days,data,ctx:{prices:{days,index:new Map(days.map((d,i)=>[d,i])),first:days[0],last:days.at(-1),point:(_t,d)=>data.get(d)||null,prior:()=>({adv:100000,complete:true})},auction:(_t,d)=>({open:data.get(d)?.open,close:data.get(d)?.close}),factor:()=>1,settlement:d=>days[(days.indexOf(d)+2)]||'2023-02-08'}};
}
test('announcement arrival respects publication, regular sessions and processing delay',()=>{
 const {ctx}=fixture();
 assert.equal(S.arrival(ctx,'2023-01-03T12:00:00Z').at,E.clock('2023-01-03',9,31));
 assert.equal(S.arrival(ctx,'2023-01-03T16:00:00Z').at,Date.parse('2023-01-03T16:00:00Z'));
 assert.equal(S.arrival(ctx,'2023-01-03T16:00:00Z','asap',300).at,Date.parse('2023-01-03T16:05:00Z'));
 assert.equal(S.arrival(ctx,'2023-01-03T21:05:00Z').day,'2023-01-04');
 assert.equal(S.arrival(ctx,'2023-01-03T16:00:00Z','next_open').day,'2023-01-04');
});
test('early close excludes entries after the permitted shortened-session window',()=>{
 const {ctx}=fixture();ctx.sessionBounds=new Map([['2023-01-03',{open:E.clock('2023-01-03',9,30),close:E.clock('2023-01-03',13,0)}]]);
 assert.equal(S.arrival(ctx,'2023-01-03T17:46:00Z').day,'2023-01-04');
});
test('an intraday price proxy uses an already-known open, never the later close/high/low',()=>{
 const {ctx,data}=fixture(),clock=S.arrival(ctx,'2023-01-03T16:00:00Z'),e={ticker:'X'};
 data.get(clock.day).close=100000;data.get(clock.day).high=200000;
 const p=S.price(ctx,e,clock,null);assert.equal(p.price,10);assert.equal(p.basis,'known_open_intraday_proxy');assert.equal(p.intraday_proxy,true);
});
test('captured prearrival prices must be complete or timestamped before arrival',()=>{
 const {ctx}=fixture(),clock=S.arrival(ctx,'2023-01-03T16:00:00Z'),e={ticker:'X'},at=clock.at/1000;
 const session={bars:[[at-1,8,8,8,8,1],[at,999,999,999,999,1]],quotes:[[at+1,100,101]]};
 assert.equal(S.price(ctx,e,clock,session).price,8);
});
test('rally and weak-close screens cannot see the unfinished announcement-day close',()=>{
 const {ctx,days,data}=fixture(),e={ticker:'X',event_date:'2023-01-19'};
 data.get('2023-01-11').close=1000;
 const s=S.signal(ctx,e,E.clock('2023-01-11',11,0),null);
 assert.equal(s.S7,'pass');assert.equal(s.S5,'unknown');assert.equal(s.last_completed_price_day,'2023-01-10');
 assert.equal(s.S5,'unknown');
});
test('an unverified UTC-day candle cannot supply a close or range before the UTC day ends',()=>{
 const F=require('./announcement_features.cjs'),{ctx}=fixture();ctx.auction=()=>({});
 assert.equal(F.closeObservation(ctx,'X','2023-01-03',Date.parse('2023-01-03T22:00:00Z')),null);
 assert.equal(F.closeObservation(ctx,'X','2023-01-03',Date.parse('2023-01-04T00:01:00Z')).price,10);
});
test('the legal effective-day close is not the future split-trading-day close',()=>{
 const {ctx}=fixture(),e={id:'x',issuer:'cik/1',cik:'1',ticker:'X',event_date:'2023-01-03',announced_trading_day:'2023-01-04'};
 assert.equal(S.signal(ctx,e,E.clock('2023-01-03',18,0),null).S5,'unknown');
});
test('cash burn excludes a later filing and does not reuse an effective-day feature',()=>{
 const {ctx}=fixture(),e={ticker:'X',event_date:'2023-01-19'};
 const raw={facts:{'us-gaap':{CashAndCashEquivalentsAtCarryingValue:{units:{USD:[{end:'2022-12-31',filed:'2023-01-10',accn:'1',val:100}]}},NetCashProvidedByUsedInOperatingActivities:{units:{USD:[{start:'2022-01-01',end:'2022-12-31',filed:'2023-01-10',accn:'1',val:-10}]}}}}};
 assert.equal(S.signal(ctx,e,E.clock('2023-01-09',11,0),raw).burn,'unknown');
 assert.equal(S.signal(ctx,e,E.clock('2023-01-11',11,0),raw).burn,'pass');
});
test('third-split eligibility counts only completed prior actions known at the announcement',()=>{
 const past=[{issuer:'cik/1',day:'2021-01-01',known:'2021-01-01T12:00:00Z'},{issuer:'cik/1',day:'2023-01-10',known:'2023-01-09T12:00:00Z'},{issuer:'cik/1',day:'2022-01-01',known:'2023-01-20T12:00:00Z'}];
 assert.equal(S.ordinal(past,'cik/1','2023-01-09T15:00:00Z'),2);
 assert.equal(S.ordinal(past,'cik/1','2023-01-11T15:00:00Z'),3);
});
test('a late disclosure cannot count the current split as its own predecessor',()=>{
 const past=[{issuer:'cik/1',day:'2023-01-04',known:'2023-01-03T12:00:00Z'}];
 assert.equal(S.ordinal(past,'cik/1','2023-01-05T15:00:00Z','2023-01-04'),1);
 assert.deepEqual(S.protocol().sizes,['usd100k']);assert.equal(S.protocol().live_initial_shares,1);
 assert.deepEqual(S.protocol().ordinal_groups,['all','first','second','third_plus']);
});

test('a reviewed legal restructuring and later trading transition count as one prior split',()=>{
 const ctx={events:[{family:'split',issuer:'cik/1',event_date:'2026-02-23',known_at:'2026-02-20T12:00Z'}],catalogue:[],announcementActionLedger:[{issuer:'cik/1',declared_date:'2026-02-23',ex_date:'2026-03-13'}],announcementActionHistory:[{issuer:'cik/1',day:'2026-03-13',known:'2026-03-10T12:00Z'}]};
 const history=S.history(ctx);assert.equal(history.length,1);assert.equal(S.ordinal(history,'cik/1','2026-03-20T12:00Z'),2);
 ctx.announcementActionLedger=[{issuer:'cik/1',declared_date:'2026-03-13',ex_date:'2026-03-13',superseded_dates:['2026-02-23']}];assert.equal(S.history(ctx).length,1);
});
test('all fundamental screens are recomputed before versus after a new filing becomes public',()=>{
 const {ctx}=fixture(),e={id:'x',issuer:'cik/1',cik:'1',ticker:'X',event_date:'2023-01-19'};
 const raw={facts:{'us-gaap':{CashAndCashEquivalentsAtCarryingValue:{units:{USD:[{end:'2022-12-31',filed:'2023-01-10',accn:'1',val:100}]}},NetCashProvidedByUsedInOperatingActivities:{units:{USD:[{start:'2022-01-01',end:'2022-12-31',filed:'2023-01-10',accn:'1',val:-10}]}},OperatingIncomeLoss:{units:{USD:[{start:'2022-01-01',end:'2022-12-31',filed:'2023-01-10',accn:'1',val:-20}]}}}}};
 assert.equal(S.signal(ctx,e,E.clock('2023-01-09',11,0),raw).operating_loss,'unknown');
 assert.equal(S.signal(ctx,e,E.clock('2023-01-11',11,0),raw).operating_loss,'pass');
 assert.equal(S.signal(ctx,e,E.clock('2023-01-11',11,0),raw).S5,'unknown');
 const keys=new Set(S.protocol().arms.flatMap(a=>a.requires));for(const k of ['score60','S1','S2','S3','S4','S5','S6','S7','reported_runway','burn','operating_loss','revenue15','margin8','accrual10','profit_no_cash','negative_equity','debt_distress','weak_prior_close'])assert.ok(keys.has(k),k);
});
test('legal changes and conditional proposals are not split announcements',()=>{
 const a=clause=>({dated_actions:[{date:'2023-08-01',clause}]});
 assert.equal(S.definiteClause(a('The DGCL amendments would change the vote required for a reverse split of stock. The amendments are anticipated to become effective on August 1, 2023.'),'2023-08-01'),false);
 assert.equal(S.definiteClause(a('If approved, the proposed reverse stock split would become effective on August 1, 2023.'),'2023-08-01'),false);
 assert.equal(S.definiteClause(a('The reverse stock split will become effective on August 1, 2023.'),'2023-08-01'),true);
 assert.equal(S.definiteClause(a('The reverse stock split will become effective on August 1, 2023.'),'2023-08-02'),false);
});
test('a partial capture is a missing window, not an observed no-fill',()=>{
 const e={issuer:'cik/1',ticker:'X'},index=new Map([['cik/1|X|2023-01-03',[{capture_start_ms:20,capture_end_ms:100,data_gaps:[]}]]]);
 assert.equal(S.sessionAt(index,e,'2023-01-03',10,90),null);
 assert.ok(S.sessionAt(index,e,'2023-01-03',20,90));
});
function fake(id,issuer,at,filled=true){return {id,issuer,day:'2023-01-03',status:filled?'filled':'no_fill',arrival_ms:at,entry_end_ms:at+60,entry:{filled_shares:+filled,target_shares:1,notional:+filled*10},close_day:null,daily:[],net_pnl:0,costs:{borrow:0,fees:0,locate:0,impact:0}};}
test('scarce slots follow actual arrival times rather than identifier order',()=>{
 const {ctx}=fixture(),t=[fake('a','a',40),fake('z','z',10),fake('y','y',20),fake('b','b',30)],r=S.admit(ctx,t);
 assert.equal(r.audit.find(x=>x.id==='a').status,'name_limit');assert.equal(r.accepted.length,3);
});
test('future no-fills reserve slots until their window actually ends',()=>{
 const {ctx}=fixture(),t=[fake('a','a',10,false),fake('b','b',20,false),fake('c','c',30,false),fake('early','d',40,false),fake('later','e',100,false)],r=S.admit(ctx,t);
 assert.equal(r.audit.find(x=>x.id==='early').status,'name_limit');assert.equal(r.audit.find(x=>x.id==='later').status,'no_fill');
});
test('a one-share entry remains one initial share and subsequent splits preserve owed units',()=>{
 const {ctx,days,data}=fixture();ctx.factor=(_t,a,b)=>a<'2023-01-04'&&b>='2023-01-04'?10:1;
 for(const day of days)if(day>='2023-01-04')data.set(day,{open:100,high:110,low:90,close:100,volume:100000});
 const e={id:'x',issuer:'cik/1',cik:'1',ticker:'X',event_date:'2023-01-04',known_at:'2023-01-03T12:00:00Z',ordinal:3,clock_basis:'fixture'};
 const t=S.executeTrade(ctx,new Map(),e,'announce_now','one_share','base',null);
 assert.equal(t.entry.filled_shares,1);assert.equal(t.entry.target_shares,1);assert.ok(Number.isFinite(t.net_pnl));
 assert.ok(t.close_day);assert.equal(t.open_liability,0);assert.ok(Math.abs(t.returns.reduce((s,r)=>s+r.units,0)-1)<1e-8);
 assert.equal(t.costs.locate,5);assert.ok(t.costs.borrow>0);assert.ok(t.costs.fees>0);
});
test('the announced-date holding rule has its own later deadline, not the entry-day deadline',()=>{
 const {ctx}=fixture(),e={id:'x',issuer:'cik/1',cik:'1',ticker:'X',event_date:'2023-01-06',known_at:'2023-01-03T12:00:00Z',ordinal:3,clock_basis:'fixture'};
 const a=S.executeTrade(ctx,new Map(),e,'announce_now','one_share','base',null,'entry20');
 const b=S.executeTrade(ctx,new Map(),e,'announce_now','one_share','base',null,'scheduled_split20');
 assert.equal(a.planned_exit,'2023-01-31');assert.equal(b.planned_exit,'2023-02-06');
 assert.equal(b.holding,'scheduled_split20');assert.notEqual(a.close_day,b.close_day);
});

test('an uncaptured afternoon cover cannot use the later official close',()=>{const C=require('./announcement_accounting.cjs'),x={auction:()=>({open:10,close:100}),prices:{days:['2024-01-02'],point:()=>({close:100})},factor:()=>1};assert.deepEqual(C.coverPrice(x,{ticker:'X',issuer:'cik/1',day:'2024-01-02'},'2024-01-02',null,100),{price:10,basis:'known_official_open_proxy'});});

test('whole-share overbuy cleanup cannot mint a gain from the later daily mark',()=>{const C=require('./announcement_accounting.cjs'),days=['2024-01-02','2024-01-03','2024-01-04'],ctx={prices:{days,index:new Map(days.map((d,i)=>[d,i])),last:days.at(-1),point:(_t,d)=>({open:d===days[0]?1:10,close:d===days[0]?1:1000,high:d===days[0]?1:1000})},auction:(_t,d)=>({open:d===days[0]?1:10,close:d===days[0]?1:1000}),factor:(_t,a,b)=>a<'2024-01-03'&&b>='2024-01-03'?10:1,settlement:d=>new Date(Date.parse(d+'T12:00Z')+86400000).toISOString().slice(0,10)};const t=C.trade(ctx,{get:()=>null},{id:'cleanup',issuer:'cik/1',ticker:'TEST',day:days[0],entry_price:1,adv_shares:100000000},{quantity:1,horizon:2,borrow_apr:0,locate_min:0,locate_per_share:0,capture:1});assert.equal(t.entry.filled_shares,1);assert.equal(t.close_day,days[1]);assert.ok(t.net_pnl<=t.entry.notional);assert.ok(t.proxy_exit);});

test('an incomplete window retains observed prices and trading-halt evidence but stays a proxy',()=>{const index=S.indexSessions({sessions:new Map([['p',{issuer:'cik/1',source_ticker:'TEST',date:'2024-01-02',open_ms:1,close_ms:10000,capture_start_ms:1,capture_end_ms:5000,bars:[[1,10,10,10,10,100]],quotes:[],statuses:[{available_ms:1000,trading:'N'}],data_gaps:[]}]])}),e={issuer:'cik/1',ticker:'TEST'};assert.equal(S.sessionAt(index,e,'2024-01-02',1,9000),null);const partial=S.sessionAt(index,e,'2024-01-02',1,9000,true);assert.equal(partial.statuses[0].trading,'N');assert.equal(partial.bars.length,1);assert.ok(partial.data_gaps.length);});
test('known halted cover evidence blocks synthetic residual liquidation',()=>{const C=require('./announcement_accounting.cjs'),date='2024-01-02',close=Date.parse(date+'T21:00Z');assert.equal(C.knownHalt({close_ms:close,statuses:[{available_ms:close-7200000,trading:'N'}]},date),true);assert.equal(C.knownHalt({close_ms:close,statuses:[{available_ms:close-7200000,trading:'N'},{available_ms:close-3600000,trading:'Y'}]},date),false);});

test('repeat history uses inclusive calendar days rather than the release hour',()=>{const F=require('./announcement_features.cjs'),ctx={prices:{days:[],point:()=>null},actions:new Map(),auction:()=>({})},e={id:'repeat',issuer:'cik/1',cik:'1',ticker:'TEST',event_date:'2024-07-01'},past=[{issuer:'cik/1',day:'2024-01-01',known:'2023-12-20T12:00Z'}];assert.equal(F.snapshot(ctx,e,Date.parse('2024-06-29T23:00Z'),null,past).S3,'pass');assert.equal(F.snapshot(ctx,e,Date.parse('2024-06-30T23:00Z'),null,past).S3,'fail');});

test('a later-price estimate is labeled, expressed in entry units, and never becomes a selection signal',()=>{
 const {ctx,days,data}=fixture(),clock=S.arrival(ctx,'2023-01-03T12:00Z');ctx.auction=()=>({});ctx.prices.point=(_t,d)=>d===days[1]?{close:100}:null;ctx.factor=(_t,a,b)=>a<b?10:1;
 const p=S.price(ctx,{ticker:'X'},clock,null);assert.equal(p.price,10);assert.equal(p.imputed,true);assert.equal(p.imputation_source_day,days[1]);
 const signals=S.signal(ctx,{ticker:'X',event_date:days[1]},clock.at,null);assert.equal(signals.S7,'unknown');assert.equal(signals.weak_prior_close,'unknown');
});
test('capital repayment offsets a mechanical consolidation gain and the event allowance is charged once',()=>{
 const C=require('./announcement_accounting.cjs'),{ctx,days,data}=fixture();ctx.factor=(_t,a,b)=>a<days[1]&&b>=days[1]?1.1:1;
 const c={id:'cash-return',issuer:'cik/1',ticker:'X',day:days[0],entry_price:10,adv_shares:100000000},o={quantity:110,horizon:2,borrow_apr:0,locate_min:0,locate_per_share:0,capture:1,event_allowance:.01};
 const without=C.trade(ctx,{get:()=>null},c,o),withCash=C.trade(ctx,{get:()=>null},c,{...o,cash_return_days:[days[1]]});
 assert.ok(withCash.costs.capital_repayment>0);assert.ok(Math.abs(without.net_pnl-withCash.net_pnl-withCash.costs.capital_repayment)<1e-7);assert.equal(withCash.costs.event_allowance,withCash.entry.notional*.01);
 withCash.arrival_ms=1;withCash.price_imputed=true;const r=S.admit(ctx,[withCash],'unlimited').summary;assert.equal(r.pnl_without_price_imputation,0);assert.equal(r.price_imputed_entries,1);assert.ok(Math.abs(r.gross_before_costs-Object.values(r.costs).reduce((s,x)=>s+x,0)-r.net_pnl)<1e-7);
});

test('a paired spin-off uses the same explicit cash-equivalent liability estimate for a two-for-one consolidation',()=>{
 const C=require('./announcement_accounting.cjs'),{ctx,days}=fixture();ctx.factor=(_t,a,b)=>a<days[1]&&b>=days[1]?2:1;
 const c={id:'spin',issuer:'cik/1',ticker:'X',day:days[0],entry_price:10,adv_shares:100000000},o={quantity:100,horizon:2,borrow_apr:0,locate_min:0,locate_per_share:0,capture:1};const plain=C.trade(ctx,{get:()=>null},c,o),paired=C.trade(ctx,{get:()=>null},c,{...o,cash_return_days:[days[1]]});assert.equal(paired.costs.capital_repayment,500);assert.ok(Math.abs(plain.net_pnl-paired.net_pnl-500)<1e-7);
});

test('a source-specified repayment uses dollars per old share instead of a fitted neutral estimate',()=>{
 const C=require('./announcement_accounting.cjs'),{ctx,days}=fixture();ctx.factor=(_t,a,b)=>a<days[1]&&b>=days[1]?36/35:1;
 const c={id:'source-cash',issuer:'cik/1',ticker:'X',day:days[0],entry_price:10,adv_shares:100000000};const t=C.trade(ctx,{get:()=>null},c,{quantity:360,horizon:2,borrow_apr:0,locate_min:0,locate_per_share:0,capture:1,cash_return_days:[days[1]],distribution_actions:[{day:days[1],cash_per_old_share:1.26}]});assert.equal(t.costs.capital_repayment,453.6);assert.ok(Math.abs(t.returns.reduce((s,r)=>s+r.units,0)-360)<1e-8);
});
