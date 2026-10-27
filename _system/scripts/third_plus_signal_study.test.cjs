'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const F=require('./third_plus_signal/features.cjs'),S=require('./third_plus_signal/statistics.cjs'),J=require('./third_plus_signal/forward.cjs'),E=require('./third_plus_signal/engine.cjs'),B=require('./reverse_split_repeat_study.cjs');
const A=require('./short_framework/adapters.cjs');
function fact(end,val,filed,accn='a',start){return {end,val,filed,accn,...(start?{start}:{})};}
function rawFacts(){
 return {cik:1,facts:{'us-gaap':{
  CashAndCashEquivalentsAtCarryingValue:{units:{USD:[fact('2024-06-30',60,'2024-08-01')]}},
  NetCashProvidedByUsedInOperatingActivities:{units:{USD:[
   fact('2023-12-31',-100,'2024-03-01','annual','2023-01-01'),
   fact('2024-06-30',-70,'2024-08-01','current','2024-01-01'),
   fact('2023-06-30',-40,'2024-08-01','current','2023-01-01')
  ]}}
 }}};
}
function fixture({missing=false,ssr=0,prices:custom,rows=1}={}){
 const days=[];for(let d='2025-01-02';days.length<45;d=A.dateAfter(d))if(![0,6].includes(new Date(d+'T12:00:00Z').getUTCDay()))days.push(d);
 const index=new Map(days.map((d,i)=>[d,i]));
 const point=(t,d)=>custom?custom(t,index.get(d)):({open:10,high:10,low:8,close:8,volume:100000});
 const candidates=Array.from({length:rows},(_,i)=>({id:'fixture'+i,issuer:'cik/'+i,ticker:'T'+i,day:days[0],i:0,ordinal:3,provider_ordinal:3,entry_price:10,liquidity_complete:true,adv_shares:1000,year:'2025'}));
 const prices={days,index,last:days.at(-1),point,prior:()=>({adv:1000,complete:true}),ssrQuery:{get:()=>({restricted:ssr})}};
 return {candidates,prices,auction:(t,d)=>({open:point(t,d).open,close:missing?null:point(t,d).close}),factor:()=>1,settlement:d=>days[index.get(d)+1]||A.dateAfter(d)};
}
const options={horizon:5,cost:'ideal',cap:null,financial:'all',ordinal:'extended',fastStats:true};
test('cash flow uses annual plus matched YTD, not division of YTD',()=>{
 const f=F.financialSnapshot(rawFacts(),'2024-08-05T09:25:00-04:00');
 assert.equal(f.cfo,-130);assert.equal(f.reported_runway,60/130);
});
test('future restatements cannot change an earlier cash snapshot',()=>{
 const r=rawFacts();r.facts['us-gaap'].CashAndCashEquivalentsAtCarryingValue.units.USD.push(fact('2024-06-30',9999,'2025-03-01'));
 assert.equal(F.financialSnapshot(r,'2024-08-05T09:25:00-04:00').cash,60);
});
test('filing-day-only facts wait until next Eastern day',()=>{
 assert.equal(F.financialSnapshot(rawFacts(),'2024-08-01T23:59:00-04:00').status,'missing_fresh_unrestricted_cash');
});
test('incomparable YTD cannot manufacture TTM cash burn',()=>{
 const r=rawFacts();r.facts['us-gaap'].NetCashProvidedByUsedInOperatingActivities.units.USD=r.facts['us-gaap'].NetCashProvidedByUsedInOperatingActivities.units.USD.slice(1,2);
 assert.equal(F.financialSnapshot(r,'2024-08-05T09:25:00-04:00').status,'missing_comparable_TTM_CFO');
});
test('ambiguous currency is unknown rather than silently converted',()=>{
 const r=rawFacts();r.facts['us-gaap'].CashAndCashEquivalentsAtCarryingValue.units.EUR=[fact('2024-06-30',10,'2024-08-01')];
 assert.equal(F.financialSnapshot(r,'2024-08-05T09:25:00-04:00').status,'ambiguous_currency');
});
test('same-filing comparable shares measure dilution',()=>{
 const raw={facts:{'us-gaap':{CommonStockSharesOutstanding:{units:{shares:[fact('2023-12-31',80,'2024-08-01'),fact('2024-06-30',100,'2024-08-01')]}}}}};
 const r=F.sharesFeature(raw,'2024-08-05T09:25:00-04:00',new Map(),()=>null);
 assert.equal(r.state,'pass');assert.equal(r.value,.25);
});
test('cross-action share counts need a primary restatement clause',()=>{
 const raw={facts:{'us-gaap':{CommonStockSharesOutstanding:{units:{shares:[fact('2023-12-31',80,'2024-08-01'),fact('2024-06-30',100,'2024-08-01')]}}}}};
 const actions=new Map([['2024-02-01',{factor:10}]]);
 assert.equal(F.sharesFeature(raw,'2024-08-05T09:25:00-04:00',actions,()=>null).state,'unknown');
 const r=F.sharesFeature(raw,'2024-08-05T09:25:00-04:00',actions,()=>'All share and per-share amounts have been retroactively adjusted for the reverse stock split.');
 assert.equal(r.value,.25);
});
test('weighted-average EPS shares are never a period-end dilution proxy',()=>{
 const raw={facts:{'us-gaap':{WeightedAverageNumberOfSharesOutstandingBasic:{units:{shares:[fact('2024-06-30',100,'2024-08-01')]}}}}};
 assert.equal(F.sharesFeature(raw,'2024-08-05T09:25:00-04:00',new Map(),()=>null).state,'unknown');
});
test('completion-language lead is not independent financing verification',()=>{
 const r=F.leadClaim('The Company completed a private placement of common stock. Net proceeds were $2 million.');
 assert.equal(r.manual_independent_review_complete,false);assert.ok(r.completed_claims.length>0);
});
test('expected future completion is not a completed transaction lead',()=>{
 assert.equal(F.leadClaim('The Company expects the offering of common stock to be completed next month.').completed_claims.length,0);
});
test('unknown features do not become negative financing or covered observations',()=>{
 assert.equal(F.andStates([F.state(true,'yes'),F.unknown('missing')]).state,'unknown');
 assert.equal(F.armState({signals:{}},'S2',true).state,'unknown');
 assert.equal(F.andStates([F.state(false,'no'),F.unknown('missing')]).state,'fail');
});
test('two different blinded reviewers and full economic fields are mandatory',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'third-plus-review-')),f=path.join(dir,'reviews.json');
 fs.writeFileSync(f,JSON.stringify([{issuer:'cik/1',deal_id:'x',known_at:'2024-01-01T00:00:00Z',source_sha256:'a'.repeat(64),source_url:'https://example.test',locator:'x',reviewers:['same','same'],outcome_blinded:true}]));
 assert.throws(()=>F.loadReviews(f),/Independent blinded/);
 fs.unlinkSync(f);fs.rmdirSync(dir);
});
test('Holm adjustment remains monotonic across overlapping rule claims',()=>{
 const rows=[{p:.001},{p:.03},{p:.04}];S.holm(rows);assert.deepEqual(rows.map(r=>r.holm_p),[.003,.06,.06]);
});
test('paired bootstrap cannot report a degenerate zero strategy as significant',()=>{
 const r=S.bootstrap([0,0,0,0],{B:100});assert.equal(r.p_positive,1);assert.deepEqual(r.interval,[0,0]);
});
test('account admission uses the same per-name and sleeve reserves',()=>{
 const c=fixture({rows:4});const r=B.replay(c,{...options,nav:1000000,maximumNames:3});
 assert.equal(r.summary.entered,3);assert.ok(r.positions.every(p=>p.entry_reference_notional<=2500));assert.equal(r.summary.funnel.risk_capacity,1);
});
test('later same-day marks do not change a new order risk budget',()=>{
 function run(close){
  const c=fixture({rows:2,prices:(t,i)=>({open:10,high:Math.max(10,t==='T0'&&i===1?close:10),low:8,close:t==='T0'&&i===1?close:10,volume:100000})});
  c.candidates[1]={...c.candidates[1],i:1,day:c.prices.days[1]};
  return B.replay(c,{...options,horizon:20,nav:1000000,causalCarry:true}).positions.find(p=>p.ticker==='T1').entry_units;
 }
 assert.equal(run(12),run(1000));
});
test('unknown and restricted SSR cannot pass the strict route',()=>{
 for(const ssr of [null,1])assert.equal(B.replay(fixture({ssr}),{...options,ssrMode:'strict'}).summary.entered,0);
 assert.equal(B.replay(fixture({ssr:0}),{...options,ssrMode:'strict'}).summary.entered,1);
});
test('a missing exit remains a full marked short liability',()=>{
 const r=B.replay(fixture({missing:true}),options);assert.equal(r.summary.open_positions,1);assert.equal(r.summary.open_liability,20000);assert.equal(r.summary.closed,0);
});
test('partial covers preserve remaining shares and complete over later sessions',()=>{
 const c=fixture({prices:(t,i)=>({open:10,high:10,low:8,close:8,volume:i===1?100:100000})});
 const r=B.replay(c,{...options,horizon:2,cap:.05});assert.equal(r.positions[0].cover_children,2);assert.equal(r.summary.net_pnl,100);
});
test('next-open risk exit respects a gap through its close threshold',()=>{
 const c=fixture({prices:(t,i)=>i===0?{open:10,high:14,low:10,close:14,volume:100000}:i===1?{open:18,high:18,low:9,close:9,volume:100000}:{open:9,high:9,low:9,close:9,volume:100000}});
 const r=B.replay(c,{...options,horizon:20,stopCloseFraction:.2});
 assert.equal(r.positions[0].closed,c.prices.days[1]);assert.equal(r.summary.net_pnl,-20000);
});
test('delayed comparisons preserve original common maturity and anchored exit',()=>{
 const c=fixture(),r=E.shiftCandidate(c,c.candidates[0],3,true);
 assert.equal(r.maturity_index,0);assert.equal(r.i,3);assert.equal(r.exit_index_override,19);
 const p=B.replay({...c,candidates:[r]},{...options,horizon:20,maturitySessions:23}).positions[0];
 assert.equal(p.deadline,19);
});
test('failed bounce can enter only after the confirming bar has completed',()=>{
 const c=fixture({prices:(t,i)=>i===0?{open:10,high:10,low:10,close:10,volume:100000}:i===1?{open:10,high:12,low:10.5,close:11,volume:100000}:i===2?{open:11,high:11,low:9,close:9,volume:100000}:{open:9,high:9,low:9,close:9,volume:100000}});
 const row={...c.candidates[0],i:1,day:c.prices.days[1]},r=E.delayConfirmation(c,[row]);
 assert.equal(r.rows.length,1);assert.equal(r.rows[0].day,c.prices.days[3]);
});
test('walk-forward training excludes future closes and unfinished loan returns',()=>{
 const r={positions:[{id:'future',closed:'2025-05-01',pending_returns:[],units:0},{id:'loan',closed:'2024-01-01',pending_returns:[{day:'2025-05-01'}],units:0},{id:'past',closed:'2024-01-01',pending_returns:[{day:'2024-01-02'}],units:0}]};
 assert.deepEqual(E.trainingRecords(r,'2025-01-01').map(p=>p.id),['past']);
});
function enrollment(){
 const policy={research_only:true,production_authority:'none'},input={event_id:'e',issuer_id:'cik/1',known_at:'2030-01-01T10:00:00Z',documented_split_ordinal:3};
 return {kind:'enrollment',event_id:'e',issuer_id:'cik/1',known_at:'2030-01-01T10:00:00Z',entry_at:'2030-01-02T14:30:00Z',source_url:'https://example.test/source',locator:'x',source_sha256:'a'.repeat(64),decision:'observe',policy_snapshot:policy,policy_sha256:J.hash(policy),input_snapshot:input,input_sha256:J.hash(input)};
}
test('forward enrollment rejects retrospective entries and future outcome labels',()=>{
 const r=enrollment();assert.throws(()=>J.validate({...r,entry_at:'2029-01-01T00:00:00Z'},[],'2030-01-01T12:00:00Z'),/precede future entry/);
 r.input_snapshot.future_return=.4;r.input_sha256=J.hash(r.input_snapshot);assert.throws(()=>J.validate(r,[],'2030-01-01T12:00:00Z'),/Outcome field/);
});
test('shadow import is atomic and its hash chain detects tampering',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'third-plus-shadow-')),f=path.join(dir,'journal.jsonl'),r=enrollment(),now='2030-01-01T12:00:00Z';
 J.append(f,[r],now);const before=fs.readFileSync(f,'utf8');
 const good={kind:'locate',event_id:'e',issuer_id:'cik/1',known_at:now,observed_at:now,source_url:'https://example.test',source_sha256:'b'.repeat(64),locator:'ticket',policy_sha256:r.policy_sha256,shares:100,apr:.5,broker_reference:'actual',status:'approval'};
 assert.throws(()=>J.append(f,[good,{...good,kind:'fill',price:10,phase:'entry'}],now),/Fill must/);
 assert.equal(fs.readFileSync(f,'utf8'),before);
 const row=JSON.parse(before);row.record.issuer_id='cik/2';fs.writeFileSync(f,JSON.stringify(row)+'\n');assert.throws(()=>J.load(f),/hash mismatch/);
 fs.unlinkSync(f);fs.rmdirSync(dir);
});
test('original mechanical-action and fixed-dollar accounting fixtures still pass',()=>{
 assert.equal(B.tests().passed,true);assert.equal(B.extendedTests().passed,true);
});

test('walk-forward fallback retains the baseline account capital constraints',()=>{
 const c=fixture(),baseline={arm:'baseline',positions:[],summary:{nav:1000000,maximumNames:3}};let observed;
 E.walkForward(c,[baseline],new Map(),(id,options,rows)=>{observed=options;return {summary:{}};});
 assert.equal(observed.nav,1000000);assert.equal(observed.maximumNames,3);
});
