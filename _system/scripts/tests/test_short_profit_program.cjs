const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source=fs.readFileSync('dashboard/short-profit-program.js','utf8');
const context={module:{exports:{}},console,URL,TextEncoder,crypto:require('node:crypto').webcrypto};
context.globalThis=context;vm.createContext(context);vm.runInContext(source,context);
const api=context.module.exports;

test('escapes untrusted filing titles and excerpts',()=>{
  assert.equal(api.esc('<img src=x onerror="run()">'),'&lt;img src=x onerror=&quot;run()&quot;&gt;');
});

test('chart accepts empty and flat research without NaN coordinates',()=>{
  assert.match(api.chart([]),/No observations/);
  const html=api.chart([['Jan',0],['Feb',0]],{label:'flat'});
  assert.ok(!html.includes('NaN'));
  assert.match(html,/aria-label="flat"/);
});

test('Monte Carlo fan has a filled band and accessible label',()=>{
  const html=api.chart([[21,-100,0,200],[42,-200,100,500]],{fan:true,label:'simulation'});
  assert.match(html,/spp-band/);assert.match(html,/role="img"/);
});

test('research data filenames cannot traverse directories',async()=>{
  await assert.rejects(api.checked('../private.json'),/Invalid research file/);
});

test('dataset build mismatch is rejected',async()=>{
  context.fetch=async()=>({ok:true,text:async()=>'{"a":1}'});
  await assert.rejects(api.checked('summary.json','wrong-hash'),/different builds/);
});

test('dashboard mounts the new lab and preserves older comparisons',()=>{
  const html=fs.readFileSync('dashboard/index.html','utf8');
  const reverse=fs.readFileSync('dashboard/reverse-splits-viz.js','utf8');
  assert.match(html,/short-profit-program\.js/);assert.match(html,/short-profit-program\.css/);
  assert.match(reverse,/ShortProfitProgram\.render/);assert.match(reverse,/ShortProfitProgram\.attach/);
  assert.match(reverse,/Earlier reverse-split portfolio and execution studies/);
});

test('public snapshot has complete expected contracts when present',()=>{
  const filename='dashboard/data/short_profit_program/summary.json';
  if(!fs.existsSync(filename))return;
  const doc=JSON.parse(fs.readFileSync(filename,'utf8'));
  assert.equal(doc.schema_version,'short_profit_program.v1');assert.equal(doc.nav,10000000);
  assert.equal(doc.counts.split,1183);assert.equal(doc.counts.deficiency,4720);
  assert.equal(doc.models.length,420);assert.equal(doc.review_panel_size,100);
  for(const m of doc.models){
    assert.ok(Number.isFinite(m.net_pnl));assert.ok(m.unresolved_positions>=0);
    assert.ok(m.observed_broker_fills===0);
    assert.ok(m.modeled_closed<=m.entered);
    assert.equal(m.modeled_closed+m.unresolved_positions,m.entered);
  }
});

test('every published source shard matches its hash, version and denominator',()=>{
  const root='dashboard/data/short_profit_program/';
  if(!fs.existsSync(root+'manifest.json'))return;
  const crypto=require('node:crypto');
  const manifest=JSON.parse(fs.readFileSync(root+'manifest.json','utf8'));
  const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(root+file)).digest('hex');
  assert.equal(hash('summary.json'),manifest.summary_sha256);
  const summary=JSON.parse(fs.readFileSync(root+'summary.json','utf8'));
  let rows=0;
  for(const part of [...manifest.parts,...manifest.files]){
    assert.equal(hash(part.file),part.sha256,part.file);
    const raw=fs.readFileSync(root+part.file,'utf8');
    assert.ok(!raw.includes('C:/Users/')&&!raw.includes('C:\\\\Users\\\\'),part.file+' exposes a local path');
    const d=JSON.parse(raw);
    if(d.dataset_version)assert.equal(d.dataset_version,summary.dataset_version);
    if(d.events){rows+=d.events.length;assert.equal(d.events.length,part.rows);}
  }
  assert.equal(rows,Object.values(summary.counts).reduce((a,b)=>a+b,0));
});
