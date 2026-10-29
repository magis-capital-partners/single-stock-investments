'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const screen=require('./third_plus_saved_screen.cjs');
const config=require('../data/reverse_splits/third_plus_signal_study/saved_screens/third_plus_no_50pct_rally.v1.json');
function snapshot(ordinal=3,value=.49){return {id:'fixture',entry_day:'2025-06-10',decision_at:'2025-06-10T09:25:00-04:00',price_asof:'2025-06-09',control:{ordinal},signals:{S7:{state:value>=.5?'fail':'pass',value,reason:'no_prior_five_session_50pct_close_rally'},S1:{state:'unknown',reason:'unreconciled_funding'}}};}
test('rally veto cannot admit first or second reverse splits',()=>{
 assert.equal(screen.evaluate(snapshot(1),config).decision,'outside_universe');
 assert.equal(screen.evaluate(snapshot(2),config).decision,'outside_universe');
 assert.equal(screen.evaluate(snapshot(3),config).decision,'selected');
 assert.equal(screen.evaluate(snapshot(5),config).decision,'selected');
 assert.equal(screen.evaluate(snapshot(2.9),config).decision,'unknown');
});
test('a daily 50% rise vetoes inclusively; just below the threshold passes',()=>{
 assert.equal(screen.evaluate(snapshot(3,.499999),config).decision,'selected');
 assert.equal(screen.evaluate(snapshot(3,.5),config).decision,'vetoed');
 assert.equal(screen.evaluate(snapshot(3,1),config).decision,'vetoed');
});
test('unavailable rally history never becomes a pass',()=>{
 const row=snapshot();row.signals.S7={state:'unknown',reason:'incomplete_adjusted_five_session_history'};
 assert.equal(screen.evaluate(row,config).decision,'unknown');
 delete row.signals.S7;assert.equal(screen.evaluate(row,config).decision,'unknown');
});
test('same-session or unavailable observation clocks cannot pass the saved screen',()=>{
 const row=snapshot();row.price_asof=row.entry_day;assert.equal(screen.evaluate(row,config).decision,'unknown');
 row.price_asof='2025-06-09';row.decision_at='2025-06-10T09:25:00';assert.equal(screen.evaluate(row,config).decision,'unknown');
});
test('fundamental unknowns do not add an undeclared requirement to the chosen screen',()=>{
 const row=snapshot();assert.equal(screen.evaluate(row,config).decision,'selected');
 const c=screen.coverage([row]);assert.equal(c.S1.calculable,0);assert.equal(c.S1.unknown,1);
 assert.equal(c.S1.unknown_reasons.unreconciled_funding,1);
 assert.equal(config.production_authority,'none');
});
test('contradictory rally value and state are rejected',()=>{
 const row=snapshot(3,.5);row.signals.S7.state='pass';assert.throws(()=>screen.evaluate(row,config),/disagree/);
});
