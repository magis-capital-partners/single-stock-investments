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
