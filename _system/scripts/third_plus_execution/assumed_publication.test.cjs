'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const Study=require('./assumed_study.cjs'),V=require('../../../dashboard/third-plus-assumed.js'),d=JSON.parse(fs.readFileSync(require('node:path').resolve(__dirname,'../../../dashboard/data/third_plus_assumed_backtest.json')));
const state={rule:'dilution',scenario:'base',policy:'E2',minutes:60,rate:.1,group:'selected',query:''};
test('all 21 signals have complete numeric paths for all 72 settings and both capacities',()=>{
 V.validate(d);assert.equal(d.rules.dilution.selected,170);assert.equal(d.rules.third_plus_only.selected,210);
 for(const r of Object.values(d.rules))for(const m of r.models){assert.equal(m.decisions.length,210);assert.ok(m.decisions.every(x=>Number.isInteger(x)&&d.decision_codes[x]));for(const p of [m.account,m.all_candidates]){assert.equal(p.selected,r.selected);assert.ok(p.entered+p.no_fill+p.ssr_skipped<=p.attempted);assert.ok(p.entered>=p.open_positions);assert.ok(Math.abs(p.net_pnl+p.costs.borrow+p.costs.fees+p.costs.impact+p.costs.locate-p.gross_before_costs)<.01);assert.ok(p.net_pnl<100000000&&p.net_pnl>-100000000);}}
 assert.ok(d.rules.debt_distress.models.every(m=>m.account.net_pnl===0&&m.account.entered===0));
});
test('visible primary result is numeric, changes with assumptions and retains audit separately',()=>{
 const V3=require('../../../dashboard/third-plus-venue.js'),html=V.view(d,state),m=V.chosen(d,state);
 assert.ok(Number.isFinite(m.account.net_pnl));assert.match(html,/Tradability assumed/);assert.match(html,/Account net marked P&amp;L|Account net marked P&L/);assert.match(html,/Higher costs/);assert.match(html,/Every candidate without slot competition/);
 assert.notEqual(m.account.net_pnl,V.chosen(d,{...state,scenario:'stress'}).account.net_pnl);assert.ok(V3.render('dilution').indexOf('data-assumed-backtest')<V3.render('dilution').indexOf('data-venue-execution'));
});
test('source and payload hashes bind the full numeric publication and report',()=>{Study.check();require('./assumed_publish.cjs').publish(true);});
test('no raw licensed data or private filesystem paths appear in the assumed publication',()=>{
 const visit=x=>{if(!x||typeof x!=='object')return;for(const [k,v]of Object.entries(x)){assert.ok(!['bars','quotes','quantity','filled_shares','trade_id','file','ts_ms','available_ms'].includes(k),'Raw field '+k);visit(v);}};visit(d);assert.ok(Object.keys(d.sources).every(f=>!f.includes('/local/')));
 const c=structuredClone(d);c.rules.dilution.opportunities[0].ticker='<script>bad</script>';assert.ok(!V.view(c,{...state,group:'all'}).includes('<script>bad'));
});
test('browser loading checks digest and rejects a mixed publication',async()=>{
 const body=JSON.stringify(d),manifest={schema:'third_plus_assumed_manifest.v1',payload:'third_plus_assumed_backtest.json',data_version:d.data_version,sha256:crypto.createHash('sha256').update(body).digest('hex')},fetcher=async url=>url.includes('manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>body};
 assert.equal((await V.load(fetcher,crypto.webcrypto)).data_version,d.data_version);manifest.sha256='0'.repeat(64);await assert.rejects(()=>V.load(fetcher,crypto.webcrypto),/do not match/);
});
