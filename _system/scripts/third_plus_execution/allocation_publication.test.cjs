'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const V=require('../../../dashboard/third-plus-allocation.js'),A=require('./allocation.cjs'),Study=require('./allocation_study.cjs'),d=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../dashboard/data/third_plus_allocation.json')));
test('every registered policy has all scenarios, capacities and budget regimes',()=>{
 V.validate(d);assert.deepEqual(d.protocol.policies,A.registry());assert.equal(d.protocol.policies.length,38);assert.equal(new Set(d.models.map(m=>m.id)).size,456);
 for(const m of d.models){assert.ok(m.summary.selected+m.summary.outside_signal===210);assert.ok(m.summary.entered<=m.summary.attempted);assert.equal(m.robustness.issuer_leaveout_count,d.cohort_issuers);assert.ok(m.robustness.issuer_leaveout_min<=m.robustness.issuer_leaveout_median);assert.ok(m.robustness.issuer_leaveout_median<=m.robustness.issuer_leaveout_max);assert.ok(Number.isFinite(m.robustness.reallocated_without_best5_issuers));}
});
test('all original numerical controls reproduce and every marked cash path reconciles',()=>{
 assert.equal(d.replications.length,36);assert.ok(d.replications.every(x=>x.passed));
 for(const m of [...d.models,...d.walk_forward])assert.ok(Math.abs(m.summary.monthly.reduce((a,x)=>a+x[1],0)-m.summary.net_pnl)<.01);
 for(const wf of d.walk_forward)assert.ok(Math.abs(wf.yearly.reduce((a,y)=>a+y.net_pnl,0)-wf.summary.net_pnl)<.01);
});
test('chronological selections enforce prior completed issuer minimums and fixed annual choices',()=>{
 for(const wf of d.walk_forward){assert.deepEqual(wf.folds.map(f=>f.year),[2024,2025,2026]);assert.equal(wf.folds[0].fallback,true);assert.equal(wf.decisions.length,210);assert.equal(new Set(wf.decisions.map(x=>x.id)).size,210);
  for(const f of wf.folds){assert.equal(f.cutoff,f.year+'-01-01');if(f.fallback)assert.equal(f.selected,'burn_100');else{assert.equal(f.selected,f.ranking[0].id);assert.ok(f.ranking[0].issuers>=20);assert.ok(f.ranking[0].base_pnl>0&&f.ranking[0].stress_pnl>0);}}
  for(const a of wf.decisions){assert.ok(a.target_usd>=0&&a.target_usd<=100000);assert.equal(a.target_usd%100,0);if(a.entry_day){const year=Number(a.entry_day.slice(0,4));assert.equal(a.policy,wf.folds.find(f=>f.year===year)?.selected||'burn_100');}}
 }
});
test('adaptive strongest-issuer removals retrain rather than subtracting individual trade profits',()=>{
 for(const wf of d.walk_forward.filter(w=>w.scenario==='base')){assert.deepEqual(wf.robustness.map(x=>x.issuers_removed),[1,5]);assert.ok(wf.robustness.every(x=>x.folds.length===3&&Number.isFinite(x.net_pnl)));}
});
test('public experiment contains only aggregated returns and derived allocation decisions',()=>{
 const banned=new Set(['bars','quotes','quantity','filled_shares','trade_id','file','ts_ms','available_ms','mark','factor']);
 const visit=x=>{if(!x||typeof x!=='object')return;for(const [k,v]of Object.entries(x)){assert.ok(!banned.has(k),'Raw market field '+k);visit(v);}};visit(d);assert.ok(!JSON.stringify(d).includes('C:/Users/'));assert.ok(/^[a-f0-9]{64}$/.test(d.input_receipts.daily_ohlcv_database_sha256));assert.equal(d.validated_improvement,false);
});
test('dashboard distinguishes historical leaders from chronological selection and controls change results',()=>{
 const s={scenario:'base',capacity:'three',budget:'matched'},html=V.view(d,s);assert.match(html,/Historical profit leader/);assert.match(html,/Chronological selection/);assert.match(html,/Unknown overlays receive no bonus/);assert.match(html,/24-session/);assert.equal(V.selected(d,s).length,38);
 assert.notEqual(V.view(d,{...s,scenario:'stress'}),html);const c=structuredClone(d);c.protocol.policies[0].label='<script>bad</script>';assert.ok(!V.view(c,s).includes('<script>bad'));
 const index=fs.readFileSync(path.resolve(__dirname,'../../../dashboard/index.html'),'utf8');assert.doesNotMatch(index,/<script src="third-plus-(?:allocation|study)\.js/);assert.match(index,/reverse-split-research\.js/);
});
test('publication hashes and complete report reproduce without private caches or network',()=>{Study.check();require('./allocation_publish.cjs').publish(true);});
test('the browser loader rejects mixed publications and accepts correctly bound bytes',async()=>{
 const body=JSON.stringify(d),manifest={schema:'third_plus_allocation_manifest.v1',payload:'third_plus_allocation.json',sha256:crypto.createHash('sha256').update(body).digest('hex'),data_version:d.data_version},fetcher=async url=>url.includes('manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>body};
 assert.equal((await V.load(fetcher,crypto.webcrypto)).data_version,d.data_version);manifest.sha256='0'.repeat(64);await assert.rejects(()=>V.load(fetcher,crypto.webcrypto),/Mixed/);
});
