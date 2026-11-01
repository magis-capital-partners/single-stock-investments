'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),F=require('./third_plus_fundamental_filters.cjs');
const at='2025-08-12T09:25:00-04:00';
function row(tag,val,end='2025-06-30',extra={}){return {tag:'us-gaap:'+tag,val,end,unit:'USD',filed:'2025-08-01',accn:'a',source:'SEC_companyfacts',dimensions:[],...extra};}
function annual(tag,val,end='2025-06-30',start='2024-07-01'){return row(tag,val,end,{start});}
function snapshot(){return {id:'x',issuer:'cik/1',ticker:'T',event_date:'2025-08-01',signals:{S7:{state:'pass'},reported_runway:{state:'pass'},S4:{state:'pass'}},reconciliation:{clock:{at,entry_eligible:true},financial:{status:'source_reconciled',cash:{period:'2025-06-30',currency:'USD',value:10},cfo:{value:-100},reported_runway_years:.1}}};}
test('future-public restatements cannot change a prior feature',()=>{
 const raw={facts:{'us-gaap':{OperatingIncomeLoss:{units:{USD:[{val:-5,start:'2024-07-01',end:'2025-06-30',filed:'2025-08-12',accn:'future'}]}}}}};assert.equal(F.rows(raw,[],at).length,0);
});
test('same-file original precision governs rounded companyfacts values',()=>{
 const rs=[row('Assets',100),row('Assets',101,'2025-06-30',{source:'original_inline_context',decimals:'0'})];assert.equal(F.point(rs,'assets','USD','2025-06-30').value,101);
});
test('conflicting same-date values remain unknown',()=>{
 const rs=[row('Assets',100),row('Assets',101)];assert.equal(F.point(rs,'assets','USD','2025-06-30'),null);
});
test('revenue growth never changes tags between current and prior periods',()=>{
 assert.equal(F.pair([annual('Revenues',80),annual('SalesRevenueNet',100,'2024-06-30','2023-07-01')],'revenue','USD','2025-06-30'),null);
});
test('year-ago anchor handles leap day without drifting into March',()=>{assert.equal(F.priorYear('2024-02-29'),'2023-02-28');});
test('a quarter uses a matched fiscal YTD difference rather than dividing YTD',()=>{
 const q=F.quarter([row('NetCashProvidedByUsedInOperatingActivities',-90,'2025-06-30',{start:'2025-01-01'}),row('NetCashProvidedByUsedInOperatingActivities',-20,'2025-03-31',{start:'2025-01-01'})],'2025-06-30');assert.equal(q.value,-70);assert.equal(q.days,91);
});
test('the exact fifteen percent revenue boundary passes',()=>{
 const s=F.buildOne(snapshot(),[annual('Revenues',85),annual('Revenues',100,'2024-06-30','2023-07-01')]);assert.equal(s.signals.revenue15.state,'pass');
});
test('zero prior revenue is undefined growth, not a revenue decline',()=>{
 const s=F.buildOne(snapshot(),[annual('Revenues',0),annual('Revenues',0,'2024-06-30','2023-07-01')]);assert.equal(s.signals.revenue15.state,'unknown');
});
test('accruals require a positive comparable year-ago asset denominator',()=>{
 const s=F.buildOne(snapshot(),[annual('NetIncomeLoss',10),row('Assets',100)]);assert.equal(s.signals.accrual10.state,'unknown');
});
test('bank classification disables operating-burn and accrual interpretations',()=>{
 const s=F.buildOne(snapshot(),[],{profile:'financial',filed_at:'2025-07-01',known_at:'2025-07-02T00:00:00-04:00'});assert.equal(s.signals.burn.state,'unknown');
});
test('missing maturity is never inferred from current liabilities',()=>{
 const s=F.buildOne(snapshot(),[row('LiabilitiesCurrent',1000)]);assert.equal(s.signals.debt_distress.state,'unknown');
});
test('stale financials and absent entry sessions cannot qualify numeric filters',()=>{
 const x=snapshot();x.reconciliation.financial.status='stale_reported_observation';assert.equal(F.buildOne(x,[annual('OperatingIncomeLoss',-1)]).signals.operating_loss.state,'unknown');
 x.reconciliation.financial.status='source_reconciled';x.reconciliation.clock.entry_eligible=false;assert.equal(F.buildOne(x,[]).signals.burn.state,'unknown');
});
test('covered comparison includes both pass and fail but excludes unknown',()=>{
 const arm={requires:['S7','burn']},s={signals:{S7:{state:'pass'},burn:{state:'fail'}}};assert.equal(F.armState(s,arm).state,'fail');assert.equal(F.armState(s,arm,true).state,'pass');s.signals.burn.state='unknown';assert.equal(F.armState(s,arm,true).state,'unknown');
});
test('all declared additions retain the chosen rally veto',()=>{
 for(const a of F.ARMS.filter(a=>!a.reference))assert.ok(a.requires.includes('S7'));assert.equal(F.ARMS.filter(a=>!a.reference).length,19);
});

const Study=require('./third_plus_fundamental_study.cjs');
test('chronological training excludes covers and loan returns after the embargo',()=>{
 const base={units:0,loan_units:0,closed:'2025-01-01',pending_returns:[{day:'2025-01-03'}]};
 assert.equal(Study.trainingPositions({positions:[base]},'2025-01-02').length,0);
 assert.equal(Study.trainingPositions({positions:[base]},'2025-01-04').length,1);
 assert.equal(Study.trainingPositions({positions:[{...base,loan_units:1}]},'2025-01-04').length,0);
});
test('too few prior completed issuers retains the saved rule',()=>{
 const ps=Array.from({length:29},(_,i)=>({issuer:String(i),units:0,loan_units:0,closed:'2025-01-01',pending_returns:[],pnl:1}));
 assert.equal(Study.selectTraining([{arm:'saved',positions:ps}],'2025-01-04').arm,'saved');
});
test('an exact eight-point margin decline passes despite floating point representation',()=>{
 const all=[annual('Revenues',100),annual('Revenues',100,'2024-06-30','2023-07-01'),annual('OperatingIncomeLoss',10),annual('OperatingIncomeLoss',18,'2024-06-30','2023-07-01')];assert.equal(F.buildOne(snapshot(),all).signals.margin8.state,'pass');
});

test('matched controls keep the rally veto and relax only the added fundamental filter',()=>{
 const arm={requires:['S7','burn']};assert.equal(F.armState({signals:{S7:{state:'fail'},burn:{state:'pass'}}},arm,true).state,'fail');
 assert.equal(F.armState({signals:{S7:{state:'unknown'},burn:{state:'pass'}}},arm,true).state,'unknown');
 assert.equal(F.armState({signals:{S7:{state:'pass'},burn:{state:'fail'}}},arm,true).state,'pass');
});
