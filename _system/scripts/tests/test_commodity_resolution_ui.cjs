const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
function harness(){
  const context={window:{},Intl,Date};vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'dashboard/commodity-resolution.js'),'utf8'),context);
  return context.window.CommodityResolution;
}
test('resolution view exposes dated source lineage, five views and the valuation boundary',()=>{
  const api=harness(),doc=JSON.parse(fs.readFileSync(path.join(root,'dashboard/data/commodity_models.json'),'utf8')).resolution;
  const html=api.render(doc);
  for(const label of ['What changed','Where tight','Scenarios','Company exposure','Falsifiers','Served model','excluded from base IRR'])assert.ok(html.includes(label),label);
  const bad=structuredClone(doc);bad.sources[0].id='<script>unsafe</script>';bad.sources[0].url='javascript:alert(1)';
  const safe=api.render(bad);assert.ok(!safe.includes('<script>'));assert.ok(!safe.includes('href="javascript:'));
  assert.match(api.renderCompany(doc,'SJT'),/Remaining gross deficit/);
  assert.match(api.renderCompany(doc,'WPM'),/FCF/);
  const hours=api.powerProfiles(doc);assert.ok(hours.length>=672&&hours.length<=745);
  assert.ok(hours.every(r=>r.metric==='native_hourly_load'&&r.weight_hours===1));
  assert.equal(api.renderCompany(doc,'UNKNOWN'),'');
});
test('hourly power response reconciles scarcity, weights and the fixed contract share',()=>{
  const api=harness(),params={nonGas:30,gasMW:50,gas:3,heat:7,variable:2,scarcity:1000,fixed:.8,contract:50};
  const result=api.powerCase([{value:100,weight_hours:24}],params);
  assert.equal(result.unserved,480);assert.equal(result.hours,24);assert.ok(Math.abs(result.price-240)<1e-8);
  assert.throws(()=>api.powerCase([],{...params,fixed:1.1}));
  assert.equal(api.powerCase([],params).price,null);
  const peaks=api.powerCase([{value:50,weight_hours:1},{value:150,weight_hours:1}],{...params,nonGas:100,gasMW:0,fixed:0});
  assert.equal(peaks.unserved,50);assert.equal(peaks.price,500);
});
