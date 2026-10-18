"""Matched comparisons reject stale bindings and keep absent performance absent."""
from pathlib import Path
import subprocess


def test_matched_fundamental_ui_validates_sources_and_shows_every_statistic():
    root = Path(__file__).resolve().parents[4]
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const mounts=new Map(),document={getElementById:id=>{if(!mounts.has(id))mounts.set(id,{innerHTML:''});return mounts.get(id)}};
const keys=['unfiltered','score60','score50','score60_or_distress'];
const record={key:'x',ticker:'<img src=x>',issuer:'cik/1',known_at:'2026-10-01T12:00:00Z',score:null,financials:{status:'missing',coverage:{families:[]},evidence:[{tag:'<script>',end:'2026-06-30',val:1,unit:'USD',source_url:'javascript:bad()'}]},decisions:Object.fromEntries(keys.map(k=>[k,{recent:'missing'}]))};
const part={schema_version:'shorts_fundamental_packet_part.v1',records:[record]};
const window=n=>({trades:n,admitted:n,issuers:n,performance_valid:n!==10,unresolved:n===10?1:0,performance:n===10?{}:{net_pnl:123.45,calmar_full_period:.75,cagr:.01},trade_statistics:{win_rate:.5},costs:{borrow:9.25},annual:[{year:'2026',trades:n}],skipped:{minimum_order_or_capacity:1}});
let study={schema_version:'shorts_fundamental_study.v1',authority:'none',production_policy_changed:false,data_cost_usd:0,bindings:{research_summary_sha256:'a'.repeat(64)},cases:keys.map((id,i)=>({id,label:id,windows:{recent:window(10+i),full:window(20+i)},chronological_periods:[],cost_sensitivities:[],without_top_issuer:{},qualification:{qualified:false}})),selection:{paper_candidate:null},packets:[{url:'data/shorts_fundamental_packets/part-000.json',sha256:hash(part)}],acquisition:{uncached_sources_pending:[]},limits:[]};
const fetch=async url=>({ok:true,arrayBuffer:async()=>new TextEncoder().encode(JSON.stringify(url.startsWith('data/shorts_fundamental_packets')?part:study)).buffer});
const ctx={window:{crypto:crypto.webcrypto},document,fetch,TextDecoder,URL};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const api=ctx.window.ShortsFundamentalViz,ref=()=>({url:'data/shorts_fundamental_research.json',sha256:hash(study),base_summary_sha256:'a'.repeat(64)});
(async()=>{
await api.open(ref());const html=mounts.get('sev-fundamental-research').innerHTML;
assert.match(html,/unresolved liability/);assert.match(html,/9.25/);assert.match(html,/2026 account results/);assert.match(html,/No fundamental policy cleared/);
api.change('full');assert.match(mounts.get('sfv-statistics').innerHTML,/>20</);
await api.search('cik/1');assert.match(mounts.get('sfv-queue').innerHTML,/&lt;img src=x&gt;/);
api.inspect('x');assert.match(mounts.get('sfv-detail').innerHTML,/&lt;script&gt;/);assert.doesNotMatch(mounts.get('sfv-detail').innerHTML,/href="javascript/);
study.data_cost_usd=1;await api.open(ref());assert.match(mounts.get('sev-fundamental-research').innerHTML,/could not be verified/);
study.data_cost_usd=0;study.bindings.research_summary_sha256='b'.repeat(64);await api.open(ref());assert.match(mounts.get('sev-fundamental-research').innerHTML,/could not be verified/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-e", script, str(root/"dashboard/shorts-fundamental-viz.js")], cwd=root,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
