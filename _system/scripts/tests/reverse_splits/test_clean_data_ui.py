"""A changed baseline or unverified source must not become a clean-data result."""
from pathlib import Path
import subprocess


def test_clean_data_ui_rejects_changed_baseline_and_escapes_source_text():
    root = Path(__file__).resolve().parents[4]
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const mounts=new Map(),document={getElementById:id=>{if(!mounts.has(id))mounts.set(id,{innerHTML:''});return mounts.get(id)}};
const record={key:'x',ticker:'<img src=x>',company:'Unsafe <script>',cik:'1234',ex_date:'2023-10-17',reported_score:70,identity_status:'confirmed_dated_SEC_cover',first_exclusion:'entry_price_unavailable',blockers:['entry_price_unavailable'],filing_sources:[],financial_evidence:[],financing_leads:[],full_underwriting:'incomplete',financing_reconciliation:'incomplete'};
const part={schema_version:'shorts_clean_queue_part.v1',records:[record]},changes={records:[{period:'recent',to_stage:'validated_prices',ticker:'<img src=x>',change:'added',before_reason:'entry_price_unavailable',after_reason:'admitted'}]};
const window=(period,n)=>({period,closed_trades:n,admitted_trades:n,scored_records:449,issuers:43});
let study={schema_version:'shorts_clean_data_research.v1',source_collection_complete:true,authority:'none',data_cost_usd:0,production_policy_changed:false,bindings:{research_summary_sha256:'a'.repeat(64)},policy_sha256:'b'.repeat(64),coverage:{confirmed_identity_records:1},stages:[{id:'original',clean_data:true,policy_sha256:'b'.repeat(64),windows:[window('recent',46),window('full',83)]}],queue:{records:1,parts:[{url:'data/shorts_clean_data_queue/part-000.json',sha256:hash(part)}]},changes:{url:'data/shorts_clean_data_changes.json',sha256:hash(changes)},limits:[]};
const fetch=async url=>({ok:true,arrayBuffer:async()=>new TextEncoder().encode(JSON.stringify(url.startsWith('data/shorts_clean_data_research')?study:url.startsWith('data/shorts_clean_data_queue')?part:changes)).buffer});
const ctx={window:{crypto:crypto.webcrypto},document,fetch,TextDecoder,URL};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const api=ctx.window.ShortsCleanDataViz,ref=()=>({url:'data/shorts_clean_data_research.json',sha256:hash(study),base_summary_sha256:'a'.repeat(64)});
(async()=>{
 await api.open(ref());assert.match(mounts.get('sev-clean-data-research').innerHTML,/original rules/);
 assert.match(mounts.get('scd-queue').innerHTML,/&lt;img src=x&gt;/);assert.doesNotMatch(mounts.get('scd-queue').innerHTML,/<img src=x>/);
 api.inspect('x');assert.match(mounts.get('scd-record').innerHTML,/&lt;script&gt;/);
 await api.search('1234');assert.match(mounts.get('scd-queue').innerHTML,/&lt;img src=x&gt;/);
 await api.changes();assert.match(mounts.get('scd-changes').innerHTML,/&lt;img src=x&gt;/);
 study.stages[0].windows[0].closed_trades=47;await api.open(ref());assert.match(mounts.get('sev-clean-data-research').innerHTML,/could not be verified/);
 study.stages[0].windows[0].closed_trades=46;study.bindings.research_summary_sha256='c'.repeat(64);await api.open(ref());assert.match(mounts.get('sev-clean-data-research').innerHTML,/could not be verified/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-e", script, str(root/"dashboard/shorts-clean-data-viz.js")], cwd=root,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
