const test=require('node:test'),assert=require('node:assert/strict');
const M=require('../../../dashboard/stock-research-metrics.js');
require('../../../dashboard/stock-research-preferences.js');
require('../../../dashboard/stock-valuation.js');
const UI=require('../../../dashboard/stock-research-explorer.js');
const source={url:'https://issuer.example/report',filed:'2026-02-01'};
const quarters=values=>values.map((value,i)=>({period:['2025-03-31','2025-06-30','2025-09-30','2025-12-31'][i],start:['2025-01-01','2025-04-01','2025-07-01','2025-10-01'][i],value,source}));
test('TTM margins divide totals rather than averaging percentages',()=>{
 const d={series:[{id:'revenue',unit:'USD',quarterly:quarters([10,20,30,40])},{id:'operating_income',unit:'USD',quarterly:quarters([1,4,9,16])},{id:'operating_margin',unit:'percent'}]};
 assert.equal(M.points(d,'operating_margin','ttm')[0].value,30);
});
test('TTM shares are duration-weighted; per-share cash is not the sum of per-quarter ratios',()=>{
 const d={share_basis:{eligible:true,splits:[],as_of:'2026-03-04',source_url:'https://issuer.example/splits'},series:[{id:'free_cash_flow',unit:'USD',quarterly:quarters([10,20,30,40])},{id:'diluted_shares',unit:'shares',quarterly:quarters([10,20,30,40])},{id:'fcf_per_share',unit:'USD/shares'}]};
 const weighted=(10*90+20*91+30*92+40*92)/365;
 assert.equal(M.points(d,'fcf_per_share','ttm')[0].value,100/weighted);
});
test('historical EPS and share counts align splits once and preserve the reported value',()=>{
 const old={period:'2019-12-31',value:12,source:{filed:'2020-02-01',url:'https://issuer.example/report'}};
 const d={share_basis:{eligible:true,as_of:'2026-11-21',source_url:'https://issuer.example/split',splits:[{date:'2020-08-31',factor:4}]},series:[{id:'diluted_eps',unit:'USD/shares',annual:[old]},{id:'shares',unit:'shares',statement:'balance',annual:[{...old,value:100}]}]};
 assert.equal(M.points(d,'diluted_eps','annual')[0].value,3);assert.equal(M.points(d,'diluted_eps','annual')[0].reported_value,12);
 assert.equal(M.points(d,'shares','annual')[0].value,400);assert.equal(old.value,12);
 assert.equal(M.points({...d,view_basis:'first'},'diluted_eps','annual')[0].value,12);
});
test('P/E uses the same reported-share common-earnings basis throughout the history',()=>{
 const d={series:[{id:'pe',statement:'valuation',unit:'multiple',monthly:[{period:'2026-01-31',value:999}]},{id:'earnings_yield',statement:'valuation',unit:'percent',monthly:[{period:'2026-01-31',value:5,source}]}]};
 assert.equal(M.points(d,'pe','annual')[0].value,20);
});
test('earnings cards separate fiscal-quarter figures from full-year EPS',()=>{
 const period='2025-12-31',doc={ticker:'T',as_of:'2026-03-01',events:[{period,date:'2026-02-01',type:'filing',title:'Results filing',source}],gaps:[],series:[{id:'revenue',unit:'USD',statement:'income',quarterly:[{period,value:100,source}],annual:[{period,value:400,source}]},{id:'diluted_eps',unit:'USD/shares',statement:'income',quarterly:[],annual:[{period,value:8,source}]}]};
 const html=UI.render(doc,'sources',{insights:[]}),quarter=html.match(/<span class="sx-result-period"><strong>Fiscal quarter:[\s\S]*?<\/span>/)[0];
 assert.match(quarter,/Revenue: 100/);assert.doesNotMatch(quarter,/Diluted EPS/);assert.match(html,/Full fiscal year:[\s\S]*?Diluted EPS: 8/);
});
test('annual QoQ is unavailable; monthly ratios use twelve-month YoY lag',()=>{
 assert.deepEqual(M.transform([{period:'2024-12-31',value:1},{period:'2025-12-31',value:2}],'qoq','USD','annual'),[]);
 const rows=Array.from({length:13},(_,i)=>({period:new Date(Date.UTC(2025,i,1)).toISOString().slice(0,10),value:i+1}));
 assert.equal(M.transform(rows,'yoy','multiple','monthly')[0].value,1200);
});
test('a negative base cannot produce a misleading indexed chart or growth percentage',()=>{
 const p=[{period:'2024-12-31',value:-2},{period:'2025-12-31',value:2}];assert.deepEqual(M.transform(p,'indexed'),[]);assert.deepEqual(M.transform(p,'yoy'),[]);
});
test('beats and misses exclude consensus captured on or after the results date',()=>{
 const d={ticker:'T',series:[{id:'revenue',quarterly:[{period:'2025-12-31',value:110,source,published_at:'2026-02-01'}]}]};
 const e=as_of=>({ticker:'T',metric:'revenue',frequency:'quarterly',kind:'street',period:'2025-12-31',as_of,value:100,source});
 assert.equal(M.beats(d,[e('2026-01-31'),e('2026-02-01'),e('2026-02-02')]).length,1);
 assert.ok(Math.abs(M.beats(d,[e('2026-01-31')])[0].surprise_pct-10)<1e-10);
});
test('source gaps do not pass screens or trigger valuation alerts',()=>{
 assert.equal(M.screen([{ticker:'MISSING',latest:{}},{ticker:'ZERO',latest:{pe:{value:0}}}],[{metric:'pe',op:'lte',value:5}]).length,1);
 assert.deepEqual(M.evaluateAlerts({ticker:'MISSING',series:[]},[{metric:'pe',op:'lte',value:5}]),[]);
});
test('a later restatement cannot make a post-result estimate look like pre-result consensus',()=>{
 const d={ticker:'T',events:[{type:'earnings_release',period:'2025-12-31',date:'2026-02-01'}],series:[{id:'revenue',unit:'USD',annual:[{period:'2025-12-31',value:120,source:{filed:'2027-02-01'}}],annual_as_reported:[{period:'2025-12-31',value:110,source:{filed:'2026-02-01'}}]}]};
 const e={kind:'street',metric:'revenue',frequency:'annual',period:'2025-12-31',as_of:'2026-03-01',value:100,unit:'USD'};
 assert.deepEqual(M.beats(d,[e]),[]);assert.equal(M.beats(d,[{...e,as_of:'2026-01-01'}])[0].actual,110);
 assert.deepEqual(M.beats(d,[{...e,as_of:'2026-01-01',unit:'EUR'}]),[]);
});
test('a filing date alone cannot admit consensus captured after an unverified earnings release',()=>{
 const d={ticker:'T',series:[{id:'revenue',unit:'USD',annual:[{period:'2025-12-31',value:110,source:{filed:'2026-02-10'}}]}]};
 const e={kind:'street',metric:'revenue',frequency:'annual',period:'2025-12-31',as_of:'2026-02-09',value:100,unit:'USD'};
 assert.deepEqual(M.beats(d,[e]),[]);
 assert.equal(M.beats(d,[{...e,as_of:'2025-12-01'}])[0].actual,110);
});
test('CSV preserves quoted commas and multiline source values',()=>{
 assert.deepEqual(UI.parseCSV('ticker,value,source_url\r\nT,12,"https://source.example/a,b"\r\n'),[{ticker:'T',value:'12',source_url:'https://source.example/a,b'}]);
 assert.throws(()=>UI.parseCSV('a\n"unfinished'));
});
test('imports reject unknown types, missing sources and future snapshot dates',()=>{
 const e={ticker:'T',kind:'street',metric:'revenue',frequency:'annual',period:'2027-12-31',as_of:'2026-01-01',value:10,unit:'USD',source};
 assert.equal(UI.validateImport({expectations:[e]},'T','2026-03-01').expectations.length,1);
 for(const edit of [{ticker:'X'},{source:{}},{as_of:'2026-05-01'},{kind:'actual'},{value:null},{source:{url:'javascript:alert(1)'}}])assert.throws(()=>UI.validateImport({expectations:[{...e,...edit}]},'T','2026-03-01'));
});
test('SVG exports carry readable axes, exact accessible values and real negative ranges',()=>{
 const svg=UI.svgChart('Cash & income',[{label:'Cash',frequency:'annual',points:[{period:'2024-12-31',value:-10},{period:'2025-12-31',value:20}]}],'USD');
 assert.match(svg,/Cash &amp; income/);assert.match(svg,/aria-label="Cash, 2024-12-31, -10"/);assert.doesNotMatch(svg,/NaN|Infinity/);
});
test('reverse valuation recovers the actual model driver for every supported company type',()=>{
 const V=global.StockValuation,c={growth:.06,payout:.3,reinvestment:.35,incremental_roic:.18,roe:.14,distribution_yield:.02,target_margin:.15,dilution:.02,exit_multiple:15};
 for(const method of ['owner_cash','earnings','book','nav','transition']){
  const model={ticker:'T',method,blockers:[],inputs:{entry_price:100,entry_date:'2026-11-18',anchor:10,horizon:7,discount_rate:.1},cases:{bear:c,base:c,bull:c}};
  const required=V.calculate(model).cases.base.irr,payout=method==='owner_cash'?1-c.reinvestment:method==='nav'?c.distribution_yield:c.payout;
  const r=M.reverseModel(V,model,{price:100,anchor:10,multiple:15,years:7,payout,required});
  assert.ok(Math.abs(r.value-c[r.key])<1e-8,method+' did not recover '+r.key);
 }
});
test('research retrieval keeps EchoStar evidence and excludes Strive from the SATS archive',async()=>{
 const original=global.fetch;
 const row=(id,cik,date)=>({id,title:'Capital allocation discussion',date,relationship:'direct',is_latest:true,category:'letters',passages:[{text:'Capital allocation and investment returns need careful review.',locator:'Fund letter paragraph'}],source_refs:[{url:'https://www.sec.gov/Archives/edgar/data/'+cik+'/filing'}],locations:[{url:'https://fund.example/'+id}]});
 const assets={'companies/ECHO.json':{pages:['echo-page.json']},'companies/SATS.json':{pages:['archive-page.json']},'echo-page.json':[row('echo','1415404','2026-11-01')],'archive-page.json':[row('legacy-echo','1415404','2026-11-01'),row('strive','1942955','2025-01-01')]};
 global.fetch=async url=>({ok:true,json:async()=>assets[String(url).replace('data/company-research/','')]});
 try{const C=require('../../../dashboard/company-research.js'),result=await C.retrieve('ECHO','capital allocation',{archives:[{ticker:'SATS',cutoff:'2026-10-30',issuer_cik:'1415404',excluded_cik:'1942955'}]});assert.ok(result.some(r=>r.id==='legacy-echo'));assert.ok(!result.some(r=>r.id==='strive'));}finally{global.fetch=original;}
});
