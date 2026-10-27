'use strict';
const fs=require('node:fs'),path=require('node:path'),{sha}=require('./archive.cjs'),V=require('../../../dashboard/third-plus-venue.js');
const ROOT=path.resolve(__dirname,'../../..'),DIR=path.join(ROOT,'_system/data/reverse_splits/third_plus_signal_study/ssr_execution_v2');
function load(){
 const bytes=fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_venue_execution.json')),d=V.validate(JSON.parse(bytes));
 const m=JSON.parse(fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_venue_execution_manifest.json')));
 if(m.sha256!==sha(bytes)||m.data_version!==d.data_version)throw Error('Venue publication hash mismatch');
 const unsigned={...d};delete unsigned.data_version;if(sha(JSON.stringify(unsigned))!==d.data_version)throw Error('Venue data version mismatch');
 for(const [f,h]of Object.entries(d.sources))if(sha(fs.readFileSync(path.join(ROOT,f)))!==h)throw Error('Stale venue source '+f);
 if(d.acquisition.authorized_cap_usd!==0||d.acquisition.reserved_cost_usd!==0)throw Error('This publication permits only $0 acquisition');
 return d;
}
const money=x=>Number.isFinite(x)?'$'+x.toFixed(2):'Unavailable';
function report(d){
 const r=d.rules.dilution,p=r.models.find(m=>m.policy==='E2'&&m.minutes===60&&m.participation===.1),ssr=r.opportunities.filter(e=>e.previous_decision==='ssr_rejected'),excluded=r.opportunities.filter(e=>['ssr_rejected','risk_capacity','missing_liquidity'].includes(e.previous_decision));
 let text='# Every-name execution on cached and $0 data\n\nThis is an explicit one-second-bar execution sensitivity. It is not observed historical execution, a borrow-verified strategy, or proof of Rule 201 compliance. Raw licensed bars and private position ledgers remain outside the public repository.\n\n';
 text+='## Coverage and outcomes\n\n| Population | Events | Independent order attempts | Modeled fills, 60m | Modeled fills, exploratory 240m | Modeled fills, full session |\n|---|---:|---:|---:|---:|---:|\n';
 for(const [label,rows]of [['Original SSR skips',ssr],['Every prior exclusion',excluded],['Default signal',r.opportunities.filter(e=>!e.execution_status.startsWith('signal_'))]])text+='| '+[label,rows.length,rows.filter(e=>e.attempted).length,rows.filter(e=>e.filled).length,rows.filter(e=>e.extended_filled).length,rows.filter(e=>e.full_session_filled).length].join(' | ')+' |\n';
 text+='\nEach independent opportunity is simulated without competition for issuer slots. It is a counterfactual attribution record. The account keeps three simultaneous short issuers; these independently executable opportunities cannot be summed as available account capacity. No-fill names remain no-fills, and signal failures remain failures.\n\n';
 text+='## Account comparisons\n\n$10m reference NAV, $100k initial parent ceiling, unchanged signal-anchored 20-session exit, 500ms latency, maximum $2k entry child, one working child per issuer. No margin-capacity or sleeve-risk admission gate. Covers can purchase at least one whole share even when its price exceeds the child-dollar ceiling.\n\n';
 text+='| Policy | Entry window | Participation | Entries | Net marked P&L | Closing drawdown | Missing cover sessions |\n|---|---:|---:|---:|---:|---:|---:|\n';
 for(const m of r.models)text+='| '+[m.policy,m.minutes===390?'Full session':m.minutes+'m',m.participation*100+'%',m.summary?.entered??'Unavailable',money(m.summary?.net_pnl),money(m.summary?.max_drawdown_dollars),m.summary?.missing_exit_sessions??'Unavailable'].join(' | ')+' |\n';
 text+='\nE0 is the matched restriction-skip control. E1 joins the modeled offer. E2 improves one modeled permitted increment. All 24 comparisons are retained for every one of the 21 frozen signals. The default remains the declared 60-minute E2/10% case. The 240-minute and full-session access extensions were added after examining first-hour no-fills and are exploratory. No parameter winner or untouched validation is claimed.\n\n';
 text+='## Evidence and assumptions\n\n'+d.protocol.assumptions.map(x=>'- '+x).join('\n')+'\n\n';
 text+='The source archive has '+d.archive.sessions+' event sessions: '+d.archive.counts.sampled_quotes+' with sampled quote paths and '+d.archive.counts.bar_quote_proxy+' requiring the lagged-bar spread proxy. Empty queried bars are retained as zero observed flow. All new requests were quoted and refreshed at $0 before download; cumulative reserved acquisition cost is $0. No ThetaData, Gateway, broker session or sealed execution holdout was accessed.\n\n';
 text+='The bar model sizes from information available before a child order, reserves cumulative and rolling past-flow capacity, then uses later bar range and volume to assign assumed fills. It never uses final-day volume to size an opening order. A uniform-within-bar price allocation and 25/50/75% capture sensitivities represent unknown buyer flow/queue. They are assumptions, not calibrated fill probabilities. Cover prices are quote/bar sensitivities; partial and unavailable covers retain obligations.\n\n';
 text+='Fractional shorts can be covered through a whole-share overbuy. Full cash and commission are charged. Any surplus long asset is assigned zero NAV credit and reported as an uncredited reserve. This does not invent a cash-in-lieu broker settlement. Unresolved identities, missing prices and remaining shorts are never silently zeroed.\n\n';
 text+='Primary account status: '+p.status+'. '+(p.summary?.missing_exit_sessions?'The marked result includes incomplete cover paths and cannot establish completed-strategy performance.':'The result remains conditional on the stated fill, borrow and national-price assumptions.')+'\n\n';
 text+='## Reproduce\n\n```powershell\npython _system/scripts/third_plus_execution/venue_capture.py plan --source-root <cache-repository>\npython _system/scripts/third_plus_execution/venue_capture.py status --source-root <cache-repository>\npython _system/scripts/third_plus_execution/venue_capture.py free-bars --source-root <cache-repository>\nnode _system/scripts/third_plus_execution/venue_study.cjs --source-root <cache-repository>\nnode _system/scripts/third_plus_execution/venue_publish.cjs\nnode --test _system/scripts/third_plus_execution/*.test.cjs\n```\n\n';
 text+='The exact source index is hash-bound and private. Public code/result hashes bind this publication. Broker behavior and borrow inventory require separate prospective confirmation; this change transmits no orders.\n\nPublication '+d.data_version+'.\n';return text;
}
function publish(check=false){
 const d=load(),files=[[path.join(DIR,'REPORT.md'),report(d)],[path.join(ROOT,'dashboard/data/third_plus_venue_execution_decisions.csv'),V.csv(d,{rule:'dilution',policy:'E2',minutes:60,rate:.1,group:'all',query:''})]];
 for(const [f,s]of files){if(check){if(fs.readFileSync(f,'utf8')!==s)throw Error('Stale venue report/export '+f);}else fs.writeFileSync(f,s);}
 console.log((check?'Verified':'Published')+' every-name conditional execution report and CSV');
}
module.exports={load,report,publish};if(require.main===module)publish(process.argv.includes('--check'));
