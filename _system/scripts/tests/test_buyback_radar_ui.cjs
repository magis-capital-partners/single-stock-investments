
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../../..');
const source=fs.readFileSync(path.join(root,'dashboard/buyback-viz.js'),'utf8');
const index=fs.readFileSync(path.join(root,'dashboard/index.html'),'utf8');
const id='a'.repeat(20),prefix='buyback_snapshots/'+id+'/';
function fixture(){
 const metric={value:8,start:'2025-06-30',end:'2026-06-30',status:'derived',sources:[{url:'https://www.sec.gov/fixture',end:'2026-06-30'}]};
 const company={schema_version:'buyback.v2',ticker:'TEST',company:'Fixture company',issuer_id:'cik:1',aliases:['TEST.A'],data_status:'verified',confidence:'high',rank_eligible:true,shares_end:'2026-06-30',snapshot_id:id,metrics:{net_reduction_1y:metric,gross_cash_ratio:{...metric,value:5}},detail_ref:prefix+'details/cik_1.json',assessment:{components:{}}};
 const event={id:'bb:event',issuer_id:'cik:1',ticker:'TEST',event_type:'issuer_tender',what:'Tender',book:'ranked',status:'active',ends:'2026-12-01',terms_verified:true,price_low:20,price_high:23,last_verified:'2026-10-20',url:'https://www.sec.gov/fixture'};
 const signal={ticker:'TEST',company:'Fixture company',issuer_id:'cik:1',data_status:'verified',shares_end:'2026-06-30',change_1y_pct:3,change_5y_pct:-12,issuance_cause:'acquisition_consideration',repurchase_fy_usd:10,repurchase_end:'2025-12-31'};
 return {'buyback_manifest.json':{schema_version:'buyback_manifest.v2',snapshot_id:id,as_of:'2026-10-20',counts:{verified:1},companies:prefix+'companies.json',events:prefix+'events.json',summary:prefix+'summary.json'},
 [prefix+'companies.json']:{snapshot_id:id,companies:[company],issuance_signals:[signal]},
 [prefix+'events.json']:{snapshot_id:id,events:[event]},
 [prefix+'summary.json']:{snapshot_id:id,changes:[],changes_count:0},
 [company.detail_ref]:{snapshot_id:id,issuer_id:'cik:1',series:{actual:[],diluted:[]},flows:{},cash_periods:{}}};
}
function harness(docs=fixture()){
 const calls=[],storage=new Map();
 class ClockDate extends Date { static now(){return Date.parse('2026-10-20T18:00:00Z');} }
 const context={window:{},location:{hash:'#/research/coverage/TEST?section=buyback'},Intl,Map,Set,Date:ClockDate,URLSearchParams,queueMicrotask:()=>{},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 fetch:async url=>{calls.push(url);const d=docs[url.replace(/^data\//,'')];return {ok:!!d,status:d?200:404,json:async()=>d};}};
 vm.createContext(context);vm.runInContext(source,context);return {api:context.window.BuybackViz,context,calls,docs,storage};
}
function routeFunction(name){
 const start=index.indexOf('function '+name+'(');assert.ok(start>=0);
 const end=index.indexOf('\n}',start);assert.ok(end>start);
 return index.slice(start,end+2);
}
test('summary, events and Shorts consume a single snapshot with canonical aliases',async()=>{
 const h=harness();await h.api.load();
 assert.equal(h.api.company('TEST.A'),h.api.company('TEST'));
 const events=h.api.projectSituations({rows:[],discovery:[],history:[]}),shorts=h.api.projectShorts({});
 assert.equal(events.buyback_snapshot.snapshot_id,shorts.buyback_snapshot.snapshot_id);
 assert.equal(events.rows[0].buyback_event.issuer_id,h.api.company('TEST').issuer_id);
 assert.equal(shorts.buyback_issuance_signals[0].ticker,'TEST');
});
test('initial loading does not request detailed share histories',async()=>{
 const h=harness();await h.api.load();h.api.renderDetail({ticker:'TEST',buyback:h.api.company('TEST')});
 assert.equal(h.calls.length,4);assert.ok(!h.calls.some(x=>x.includes('/details/')));
});
test('load is shared across simultaneous consumers',async()=>{
 const h=harness();await Promise.all([h.api.load(),h.api.load(),h.api.load()]);assert.equal(h.calls.filter(x=>x==='data/buyback_manifest.json').length,1);
});
test('mixed snapshots withhold all buyback projections',async()=>{
 const docs=fixture();docs[prefix+'events.json'].snapshot_id='b'.repeat(20);
 const h=harness(docs);assert.equal(await h.api.load(),null);assert.equal(h.api.company('TEST'),null);assert.match(h.api.projectSituations({}).buyback_error,/out of sync/);
});
test('invalid paths cannot fetch outside the snapshot directory',async()=>{
 const docs=fixture();docs['buyback_manifest.json'].companies='../private.json';
 const h=harness(docs);assert.equal(await h.api.load(),null);assert.equal(h.calls.length,1);
});
test('legacy feeds cannot repopulate unverified positive numbers',async()=>{
 const h=harness({});await h.api.load();assert.equal(h.api.company('TEST'),null);
 assert.match(h.api.renderHoldingsCell({buyback:{buyback_yield_pct:100}}),/Awaiting verified data/);
});
test('missing values sort last in either direction',async()=>{
 const h=harness();await h.api.load();const a={ticker:'A',buyback:h.api.company('TEST')},b={ticker:'B',buyback:{data_status:'unavailable'}};
 assert.ok(h.api.compareRows(a,b,'net_reduction_1y',true)<0);assert.ok(h.api.compareRows(a,b,'net_reduction_1y',false)<0);
});
test('stale and failed refresh records are not numerically ranked',async()=>{
 const h=harness();await h.api.load();const row=h.api.company('TEST');
 assert.equal(h.api.metric({...row,data_status:'stale'},'net_reduction_1y').value,null);
 assert.equal(h.api.metric({...row,refresh_status:'fetch_failed'},'net_reduction_1y').value,null);
});
test('Coverage shows measurement date, actual reduction and cash definition',async()=>{
 const h=harness();await h.api.load();const html=h.api.renderHoldingsCell({buyback:h.api.company('TEST')});
 assert.match(html,/8.0% net reduced/);assert.match(html,/Shares 2026-06-30/);assert.match(html,/5.0% cash/);
});
test('filters use verified eligibility and events from shared data',async()=>{
 const h=harness();await h.api.load();const row={ticker:'TEST',buyback:h.api.company('TEST')};
 assert.ok(h.api.matches(row,'verified'));assert.ok(h.api.matches(row,'events'));
 assert.ok(!h.api.matches({...row,buyback:{...row.buyback,rank_eligible:false}},'verified'));
});

test('focused shortlist requires recurring reductions and evidenced repurchase cash',async()=>{
 const h=harness();await h.api.load();const b=h.api.company('TEST');
 const row={ticker:'TEST',buyback:{...b,metrics:{...b.metrics,net_reduction_3y:{...b.metrics.net_reduction_1y,value:12}}}};
 assert.ok(h.api.matches(row,'focused'));
 for(const [key,value] of [['net_reduction_1y',4.99],['net_reduction_3y',-1],['gross_cash_ratio',0]]){
  const changed={...row,buyback:{...row.buyback,metrics:{...row.buyback.metrics,[key]:{...b.metrics.net_reduction_1y,value}}}};
  assert.ok(!h.api.matches(changed,'focused'),key);
 }
 assert.ok(!h.api.matches({...row,buyback:{...row.buyback,refresh_status:'fetch_failed'}},'focused'));
});
test('Special Situations replaces only its buyback lane',async()=>{
 const h=harness();await h.api.load();const doc=h.api.projectSituations({rows:[{id:'old',lane:'buyback_events'},{id:'merger',lane:'mergers'}]});
 assert.equal(doc.rows.length,2);assert.ok(doc.rows.some(x=>x.id==='merger'));assert.ok(!doc.rows.some(x=>x.id==='old'));
});
test('issuance signals respect query, framework and stage',async()=>{
 const h=harness();await h.api.load();const rows=h.api.projectShorts({}).buyback_issuance_signals;
 assert.match(h.api.renderSignals(rows,{framework:'all',query:'TEST'}),/Issuing again \/ 1/);
 assert.match(h.api.renderSignals(rows,{framework:'dilution_financing',query:'missing'}),/Issuing again \/ 0/);
 assert.equal(h.api.renderSignals(rows,{framework:'fraud'}),'');assert.equal(h.api.renderSignals(rows,{stage:'live'}),'');
});
test('dispositions require a reason field and retain source date and cause',async()=>{
 const h=harness();await h.api.load();const html=h.api.renderSignals(h.api.projectShorts({}).buyback_issuance_signals,{});
 assert.match(html,/data-bb-reason/);assert.match(html,/2026-06-30/);assert.match(html,/acquisition consideration/);assert.match(html,/Gross repurchases/);
});
test('untrusted names and evidence are escaped',async()=>{
 const h=harness();await h.api.load();const html=h.api.renderEventDetails({what:'<script>',terms:{conditions:'<img onerror=alert(1)>'},url:'javascript:alert(1)'});
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('href="javascript:'));assert.match(html,/&lt;img/);
});
test('tender payoff accounts for acceptance, leftovers and fees',()=>{
 const h=harness();const r=h.api.tenderScenario({purchase:20,offer:23,acceptance:.5,unaccepted:18,fees:.1,days:30});
 assert.ok(Math.abs(r.gain-.4)<1e-10);assert.ok(Math.abs(r.return_pct-2)<1e-10);
 assert.equal(h.api.tenderScenario({purchase:0,offer:23,acceptance:1,unaccepted:0,fees:0,days:30}),null);
});
test('EPS scenario includes issuance and independent earnings assumptions',()=>{
 const h=harness();const r=h.api.epsScenario({shares:100,earnings:100,retire:10,issue:5,earnings_change:0});
 assert.equal(r.before,1);assert.ok(Math.abs(r.after-100/95)<1e-10);
 assert.equal(h.api.epsScenario({shares:100,earnings:100,retire:100,issue:0,earnings_change:0}),null);
});
test('tender terms never assume odd-lot priority',()=>{
 const h=harness();assert.match(h.api.renderEventDetails({event_type:'issuer_tender',price_low:20,price_high:23}),/Unverified/);
});
test('Coverage and Shorts routes accept focus parameters',()=>{
 const c={SITUATION_LANE_IDS:{'buyback-events':'buyback_events'},WATCHLIST_VIEWS:new Set()};vm.createContext(c);vm.runInContext(routeFunction('parseRouteFromHashString'),c);
 assert.equal(c.parseRouteFromHashString('#/research/coverage/TEST?section=buyback').ticker,'TEST');
 assert.equal(c.parseRouteFromHashString('#/ideas/short-alpha?buyback=TEST').view,'short-alpha');
 assert.equal(c.parseRouteFromHashString('#/ideas/situations/buyback-events/TEST').situationFocus,'TEST');
});
test('route normalization preserves Buyback detail and Shorts focus',()=>{
 let last;const c={activeView:'holdings',selected:'TEST',location:{hash:'#/research/coverage/TEST?section=buyback'},URLSearchParams,setAppHash:x=>{last=x;}};
 vm.createContext(c);vm.runInContext(routeFunction('syncRouteHash'),c);c.syncRouteHash();assert.equal(last,'#/research/coverage/TEST?section=buyback');
 c.activeView='short-alpha';c.shortAlphaSection='ideas';c.location.hash='#/ideas/short-alpha?buyback=TEST';c.syncRouteHash();assert.equal(last,'#/ideas/short-alpha?buyback=TEST');
});
test('every inline dashboard script compiles',()=>{
 let count=0;for(const m of index.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)){if(/\bsrc=/.test(m[1]) || /application\/(?:json|ld\+json)/.test(m[1]))continue;new vm.Script(m[2]);count++;}assert.ok(count>0);
});

test('an overdue publication cannot retain positive rankings or active events',async()=>{
 const docs=fixture();docs['buyback_manifest.json'].generated_at='2026-10-01T00:00:00Z';
 const h=harness(docs);await h.api.load();const b=h.api.company('TEST');
 assert.equal(h.api.metric(b,'net_reduction_1y').value,null);
 assert.equal(h.api.projectSituations({}).rows.length,0);
 assert.equal(h.api.projectSituations({}).discovery.length,1);
 assert.equal(h.api.projectShorts({}).buyback_issuance_signals.length,0);
 assert.match(h.api.renderHoldingsCell({buyback:b}),/snapshot overdue/);
});

test('workspace routes retain a legacy Buyback focus in the Business view',()=>{
 let last; const c={activeView:'holdings',selected:'TEST',ResearchWorkspace:{activeTab:()=> 'business'},location:{hash:'#/research/coverage/TEST?section=buyback'},URLSearchParams,setAppHash:value=>{last=value;}};
 vm.createContext(c);vm.runInContext(routeFunction('syncRouteHash'),c);c.syncRouteHash();assert.equal(last,'#/research/coverage/TEST?section=business&focus=buyback');
});
