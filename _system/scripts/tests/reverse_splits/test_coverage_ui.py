"""Tampered, stale and ambiguous research must not masquerade as verified facts."""
from pathlib import Path
import subprocess


def test_expanded_research_verifies_bindings_and_escapes_names():
    root = Path(__file__).resolve().parents[4]
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const mounts=new Map(),document={getElementById:id=>{if(!mounts.has(id))mounts.set(id,{innerHTML:''});return mounts.get(id)}};
const id='p1_documented_estimates_fundamental_recent';
const audit={schema_version:'shorts_coverage_audit.v1',id,journal:[{key:'x',ticker:'<img src=x>',date:'2026-10-01',shares:0,reason:'entry_price_unavailable'}],announcement_plans:{},forecasts:{}};
const packet={key:'x',ticker:'<img src=x>',issuer:'cik/1',known_at:'2026-10-01',assumptions:[],imputed_signals:{},financials:{evidence:[{tag:'us-gaap:Assets',end:'2026-06-30',filed:'2026-08-01',val:100,unit:'USD',accn:'0000000001-26-000001'}]},frameworks:[],completed_underwriting:false,authority:'none',financing:{scenarios:[]}};
const row={id,policy_id:'p1',scenario_id:'documented_estimates',label:'Estimates',variant:'fundamental',window:'recent',trades:0,issuers:0,estimated_rating_trades:0,performance_valid:false,unresolved_admitted_names:1,margin_stress_breaches:0,considered_events:1,admitted_positions:0,skipped:{entry_price_unavailable:1},costs:{borrow:0,slippage:0,commission:0}};
let study={schema_version:'shorts_coverage_research.v1',authority:'none',data_cost_usd:0,paid_requests:0,frozen_rsi3_unchanged:true,bindings:{frozen_rsi3_summary_sha256:'a'.repeat(64)},coverage:{input_events:10,prepared_events:9,reported_ratings:2,estimated_ratings:7,approved_locates:0},plan:{policies:[{},{sessions:10,entry:'post_split_next_open'}]},cases:[row],assumptions:[],remaining:[],strict_case:{trades:0,reason:'no actual approvals'},audit_files:{[id]:{url:'data/shorts_coverage_audits/'+id+'.json',sha256:hash(audit)}},names:[{key:'x',url:'data/shorts_coverage_packets/'+'a'.repeat(24)+'.json',sha256:hash(packet)}]};
const fetch=async url=>({ok:true,arrayBuffer:async()=>new TextEncoder().encode(JSON.stringify(url.startsWith('data/shorts_coverage_research')?study:url.startsWith('data/shorts_coverage_audits')?audit:packet)).buffer});
const ctx={window:{crypto:crypto.webcrypto},document,fetch,TextDecoder,URL};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const api=ctx.window.ShortsCoverageViz;
const ref=()=>({url:'data/shorts_coverage_research.json',sha256:hash(study),base_summary_sha256:'a'.repeat(64)});
(async()=>{
 await api.open(ref());assert.match(mounts.get('sev-coverage-research').innerHTML,/documented assumptions/);
 assert.match(mounts.get('sev-coverage-research').innerHTML,/not an observed trade/);
 await api.inspect(id);assert.match(mounts.get('scv-audit').innerHTML,/&lt;img src=x&gt;/);
 assert.doesNotMatch(mounts.get('scv-audit').innerHTML,/<img src=x>/);
 await api.name('x');assert.match(mounts.get('scv-name').innerHTML,/Announcement plan versus entry decision/);
 assert.match(mounts.get('scv-name').innerHTML,/Full underwriting remains incomplete/);
 assert.match(mounts.get('scv-name').innerHTML,/Reported financial facts and filing dates/);
 assert.match(mounts.get('scv-name').innerHTML,/https:\/\/www.sec.gov\/Archives\/edgar\/data\/1\/000000000126000001\//);
 study={...study,data_cost_usd:1};await api.open(ref());assert.match(mounts.get('sev-coverage-research').innerHTML,/could not be verified/);
 study={...study,data_cost_usd:0,bindings:{frozen_rsi3_summary_sha256:'b'.repeat(64)}};
 await api.open(ref());assert.match(mounts.get('sev-coverage-research').innerHTML,/could not be verified/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-e", script, str(root/"dashboard/shorts-coverage-viz.js")],
                            cwd=root, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
