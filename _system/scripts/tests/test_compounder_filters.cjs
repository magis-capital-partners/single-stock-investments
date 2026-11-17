'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const read = file => fs.readFileSync(path.join(root,file),'utf8');
const serial = JSON.parse(read('dashboard/data/serial_acquirers.json'));

async function harness() {
  const context = {window:{}, navigator:{languages:['en-US']}, Date, Intl, Map, Set, URLSearchParams,
    fetch:async url=>({ok:true,json:async()=>JSON.parse(read('dashboard/'+url))})};
  vm.createContext(context);
  for (const name of ['ui-format.js','valuation-viz.js','compounders.js']) vm.runInContext(read('dashboard/'+name),context);
  await context.window.Compounders.load();
  return context.window.Compounders;
}

test('both universes reach coverage without replacing existing research or publishing invented returns', async()=>{
  const c = await harness();
  const prior = {ticker:'CSU', company:'Original', valuation_decision:{return_publishable:false}, owned:{role:'long'}};
  const coverage = [prior]; c.mergeCoverage(coverage); c.mergeCoverage(coverage);
  assert.equal(coverage[0],prior);
  assert.equal(new Set(coverage.map(r=>r.ticker)).size,coverage.length);
  assert.equal(c.rows(coverage,'serial-acquirers',true).length,141);
  assert.equal(c.rows(coverage,'compounders',true).length,46);
  for (const r of coverage.slice(1)) {
    assert.equal(r.valuation_decision.return_publishable,false);
    assert.equal(r.valuation_decision.model_level,'unmodeled');
    assert.equal(r.owned,undefined);
  }
  assert.equal(c.member('TOI'),undefined);
  assert.equal(c.member('BG'),undefined);
  assert.equal(c.member('CMG'),undefined);
});

test('global market and search results intersect the selected universe',async()=>{
  const c = await harness(), coverage=[]; c.mergeCoverage(coverage);
  const swedish = coverage.filter(r=>r.market==='SE');
  const rows = c.rows(swedish,'serial-acquirers',true);
  assert.equal(rows.length,serial.companies.filter(r=>r.market==='SE').length);
  assert.ok(rows.every(r=>r.record.market==='SE'));
  assert.equal(c.rows(coverage.filter(r=>r.ticker==='TOI'),'serial-acquirers',true).length,0);
  assert.deepEqual(Array.from(c.rows(coverage.filter(r=>r.company.includes('Sunbelt')),'serial-acquirers',true),r=>r.ticker),['SUNB']);
});

test('the two views retain separate group controls and correct company routes',async()=>{
  const c = await harness(), coverage=[]; c.mergeCoverage(coverage);
  const events={};
  const host={isConnected:true,hidden:false,dataset:{},innerHTML:'',querySelector:selector=>({addEventListener:(_event,fn)=>{events[selector]=fn;}})};
  await c.mount(host,coverage,null,'serial-acquirers');
  assert.match(host.innerHTML,/Serial acquirers/);
  events['[data-comp-group]']({target:{value:'banks'}});
  assert.match(host.innerHTML,/14 of 141 companies/);
  assert.match(host.innerHTML,/#\/research\/serial-acquirers\/FCNCA/);
  await c.mount(host,coverage,null,'compounders');
  assert.match(host.innerHTML,/Quality compounders/);
  assert.match(host.innerHTML,/46 of 46 companies/);
  assert.match(host.innerHTML,/#\/research\/compounders\/MA/);
  await c.mount(host,coverage,null,'serial-acquirers');
  assert.match(host.innerHTML,/14 of 141 companies/);
  c.reset(); await c.mount(host,coverage,null,'serial-acquirers');
  assert.match(host.innerHTML,/141 of 141 companies/);
});

test('toolbar filters combine, toggle off and clear together',()=>{
  const html=read('dashboard/index.html');
  const code=html.slice(html.indexOf('function onFilterClick(btn) {'),html.indexOf('\nfunction renderOwnedFilter()'));
  const ctx={marketFilter:'SE',sleeveFilter:'ALL',valuationFilter:'ALL',fearFilter:'ALL',
    researchScope:'coverage',needsWork:false,ownedOnly:false, search:{value:'Lifco'},
    document:{getElementById:()=>ctx.search},window:{Compounders:{reset(){}}},
    renderMarketFilters(){},renderSleeveFilters(){},renderValuationFilters(){},renderTechnicalFilters(){},
    renderOwnedFilter(){},clearTickerSelection(){},syncHoldingsQuery(){},setAppHash(hash){ctx.hash=hash;}};
  vm.createContext(ctx);vm.runInContext(code,ctx);
  ctx.onFilterClick({dataset:{universe:'serial-acquirers'}});
  ctx.onFilterClick({dataset:{valuationFilter:'evidence-blocked'}});
  ctx.onFilterClick({dataset:{filter:'owned'}});
  assert.equal(ctx.marketFilter,'SE');assert.equal(ctx.researchScope,'serial-acquirers');
  assert.equal(ctx.valuationFilter,'evidence-blocked');assert.equal(ctx.ownedOnly,true);
  ctx.onFilterClick({dataset:{filter:'owned'}});assert.equal(ctx.ownedOnly,false);
  ctx.onFilterClick({dataset:{filter:'reset'}});
  assert.equal(ctx.marketFilter,'ALL');assert.equal(ctx.researchScope,'coverage');
  assert.equal(ctx.valuationFilter,'ALL');assert.equal(ctx.search.value,'');
  assert.equal(ctx.hash,'#/research/coverage');
  assert.doesNotMatch(html,/id="compounder-entry"|class="view-tab compounder-tab"/);
});

test('lazy company details refresh the filtered view after core objects are replaced',async()=>{
  const c=await harness();
  const coverage=[{ticker:'MA',detail_shard:'data/tickers/MA.json'}];
  const host={isConnected:true,hidden:false,dataset:{},innerHTML:'',querySelector:()=>({addEventListener(){}})};
  await c.mount(host,()=>coverage,async ticker=>{
    coverage[0]={ticker,__detail:true,units:{currency:'USD'},
      valuation_decision:{research_return_available:true,calculation_status:'complete',price_per_share:100,
        market_sync:{status:'verified',valid_until:'2099-01-01'},forward_return_at_price_pct:{base:15}},
      shared_forecast:{status:'available',buy_prices:[{hurdle_pct:12,prices:{base:110}}]}};
  },'compounders');
  assert.match(host.innerHTML,/class="desk-status entry_zone"/);
});
