#!/usr/bin/env node
'use strict';
// Reusable selection over completed offline feature snapshots. No order route.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'../..'),BASE=path.join(ROOT,'_system/data/reverse_splits/third_plus_signal_study');
const PRIVATE=path.join(ROOT,'_system/data/reverse_splits/local/third_plus_signal_study');
const CONFIG=path.join(BASE,'saved_screens/third_plus_no_50pct_rally.v1.json');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
function write(file,data){fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,typeof data==='string'?data:JSON.stringify(data,null,2)+'\n');}
function validate(config){
 if(config.schema!=='third_plus_saved_screen.v1'||config.universe.minimum_documented_reverse_split_ordinal!==3||config.filter.feature!=='S7'
  ||config.filter.completed_sessions!==5||config.filter.veto_if_any_daily_return_greater_than_or_equal_to!==.5
  ||config.filter.pass_if_maximum_daily_return_less_than!==.5||config.filter.unknown_action!=='exclude'
  ||config.additional_fundamental_requirements.length||config.production_authority!=='none')throw new Error('Unexpected saved screen definition');
 return config;
}
function evaluate(snapshot,config){
 validate(config);
 const ordinal=snapshot.control?.ordinal;
 if(!Number.isInteger(ordinal)||ordinal<1)return {decision:'unknown',reason:'reverse_split_ordinal_unavailable'};
 if(ordinal<config.universe.minimum_documented_reverse_split_ordinal)return {decision:'outside_universe',reason:'fewer_than_three_documented_reverse_splits'};
 const signal=snapshot.signals?.S7;
 if(!signal||signal.state==='unknown')return {decision:'unknown',reason:signal?.reason||'five_completed_session_rally_history_unavailable'};
 const before=snapshot.price_asof,entry=snapshot.entry_day,clock=snapshot.decision_at;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(before||'')||!/^\d{4}-\d{2}-\d{2}$/.test(entry||'')||before>=entry
  ||!Number.isFinite(Date.parse(clock))||!/(Z|[+-]\d\d:\d\d)$/.test(clock)||clock.slice(0,10)!==entry)return {decision:'unknown',reason:'completed_pre_entry_observation_clock_unavailable'};
 if(!Number.isFinite(signal.value)||signal.reason!=='no_prior_five_session_50pct_close_rally')return {decision:'unknown',reason:'unrecognized_rally_measurement'};
 const veto=signal.value>=config.filter.veto_if_any_daily_return_greater_than_or_equal_to;
 if(signal.state!==(veto?'fail':'pass'))throw new Error('Rally state/value disagree for '+snapshot.id);
 return {decision:veto?'vetoed':'selected',reason:veto?'at_least_one_prior_daily_rally_at_or_above_50pct':'third_plus_and_no_prior_daily_50pct_rally',maximum_prior_daily_return:signal.value};
}
function coverage(rows){
 return Object.fromEntries(['score60','reported_runway','S1','S2','S4'].map(id=>{
  const states={pass:0,fail:0,unknown:0},unknown_reasons={};
  for(const row of rows){const s=row.signals?.[id]||{state:'unknown',reason:'feature_missing'};states[s.state]++;if(s.state==='unknown')unknown_reasons[s.reason]=(unknown_reasons[s.reason]||0)+1;}
  return [id,{...states,calculable:states.pass+states.fail,unknown_reasons}];
 }));
}
function exportScreen(){
 const config=validate(read(CONFIG)),file=path.join(PRIVATE,'features.local.json'),snapshots=read(file),studyFile=path.join(BASE,'summary.json'),study=read(studyFile);
 if(!Array.isArray(snapshots)||snapshots.length!==study.coverage_candidates)throw new Error('Study and snapshot population disagree');
 const measured={pass:0,fail:0,unknown:0};for(const s of snapshots)measured[s.signals.S7.state]++;
 if(JSON.stringify(measured)!==JSON.stringify(study.coverage.S7))throw new Error('Study and snapshot rally coverage disagree');
 const decisions=snapshots.map(s=>({id:s.id,issuer:s.issuer,ticker:s.ticker,entry_day:s.entry_day,ordinal:s.control.ordinal,...evaluate(s,config)}));
 const counts={selected:0,vetoed:0,unknown:0,outside_universe:0};for(const d of decisions)counts[d.decision]++;
 const selected=snapshots.filter((s,i)=>decisions[i].decision==='selected');
 const binding={study_data_version:study.data_version,study_summary_sha256:hash(studyFile),feature_snapshots_sha256:hash(file),screen_definition_sha256:hash(CONFIG),screen_exporter_sha256:hash(__filename)};
 const summary={schema:'third_plus_saved_screen_result.v1',screen_id:config.id,built_at:new Date().toISOString(),price_asof:study.price_asof,source:binding,
  candidate_events:snapshots.length,counts,selected_issuers:new Set(selected.map(s=>s.issuer)).size,
  selected_ordinals:Object.fromEntries(Object.entries(Object.groupBy(selected,s=>s.control.ordinal>=5?'5+':String(s.control.ordinal))).map(([k,v])=>[k,v.length])),
  portfolio_fills_inferred:false,production_authority:'none',validation_status:config.validation_status};
 const audit={schema:'third_plus_fundamental_coverage.v1',built_at:summary.built_at,source:binding,companyfacts_issuers_present:study.audit.companyfacts_issuers,
  all_third_plus_events:{events:snapshots.length,features:coverage(snapshots)},after_saved_rally_veto:{events:selected.length,features:coverage(selected)},
  financing_documents:study.audit.financing_documents,completion_language_leads:study.audit.completion_claim_documents,independent_financing_reviews:study.audit.independent_financing_reviews,
  interpretation:'Calculable means pass or fail, not that a candidate passes the filter. Unknown combines missing/stale observations and unresolved reconciliation. Event counts are not trade counts.'};
 write(path.join(BASE,'saved_screens/third_plus_no_50pct_rally.summary.json'),summary);
 write(path.join(PRIVATE,'third_plus_no_50pct_rally.selection.local.json'),{...summary,decisions});
 write(path.join(BASE,'fundamental_coverage.json'),audit);
 const names={score60:'Existing composite fundamental score',reported_runway:'Reported cash runway',S1:'Cash pressure after funding reconciliation',S2:'Recent completed dilutive financing',S4:'Comparable six-month share dilution'};
 const table=Object.keys(names).map(id=>'| '+names[id]+' | '+audit.all_third_plus_events.features[id].calculable+'/'+snapshots.length+' | '+audit.after_saved_rally_veto.features[id].calculable+'/'+selected.length+' |').join('\n');
 const all=audit.all_third_plus_events.features,reason=(id,key)=>all[id].unknown_reasons[key]||0;
 const text='# Why fundamental calculations are unknown\n\nSource: the completed offline third-plus study, version '+study.data_version+'. The raw companyfacts cache is present for all '+study.audit.companyfacts_issuers+' candidate issuers. Missing files are not the main problem. The implemented features require values that were public before each historical entry, comparable accounting periods, and consistent cash/share units.\n\n| Calculation | Calculable on third-plus universe | Calculable after saved rally veto |\n|---|---:|---:|\n'+table+'\n\nCalculable includes both passing and failing observations. These are candidate events, before execution and portfolio constraints.\n\n## Cash runway\n\nReported runway is calculable for '+all.reported_runway.calculable+' of '+snapshots.length+' events. For the remaining '+all.reported_runway.unknown+', '+reason('S1','missing_fresh_unrestricted_cash')+' lack a qualifying unrestricted cash observation no older than 200 days, '+reason('S1','missing_comparable_TTM_CFO')+' lack comparable trailing-twelve-month operating cash flow, and '+reason('S1','no_decision_session')+' has no decision session. A standard tag/freshness restriction can exclude an issuer even when its full filing contains useful information.\n\nThe adjusted cash-pressure feature is calculable for only '+all.S1.calculable+' events because another '+reason('S1','known_or_provider_flagged_funding_requires_pro_forma_reconciliation')+' have known/provider-flagged fundraising since the cash balance that has not been reconciled. A completed financing can replenish cash. An announcement, registration or unclosed offering is insufficient to determine its cash effect. This is unfinished source reconciliation, not proof that all those cash balances are unavailable.\n\n## Financing\n\nThe cache contains '+audit.financing_documents+' financing documents and '+audit.completion_language_leads+' completion-language leads, but '+audit.independent_financing_reviews+' independently reconciled reviews. The study required two outcome-blinded reviews of transaction identity, closing, cash, saleability and share units. That is a study evidence requirement, not an SEC requirement. Extraction alone does not meet it. Accordingly S2 is unknown, rather than falsely marked as no financing. The same requirement blocks financing-dependent combinations.\n\n## Share dilution\n\nOnly '+all.S4.calculable+' of '+snapshots.length+' events have a usable six-month comparison under the implemented rule: '+reason('S4','no_same_filing_six_month_comparison')+' lack two period-end common-share observations 150–240 days apart in the same filing; '+reason('S4','cross_action_share_units_require_primary_review')+' cross a corporate action without a verified common restatement basis; '+reason('S4','missing_fresh_period_end_common_shares')+' lack a fresh qualifying period-end share count; '+reason('S1','no_decision_session')+' has no decision session. The same-filing restriction is conservative and excludes many potentially recoverable cross-filing comparisons. Weighted-average EPS shares are not an interchangeable denominator.\n\n## Closing the gaps\n\n1. Reconcile the cached financing sources into unique actual deals, including net cash and actual issuance dates; import truthful independent reviews with the existing review-import command.\n2. Extract additional share-count observations from the cached filings, then reconcile cross-filing share classes, split/ADS units and restatements under an explicitly versioned feature revision.\n3. Recover absent standard/custom cash-flow tags and annual/YTD comparisons from original filings, preserving their historical public clocks. Reassess freshness only as a declared research change.\n4. Rebuild and compare both the full universe and identical covered universes. Unknown must stay separate from false.\n\n## Saved screen\n\nThe saved screen is third-or-later reverse split AND no single adjusted daily close-to-close rise of at least 50% in the five completed sessions before entry. It currently selects '+counts.selected+' events, vetoes '+counts.vetoed+' and excludes '+counts.unknown+' unknowns. No additional fundamental condition is required. This is not a cumulative five-day rally test. It is saved for research reuse; the historical study did not validate it for live trading.\n';
 write(path.join(BASE,'FUNDAMENTAL_COVERAGE.md'),text);return summary;
}
module.exports={validate,evaluate,coverage,exportScreen};
if(require.main===module)try{console.log(JSON.stringify(exportScreen(),null,2));}catch(e){console.error(e.stack||e);process.exitCode=1;}
