const test=require('node:test');
const assert=require('node:assert/strict');
const {monteCarlo,quantile}=require('../../../dashboard/short-sleeve-engine.js');

test('quantiles preserve zero and exclude unavailable ratios',()=>{
  assert.equal(quantile([null,0,1,2],.5),1);
  assert.equal(quantile([null],.5),null);
});
test('zero activity stays flat with missing Calmar rather than infinity',()=>{
  const r=monteCarlo(['2024-01-02','2024-02-01'],[{scenario:'base',series:[]}],20,1,7).base;
  assert.equal(r.ending.p50,1);assert.equal(r.cagr.p50,0);assert.equal(r.max_drawdown.p95,0);assert.equal(r.calmar.p50,null);
});
test('repeated identical seed is deterministic and cost cases share the sampled months',()=>{
  const days=['2024-01-02','2024-01-03','2024-02-01','2024-02-02'];
  const models=[{scenario:'bull',series:[[0,.001,.01,.011],[2,-.0005,.02,.022]]},{scenario:'bear',series:[[0,.0005,.01,.011],[2,-.001,.02,.022]]}];
  const a=monteCarlo(days,models,40,1,42),b=monteCarlo(days,models,40,1,42);
  assert.deepEqual(a,b);assert.ok(a.bear.ending.p50<a.bull.ending.p50);assert.ok(a.bear.max_drawdown.p95>=a.bull.max_drawdown.p95);
});
test('a first-day loss enters maximum drawdown and insolvency is retained',()=>{
  const r=monteCarlo(['2024-01-02'],[{scenario:'bear',series:[[0,-1.2,2,2.1]]}],5,1,42).bear;
  assert.equal(r.ruin_probability,1);assert.equal(r.cagr.p50,null);assert.ok(r.max_drawdown.p50>=1.2);
});
test('insolvent growth paths retain their percentile rank rather than being dropped',()=>{
  const r=monteCarlo(['2024-01-02','2024-02-01'],[{scenario:'base',series:[[0,-1.2,2,2.1],[1,.01,.01,.011]]}],100,1/252,42).base;
  assert.ok(r.ruin_probability>.1&&r.ruin_probability<.9);
  assert.equal(r.cagr.p05,null);
});
