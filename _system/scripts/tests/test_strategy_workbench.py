"""Exercise strategy routing and the actual Insights renderers without a broker."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def node(source):
    result = subprocess.run(["node", "-"], input=source, text=True, encoding="utf-8", capture_output=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr


def test_strategy_routes_and_legacy_links_keep_the_requested_workspace():
    node(r'''
const assert=require('node:assert/strict');
const S=require('./dashboard/strategy-workbench.js');
for(const section of ['backtest','announcement','forward']){
 const route=S.parseRoute('#/ideas/short-alpha/'+section+'?ticker=ABC');
 assert.equal(route.view,'systematic-shorts');assert.equal(route.strategySection,section);assert(route.canonical);assert.equal(route.query,'ticker=ABC');
}
assert.equal(S.parseRoute('#/strategies/biotech-quant/signals').view,'biotech-quant');
assert.equal(S.parseRoute('#/insights/memory/biotech').view,'biotech-quant');
assert.equal(S.parseRoute('#/strategies/biotech-quant/forward'),null);
assert.equal(S.stateFromHash(S.route('biotech-quant','signals',{query:'A & B',page:2})).query,'A & B');
assert.equal(S.stateFromHash(S.route('biotech-quant','signals',{query:'A & B',page:2})).page,2);
''')


def test_five_strategy_navigation_has_the_requested_order_and_active_parent():
    html = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
    nav = html.split('id="strategies-subnav"', 1)[1].split('</nav>', 1)[0]
    labels = ['>SPX 0DTE<', '>LS Algo<', '>Systematic Shorts<', '>Darwin CC ', '>Biotech Quant<']
    assert [nav.index(label) for label in labels] == sorted(nav.index(label) for label in labels)
    assert "['spx-0dte', 'letf', 'systematic-shorts', 'darwin', 'biotech-quant'].includes(view)" in html


def test_memory_filters_review_scope_and_biotech_extraction():
    node(r'''
global.window=global;
const assert=require('node:assert/strict');require('./dashboard/search-match.js');require('./dashboard/insights-viz.js');
const escapeHtml=v=>String(v??'').replaceAll('<','&lt;').replaceAll('>','&gt;');
const linkHtml=(url,label)=>`<a href="${url}">${escapeHtml(label)}</a>`;
const memory={summary:{claim_count:2},claim_ledger:[{ticker:'AAA',claim:'OLD_CLAIM',date:'2020-01-01'},{ticker:'AAA',claim:'ARCHIVED_CLAIM',date:'2020-01-01',lifecycle:'superseded'}],review_queue:[{ticker:'AAA',reason:'AAA_REVIEW'},{ticker:'ZZZ',reason:'ZZZ_REVIEW'}]};
const insights={letter_index:[{quarter:'2026Q3',letter_date:'2026-09-30',fund:'Example'}]};
const options={escapeHtml,linkHtml,activeSection:'memory',memory,quarter:'latest'};
let html=InsightsViz.renderInsightsPanel(insights,options);
assert(html.includes('OLD_CLAIM'));assert(!html.includes('ARCHIVED_CLAIM'));assert(!html.includes('data-memory-view="biotech"'));
html=InsightsViz.renderInsightsPanel(insights,{...options,memoryLifecycleFilter:'all'});assert(html.includes('ARCHIVED_CLAIM'));
html=InsightsViz.renderInsightsPanel(insights,{...options,memoryViewMode:'review',fundSearch:'AAA',bookOnly:true,tickers:[{ticker:'AAA',in_holdings:true}]});
assert(html.includes('AAA_REVIEW'));assert(!html.includes('ZZZ_REVIEW'));
assert(!html.includes('Methodology library'));
''')


def test_ticker_sort_pagination_and_actual_displayed_evidence_dates():
    node(r'''
global.window=global;
const assert=require('node:assert/strict');require('./dashboard/search-match.js');require('./dashboard/insights-viz.js');
const escapeHtml=v=>String(v??'');const linkHtml=(u,t)=>`<a href="${u}">${t}</a>`;
const row=(ticker,date,mat,tier)=>({ticker,company:ticker,essential_insights:{source_mix:['superinvestor_letter'],owner:{date,title:ticker+' ownership change',summary:'Changed ownership',source:'superinvestor_letter'},insider_materiality:mat,insider_tier:tier}});
const options={escapeHtml,linkHtml,activeSection:'tickers',tickerSourceFilter:'ownership',tickerViewMode:'history',tickerSortMode:'fresh',tickers:[row('AAA','2020-01-01',90,'signal'),row('ZZZ','2026-10-01',10,'signal')]};
let html=InsightsViz.renderInsightsPanel({},options);
assert.deepEqual([...html.matchAll(/data-ticker-insight="([^"]+)"/g)].map(m=>m[1]),['ZZZ','AAA']);
assert(html.includes('2020-01-01'));assert(!html.includes('class="macro-desk"'));
const rows=Array.from({length:85},(_,i)=>row('T'+String(i).padStart(3,'0'),'2026-10-01',null,null));
html=InsightsViz.renderInsightsPanel({},{...options,tickers:rows,tickerPage:2});
assert.equal([...html.matchAll(/data-ticker-insight="([^"]+)"/g)].length,5);assert(html.includes('85 matching companies'));
''')


def test_biotech_workspace_renders_data_and_escapes_source_content():
    node(r'''
const assert=require('node:assert/strict');const S=require('./dashboard/strategy-workbench.js');
const doc={as_of:'2026-10-29',summary:{universe:2,scored:1},signals:[{ticker:'AAA',company:'<script>unsafe</script>',strategy_score:80,in_book:true}],coverage:[],history:{quarters:{}},protocol:{},paper:{},backtest:{},funds:[],experiments:[]};
for(const section of ['overview','signals','portfolio','backtest','risk','research']){
 const html=S.renderBio(doc,{section,query:'',scope:'universe',direction:'all',size:'all',flag:'all',page:0});
 assert(html.includes('Biotech Quant'));assert(!html.includes('<script>unsafe</script>'));
}
assert.equal(S.bioFiltered(doc,{query:'AAA',scope:'book',direction:'all',size:'all',flag:'all'}).length,1);
assert.equal(S.bioFiltered(doc,{query:'ZZZ',scope:'book',direction:'all',size:'all',flag:'all'}).length,0);
''')


def test_unrelated_news_matches_do_not_displace_company_evidence():
    node(r'''
global.window=global;
const assert=require('node:assert/strict');require('./dashboard/search-match.js');require('./dashboard/insights-viz.js');
const noise={source:'news',title:'Union Gilloise run riot against Hapoel — Yahoo Sports',date:'2026-10-23'};
const owner={source:'superinvestor_letter',title:'Ownership changed',date:'2026-06-30'};
assert.equal(InsightsViz.pickPrimaryInsight({latest:noise,owner}).title,'Ownership changed');
const memory={claim_ledger:[{ticker:'RIOT',source_type:'news',claim:noise.title,date:noise.date}]};
const options={escapeHtml:v=>String(v??''),linkHtml:(u,t)=>`<a href="${u}">${t}</a>`,activeSection:'memory',memory};
assert(!InsightsViz.renderInsightsPanel({},options).includes('Yahoo Sports'));
const history=InsightsViz.renderInsightsPanel({},{...options,memoryLifecycleFilter:'all'});
assert(history.includes('Yahoo Sports'));assert(history.includes('Possible unrelated source match'));
''')
