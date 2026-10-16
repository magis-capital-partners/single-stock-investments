"""Policy changes must switch the audit, including out-of-order responses."""
from pathlib import Path
import subprocess


def test_policy_audit_race_and_untrusted_ticker_escaping():
    root = Path(__file__).resolve().parents[4]
    script = r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const mounts = new Map();
const document = {getElementById: id => {if (!mounts.has(id)) mounts.set(id, {innerHTML:''}); return mounts.get(id);}};
const groups = ['announcement_next_open_5_bracket','announcement_next_open_10_bracket'];
const audits = Object.fromEntries(groups.map((g, i) => [g, {outcomes:{x:'daily_benchmark'}, forecasts:{x:{gross_edge:(i+1)/10,gross:{}}},accounts:{capital50k:{x:{shares:i+1,reason:'included',net_edge:(i+1)/10}}}}]));
const fetch = async url => {const g = groups.find(k=>url.includes(k)); await new Promise(r=>setTimeout(r,g===groups[0]?40:1)); return {ok:true,arrayBuffer:async()=>new TextEncoder().encode(JSON.stringify(audits[g])).buffer};};
const context = {window:{},document,fetch,setTimeout,TextDecoder,URL};
vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const api = context.window.ShortsEdgeV3Viz;
const data = {schema_version:'shorts_net_edge.v3',policy:{entry:'announcement_next_open',sessions:5,bracket:true,prospective_start:'2026-10-16'},primary_case:'capital50k',coverage:{},accounts:[{id:'capital50k',label:'50k',account:{equity:50000,commission_minimum:1,commission_per_share:.005,commission_max_fraction:.01}}],cases:groups.map(group=>({group,account_id:'capital50k',variant:'net_edge',trades:0,costs:{},skipped:{}})),names:[{key:'x',ticker:'<X>',rating:80,announcement:'2026-10-01T12:00:00Z'}],validation:Object.fromEntries(groups.map(g=>[g,{observations:1}])),audit_files:Object.fromEntries(groups.map(g=>[g,{url:'data/net_edge_audits_v3/'+g+'.json',sha256:'a'.repeat(64)}])),ssr:{counts:{},limit_replay:{},rule:''},sources:[],definitions:{},limits:[]};
(async()=>{
  assert.match(api.render(data),/RSI-3.0/);
  await new Promise(r=>setTimeout(r,5)); api.change('hold','10');
  await new Promise(r=>setTimeout(r,80));
  assert.match(mounts.get('sev-names').innerHTML,/20%/);
  assert.match(mounts.get('sev-names').innerHTML,/&lt;X&gt;/);
  assert.doesNotMatch(mounts.get('sev-names').innerHTML,/>10%</);
  api.inspect(0); assert.match(mounts.get('sev-detail').innerHTML,/&lt;X&gt;/);
  api.change('query','NO MATCH'); assert.match(mounts.get('sev-names').innerHTML,/0 matching/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-e", script, str(root/"dashboard/shorts-edge-v3-viz.js")],
                            cwd=root, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr


def test_free_evidence_integrity_selection_race_and_borrow_ceiling():
    root = Path(__file__).resolve().parents[4]
    script = r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const crypto = require('node:crypto'), hash = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const mounts = new Map(), document = {getElementById:id=>{if(!mounts.has(id))mounts.set(id,{innerHTML:''});return mounts.get(id)}};
const group = 'announcement_next_open_5_bracket';
const plan = {trial_shares:100,net_edge:.03,net_lower_bound:.01,expected_borrow:.02,expected_billed_days:5};
const audit = {outcomes:{x:'daily_benchmark',y:'daily_benchmark'},forecasts:Object.fromEntries(['x','y'].map(k=>[k,{gross_edge:.1,announcement_plans:{capital50k:plan}}])),accounts:{capital50k:{}}};
const packet = key => ({schema_version:'shorts_free_packet.v1',event_id:key,outcome_blinded:true,financials:{currency:'USD'},documents:[],frameworks:[],financing_terms:[{excerpt:`${key} <img src=x onerror=alert(1)>`,source_url:'javascript:alert(1)',known_at:'2026-01-01',locator:'one',accession:'one'}]});
const packets = {x:packet('x'),y:packet('y')};
const paths = {x:'data/free_short_packets/'+ 'a'.repeat(24)+'.json',y:'data/free_short_packets/'+'b'.repeat(24)+'.json'};
const free = {schema_version:'shorts_free_evidence.v1',data_cost_usd:0,paid_requests:0,packets:2,names:['x','y'].map(k=>({event_id:k,path:paths[k],sha256:hash(packets[k])}))};
const bodies = {'data/shorts_free_evidence.json':free,['data/net_edge_audits_v3/'+group+'.json']:audit,[paths.x]:packets.x,[paths.y]:packets.y};
const fetch = async url => {const path=url.split('?')[0];await new Promise(r=>setTimeout(r,path===paths.x?45:1));return {ok:true,arrayBuffer:async()=>new TextEncoder().encode(JSON.stringify(bodies[path])).buffer}};
const context = {window:{crypto:crypto.webcrypto},document,fetch,setTimeout,TextDecoder,URL};vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const api = context.window.ShortsEdgeV3Viz;
const data = {schema_version:'shorts_net_edge.v3',policy:{entry:'announcement_next_open',sessions:5,bracket:true,assumed_annual_borrow:.5,preborrow_fee_per_share:0},coverage:{},accounts:[{id:'capital50k',account:{equity:50000}}],cases:[{group,account_id:'capital50k',variant:'net_edge',costs:{},skipped:{}}],names:['x','y'].map(k=>({key:k,ticker:k,rating:80,announcement:'2026-07-07T12:00:00Z'})),validation:{[group]:{}},audit_files:{[group]:{url:'data/net_edge_audits_v3/'+group+'.json',sha256:hash(audit)}},ssr:{counts:{},limit_replay:{}},sources:[],definitions:{},limits:[],free_evidence_ref:{url:'data/shorts_free_evidence.json',sha256:hash(free)}};
(async()=>{
 api.render(data);await new Promise(r=>setTimeout(r,80));
 assert.match(mounts.get('sev-free-summary').innerHTML,/\$0 in data charges/);
 api.inspect(0);api.inspect(1);await new Promise(r=>setTimeout(r,110));
 assert.match(mounts.get('sev-detail').innerHTML,/125% annual fee ceiling/);
 assert.match(mounts.get('sev-free-detail').innerHTML,/y &lt;img/);
 assert.doesNotMatch(mounts.get('sev-free-detail').innerHTML,/x &lt;img|<img|href="javascript:/);
 bodies[paths.x] = {...packets.x,financing_terms:[{excerpt:'tampered'}]};
 api.inspect(0);await new Promise(r=>setTimeout(r,110));
 assert.match(mounts.get('sev-free-detail').innerHTML,/could not be verified/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-e", script, str(root/"dashboard/shorts-edge-v3-viz.js")],
                            cwd=root, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
