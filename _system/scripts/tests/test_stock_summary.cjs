
const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../../../dashboard/stock-summary.js');
const P = require('../../../dashboard/stock-performance.js');

test('two sessions do not offer multi-month ranges or an annualized return',()=>{
  const prices=[['2026-11-17',100],['2026-11-18',97.36]];
  assert.deepEqual(S.eligibleRanges(prices).map(r=>r[0]),['All']);
  assert.deepEqual(S.selectedPoints(prices,'All'),prices);
  assert.equal(P.windowData({points:prices.map(([day,v])=>[day,v,v])}).cagr,null);
});
test('native prices use the selected session window',()=>{
  const prices=[['2025-02-24',15],['2026-10-20',94],['2026-11-02',100],['2026-11-20',79.24]];
  assert.deepEqual(S.eligibleRanges(prices).map(r=>r[0]),['1M','3M','6M','1Y','All']);
  assert.deepEqual(S.selectedPoints(prices,'1M'),prices.slice(2));
  assert.equal(P.windowData({points:[['2025-01-01',100,100],['2026-01-01',110,110]]}).total > 0,true);
});
