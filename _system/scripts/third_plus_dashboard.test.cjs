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

const D=require('../../dashboard/third-plus-study-details.js'),Audit=require('./build_third_plus_decision_audit.cjs');
test('all 189 event audits classify the entire cohort and reconcile every frozen funnel',()=>{
 for(const c of doc.cases)for(const r of doc.rules){const a=doc.audit.models[c.id][r.id],m=doc.models[c.id][r.id];assert.equal(a.statuses.length,210);assert.ok(a.statuses.every(Boolean));assert.equal(a.statuses.filter(s=>!s.startsWith('signal_')).length,m.funnel.selected);for(const [k,n]of Object.entries(m.funnel))if(k!=='selected')assert.equal(a.statuses.filter(s=>s===k).length,n);}
 assert.equal(new Set(doc.audit.events.map(e=>e.id)).size,210);assert.equal(doc.audit.verification.positions_and_daily_paths_exact,true);
});
test('default exclusions resolve to maturity, BINI liquidity, restricted status and three-name limits',()=>{
 const a=doc.audit.models.primary.dilution,rs=D.rows(doc,{rule:'dilution',case:'primary'});
 assert.equal(a.statuses.filter(s=>s==='entered').length,40);assert.equal(a.statuses.filter(s=>s==='signal_fail').length,33);assert.equal(a.statuses.filter(s=>s==='signal_unknown').length,7);
 assert.deepEqual(rs.filter(r=>r.status==='common_maturity_excluded').map(r=>r.ticker),['JAGX','CTNT','CDT','KUST']);
 assert.ok(rs.filter(r=>r.status==='common_maturity_excluded').every(r=>r.detail.reason==='common_20_session_maturity'));
 assert.deepEqual(rs.filter(r=>r.status==='missing_liquidity').map(r=>r.ticker),['BINI']);
 assert.equal(rs.filter(r=>r.status==='ssr_rejected'&&r.detail.reason==='restricted').length,97);assert.equal(rs.filter(r=>r.status==='ssr_rejected'&&r.detail.reason==='unknown').length,0);
 const risk=rs.filter(r=>r.status==='risk_capacity');assert.equal(risk.length,28);assert.ok(risk.every(r=>r.detail.reason==='three_name_limit'&&r.detail.size.open_events.length===3));
 assert.equal(rs.find(r=>r.ticker==='DFLI').status,'signal_unknown');
});
test('every admitted size is the minimum whole-share ceiling and matches aggregate sizes and exit states',()=>{
 for(const c of doc.cases)for(const r of doc.rules){const m=doc.models[c.id][r.id],rs=D.rows(doc,{rule:r.id,case:c.id}).filter(x=>x.status==='entered');let total=0;for(const x of rs){const s=x.detail.size;assert.ok(s.notional>0&&s.notional<=25000);assert.ok(Math.abs(s.notional-Math.min(...Object.values(s.limits)))<=.011);assert.ok(s.binding.every(k=>Math.abs(s.notional-s.limits[k])<=.011));assert.ok(Math.abs(s.notional/25000-s.target_fraction)<.000001);total+=s.notional;}if(rs.length)assert.ok(Math.abs(total/rs.length-m.mean_position)<.006);assert.equal(rs.filter(x=>x.detail.position.open).length,m.open_positions);assert.equal(rs.filter(x=>!x.detail.position.open).length,m.closed);}
});
test('event publication contains derived sizing but no raw market prices or per-event returns',()=>{
 const forbidden=new Set(['entry_price','entry_fill','adv_shares','adv_dollars','volume','qty','entry_units','pnl','net_return','gross_pnl','mark','borrow','fees','covers','daily']);
 function walk(x){if(!x||typeof x!=='object')return;for(const [k,v]of Object.entries(x)){assert.ok(!forbidden.has(k),'Forbidden audit key '+k);walk(v);}}walk(doc.audit);
});
test('candidate search and CSV preserve event identity and all requested exclusion rows',()=>{
 const state={rule:'dilution',case:'primary',auditFilter:'selected_exclusions'};
 assert.equal(D.filtered(doc,state).length,130);assert.equal(D.filtered(doc,{...state,auditQuery:'bini'}).length,2);assert.equal(D.filtered(doc,{...state,auditFilter:'signal_exclusions'}).length,40);
 const csv=D.csv(doc,state,'decisions');assert.equal(csv.charCodeAt(0),65279);assert.equal(csv.trimEnd().split('\r\n').length,131);assert.match(csv,/'?BINI/);
 const sizes=D.csv(doc,state,'sizes');assert.equal(sizes.trimEnd().split('\r\n').length,41);assert.match(sizes,/1812.51/);assert.match(sizes,/2505/);
});
test('candidate names, audit search and downloadable CSV resist markup and formula injection',()=>{
 const x=structuredClone(doc);x.audit.events[0].name='<img src=x onerror=alert(1)>';x.audit.events[0].ticker='=HYPERLINK("bad")';
 const html=D.audit(x,{rule:'dilution',case:'primary',auditFilter:'all',auditQuery:'<script>'});assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img src=x'));
 assert.ok(D.csv(x,{rule:'dilution',case:'primary',auditFilter:'all'},'decisions').includes("'=HYPERLINK"));
});
test('guide discloses future same-day volume, zero SPX stress, no automatic stop and unresolved exits',()=>{
 const html=D.guide(doc,{rule:'dilution',case:'primary'});assert.match(html,/uses future same-day information/);assert.match(html,/Other-sleeve stress loss was zero/);assert.match(html,/no automatic stop/);assert.match(html,/fully implementable/);assert.match(html,/not verified actual bills/);
 const sizes=D.sizing(doc,{rule:'dilution',case:'primary'});assert.match(sizes,/95%/);assert.match(sizes,/0.0025/);assert.match(sizes,/0.01/);assert.match(sizes,/35.58/);
});
test('audit instrumentation fails closed when an expected frozen hook changes',()=>{
 const source=fs.readFileSync(path.join(ROOT,'_system/scripts/reverse_split_repeat_study.cjs'),'utf8');assert.ok(Audit.instrument(source).includes('opts.audit?.'));
 assert.throws(()=>Audit.instrument(source.replace('  const byDay=new Map();','  const differentName=new Map();')),/Frozen audit hook changed/);
});
