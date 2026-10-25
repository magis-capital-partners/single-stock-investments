'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const P=require('./build_third_plus_dashboard.cjs'),V=require('../../dashboard/third-plus-study.js');
const ROOT=path.resolve(__dirname,'../..'),doc=P.build();
test('publication preserves cohort counts and the frozen benchmark results',()=>{
 assert.equal(doc.cohort.events,210);assert.equal(doc.cohort.saved_events+doc.cohort.vetoed+doc.cohort.unknown_rally,210);
 assert.equal(doc.models.primary.saved.net_pnl,7385.199847977776);assert.equal(doc.models.primary.dilution.net_pnl,7997.102773533332);
});
test('every rule has the nine declared cases without fabricating a cross-product',()=>{
 assert.equal(doc.rules.length,21);assert.equal(doc.cases.length,9);
 for(const c of doc.cases)for(const r of doc.rules)assert.ok(doc.models[c.id][r.id]);
 assert.equal(doc.models.full_20.saved.nav,null);assert.equal(doc.models.primary.saved.nav,1000000);
});
test('all monthly totals and admission funnels reconcile to model accounting',()=>{
 for(const byRule of Object.values(doc.models))for(const m of Object.values(byRule)){
 assert.ok(Math.abs(m.monthly.reduce((n,p)=>n+p[1],0)-m.net_pnl)<.01);
 assert.ok(Math.abs(m.gross_pnl-m.execution_cost-m.borrow_cost-m.commissions_and_fees-m.net_pnl)<.01);
 const excluded=Object.entries(m.funnel).filter(([k])=>!['selected','entered'].includes(k)).reduce((n,[,v])=>n+v,0);assert.equal(excluded+m.entered,m.funnel.selected);
 }
});
test('publication contains aggregate results without trade or per-event price records',()=>{
 assert.equal(doc.production_authority,'none');assert.equal(doc.verified_entries,0);assert.equal(doc.models.primary.saved.positions,undefined);assert.equal(doc.models.primary.saved.daily,undefined);
 assert.ok(Object.keys(doc.source_hashes).every(k=>!k.includes('/local/')));
});
test('unknown sizes and missing metrics never render as zero dollars',()=>{assert.equal(V.money(null),'Unavailable');assert.equal(V.money(undefined),'Unavailable');assert.equal(V.money(0),'$0');});
test('primary and hypothetical scenarios state their different sizing assumptions',()=>{
 const primary=V.view(doc,{rule:'dilution',case:'primary',all:false}),full=V.view(doc,{rule:'dilution',case:'full_20',all:false});
 assert.match(primary,/Conditional historical replay/);assert.match(primary,/not a verified fill/);assert.match(full,/Hypothetical execution sensitivity/);assert.match(full,/No account or volume cap/);
});
test('study text and labels are escaped before reaching markup',()=>{
 const altered=JSON.parse(JSON.stringify(doc));altered.rules.find(r=>r.id==='dilution').label='<img src=x onerror=alert(1)>';
 const view=V.view(altered,{rule:'dilution',case:'primary',all:false});assert.ok(!view.includes('<img src=x'));assert.ok(view.includes('&lt;img'));
});
test('missing comparisons are rejected instead of being displayed as flat zero profits',()=>{
 const altered=JSON.parse(JSON.stringify(doc));delete altered.models.h10.dilution;assert.throws(()=>V.validate(altered),/comparison is missing/);
});
function replies(data,changeManifest={},body=JSON.stringify(data)){
 const manifest={schema:'third_plus_dashboard_manifest.v1',payload:'third_plus_study.json',sha256:crypto.createHash('sha256').update(body).digest('hex'),data_version:data.data_version,...changeManifest};
 return async url=>url.includes('manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>body};
}
test('loader verifies exact publication bytes and rejects a changed payload',async()=>{
 assert.equal((await V.load(replies(doc),crypto.webcrypto)).data_version,doc.data_version);
 await assert.rejects(()=>V.load(replies(doc,{sha256:'0'.repeat(64)}),crypto.webcrypto),/different publications/);
});
test('loader rejects a validly hashed payload with a mismatched study version',async()=>{
 await assert.rejects(()=>V.load(replies(doc,{data_version:'1'.repeat(64)}),crypto.webcrypto),/Mixed study versions/);
});
test('primary evidence remains distinguished from code checks and live readiness',()=>{
 const html=V.view(doc,{rule:'dilution',case:'h10',all:false});
 assert.match(html,/20-session reference case/);assert.match(html,/No validated added filter/);assert.match(html,/verified-execution entries/);assert.match(html,/primary issuer-based 95% interval/);
});
test('published dashboard bytes are reproducible from the committed study sources',()=>{P.publish(true);});
