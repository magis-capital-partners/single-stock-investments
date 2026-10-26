'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const Pub=require('./publish.cjs'),Study=require('./study.cjs'),Archive=require('./archive.cjs'),V=require('../../../dashboard/third-plus-execution.js');
const doc=Pub.load();
test('all 21 signals have complete 96-definition matrices and coherent evidence counts',()=>{
 assert.equal(doc.validation.model_definitions,2016);
 for(const r of Object.values(doc.rules))for(const m of r.models){assert.equal(m.data_ready+m.missing_entry_evidence,m.selected);if(m.status==='not_estimable'){assert.equal(m.summary,null);assert.equal(m.comparison,null);}}
 assert.equal(doc.rules.dilution.selected,170);assert.equal(doc.cache_audit.groups.original_ssr_skips.events,100);
});
test('every original decision remains accounted for and signal failures are distinguished from missing execution',()=>{
 for(const r of Object.values(doc.rules)){assert.equal(r.candidate_decisions.length,210);assert.equal(r.candidate_decisions.filter(e=>!e.status.startsWith('signal_')).length,r.selected);}
 const x=doc.rules.dilution.candidate_decisions;assert.equal(x.filter(e=>e.status==='execution_data_missing').length,170);assert.equal(x.filter(e=>e.status==='signal_fail').length,33);assert.equal(x.filter(e=>e.status==='signal_unknown').length,7);
});
test('matrix changes only declared dimensions, with twelve primary comparisons and four matched controls',()=>{
 const grid=Study.grid(Study.protocol()),p=grid.filter(g=>g.latency_ms===500&&g.borrow_mode==='conditional');
 assert.equal(grid.length,96);assert.equal(p.filter(g=>g.policy!=='E0').length,12);assert.equal(p.filter(g=>g.policy==='E0').length,4);
 assert.ok(grid.every(g=>g.participation<=.1&&[30,60].includes(g.minutes)));
});
test('cache audit distinguishes indexed, sampled, qualified and borrow evidence',()=>{
 assert.equal(doc.cache_audit.groups.population.prepared_files,67);assert.equal(doc.cache_audit.groups.population.complete_sampled_60m,63);
 assert.equal(doc.cache_audit.groups.selected.prepared_files,57);assert.equal(doc.cache_audit.groups.selected.complete_sampled_60m,53);
 assert.equal(doc.cache_audit.groups.original_ssr_skips.prepared_files,31);assert.equal(doc.cache_audit.groups.original_ssr_skips.complete_sampled_60m,28);
 assert.equal(doc.archive.sessions,0);assert.equal(doc.validation.actual_broker_fills,0);assert.equal(doc.production_authority,'none');
});
test('flow budgets remain diagnostics and do not create positions, fill rates or P&L',()=>{
 const d=doc.cache_audit.flow_budget_diagnostics.find(x=>x.group==='original_ssr_skips'&&x.minutes===60&&x.participation===.1);
 assert.equal(d.n,31);assert.equal(d.median_flow_budget_usd,6832.085);assert.equal(d.parents_with_100k_flow_budget,3);
 const m=doc.rules.dilution.models.find(m=>m.id==='E2_60m_10pct_500ms_conditional');assert.equal(m.summary,null);
});
test('public data excludes raw licensed prices, quantities, per-event returns and broker confirmations',()=>{
 function walk(x){if(!x||typeof x!=='object')return;for(const [k,v]of Object.entries(x)){assert.ok(!['entry_price','adv_shares','filled_shares','quantity','proceeds','confirmation','daily','positions','events_raw','file'].includes(k),'Forbidden public key '+k);walk(v);}}
 // Metadata events and aggregate hypothetical dollar budgets are intentionally public.
 walk(doc);assert.ok(Object.keys(doc.sources).every(k=>!k.includes('/local/')));
});
test('SSR dashboard shows unavailable values, full methods and search without claiming profitable fills',()=>{
 const state={rule:'dilution',latency:500,borrow:'conditional',group:'selected',query:''},html=V.view(doc,state);
 assert.equal(V.models(doc,state).length,16);assert.equal(V.rows(doc,state).length,170);assert.equal(V.rows(doc,{...state,group:'all'}).length,210);
 assert.equal(V.rows(doc,{...state,query:'bini'}).length,2);
 assert.match(html,/performance unavailable/);assert.match(html,/partial fills/);assert.match(html,/Not estimable/);assert.match(html,/Archived usable approvals/);assert.match(html,/not an SSR fill result/);
 assert.ok(!html.includes('>$0<'));assert.equal(V.money(null),'Unavailable');
});
test('new panel escapes ticker names, labels and search text',()=>{
 const copy=structuredClone(doc);copy.events[0].ticker='<img src=x>';copy.rules.dilution.label='<script>bad</script>';
 const html=V.view(copy,{rule:'dilution',latency:500,borrow:'conditional',group:'all',query:'<img'});
 assert.ok(!html.includes('<img src=x>'));assert.ok(!html.includes('<script>'));assert.ok(html.includes('&lt;img'));
});
test('manifest hash and model-schema failures prevent mixed or false performance display',async()=>{
 const body=JSON.stringify(doc),manifest={schema:'third_plus_execution_dashboard_manifest.v1',payload:'third_plus_execution.json',data_version:doc.data_version,sha256:Archive.sha(body)};
 const fetcher=async url=>url.includes('_manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>body};
 assert.equal((await V.load(fetcher,crypto.webcrypto)).data_version,doc.data_version);
 manifest.sha256='0'.repeat(64);await assert.rejects(()=>V.load(fetcher,crypto.webcrypto),/different publications/);
 const copy=structuredClone(doc);copy.rules.dilution.models.find(x=>x.status==='not_estimable').summary={net_pnl:0};assert.throws(()=>V.validate(copy),/financial result/);
});
test('gap CSV includes all 210 event identities and is formula safe',()=>{
 const csv=Pub.gapCsv(doc);assert.equal(csv.charCodeAt(0),65279);assert.equal(csv.trimEnd().split('\n').length,211);
 const copy=structuredClone(doc);copy.cache_audit.events[0].ticker='=HYPERLINK("bad")';assert.ok(Pub.gapCsv(copy).includes("'=HYPERLINK"));
});
test('archive rejects synthetic, hash-mismatched and out-of-directory inputs',()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ssi-ssr-archive-'));
 const file=path.join(tmp,'session.local.json'),index=path.join(tmp,'index.local.json');
 try{
  const s={schema:'third_plus_execution_session.v1',event_id:'e1',date:'2026-01-01',synthetic:true,events:[]};
  fs.writeFileSync(file,JSON.stringify(s));
  const row={kind:'entry',event_id:'e1',date:'2026-01-01',file:'session.local.json',sha256:Archive.sha(fs.readFileSync(file))};
  fs.writeFileSync(index,JSON.stringify({schema:'third_plus_execution_archive.v1',sessions:[row]}));assert.throws(()=>Archive.loadArchive(tmp),/synthetic/);
  const inner=path.join(tmp,'inside');fs.mkdirSync(inner);fs.writeFileSync(path.join(inner,'index.local.json'),JSON.stringify({schema:'third_plus_execution_archive.v1',sessions:[{...row,file:'../session.local.json'}]}));assert.throws(()=>Archive.loadArchive(inner),/Forbidden archive path/);
  row.sha256='f'.repeat(64);fs.writeFileSync(index,JSON.stringify({schema:'third_plus_execution_archive.v1',sessions:[row]}));assert.throws(()=>Archive.loadArchive(tmp),/hash mismatch/);
 }finally{assert.ok(path.resolve(tmp).startsWith(path.resolve(os.tmpdir())+path.sep));fs.rmSync(tmp,{recursive:true,force:true});}
});
test('committed SSR report, dashboard bytes and gap export reproduce exactly',()=>Pub.publish(true));
