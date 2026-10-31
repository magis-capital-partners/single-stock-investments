'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../../..');
function harness(files){
 const c={window:{},Date,Intl,Map,Set,URLSearchParams,fetch:async url=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(root,'dashboard',url),'utf8'))})};
 vm.createContext(c);for(const f of files)vm.runInContext(fs.readFileSync(path.join(root,'dashboard',f),'utf8'),c);return c.window;
}
test('compounders retain every member, respect withholding and valid quote expiry',async()=>{
 const w=harness(['valuation-viz.js','compounders.js']);await w.Compounders.load();
 const base={ticker:'MA',valuation_decision:{research_return_available:true,calculation_status:'complete',price_per_share:100,market_sync:{status:'verified',valid_until:'2099-01-01'},forward_return_at_price_pct:{base:15}},shared_forecast:{status:'available',buy_prices:[{hurdle_pct:12,prices:{base:110}}]}};
  let rows=w.Compounders.rows([base]);assert.equal(rows.length,46);assert.equal(rows.find(r=>r.ticker==='MA').status,'entry_zone');
  assert.ok(rows.some(r=>r.ticker==='PBT'&&r.name==='Permian Basin Royalty Trust'));assert.ok(rows.some(r=>r.ticker==='LB'&&r.name==='LandBridge'));assert.ok(rows.some(r=>r.ticker==='HEI'));
 base.valuation_decision.market_sync.valid_until='2020-01-01';rows=w.Compounders.rows([base]);assert.equal(rows[0].target,null);assert.equal(rows[0].irr,null);
 base.valuation_decision.research_return_available=false;base.valuation_decision.market_sync.valid_until='2099-01-01';assert.equal(w.Compounders.rows([base])[0].status,'needs_evidence');
});
test('company-specific registry only attaches respiratory demand to QDEL',()=>{
 const w=harness(['company-models.js']);assert.equal(w.CompanyModels.relevant('QDEL').length,1);assert.equal(w.CompanyModels.relevant('CME').length,0);assert.equal(w.CompanyModels.relevant('NEM').length,0);
});
test('legacy GLD values are withheld without altering a different security',()=>{
 const w=harness(['commodity-model-viz.js']);const clean=w.CommodityModelViz.cleanLegacyGold({items:[{source:'theme:gold_spot_usd',actual:366,history:{points:[1,2]}},{ticker:'GLD',value:366}],series:{'theme:gold_spot_usd':{value:366}}});
 assert.equal(clean.items[0].actual,null);assert.equal(clean.items[0].history,null);assert.equal(clean.items[1].value,366);assert.equal(clean.series['theme:gold_spot_usd'],null);
});
test('commodity UI labels assumptions, dependencies and missing inputs',()=>{
 const w=harness(['commodity-model-viz.js']);const d=JSON.parse(fs.readFileSync(path.join(root,'dashboard/data/commodity_models.json'),'utf8'));
 const html=w.CommodityModelViz.render(d);assert.equal((html.match(/data-commodity="/g)||[]).length,4);assert.match(html,/excluded from base IRR/);assert.match(html,/Concentrate|concentrate/);assert.match(html,/Unavailable/);assert.match(html,/source audit/i);
 d.models[0].title='<script>alert(1)</script>';assert.doesNotMatch(w.CommodityModelViz.render(d),/<script>/);
});
test('forced flows separate ended windows and headlines from dated situations',()=>{
 const w=harness(['special-situations-viz.js']);
 const row={lane:'forced_sellers',evidence_kind:'filing',status:'open'};
 const html=w.SpecialSituationsViz.render({rows:[{...row,ticker:'ENDED',ends:'2013-07-11'},{...row,ticker:'FUTURE',ends:'2099-01-01'},{...row,ticker:'UNKNOWN'},{...row,ticker:'HEADLINE',evidence_kind:'news',ends:'2099-01-01'}],lanes:[{id:'forced_sellers'}]},{lane:'forced_sellers'});
 assert.match(html,/1 ranked/);assert.match(html,/Show 1 ended situation/);assert.doesNotMatch(html,/>ENDED</);assert.match(html,/Unverified candidates · 2/);
});
