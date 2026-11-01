'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const E=require('./third_plus_reconciliation_engine.cjs');
const at='2025-08-12T09:25:00-04:00';
function fact(tag,val,end='2025-06-30',extra={}){return {tag:'us-gaap:'+tag,val,end,unit:'USD',filed:'2025-08-01',accn:'b',source:'original_inline_context',dimensions:[],...extra};}
test('Cash is an unrestricted-cash input without adding restricted-cash totals',()=>{
 const c=E.cash([fact('Cash',100),fact('CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',150)]);assert.equal(c.value,100);
});
test('a Cash caption explicitly including restricted cash must subtract its reported component',()=>{
 const c=E.cash([fact('Cash',679000,'2025-06-30',{row_label:'Cash (includes $0.27 million of restricted cash) 679 653'}),fact('RestrictedCash',270000)]);assert.equal(c.value,409000);
});
test('a current primary statement row governs note-currency cash observations',()=>{
 const c=E.cash([fact('Cash',6012,'2025-06-30',{row_label:'Cash $ 6,012 $ 7,934'}),fact('Cash',27332,'2025-06-30',{unit:'CNY'})]);assert.equal(c.currency,'USD');assert.equal(c.value,6012);
});
test('total CFO adds continuing and discontinued operations from one matching period',()=>{
 const x={start:'2025-01-01'};const flows=E.totalFlows([fact('NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',-100,'2025-06-30',x),fact('CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations',30,'2025-06-30',x)],'USD');assert.equal(flows[0].val,-70);
});
test('a generic total CFO tag cannot override an explicit continuing-operations caption',()=>{
 const rows=[fact('NetCashProvidedByUsedInOperatingActivities',-100,'2025-06-30',{start:'2025-01-01',row_label:'Net cash used in operating activities, continuing operations'})];assert.equal(E.totalFlows(rows,'USD').length,0);
});
test('as-of facts exclude future-public source reports, even if downloaded now',()=>{
 const docs=[{accession:'future',filed_at:'2025-08-12',facts:[{tag:'us-gaap:Cash',value:999,end:'2025-06-30',unit:'USD',dimensions:[]}]}];assert.equal(E.publicRows({facts:{}},docs,at).length,0);
});
function share(end,val,filed,accn){return fact('CommonStockSharesOutstanding',val,end,{unit:'shares',filed,accn});}
test('identity actions never block an otherwise comparable share count',()=>{
 const rows=[share('2025-06-30',200,'2025-08-01','b'),share('2024-12-31',100,'2025-02-01','a')];const out=E.shares(rows,[],'T',new Map([['2025-04-01',{factor:1,priority:0,basis:'legacy_database'}]]),at);assert.equal(out.growth,1);
});
test('a reverse split after both source observations cannot change measured dilution',()=>{
 const rows=[share('2025-06-30',200,'2025-08-01','b'),share('2024-12-31',100,'2025-02-01','a')];const actions=new Map([['2025-08-11',{factor:100,priority:2,basis:'provider'}]]);assert.equal(E.shares(rows,[],'T',actions,at).growth,1);
});
test('overlapping historical counts prove a filing restatement and avoid double adjustment',()=>{
 const rows=[share('2025-06-30',20,'2025-08-01','b'),share('2024-12-31',10,'2025-08-01','b'),share('2024-12-31',100,'2025-02-01','a')];
 const actions=new Map([['2025-07-01',{factor:10,priority:4,basis:'primary_schedule_matched'}]]);const out=E.shares(rows,[],'T',actions,at);assert.equal(out.growth,1);assert.match(out.latest_basis.basis,/overlapping/);
});
test('an actual May split clause is not mistaken for prospective may language',()=>{
 const rows=[share('2025-06-30',20,'2025-08-01','b'),share('2024-12-31',100,'2025-02-01','a')];const doc={accession:'b',filed_at:'2025-08-01',text:'',paragraphs:['On May 16, 2025, the Company effected a 1-for-10 reverse stock split.']};const actions=new Map([['2025-05-19',{factor:10,priority:2,basis:'provider'}]]);assert.equal(E.shares(rows,[doc],'T',actions,at).growth,1);
});
test('a prospective ratio/date statement is not proof an action happened',()=>{
 const rows=[share('2025-06-30',20,'2025-08-01','b'),share('2024-12-31',100,'2025-02-01','a')];const doc={accession:'b',filed_at:'2025-08-01',text:'',paragraphs:['The Company expects to effect a 1-for-10 reverse stock split on May 19, 2025.']};const actions=new Map([['2025-05-19',{factor:10,priority:2,basis:'provider'}]]);assert.equal(E.shares(rows,[doc],'T',actions,at).status,'unresolved_share_unit_basis');
});

test('issued shares can prove a dilution lower bound without pretending they are outstanding shares',()=>{
 const rows=[share('2025-06-30',200,'2025-08-01','b'),fact('CommonStockSharesIssued',100,'2024-12-31',{unit:'shares',filed:'2025-02-01',accn:'a'})];
 const out=E.shares(rows,[],'T',new Map(),at);assert.equal(out.status,'source_reconciled_threshold_bound');assert.equal(out.growth,null);assert.equal(out.growth_lower_bound,1);assert.equal(out.threshold_pass,true);
});
test('an inconclusive issued-share bound cannot manufacture a passing or failing dilution signal',()=>{
 const rows=[share('2025-06-30',110,'2025-08-01','b'),fact('CommonStockSharesIssued',100,'2024-12-31',{unit:'shares',filed:'2025-02-01',accn:'a'})];
 assert.equal(E.shares(rows,[],'T',new Map(),at).status,'unresolved_share_unit_basis');
});

