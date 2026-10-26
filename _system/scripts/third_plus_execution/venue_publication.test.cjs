'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs');
const Pub=require('./venue_publish.cjs'),V=require('../../../dashboard/third-plus-venue.js');
const d=JSON.parse(fs.readFileSync(require('node:path').resolve(__dirname,'../../../dashboard/data/third_plus_venue_execution.json'),'utf8'));
const state={rule:'dilution',policy:'E2',minutes:60,rate:.1,group:'excluded',query:''};
test('all original exclusions remain individual opportunities and no historical evidence is upgraded',()=>{
 V.validate(d);assert.equal(V.rows(d,state).length,129);assert.equal(V.rows(d,{...state,group:'ssr'}).length,100);
 const excluded=V.rows(d,state);assert.equal(excluded.filter(e=>e.attempted).length,129);assert.equal(excluded.filter(e=>e.full_session_filled).length,129);
 assert.ok(excluded.some(e=>!e.filled&&e.full_session_filled),'Shorter-window no-fills must remain visible');
 assert.equal(d.verified_nbbo_entries,0);assert.equal(d.verified_borrow_entries,0);assert.equal(d.acquisition.reserved_cost_usd,0);assert.equal(d.acquisition.authorized_cap_usd,0);
 assert.equal(d.rules.dilution.opportunities.filter(e=>e.previous_decision==='ssr_rejected'&&e.evaluated).length,100);
});
test('every frozen signal has all methods, participation rates and declared windows',()=>{
 assert.equal(Object.keys(d.rules).length,21);
 for(const r of Object.values(d.rules)){assert.equal(r.models.length,24);assert.equal(r.opportunities.length,210);assert.equal(new Set(r.models.map(m=>m.id)).size,24);}
});
test('monthly cash accounting reconciles and missing results never become zero profit',()=>{
 for(const r of Object.values(d.rules))for(const m of r.models){
  if(m.status==='not_estimable')assert.equal(m.summary,null);
  if(m.summary)assert.ok(Math.abs(m.summary.monthly.reduce((n,x)=>n+x[1],0)-m.summary.net_pnl)<.01);
 }
 assert.equal(V.money(null),'Unavailable');assert.equal(V.money(0),'$0');
});
test('dashboard distinguishes independent fills, account slots and bar assumptions',()=>{
 const html=V.view(d,state);assert.match(html,/one-second Nasdaq bars/);assert.match(html,/three concurrent issuers/);assert.match(html,/exploratory 240-minute/);assert.match(html,/Borrow availability/);assert.match(html,/not observed executions/);
 assert.ok(!html.includes('verified historical fills'));assert.equal(V.rows(d,{...state,query:'shph'}).length,1);
});
test('CSV includes every event, remains formula safe and labels conditional evidence',()=>{
 const s=V.csv(d,{...state,group:'all'});assert.equal(s.charCodeAt(0),65279);assert.equal(s.trimEnd().split('\n').length,211);assert.match(s,/conditional venue\/NBB\/borrow sensitivity/);
 const c=structuredClone(d);c.rules.dilution.opportunities[0].ticker='=DANGEROUS()';assert.match(V.csv(c,{...state,group:'all'}),/'=DANGEROUS/);
});
test('new public artifacts contain derived decisions without raw bars, quotes, shares or private paths',()=>{
 const visit=x=>{if(!x||typeof x!=='object')return;for(const [k,v]of Object.entries(x)){assert.ok(!['bars','quotes','quantity','filled_shares','trade_id','file','ts_ms','available_ms'].includes(k),'Raw field '+k);visit(v);}};visit(d);
 assert.ok(Object.keys(d.sources).every(k=>!k.includes('/local/')));
});
test('publication hash verification rejects mixed data and HTML escapes untrusted names',async()=>{
 const body=JSON.stringify(d),m={schema:'third_plus_venue_manifest.v2',payload:'third_plus_venue_execution.json',data_version:d.data_version,sha256:crypto.createHash('sha256').update(body).digest('hex')};
 const fetcher=async url=>url.includes('manifest')?{ok:true,json:async()=>m}:{ok:true,text:async()=>body};
 assert.equal((await V.load(fetcher,crypto.webcrypto)).data_version,d.data_version);m.sha256='0'.repeat(64);await assert.rejects(()=>V.load(fetcher,crypto.webcrypto),/different publications/);
 const c=structuredClone(d);c.rules.dilution.opportunities[0].ticker='<script>bad</script>';assert.ok(!V.view(c,{...state,group:'all'}).includes('<script>bad'));
});
test('report and decision export reproduce without licensed caches or network',()=>Pub.publish(true));
