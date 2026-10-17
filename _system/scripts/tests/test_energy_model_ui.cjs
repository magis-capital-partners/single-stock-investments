/* Run with node; verifies companion failures cannot break the legacy renderer. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const viz = require(path.join(root, 'dashboard/energy-model-viz.js'));
assert.match(viz.render(null, null), /temporarily unavailable/);
assert.match(viz.render({schema_version:'2.0'}, null), /temporarily unavailable/);
const warn = console.warn;
console.warn = () => {};
assert.match(viz.render({schema_version:'1.0',scenarios:[{id:'reference'}]}, null), /temporarily unavailable/);
console.warn = warn;
const file = path.join(root,'dashboard/data/energy_model.json');
if(fs.existsSync(file)) {
  const model = JSON.parse(fs.readFileSync(file,'utf8'));
  const bridge = JSON.parse(fs.readFileSync(path.join(root,'dashboard/data/energy_btc_bridge.json'),'utf8'));
  assert.match(viz.render(model,bridge), /Apply energy to BTC comparison/);
  assert.match(viz.render(model,{...bridge,model_id:'different'}), /cost overlay is disabled/);
  assert.match(viz.render(model,null), /optional BTC energy overlay is unavailable/);
  assert.match(viz.render(model,bridge,{status:'failed',error:'EIA temporarily unavailable'}), /last energy refresh failed/);
  const escaped = structuredClone(model);
  escaped.scenarios[0].label = '<img src=x onerror=alert(1)>';
  const html=viz.render(escaped,bridge);
  assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;img'));
}
console.log('Energy UI: missing, malformed, mismatched and escaped-source cases passed');