const Funding=require('./third_plus_reconciliation_funding.cjs');
function review(id,filed,extra={}){return {claim_id:id,issuer:'cik/1',accession:id,known_filed_date:filed,independent_review:false,outcome_blinded:false,state:'completed_issuer_financing',deal_key:'cik/1/deal',closed_date:'2025-01-03',...extra};}
test('a net amount first published later cannot leak into an earlier financing snapshot',()=>{
 const rows=[review('a','2025-01-03',{gross_cash:100}),review('b','2025-01-20',{net_cash:90})];
 assert.equal(Funding.dealsAsOf(rows,'2025-01-10T09:25:00-05:00')[0].net_cash,null);
 assert.equal(Funding.dealsAsOf(rows,'2025-01-21T09:25:00-05:00')[0].net_cash.value,90);
});
test('repeated disclosures and cumulative ATM totals are counted once per economic deal',()=>{
 const rows=[review('a','2025-01-03',{gross_cash_cumulative:100,cash_series:'cumulative'}),review('b','2025-01-10',{gross_cash_cumulative:150,cash_series:'cumulative'})];
 const deals=Funding.dealsAsOf(rows,'2025-01-15T09:25:00-05:00');assert.equal(deals.length,1);assert.equal(deals[0].gross_cash.value,150);
});
test('a cumulative interval crossing the balance date cannot be added in full',()=>{
 const row=review('a','2025-01-10',{closed_date:null,cash_interval:['2024-12-01','2025-01-09'],net_cash:90});
 const event={id:'x',issuer:'cik/1',clock:{at:'2025-01-15T09:25:00-05:00'},financial:{cash:{period:'2024-12-31',value:100}}};
 const out=Funding.caseFunding(event,[row],[]);assert.equal(out.identified_net_cash_after_balance,0);assert.equal(out.unresolved_cash_items[0].reason,'cash_interval_not_wholly_after_balance_date');
});
test('noncash consideration remains separate from cash proceeds',()=>{
 const row=review('a','2025-01-03',{cash_consideration:25,non_cash_consideration:109});
 const deal=Funding.dealsAsOf([row],'2025-01-10T09:25:00-05:00')[0];assert.equal(deal.cash_consideration.value,25);assert.equal(deal.non_cash_consideration.value,109);assert.equal(deal.gross_cash,null);
});
test('single-analyst evidence cannot be relabeled independent or bound to another issuer',()=>{
 const row=review('a','2025-01-03',{independent_review:true});assert.throws(()=>Funding.validateReviews([row],new Map()),/invent independent/);
 const wrong=review('b','2025-01-03');assert.throws(()=>Funding.validateReviews([wrong],new Map([['b',{cik:2,filed_at:'2025-01-03'}]])),/identity/);
});

test('cash with an unbound currency cannot be added to a USD balance',()=>{
 const event={id:'x',issuer:'cik/1',clock:{at:'2025-01-15T09:25:00-05:00'},financial:{cash:{period:'2024-12-31',value:100,currency:'USD'}}};
 const row=review('a','2025-01-03',{net_cash:90});const out=Funding.caseFunding(event,[row],[]);assert.equal(out.identified_net_cash_after_balance,0);assert.equal(out.unresolved_cash_items[0].reason,'cash_currency_not_bound_to_balance_currency');
});
test('later currency evidence cannot leak into an earlier financing snapshot',()=>{
 const rows=[review('a','2025-01-03',{net_cash:90}),review('b','2025-01-20',{cash_currency:'USD'})];
 assert.equal(Funding.dealsAsOf(rows,'2025-01-10T09:25:00-05:00')[0].net_cash.currency,null);
 assert.equal(Funding.dealsAsOf(rows,'2025-01-21T09:25:00-05:00')[0].net_cash.currency,'USD');
});

const Audit=require('./third_plus_reconciliation_report.cjs');
function syntheticPopulation(){return Array.from({length:210},(_,i)=>({id:String(i),clock:{at:'2025-01-15T09:25:00-05:00'},financial:{cash:{value:1},cfo:{value:-1}},shares:{growth:1},financing:{adjusted_cash_is_complete:false,independent_financing_review_complete:false}}));}
test('the all-210 audit rejects duplicate identities and future-public supporting evidence',()=>{
 let events=syntheticPopulation(),features=events.map(e=>({id:e.id}));assert.equal(Audit.assertEvents(events,features).unique_events,210);
 events[0].financial.cash.evidence={known_at:'2025-01-16T00:00:00-05:00'};assert.throws(()=>Audit.assertEvents(events,features),/Future-public/);
 events=syntheticPopulation();events[1].id=events[0].id;assert.throws(()=>Audit.assertEvents(events,features),/unique events/);
});
test('a bound passes population completeness only when it actually proves the threshold',()=>{
 const events=syntheticPopulation(),features=events.map(e=>({id:e.id}));events[0].shares={growth:null,threshold_pass:true,growth_lower_bound:.3};assert.doesNotThrow(()=>Audit.assertEvents(events,features));
 events[0].shares.growth_lower_bound=.1;assert.throws(()=>Audit.assertEvents(events,features),/Unresolved dilution/);
});
