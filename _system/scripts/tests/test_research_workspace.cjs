const assert = require('node:assert/strict');
const {test} = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname,'../../..');
const context = vm.createContext({Intl,Map,Set,URLSearchParams,module:{exports:{}}});
for(const file of ['valuation-viz.js','research-workspace.js']) vm.runInContext(fs.readFileSync(path.join(root,'dashboard',file),'utf8'),context);
const rw = context.ResearchWorkspace;
const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const h = {escapeHtml,quoteUnitsOf:()=>({}),fmtQuote:n=>n==null?'—':`EUR ${n}`,linkHtml:(url,label)=>`<a href="${escapeHtml(url)}">${escapeHtml(label)}</a>`};
const metric = {...{metric:'revenue',label:'Revenue',display:true,tier:'primary',latest_period:'2026-06-30',level_latest:25,growth_latest:.25,basis:'yoy',points:[{period:'2025-06-30',value:20},{period:'2026-06-30',value:25}]}};
test('null, blank and non-finite observations never become zero',()=>{
 for(const value of [null,undefined,'',false,true,NaN,Infinity,'bad',[],{}]) assert.equal(rw.number(value),null);
 assert.equal(rw.number(0),0);
 assert.equal(rw.number(-2),-2);
});
test('current charts respect upstream signal exclusions and do not mutate data',()=>{
 const metrics=[metric,{...metric,display:false},{...metric,artifact:true},{...metric,stale:true},{...metric,tier:'excluded'}];
 const original=JSON.stringify(metrics);
 assert.equal(rw.metrics({kpi_trends:{metrics}}).length,1);
 assert.equal(JSON.stringify(metrics),original);
});
test('current observations retain period, unit and source without inventing a trend',()=>{
 const html=rw.kpis({compounder_monitor:{kpi_coverage:[{kpi_id:'adv',status:'current',value:0,unit:'contracts_per_day',period:'2026-09',source:{ref:'https://example.com/source'}}]}},h,3);
 assert.match(html,/2026-09/); assert.match(html,/contracts per day/); assert.match(html,/trend unavailable/); assert.match(html,/https:\/\/example.com\/source/); assert.doesNotMatch(html,/<svg/);
});
test('historical series are explicitly separated from current signals',()=>{
 const t={kpi_trends:{metrics:[{...metric,display:false,stale:true}]}};
 assert.match(rw.kpis(t,h),/No current/);
 assert.match(rw.kpis(t,h,Infinity,true),/Historical series · not a current signal/);
 assert.match(rw.kpis(t,h,Infinity,true),/stale/);
});
test('a present value never becomes a forward-return figure',()=>{
 const t={valuation_decision:{output_basis:'present_value_today',return_publishable:false,value_per_share:{low:70,base:100,high:150},price_per_share:80,annualized_return_at_price_pct:{base:42},forward_return_reason:'Dated cash flows required'}};
 const html=rw.range(t,h); assert.match(html,/Forward return/); assert.match(html,/Unavailable/); assert.doesNotMatch(html,/42%/); assert.match(html,/Price date missing/);
});
test('blocked thresholds stay withheld while a valid research diagnostic stays labelled',()=>{
 const t={valuation_decision:{return_publishable:false},pricing_analysis:{buy_zones:{status:'blocked',zones:[{label:'Never publish',price:50}]}},compounder_monitor:{tci_return_bridge:{horizon_years:7,model_as_of:'2026-06-30',scenarios:{bear:{exact_irr_pct:-5},base:{exact_irr_pct:0},bull:{exact_irr_pct:12}}}}};
 assert.doesNotMatch(rw.range(t,h),/Never publish/);
 const html=rw.scenarios(t,h); assert.match(html,/research only; capital action blocked/); assert.match(html,/-5%/);assert.match(html,/0%/);assert.match(html,/7-year horizon/);
});
test('a quote outside the valuation range is included in the ruler domain',()=>{
 const t={valuation_decision:{price_per_share:300,present_value_today_per_share:{low:50,base:100,high:150},return_publishable:false}};
 const html=rw.range(t,h);assert.match(html,/EUR 300/);assert.match(html,/rw-ruler-price" style="left:95%/);
});
test('missing model and sparse research produce useful next steps',()=>{
 const html=rw.overview({ticker:'TST'}, {...h,developments:[]}); assert.match(html,/primary evidence/);assert.match(html,/No dated developments/);assert.doesNotMatch(html,/NaN|undefined/);
});
test('legacy buyback routes resolve to the business view and unknown tabs to overview',()=>{
 assert.equal(rw.validTab('buyback'),'business'); assert.equal(rw.validTab('evidence'),'evidence');assert.equal(rw.validTab('bad'),'overview');
});
test('labels and source references are escaped',()=>{
 const html=rw.kpis({kpi_trends:{metrics:[{...metric,label:'<script>bad</script>',evidence_ref:'reports/test "file".json'}]}},h);
 assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);assert.match(html,/%22file%22/);
});

test('technical review instructions get a readable overview label',()=>{
 assert.equal(rw.friendlyAction('Complete the next hash-bound isolated outputs: pre_mortem.json'), 'Complete the independent review documents.');
 assert.equal(rw.friendlyAction('Replace stale or unbound outputs against the frozen packet'), 'Update the independent review with the latest evidence.');
});
