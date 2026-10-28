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
 const r=d.rules.dilution,m=V.chosen(d,{rule:'dilution',policy:'E2',minutes:60,rate:.1}),b=r.price_benchmark;
 let text='# Corrected every-candidate execution audit\n\nHistorical executable account performance is **not established**. The former marked P&L and drawdown are retired, not restated as zero. Available bars and sampled venue quotes cannot establish historical usable borrow, national-price eligibility, queue priority, broker margin or complete loan/exit outcomes. No winning parameter or live strategy is selected.\n\n';
 text+='## Repaired mechanics\n\n'+d.protocol.assumptions.map(x=>'- '+x).join('\n')+'\n\n';
 text+='## Entire cohort remains visible\n\n210 original events; '+r.selected+' pass the default saved rally veto plus share-growth signal. All 21 frozen signals retain 24 account definitions. Required evidence is checked before calculating portfolio admissions and returns. Independent bar entry diagnostics do not substitute for those account results.\n\n';
 text+='| Missing requirement in default account | Candidates |\n|---|---:|\n';
 const reasons=[...new Set(m.coverage.flatMap(x=>x.reasons))].sort();
 for(const k of reasons)text+='| '+k+' | '+m.coverage.filter(x=>x.reasons.includes(k)).length+' |\n';
 text+='\nThe archive includes '+d.archive.sessions+' event sessions, '+(d.archive.counts.sampled_quotes||0)+' with sampled quotes and '+(d.archive.counts.missing_quotes||0)+' without. Missing source/symbol capture is preserved as a gap, not an empty observed market. Receipt/index/source hashes bind the local inputs. Raw licensed prices and position quantities remain private.\n\n';
 text+='## Official-price benchmark\n\nThis is a separate price-only diagnostic, not executable P&L. '+b.complete_price_pairs+' / '+b.events+' selected events have both official auction prices and resolved split/security continuity; '+b.missing_or_immature+' remain missing or immature. Complete cases are a selected subset.\n\n';
 text+='| Outcome coverage | Events |\n|---|---:|\n';for(const [k,n]of Object.entries(b.statuses))text+='| '+k+' | '+n+' |\n';
 text+='\n## Security lifecycle sources\n\n';for(const e of d.lifecycle.events)text+='- '+e.ticker+' ('+e.issuer+'), '+e.effective+': '+e.kind+(e.successor?' → '+e.successor:e.destination?' → '+e.destination:'')+'. [Primary filing]('+e.source_url+').\n';
 text+='\n## Risk and validation\n\nThe hypothetical account retains three issuers and adds declared budgets: 0.25% equity per issuer, 1% sleeve gross, a 2% loss budget under a +200% squeeze, and 80% margin usage. These are model limits; verified mode still requires the historical broker schedule. A risk breach has no assumed successful liquidation. The 21 signals and 24 settings remain retrospective; no untouched validation claim is made.\n\n';
 text+='Regression tests cover buy-limit violations, missing quotes, nonuniform bar paths, symbol transitions, split units, venue changes, stale-price gaps, evidence gating, fees and publication consistency. Passing mechanics tests does not establish historical profitability. Missing historical borrow, OTC executions or broker settlement records remain explicit unresolved inputs. No ThetaData, IB Gateway, broker session, paid acquisition or sealed holdout was accessed.\n\n';
 text+='## Reproduce offline\n\n```powershell\npython _system/scripts/third_plus_execution/venue_capture.py normalize-free --source-root <cache-repository>\nnode _system/scripts/third_plus_execution/venue_study.cjs --source-root <cache-repository>\nnode _system/scripts/third_plus_execution/venue_publish.cjs\nnode --test _system/scripts/third_plus_execution/*.test.cjs\n```\n\nThe normalizer uses existing receipt-verified files only and performs no downloads. Missing successor captures stay missing even when successor daily benchmark prices exist. Qualified replay inputs and historical lending/settlement evidence are required to produce an executable account estimate.\n\nPublication '+d.data_version+'.\n';return text;
}
function publish(check=false){
 const d=load(),files=[[path.join(DIR,'REPORT.md'),report(d)],[path.join(ROOT,'dashboard/data/third_plus_venue_execution_decisions.csv'),V.csv(d,{rule:'dilution',policy:'E2',minutes:60,rate:.1,group:'all',query:''})]];
 for(const [f,s]of files){if(check){if(fs.readFileSync(f,'utf8')!==s)throw Error('Stale venue report/export '+f);}else fs.writeFileSync(f,s);}
 console.log((check?'Verified':'Published')+' every-name conditional execution report and CSV');
}
module.exports={load,report,publish};if(require.main===module)publish(process.argv.includes('--check'));
