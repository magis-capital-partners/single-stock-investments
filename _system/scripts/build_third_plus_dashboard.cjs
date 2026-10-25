#!/usr/bin/env node
'use strict';
// Publishes aggregates plus categorical event decisions and derived sizing dollars.
// No raw prices, volumes, quantities, per-event returns or broker data.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'../..'),STUDY='_system/data/reverse_splits/third_plus_signal_study/';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const read=n=>JSON.parse(fs.readFileSync(path.join(ROOT,STUDY,n),'utf8'));
const SOURCE_FILES=['plan.json','saved_screens/third_plus_no_50pct_rally.summary.json','reconciliation_v2/summary.json','fundamental_filters_v3/summary.json','fundamental_filters_v3/manifest.json','fundamental_filters_v3/validation.json','fundamental_filters_v3/implementation_revision.json','fundamental_filters_v3/decision_audit.json','fundamental_filters_v3/experiment_register.json'];
const CASES=[
 {id:'primary',label:'20 sessions · reference sizing',note:'$1m reference NAV; 1% participation; three-name limit; existing squeeze reserves.'},
 {id:'h10',label:'10 sessions · reference sizing',note:'Same account, costs and participation; common 20-session maturity exclusion.'},
 {id:'stress',label:'20 sessions · high costs',note:'150% annual borrow and 4.25% roundtrip execution assumption; reference sizing.'},
 {id:'lower_cost',label:'20 sessions · lower costs',note:'20% annual borrow and 1% roundtrip execution assumption; reference sizing.'},
 {id:'cap_0.001',label:'20 sessions · 0.1% participation',note:'Tighter historical volume cap; the same account limits.'},
 {id:'cap_0.05',label:'20 sessions · 5% participation',note:'Looser historical volume cap; the same account limits. Available borrowing remains unverified.'},
 {id:'full_20',label:'20 sessions · hypothetical $25k fills',hypothetical:true,note:'No account or volume cap. Assumes the target can be borrowed, filled and covered; capacity is not established.'},
 {id:'full_10',label:'10 sessions · hypothetical $25k fills',hypothetical:true,note:'No account or volume cap. Assumed borrowing and execution; not an achievable-profit estimate.'},
 {id:'SSR_proxy',label:'20 sessions · SSR fill sensitivity',hypothetical:true,note:'Unsupported passive-capture proxy for restricted short sales; not verified execution.'}
];
const METRICS=['horizon','cost','cap','nav','target','maximumNames','ssrMode','entered','issuers','closed','net_pnl','gross_pnl','borrow_cost','commissions_and_fees','execution_cost','mean_position','median_position','max_drawdown_dollars','worst_trade','best_trade','worst_day','win_rate_closed','risk_breach_sessions','open_positions','open_liability','stale_sessions','overdue_positions','fractional_residuals','identity_unresolved','full_target_entries','pnl_without_best_issuer','pnl_without_best5_issuers','common_mean_monthly','closed_trade_pnl','open_trade_marked_pnl','peak_exposure','peak_margin','broker_verified_entries','funnel','entry_years'];
function compact(s){
 const out=Object.fromEntries(METRICS.map(k=>[k,s[k]??null]));
 out.monthly=s.common_monthly.map(m=>[m.month,m.pnl]);
 return out;
}
function build(){
 const audit=read('fundamental_filters_v3/decision_audit.json');
 const doc=read('fundamental_filters_v3/summary.json'),recon=read('reconciliation_v2/summary.json'),saved=read('saved_screens/third_plus_no_50pct_rally.summary.json'),plan=read('plan.json'),validation=read('fundamental_filters_v3/validation.json'),manifest=read('fundamental_filters_v3/manifest.json');
 const sourceHashes=Object.fromEntries(SOURCE_FILES.map(n=>[STUDY+n,sha(fs.readFileSync(path.join(ROOT,STUDY,n)))]));
 if(sourceHashes[STUDY+'fundamental_filters_v3/summary.json']!==manifest.outputs['summary.json'])throw new Error('Study summary does not match its manifest');
 if(doc.parent_reconciliation!==recon.data_version||doc.data_version!==validation.data_version)throw new Error('Mixed research versions');
 const models={primary:Object.fromEntries(doc.primary.map(r=>[r.arm,compact(r.summary)]))};
 for(const c of CASES.slice(1))models[c.id]=Object.fromEntries(doc.scenarios.filter(s=>s.kind===c.id).map(s=>[s.arm,compact(s.summary)]));
 const rules=doc.protocol.arms.map(a=>{const row=doc.primary.find(r=>r.arm===a.id);return {...a,coverage:row.coverage,increment:row.vs_saved.incremental_net,issuer_interval:row.vs_saved.issuer_bootstrap_95,calendar_interval:row.vs_saved.calendar_block_total_95,holm_p:row.holm_p,covered_increment:row.vs_covered.incremental_net,decision:row.decision};});
 const data={schema:'third_plus_dashboard.v1',built_at:doc.built_at,market_through:doc.price_asof,first:doc.common_first,months:doc.common_months,data_version:doc.data_version,reconciliation_version:recon.data_version,
 cohort:{events:doc.events,issuers:plan.baseline_definition.issuers,saved_events:saved.counts.selected,saved_issuers:saved.selected_issuers,vetoed:saved.counts.vetoed,unknown_rally:saved.counts.unknown},
 journey:[
 {title:'Explore reverse splits',value:'Size + repeat count',detail:'Earlier studies examined split magnitude and repeated actions. A large split ratio alone was not treated as a proven short signal.'},
 {title:'Freeze the third-plus cohort',value:doc.events+' events · '+plan.baseline_definition.issuers+' issuers',detail:'Count documented distinct prior actions by SEC issuer. Use only history known before the decision.'},
 {title:'Save the rally veto',value:saved.counts.selected+' candidates remain',detail:'Exclude any single adjusted daily close-to-close rise of at least 50% in the five completed sessions before entry. Unknown history is excluded.'},
 {title:'Reconcile the filings',value:'210 cash + cash-flow records',detail:'Recover original contexts, total operating cash flow and comparable share units. Exact dilution for 209 events; one proven threshold bound.'},
 {title:'Compare fixed additions',value:doc.protocol.primary_tests+' added rules',detail:doc.validation.model_definitions+' model definitions; '+doc.validation.unique_replays+' unique replays. Keep account rules, clocks and costs comparable.'},
 {title:'Check what survives',value:doc.finalists.length+' validated additions',detail:'Require uncertainty, concentration, chronology, costs and exit obligations to pass. The highest historical profit is not an established optimum.'}
 ],
 rules,cases:CASES,models,audit,coverage:doc.coverage,feature_rules:doc.protocol.feature_rules,profiles:doc.profiles,
 reconciliation:{cash:recon.cash_numeric,cfo:recon.ttm_cfo_numeric,exact_share_growth:recon.share_growth_numeric,dilution_threshold:recon.share_threshold_resolved,stale_cash:recon.remaining_source_limitations.stale_cash_observations,stale_shares:recon.remaining_source_limitations.stale_share_observations,missing_entry:recon.no_original_entry_session,financial_reports:recon.financial_reports_recovered,current_reports:recon.financing_reports,transaction_reports:recon.full_transaction_reports,source_files:recon.validation.recovered_source_files_hash_verified,financing_adjusted_cash_verified:recon.all_210_financing_adjusted_cash_verified,independent_financing_reviews_complete:recon.all_210_independent_financing_reviews_complete},
 tests:{node_passed:validation.node_tests.passed,python_passed:validation.python_tests.passed,future_public_evidence:validation.future_public_evidence,baseline_replications:validation.baseline_replications.length,covered_positions_checked:validation.covered_control_position_checks,models:doc.validation.model_definitions,unique_replays:doc.validation.unique_replays,primary_claims:doc.protocol.primary_tests,validated_additions:doc.finalists.length},
 chronology:{quarters:doc.walk_forward.decisions.length,selected_additions:doc.walk_forward.decisions.filter(q=>q.arm!=='saved').length,minimum_training_issuers:30,net_pnl:doc.walk_forward.summary.net_pnl},
 issuer_removal_replays:doc.issuer_removal_replays.map(r=>({arm:r.arm,count:r.count,net_pnl:r.summary.net_pnl,open_positions:r.summary.open_positions})),
 verified_entries:doc.verified_execution.entered,production_authority:'none',source_hashes:sourceHashes,
 links:{report:'https://github.com/magis-capital-partners/single-stock-investments/blob/main/'+STUDY+'fundamental_filters_v3/REPORT.md',recommendation:'https://github.com/magis-capital-partners/single-stock-investments/blob/main/'+STUDY+'fundamental_filters_v3/RECOMMENDATION.md',protocol:'https://github.com/magis-capital-partners/single-stock-investments/blob/main/'+STUDY+'fundamental_filters_v3/protocol.json',reconciliation:'https://github.com/magis-capital-partners/single-stock-investments/blob/main/'+STUDY+'reconciliation_v2/REPORT.md'}};
 if(audit.verification.frozen_manifest_sha256!==sourceHashes[STUDY+'fundamental_filters_v3/manifest.json']||audit.verification.experiment_register_sha256!==sourceHashes[STUDY+'fundamental_filters_v3/experiment_register.json']||audit.verification.engine_sha256!==manifest.freeze.code['_system/scripts/reverse_split_repeat_study.cjs']||audit.verification.features_sha256!==manifest.features_sha256)throw new Error('Decision audit source fingerprints do not match');
 if(audit.schema!=='third_plus_decision_audit.v1'||audit.data_version!==doc.data_version||audit.events.length!==210||audit.verification.models!==189||audit.verification.positions_and_daily_paths_exact!==true)throw new Error('Incomplete decision audit');
 for(const c of CASES)for(const r of rules){const m=models[c.id][r.id],a=audit.models[c.id]?.[r.id];if(!a||a.statuses.length!==210||a.statuses.some(s=>!s))throw new Error('Missing event decisions');for(const [key,n]of Object.entries(m.funnel)){if(key!=='selected'&&a.statuses.filter(s=>s===key).length!==n)throw new Error('Event audit does not reconcile: '+c.id+' / '+r.id+' / '+key);}if(a.statuses.filter(s=>!s.startsWith('signal_')).length!==m.funnel.selected)throw new Error('Audit selection mismatch');for(const [i,d]of Object.entries(a.details))if(a.statuses[i]==='entered'&&(!Number.isFinite(d.size?.notional)||!d.position||!d.size.binding.length))throw new Error('Missing admitted size');}
 if(data.cohort.events!==210||rules.length!==21||rules.some(r=>CASES.some(c=>!models[c.id][r.id])))throw new Error('Incomplete study publication');
 for(const byRule of Object.values(models))for(const m of Object.values(byRule)){
 if(Math.abs(m.monthly.reduce((sum,p)=>sum+p[1],0)-m.net_pnl)>.01)throw new Error('Monthly P&L does not reconcile');
 const excluded=Object.entries(m.funnel).filter(([k])=>!['selected','entered'].includes(k)).reduce((n,[,v])=>n+v,0);
 if(excluded+m.entered!==m.funnel.selected)throw new Error('Funnel does not reconcile');
 }
 return data;
}
function publish(check=false){
 const doc=build(),body=JSON.stringify(doc)+'\n',file=path.join(ROOT,'dashboard/data/third_plus_study.json'),manifest=JSON.stringify({schema:'third_plus_dashboard_manifest.v1',data_version:doc.data_version,payload:'third_plus_study.json',sha256:sha(body)},null,2)+'\n',mf=path.join(ROOT,'dashboard/data/third_plus_study_manifest.json');
 const D=require('../../dashboard/third-plus-study-details.js'),csvs=[['exclusions','decisions','selected_exclusions'],['all_decisions','decisions','all'],['sizing','sizes','entered']].map(([name,kind,filter])=>({file:path.join(ROOT,'dashboard/data/third_plus_dilution_primary_'+name+'.csv'),body:D.csv(doc,{rule:'dilution',case:'primary',auditFilter:filter},kind).replaceAll('\r\n','\n')}));
 if(check){if(fs.readFileSync(file,'utf8')!==body||fs.readFileSync(mf,'utf8')!==manifest||csvs.some(c=>fs.readFileSync(c.file,'utf8')!==c.body))throw new Error('Dashboard study snapshot is stale');return;}
 for(const c of csvs)fs.writeFileSync(c.file,c.body);
 fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,body);fs.writeFileSync(mf,manifest);console.log('Published '+doc.rules.length+' rules / '+doc.cases.length+' cases; '+Buffer.byteLength(body)+' bytes');
}
module.exports={build,publish,compact,CASES};
if(require.main===module)publish(process.argv.includes('--check'));
