import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const root=new URL('../',import.meta.url);
function load(name){const c={window:{},Intl,Map,Set,Date,console};vm.createContext(c);vm.runInContext(fs.readFileSync(new URL(name,root),'utf8'),c);return c.window;}
test('newer static observations replace a successful but stale API response',()=>{
 const api=load('market-risk-data.js').MarketRiskData;
 const row={component:'vix_regime',symbol:'VIX',scope:'market',quality_state:'ready'};
 const merged=api.merge({components:[{...row,as_of:'2026-10-20',value:15}]},{},{components:[{...row,as_of:'2026-10-21',value:20}]});
 assert.equal(merged.components[0].value,20);assert.equal(merged.components[0].delivery_origin,'committed');
});
test('source status is ordered by exceptions and escapes unsafe names',()=>{
 const api=load('workspace-tools.js').WorkspaceTools;
 const d={surfaces:[{id:'ok',label:'Ready',status:'fresh',stamp:'2026-10-23T01:00:00Z',max_age_hours:48},{id:'bad',label:'<script>',status:'missing',exists:false}]};
 assert.equal(api.sourceRows(d,{},Date.parse('2026-10-23T02:00:00Z'))[0].id,'bad');
 assert.doesNotMatch(api.renderStatus(d,{}),/<script>/);
});
test('aggregates nulls sort last and never pass value or leverage thresholds',()=>{
 const api=load('aggregates-viz.js').AggregatesViz;
 const rows=[{ticker:'NULL',company:'Missing',peer_group:'aggregates_focused',financial_status:'unverified_legacy'},{ticker:'VALUE',company:'Known',peer_group:'aggregates_focused',financial_status:'verified',ev_ebitda:8,fcf_yield_pct:5,net_debt_ebitda:1}];
 for(const direction of ['asc','desc']){const s={...api.DEFAULT,sort:'ev',direction};assert.equal(api.filterRows(rows,s)[0].ticker,'VALUE');}
 assert.deepEqual([...api.filterRows(rows,{...api.DEFAULT,preset:'value'})].map(r=>r.ticker),['VALUE']);
});
test('pure aggregates and integrated construction groups remain distinct',()=>{
 const api=load('aggregates-viz.js').AggregatesViz;
 const rows=[{ticker:'VMC',company:'Rock',peer_group:'aggregates_focused'},{ticker:'GVA',company:'Contractor',peer_group:'contractors_asphalt'}];
 assert.equal(api.filterRows(rows,{...api.DEFAULT}).length,1);
 assert.equal(api.filterRows(rows,{...api.DEFAULT,peer:'all'}).length,2);
});
test('dashboard inline scripts compile after navigation and screen integration',()=>{
 const html=fs.readFileSync(new URL('index.html',root),'utf8');let count=0;
 for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)){if(/\bsrc=/.test(m[1]))continue;new vm.Script(m[2]);count++;}
 assert.ok(count>0);assert.match(html,/#\/data-status/);assert.match(html,/#\/insights\/investors\/signals/);
});
