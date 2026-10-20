const test=require('node:test');
const assert=require('node:assert/strict');
const {monteCarlo,quantile}=require('../../../dashboard/short-sleeve-engine.js');

test('quantiles preserve zero and exclude unavailable ratios',()=>{
  assert.equal(quantile([null,0,1,2],.5),1);
  assert.equal(quantile([null],.5),null);
});
test('zero activity stays flat with missing Calmar rather than infinity',()=>{
  const r=monteCarlo(['2024-01-02','2024-02-01'],[{scenario:'base',series:[]}],20,1,7).base;
  assert.equal(r.ending.p50,1);assert.equal(r.cagr.p50,0);assert.equal(r.max_drawdown.p95,0);assert.equal(r.calmar.p50,null);
});
test('repeated identical seed is deterministic and cost cases share the sampled months',()=>{
  const days=['2024-01-02','2024-01-03','2024-02-01','2024-02-02'];
  const models=[{scenario:'bull',series:[[0,.001,.01,.011],[2,-.0005,.02,.022]]},{scenario:'bear',series:[[0,.0005,.01,.011],[2,-.001,.02,.022]]}];
  const a=monteCarlo(days,models,40,1,42),b=monteCarlo(days,models,40,1,42);
  assert.deepEqual(a,b);assert.ok(a.bear.ending.p50<a.bull.ending.p50);assert.ok(a.bear.max_drawdown.p95>=a.bull.max_drawdown.p95);
});
test('a first-day loss enters maximum drawdown and insolvency is retained',()=>{
  const r=monteCarlo(['2024-01-02'],[{scenario:'bear',series:[[0,-1.2,2,2.1]]}],5,1,42).bear;
  assert.equal(r.ruin_probability,1);assert.equal(r.cagr.p50,null);assert.ok(r.max_drawdown.p50>=1.2);
});
test('insolvent growth paths retain their percentile rank rather than being dropped',()=>{
  const r=monteCarlo(['2024-01-02','2024-02-01'],[{scenario:'base',series:[[0,-1.2,2,2.1],[1,.01,.01,.011]]}],100,1/252,42).base;
  assert.ok(r.ruin_probability>.1&&r.ruin_probability<.9);
  assert.equal(r.cagr.p05,null);
});
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('cached selection cannot be overwritten by a previous simulation or error',()=>{
  const workers=[],controls=new Map(),status={setAttribute(){},textContent:null};
  const host={isConnected:true,innerHTML:'',querySelector:selector=>selector==='.ss-mc-summary'?status:null,
    querySelectorAll(selector){
      if(selector!=='[data-ss-control]')return [];
      return ['nav','bps','horizon','capacity'].map(key=>{
        const el={dataset:{ssControl:key},value:'',addEventListener(_,fn){this.change=fn;}};
        controls.set(key,el);return el;
      });
    }};
  const sandbox={window:{},sessionStorage:{getItem:()=>null,setItem:()=>{}},
    Worker:class{constructor(){workers.push(this);}postMessage(data){this.input=data;}terminate(){}},setTimeout};
  const source=fs.readFileSync(path.join(__dirname,'../../../dashboard/short-sleeve-viz.js'),'utf8');
  vm.runInNewContext(source,sandbox);
  const doc=JSON.parse(fs.readFileSync(path.join(__dirname,'../../../dashboard/data/short_sleeve.json'),'utf8'));
  doc.execution_audit=JSON.parse(fs.readFileSync(path.join(__dirname,'../../../dashboard/data/short_execution_audit.json'),'utf8'));
  sandbox.window.ShortSleeveViz.mount(host,doc);
  assert.match(host.innerHTML,/Latest execution audit/);
  assert.match(host.innerHTML,/126 \/ 282/);
  assert.match(host.innerHTML,/not validated by this audit/);
  assert.match(host.innerHTML,/Databento access verified/);
  assert.match(host.innerHTML,/New downloads are capped at \$0/);
  assert.doesNotMatch(host.innerHTML,/none is configured/);
  const results=Object.fromEntries(['bear','base','bull'].map(id=>[id,{trials:10,cagr:{p50:.01},
    max_drawdown:{p95:.02},loss_probability:.1,ruin_probability:0,
    peak_margin:{p95:.01},peak_collateral:{p95:.011},fan:[]} ]));
  workers[0].onmessage({data:{results}});
  const first=host.innerHTML;
  const select=value=>{const el=controls.get('horizon');el.value=value;el.change();};
  select('2');assert.equal(workers.length,2);
  select('1');assert.equal(host.innerHTML,first);
  const other=structuredClone(results);other.base.cagr.p50=.99;
  workers[1].onmessage({data:{results:other}});
  assert.equal(host.innerHTML,first,'stale results changed a cached selection');
  workers[1].onmessage({data:{error:'previous scenario failed'}});
  assert.equal(status.textContent,null,'stale error changed a cached selection');
});
