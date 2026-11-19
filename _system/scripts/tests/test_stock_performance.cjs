const {test}=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../../../dashboard/stock-performance.js');
const record={currency:'USD',status:'partial',basis:'Dividends reinvested',points:[['2000-01-01',100,100],['2010-01-01',200,200],['2015-01-01',100,100],['2020-01-01',250,300]],benchmark:{currency:'USD',source_url:'https://example.com/benchmark',points:[['2000-01-01',100,100],['2010-01-01',150,150],['2015-01-01',120,120],['2020-01-01',200,200]]}};
test('full history rebases real observations and reports drawdown from a running peak',()=>{
 const d=ui.windowData(record);assert.equal(d.total,2);assert.equal(d.ending,30000);assert.equal(d.drawdown,-.5);
 assert.equal(d.values[0].total,10000);assert.equal(d.values.at(-1).price,25000);assert.ok(d.cagr>0);
});
test('selected period rebases stock and benchmark on exactly the same observed dates',()=>{
 const d=ui.windowData(record,'5');assert.equal(d.start,'2015-01-01');assert.equal(d.total,2);
 assert.equal(d.values[0].benchmark,10000);assert.ok(Math.abs(d.values.at(-1).benchmark-10000*200/120)<1e-8);
});
test('mismatched currency and missing benchmark observations never become made-up returns',()=>{
 const copy=JSON.parse(JSON.stringify(record));copy.benchmark.currency='EUR';assert.equal(ui.windowData(copy).benchmark,null);
 copy.benchmark.currency='USD';copy.benchmark.points.splice(1,1);assert.equal(ui.windowData(copy).values[1].benchmark,null);
 assert.equal(ui.windowData({points:[]}),null);
});
test('complete loss remains minus 100 percent and zero is not treated as missing',()=>{
 const copy={...record,benchmark:null,points:[['2000-01-01',100,100],['2020-01-01',1,0]]};
 assert.equal(ui.windowData(copy).total,-1);assert.equal(ui.windowData(copy).drawdown,-1);
});
test('performance UI includes source definitions, period controls and explicit incomplete coverage',()=>{
 const html=ui.render({ticker:'CPRT',one_pager:{performance:record}});
 assert.match(html,/Growth of/);assert.match(html,/Largest decline from a peak/);assert.match(html,/Distribution verification incomplete/);
 assert.match(html,/Annual values, sources and return definitions/);assert.match(html,/aria-pressed="true">All history/);
 assert.match(html,/S&amp;P 500|S&P 500/);
});


test('turning off the benchmark preserves the entire stock history and zero closing wealth',()=>{
 const copy=JSON.parse(JSON.stringify(record));copy.points.unshift(['1960-01-01',10,10]);
 assert.equal(ui.windowData(copy,'all',false).start,'1960-01-01');
 assert.equal(ui.windowData(copy,'all',true).start,'2000-01-01');
 const loss={currency:'USD',points:[['2000-01-01',100,100],['2001-01-01',0,0]]};
 assert.equal(ui.windowData(loss).total,-1);
 assert.match(ui.render({ticker:'MISSING'}),/history is not available for this listing/);
});
