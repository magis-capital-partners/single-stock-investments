'use strict';
// Additional as-of fundamentals for the reconciled third-plus cohort. No network.
const F=require('./third_plus_signal/features.cjs'),R=require('./third_plus_reconciliation_engine.cjs'),A=require('./short_framework/adapters.cjs');
const DAY=86400000,finite=Number.isFinite,days=(a,b)=>(Date.parse(b)-Date.parse(a))/DAY;
const ALIASES={
 net_income:['us-gaap:NetIncomeLoss','ifrs-full:ProfitLoss'],
 operating_income:['us-gaap:OperatingIncomeLoss','ifrs-full:ProfitLossFromOperatingActivities'],
 revenue:['us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax','us-gaap:Revenues','us-gaap:SalesRevenueNet','us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax','ifrs-full:Revenue'],
 assets:['us-gaap:Assets','ifrs-full:Assets'],
 equity:['us-gaap:StockholdersEquity','ifrs-full:Equity'],
 debt_due:['us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths','ifrs-full:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths']
};
const state=(value,reason,extra={})=>({state:value===null?'unknown':value?'pass':'fail',reason,...extra});
function rows(raw,docs,at){
 const wanted=new Set(Object.values(ALIASES).flat()),all=R.publicRows(raw,docs,at);
 for(const name of wanted){const [ns,tag]=name.split(':');for(const [unit,vs]of Object.entries(raw.facts?.[ns]?.[tag]?.units||{}))for(const v of vs){
 const known=v.filed?A.nyClock(A.dateAfter(v.filed),'00:00:00'):null;
 if(v.accn&&v.end&&v.end<=at.slice(0,10)&&finite(v.val)&&known&&Date.parse(known)<=Date.parse(at))all.push({...v,tag:name,unit,source:'SEC_companyfacts',source_url:raw.__source_url,source_sha256:raw.__source_sha256,known_at:known,dimensions:[]});
 }}
 return all.filter(f=>!f.dimensions?.length);
}
function metricRows(all,tag,currency){
 const chosen=new Map();for(const f of all.filter(f=>f.tag===tag&&f.unit===currency)){
 const key=[f.start||'',f.end,f.accn].join('|'),prior=chosen.get(key),rank=f=>(f.source==='original_inline_context'?1000:0)+(f.decimals==='INF'?100:Number(f.decimals)||0)+(f.row_label?1:0);
 if(!prior||rank(f)>rank(prior))chosen.set(key,f);
 else if(rank(f)===rank(prior)&&f.val!==prior.val)chosen.set(key,{...prior,conflict:true});
 }
 return [...chosen.values()].filter(f=>!f.conflict);
}
function flow(all,metric,currency,anchor){
 for(const tag of ALIASES[metric]){const v=F.ttmFlow(metricRows(all,tag,currency),anchor);if(v)return {...v,tag};}return null;
}
function priorYear(anchor){const d=new Date(anchor+'T12:00:00Z'),m=d.getUTCMonth();d.setUTCFullYear(d.getUTCFullYear()-1);if(d.getUTCMonth()!==m)d.setUTCDate(0);return d.toISOString().slice(0,10);}
function pair(all,metric,currency,anchor){
 for(const tag of ALIASES[metric]){const rs=metricRows(all,tag,currency),current=F.ttmFlow(rs,anchor),prior=F.ttmFlow(rs,priorYear(anchor));if(current&&prior)return {current:{...current,tag},prior:{...prior,tag},tag};}return null;
}
function point(all,metric,currency,anchor){
 for(const tag of ALIASES[metric]){const rs=metricRows(all,tag,currency).filter(f=>!f.start&&f.end===anchor).sort((a,b)=>b.filed.localeCompare(a.filed));
 if(!rs.length)continue;const latest=rs.filter(f=>f.filed===rs[0].filed);if(new Set(latest.map(f=>f.val)).size!==1)return null;return {value:rs[0].val,evidence:[rs[0]],tag};}return null;
}
function quarter(flows,anchor){
 for(const r of flows.filter(f=>f.end===anchor).sort((a,b)=>b.filed.localeCompare(a.filed))){
 const n=days(r.start,r.end)+1;if(n>=60&&n<=105)return {value:r.val,days:n,evidence:[r],basis:'reported_quarter'};
 const prev=flows.filter(p=>p.start===r.start&&days(p.end,r.end)>=60&&days(p.end,r.end)<=105).sort((a,b)=>b.end.localeCompare(a.end)||b.filed.localeCompare(a.filed))[0];
 if(prev)return {value:r.val-prev.val,days:days(prev.end,r.end),evidence:[r,prev],basis:'matched_YTD_difference'};
 }return null;
}
function profile(sic){
 if(sic===null||sic===undefined)return 'unknown';
 if([6221,6770].includes(sic)||sic>=6720&&sic<=6729)return 'fund_or_trust';
 if(sic>=6020&&sic<=6099||sic>=6311&&sic<=6411)return 'financial';
 if(sic>=6111&&sic<=6163)return 'lender';
 return sic===6798?'real_estate':'operating';
}
function buildOne(snapshot,all,datedProfile=null){
 const e=snapshot.reconciliation,fin=e.financial,at=e.clock.at,currency=fin.cash.currency,anchor=fin.cash.period;
 const eligible=e.clock.entry_eligible&&fin.status==='source_reconciled';
 const ni=flow(all,'net_income',currency,anchor),oi=flow(all,'operating_income',currency,anchor),rp=pair(all,'revenue',currency,anchor),op=pair(all,'operating_income',currency,anchor);
 const asset=point(all,'assets',currency,anchor),oldAsset=point(all,'assets',currency,priorYear(anchor)),equity=point(all,'equity',currency,anchor),due=point(all,'debt_due',currency,anchor);
 const cfo=fin.cfo.value,reported=fin.reported_runway_years,q=quarter(R.totalFlows(all,currency),anchor),qRunway=q?.value<0?fin.cash.value/(-q.value*365.25/q.days):null;
 const avgAssets=asset?.value>0&&oldAsset?.value>0?(asset.value+oldAsset.value)/2:null;
 const accrual=ni&&avgAssets?(ni.value-cfo)/avgAssets:null;
 const revGrowth=rp&&rp.prior.value>0&&rp.current.value>=0?rp.current.value/rp.prior.value-1:null;
 const margin=rp&&op&&rp.current.value>0&&rp.prior.value>0?op.current.value/rp.current.value-op.prior.value/rp.prior.value:null;
 const p=datedProfile&&Date.parse(datedProfile.known_at)<=Date.parse(at)&&days(datedProfile.filed_at,at.slice(0,10))<=550?datedProfile:null;
 const applicable=!p||!['financial','lender','fund_or_trust'].includes(p.profile);
 const metric=(value,pass,reason,extra={})=>!eligible?state(null,!e.clock.entry_eligible?'no_original_entry_session':'stale_reported_observation'):state(value===null?null:pass,reason,{value,...extra});
 const signals={...snapshot.signals,
 burn:metric(cfo,cfo<0,'negative_reconciled_total_TTM_CFO'),
 operating_loss:metric(oi?.value??null,oi?.value<0,'negative_TTM_operating_income'),
 revenue15:metric(revGrowth,revGrowth<=-.15+1e-12,'TTM_revenue_decline_at_least_15pct_same_tag'),
 margin8:metric(margin,margin<=-.08+1e-12,'TTM_operating_margin_decline_at_least_8_percentage_points'),
 accrual10:metric(accrual,accrual>=.1-1e-12,'NI_minus_CFO_over_average_current_and_year_ago_assets'),
 profit_no_cash:metric(ni?.value??null,ni?.value>0&&cfo<0,'positive_TTM_net_income_with_negative_total_CFO'),
 negative_equity:metric(equity?.value??null,equity?.value<0,'negative_reported_stockholders_equity')
 };
 const distressConditions=[metric(cfo,cfo<0,'TTM_burn'),metric(reported,reported!==null&&reported<=1,'reported_TTM_runway_at_most_one_year'),state(!eligible?null:q?q.value<0&&qRunway<=1:null,'reported_quarter_runway_at_most_one_year',{value:qRunway}),signals.operating_loss,metric(due?.value??null,due?.value>fin.cash.value&&due?.value>0,'explicit_next_twelve_month_debt_maturity_exceeds_cash'),state(p?.profile==='operating'?true:null,'dated_operating_profile_required')];
 signals.debt_distress=F.andStates(distressConditions);
 if(!applicable)for(const key of ['burn','reported_runway','accrual10','profit_no_cash','debt_distress'])signals[key]=state(null,'dated_profile_disables_cash_or_accrual_lens');
 return {id:snapshot.id,issuer:snapshot.issuer,ticker:snapshot.ticker,event_date:snapshot.event_date,decision_at:at,signals,metrics:{period:anchor,currency,net_income:ni,operating_income:oi,revenue_pair:rp,operating_income_pair:op,current_assets_total:asset,year_ago_assets_total:oldAsset,equity,debt_maturity:due,quarter_cfo:q,quarter_reported_runway_years:qRunway,accrual_ratio:accrual,revenue_growth:revGrowth,margin_change:margin},profile:p||{profile:'unknown',reason:'No dated historical SIC source; generic numeric screens remain exploratory, not completed underwriting.'}};
}
const ARMS=[
 {id:'third_plus_only',requires:[],label:'Third-plus only',reference:true},
 {id:'saved',requires:['S7'],label:'Third-plus + rally veto',reference:true},
 ...[['legacy_score60','score60','Existing score ≥60'],['burn','burn','Negative operating cash flow'],['runway','reported_runway','Reported runway <6 months'],['dilution','S4','Share growth ≥25%'],['operating_loss','operating_loss','Operating loss'],['revenue15','revenue15','Revenue decline ≥15%'],['margin8','margin8','Operating margin decline ≥8pp'],['accrual10','accrual10','Accrual ratio ≥10%'],['profit_no_cash','profit_no_cash','Profit without operating cash'],['negative_equity','negative_equity','Negative equity'],['debt_distress','debt_distress','Framework debt-maturity distress'],['rapid_repeat','S3','Previous split within 180 days'],['weak_close','S5','Weak split-day close'],['price_weakness','S6','Prior 20-session return ≤−20%']].map(([id,key,label])=>({id,requires:['S7',key],label})),
 {id:'burn_dilution',requires:['S7','burn','S4'],label:'Cash burn + dilution'},
 {id:'runway_dilution',requires:['S7','reported_runway','S4'],label:'Short reported runway + dilution'},
 {id:'loss_dilution',requires:['S7','operating_loss','S4'],label:'Operating loss + dilution'},
 {id:'runway_dilution_loss',requires:['S7','reported_runway','S4','operating_loss'],label:'Short runway + dilution + operating loss'},
 {id:'runway_dilution_revenue',requires:['S7','reported_runway','S4','revenue15'],label:'Short runway + dilution + revenue decline'}
];
function armState(s,arm,covered=false){
 if(!s)return state(null,'missing_feature_snapshot');
 if(!arm.requires.length)return state(true,'unfiltered');
 const vs=arm.requires.map(k=>s.signals[k]||state(null,'missing_feature'));
 if(covered){if(arm.requires.includes('S7')&&s.signals.S7?.state!=='pass')return state(s.signals.S7?.state==='fail'?false:null,'saved_rally_veto_required_in_matched_control');return state(vs.every(v=>v.state!=='unknown')?true:null,'same_feature_covered_saved_screen');}
 return F.andStates(vs);
}
module.exports={ALIASES,state,rows,metricRows,flow,pair,point,priorYear,quarter,profile,buildOne,ARMS,armState};
