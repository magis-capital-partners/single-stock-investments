'use strict';
const fs=require('node:fs'),path=require('node:path');
const F=require('./third_plus_signal/features.cjs'),A=require('./short_framework/adapters.cjs');
const DAY=86400000,age=(a,b)=>(Date.parse(b)-Date.parse(a))/DAY;
const short=f=>f.tag.split(':').at(-1),finite=Number.isFinite;
const nextAt=d=>A.nyClock(A.dateAfter(d),'00:00:00');
function clock(e){if(e.decision_at)return {at:e.decision_at,basis:'original_study_entry_clock',entry_eligible:true};let d=A.dateAfter(e.event_date);while([0,6].includes(new Date(d+'T12:00:00Z').getUTCDay()))d=A.dateAfter(d);return {at:A.nyClock(d,'09:25:00'),basis:'prospective_next_weekday_financial_snapshot_only',entry_eligible:false};}
function publicRows(raw,docs,at){
 const rows=[];
 for(const [ns,tags]of Object.entries(raw.facts||{}))for(const [tag,data]of Object.entries(tags)){
 if(!/Cash|OperatingActivities|CommonStockSharesOutstanding|EntityCommonStockSharesOutstanding|^(Assets|Liabilities|StockholdersEquity|NetIncomeLoss|Revenues|RevenueFromContractWithCustomerExcludingAssessedTax)$/.test(tag))continue;
 for(const [unit,values]of Object.entries(data.units||{}))for(const v of values)if(v.end&&v.filed&&v.accn&&finite(v.val)&&v.end<=at.slice(0,10)&&Date.parse(nextAt(v.filed))<=Date.parse(at))rows.push({...v,tag:ns+':'+tag,unit,source:'SEC_companyfacts',source_url:raw.__source_url||null,source_sha256:raw.__source_sha256||null,known_at:nextAt(v.filed),dimensions:[]});}
 for(const doc of docs)if(doc.filed_at&&Date.parse(nextAt(doc.filed_at))<=Date.parse(at))for(const v of doc.facts)if(v.end&&v.end<=at.slice(0,10)&&finite(v.value))rows.push({...v,val:v.value,filed:doc.filed_at,accn:doc.accession,source:'original_inline_context',source_url:doc.source_url,source_sha256:doc.source_sha256,known_at:nextAt(doc.filed_at)});
 return rows;
}
function dedup(rows){
 const by=new Map();for(const r of rows){const key=[r.tag,r.unit,r.start||'',r.end,r.accn,JSON.stringify(r.dimensions),r.context_id||'',r.row_label||''].join('|'),old=by.get(key);
 if(!old||r.source==='original_inline_context')by.set(key,r);}
 return [...by.values()];
}
function compact(f){if(!f)return null;const {row_label,dimensions,...rest}=f;return {...rest,row_label:row_label?.slice(0,450),dimensions};}
function cash(rows){
 const originalKeys=new Set(rows.filter(f=>f.source==='original_inline_context').map(f=>[f.tag,f.unit,f.start||'',f.end,f.accn].join('|')));
 const consolidated=dedup(rows.filter(f=>f.source==='original_inline_context'||!originalKeys.has([f.tag,f.unit,f.start||'',f.end,f.accn].join('|')))).filter(f=>!f.start&&!f.dimensions.length&&/^[A-Z]{3}$/.test(f.unit)&&f.val>=0);
 const eligible=[];
 for(const f of consolidated){const tag=short(f),label=(f.row_label||'').split(/\s+(?:[$€£]\s*)?[(−-]?\d/)[0].trim();let basis,priority;
 if(tag==='CashAndCashEquivalentsAtCarryingValue'||tag==='CashAndCashEquivalents'){basis='reported_unrestricted_cash_and_equivalents';priority=3;}
 else if(tag==='Cash'){basis='reported_cash_excluding_restricted';priority=2;}
 else if(/CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents/.test(tag)&&/^cash(?: and cash equivalents)?[,:]?\s*$/i.test(label)){basis='balance_row_identifies_cash_without_restricted_caption';priority=1;}
 if(basis){
 const related=consolidated.filter(r=>r.accn===f.accn&&r.end===f.end&&r.unit===f.unit);
 const includesRestricted=related.some(r=>r.tag===f.tag&&/includes.{0,100}restricted cash/i.test(r.row_label||''));
 if(includesRestricted){const restricted=related.find(r=>['RestrictedCash','RestrictedCashAndCashEquivalents'].includes(short(r)));if(!restricted||restricted.val>f.val)continue;eligible.push({...f,val:f.val-restricted.val,cash_classification:'reported_cash_less_explicit_restricted_cash',restricted_cash_evidence:compact(restricted),priority});}
 else eligible.push({...f,cash_classification:basis,priority});
 }
 }
 eligible.sort((a,b)=>b.end.localeCompare(a.end)||b.priority-a.priority||b.filed.localeCompare(a.filed));
 const newestEnd=eligible[0]?.end; const statement=eligible.filter(f=>f.end===newestEnd&&f.source==='original_inline_context'&&/^(?:cash|cash and cash equivalents)[\s,(:$]/i.test(f.row_label||'')); if(statement.length){const keep=new Set(statement);eligible.splice(0,eligible.length,...statement);} const best=eligible[0];if(!best)return {status:'unresolved_unrestricted_cash_classification'};
 const currencies=new Set(eligible.filter(x=>x.end===best.end&&x.priority===best.priority).map(x=>x.unit));
 if(currencies.size!==1)return {status:'ambiguous_current_cash_currency',choices:[...currencies]};
 return {status:'source_reconciled',value:best.val,period:best.end,currency:best.unit,basis:best.cash_classification,evidence:compact(best)};
}
function totalFlows(rows,currency){
 const original=new Set(rows.filter(f=>f.source==='original_inline_context').map(f=>[f.tag,f.start,f.end,f.accn,f.unit,JSON.stringify(f.dimensions)].join('|')));
 rows=rows.filter(f=>f.start&&f.unit===currency&&(f.source==='original_inline_context'||!original.has([f.tag,f.start,f.end,f.accn,f.unit,JSON.stringify(f.dimensions)].join('|'))));
 const precision=f=>f.decimals==='INF'?100:Number.isFinite(Number(f.decimals))?Number(f.decimals):-100;
 function best(list){return list.slice().sort((a,b)=>precision(b)-precision(a)||Number(!a.row_label)-Number(!b.row_label))[0];}
 const map=new Map();for(const f of rows){const key=[f.start,f.end,f.accn].join('|'),g=map.get(key)||[];g.push(f);map.set(key,g);}
 const result=[];
 for(const all of map.values()){
 const v=all.filter(f=>!f.dimensions.length);
 const continuing=f=>short(f)==='NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'||(/continuing operations/i.test(f.row_label||'')&&/OperatingActivities/.test(short(f)));
 const total=best(v.filter(f=>(short(f)==='NetCashProvidedByUsedInOperatingActivities'||short(f)==='CashFlowsFromUsedInOperatingActivities')&&!continuing(f)));
 if(total){result.push({...total,scope:'reported_total'});continue;}
 const cont=best(v.filter(continuing));let disc=best(v.filter(f=>(short(f)==='CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations'||(f.tag==='sbev:OperatingCashFlows'&&/^Operating cash flows/i.test(f.row_label||'')))));
 if(!disc){
  const components=new Map();for(const f of all.filter(f=>short(f)==='CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations'&&f.dimensions.length)){
   const business=f.dimensions.find(d=>/IncomeStatementBalanceSheetAndAdditionalDisclosuresByDisposalGroupsIncludingDiscontinuedOperationsAxis/.test(d.axis));if(!business)continue;
   const prev=components.get(business.member);if(!prev||precision(f)>precision(prev))components.set(business.member,f);
  }
  const netScopes=new Map();for(const f of v.filter(f=>/cash/i.test(short(f))&&/^Net (?:increase|decrease|increase \(decrease\)|decrease \(increase\)).*cash.*(?:discontinued operations|held.for.sale)/i.test(f.row_label||''))){const scope=/held.for.sale/i.test(f.row_label)?'held_for_sale':'discontinued';const prev=netScopes.get(scope);if(!prev||precision(f)>precision(prev))netScopes.set(scope,f);}
 const netTotal=netScopes.size?{...netScopes.values().next().value,val:[...netScopes.values()].reduce((sum,f)=>sum+f.val,0),components:[...netScopes.values()].map(compact)}:best(v.filter(f=>short(f)==='NetCashProvidedByUsedInDiscontinuedOperations'));
  if(components.size&&netTotal){const netParts=[...components].map(([member,f])=>best(all.filter(n=>short(n)==='NetCashProvidedByUsedInDiscontinuedOperations'&&n.dimensions.some(d=>d.member===member))));
   if(netParts.every(Boolean)&&Math.abs(netParts.reduce((s,f)=>s+f.val,0)-netTotal.val)<1e-6){const parts=[...components.values()];disc={...parts[0],tag:'derived:CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations',val:parts.reduce((s,f)=>s+f.val,0),dimensions:[],components:parts.map(compact),scope:'disposal_group_operating_components_reconciled_to_total_discontinued_cash_change',net_cash_reconciliation:{reported:compact(netTotal),components:netParts.map(compact)}};}
  }
 }
 if(cont&&disc)result.push({...cont,tag:'derived:TotalOperatingCashFlow',val:cont.val+disc.val,scope:'continuing_plus_discontinued_same_filing_period',components:[compact(cont),compact(disc)]});
 }
 return result;
}
function financial(rows,at){
 const c=cash(rows);if(c.status!=='source_reconciled')return {cash:c,cfo:{status:'blocked_by_cash'},status:'unknown'};
 const flows=totalFlows(rows,c.currency),ttm=F.ttmFlow(flows,c.period);
 return {cash:{...c,age_days:age(c.period,at.slice(0,10)),fresh:age(c.period,at.slice(0,10))<=200},
 cfo:ttm?{status:'source_reconciled',value:ttm.value,basis:ttm.basis,evidence:ttm.evidence.map(compact)}:{status:'unresolved_comparable_total_TTM_CFO',available_total_periods:flows.length},
 reported_runway_years:ttm&&ttm.value<0?c.value/-ttm.value:null,positive_operating_cash_flow:ttm?ttm.value>=0:null,
 status:ttm?(age(c.period,at.slice(0,10))<=200?'source_reconciled':'stale_reported_observation'):'unknown'};
}
function shares(rows,docs,ticker,actions,at){
 const publicDocs=docs.filter(d=>d.filed_at&&Date.parse(nextAt(d.filed_at))<=Date.parse(at));
 const header=publicDocs.map(d=>({doc:d,text:d.text.slice(Math.max(0,d.text.indexOf('Title of each class')-100),d.text.indexOf('Title of each class')+1800)})).find(x=>/Class A Common Stock|Common Stock.*Voting|Voting.*Common Stock/i.test(x.text)&&x.text.includes(ticker));
 const listedClass=header?(/Class A Common Stock/i.test(header.text)?'class_A':'voting'):null;
 function eligibleDimensions(f){return f.dimensions.every(d=>
 /StatementEquityComponentsAxis/.test(d.axis)&&/CommonStockMember$/.test(d.member)
 ||/StatementClassOfStockAxis/.test(d.axis)&&((listedClass==='class_A'&&/CommonClassAMember$|ClassACommonStockMember$/.test(d.member))||(listedClass==='voting'&&/CommonStockVotingMember$|VotingCommonStockMember$/.test(d.member))));}
 const points=dedup(rows).filter(f=>!f.start&&eligibleDimensions(f)&&f.unit==='shares'&&f.val>0&&['CommonStockSharesOutstanding','EntityCommonStockSharesOutstanding'].includes(short(f)));

 const balances=points.filter(f=>short(f)==='CommonStockSharesOutstanding');
 const freshBalance=balances.some(f=>age(f.end,at.slice(0,10))<=200);
 const relevant=(freshBalance?balances:points.filter(f=>short(f)==='EntityCommonStockSharesOutstanding')).sort((a,b)=>b.end.localeCompare(a.end)||b.filed.localeCompare(a.filed)||Number(b.source==='original_inline_context')-Number(a.source==='original_inline_context'));
 const latest=relevant[0];if(!latest)return {status:'unresolved_common_share_count'};
 let older=relevant.filter(f=>age(f.end,latest.end)>=150&&age(f.end,latest.end)<=240).sort((a,b)=>Number(b.accn===latest.accn)-Number(a.accn===latest.accn)||Math.abs(age(a.end,latest.end)-182)-Math.abs(age(b.end,latest.end)-182)||b.filed.localeCompare(a.filed));
 if(!older.length)older=dedup(rows).filter(f=>!f.start&&eligibleDimensions(f)&&f.unit==='shares'&&f.val>0&&short(f)==='CommonStockSharesIssued'&&age(f.end,latest.end)>=150&&age(f.end,latest.end)<=240).sort((a,b)=>b.end.localeCompare(a.end)||b.filed.localeCompare(a.filed)).map(f=>({...f,outstanding_upper_bound_only:true}));
 if(!older.length)return {status:'unresolved_six_month_share_observation',latest:compact(latest),denominator:short(latest),listed_class:listedClass,listed_class_evidence:header?{accession:header.doc.accession,source_url:header.doc.source_url,source_sha256:header.doc.source_sha256,header:header.text.slice(0,1200)}:null};
 const actionProofs=new Map();
 function proof(day,factor){const key=day+'/'+factor;if(actionProofs.has(key))return actionProofs.get(key);
 const months=['January','February','March','April','May','June','July','August','September','October','November','December'],parts=day.split('-'),datePattern=new RegExp([-4,-3,-2,-1,0].map(offset=>{const d=new Date(Date.parse(day)+offset*DAY);return months[d.getUTCMonth()]+'\\s+0?'+d.getUTCDate()+',?\\s+'+d.getUTCFullYear();}).join('|'),'i');
 const words={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,twenty:20,thirty:30,forty:40,fifty:50,sixty:60,seventy:70,eighty:80,ninety:90,hundred:100};
 const parseNumber=s=>/^\d+(?:\.\d+)?$/.test(s)?Number(s):s.toLowerCase().split(/[ -]/).reduce((n,w)=>w==='hundred'?n*100:n+(words[w]||0),0);
 for(const doc of docs.filter(d=>d.filed_at&&Date.parse(nextAt(d.filed_at))<=Date.parse(at))){for(const paragraph of doc.paragraphs||[]){if(!/reverse (?:stock )?split/i.test(paragraph))continue;
 const segments=paragraph.split(/(?<=[.!?])\s+(?=[A-Z(])/);for(let i=0;i<segments.length;i++){let clause=segments[i];const hit=clause.match(datePattern);if(!hit)continue;
 if(!/split/i.test(clause)&&segments[i+1]&&!/\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d/.test(segments[i+1]))clause+=' '+segments[i+1];
 if(!/reverse (?:stock )?split/i.test(clause)||/(?:expects?|expected|may\s+(?:effect|implement|complete|occur)|subject to|proposed|will effect)/i.test(clause))continue;
 const ratios=[...clause.matchAll(/(?:1|one)[ -]*(?:for|to)[ -]*([a-z]+(?:-[a-z]+)?|\d+(?:,\d{3})*(?:\.\d+)?)|every\s+([a-z -]+|\d+)\s+(?:shares|issued)|(?:ratio of\s+)?(\d+)[ -]*(?:to|for)[ -]*1\b/gi)].map(m=>Number((m[1]||m[3]||'').replaceAll(',',''))||parseNumber((m[1]||m[2]||'').trim()));
 if(ratios.some(r=>Math.abs(r/factor-1)<1e-8)){const p={basis:'original_filing_action_date_ratio_clause',catalogue_trading_day:day,source_effective_date:hit[0],source_url:doc.source_url,source_sha256:doc.source_sha256,accession:doc.accession,known_at:nextAt(doc.filed_at),clause:clause.slice(0,1400)};actionProofs.set(key,p);return p;}
 }} }
 actionProofs.set(key,null);return null;}
 function factor(a,b){let total=1;const evidence=[];for(const [d,v]of actions||[])if(a<d&&d<=b){if(v.factor===1)continue;if(!(v.factor>0))return {value:null,reason:'action_conflict',day:d};const corroboration=v.priority>=3?null:proof(d,v.factor);if(v.priority<3&&!corroboration)return {value:null,reason:'action_not_primary_reconciled',day:d};if(corroboration){const legal=new Date(Date.parse(corroboration.source_effective_date+' 12:00:00 GMT')).toISOString().slice(0,10);if(legal!==d&&((a>=legal&&a<d)||(b>=legal&&b<d)))return {value:null,reason:'legal_and_trading_date_boundary_requires_review',day:d,source_effective_day:legal};}total*=v.factor;evidence.push({day:d,...v,primary_corroboration:corroboration});}return {value:total,actions:evidence};}
 function basis(f){
 const changed=factor(f.end,f.filed);if(changed.value===null)return {status:'unresolved',reason:changed.reason,action:changed};
 if(changed.value===1)return {status:'source_reconciled',anchor:f.end,basis:'no_action_between_observation_and_filing'};
 const doc=docs.find(d=>d.accession===f.accn),text=doc?.text||'';
 // The same historical count shown in two filings directly identifies a change
 // of share units. This avoids assuming every filing restates a subsequent split.
 const currentCounts=points.filter(p=>p.accn===f.accn&&short(p)===short(f));
 for(const current of currentCounts){for(const prior of points.filter(p=>p.accn!==f.accn&&p.filed<f.filed&&p.end===current.end&&short(p)===short(f))){
 const previousAction=factor(prior.end,prior.filed);if(previousAction.value!==1)continue;
 const possibilities=[...new Set([f.end,f.filed])].filter(anchor=>anchor>=prior.end).map(anchor=>({anchor,adjustment:factor(prior.end,anchor)})).filter(v=>v.adjustment.value&&Math.abs(prior.val/v.adjustment.value-current.val)<=Math.max(1,Math.abs(current.val)*1e-8));
 if(possibilities.length===1)return {status:'source_reconciled',anchor:possibilities[0].anchor,basis:'overlapping_historical_share_count_reconciles_filing_units',same_period_current:compact(current),same_period_prior:compact(prior),actions:possibilities[0].adjustment.actions};
 }}

 const clauses=[...text.matchAll(/[^.]{0,180}(?:(?:all|share|per.share).{0,180}(?:retroactiv|retrospect)(?:ely|ively)? (?:adjusted|restated)|(?:share|per.share).{0,180}(?:have been|were|are) adjusted[^.]{0,180}(?:reverse|stock) split)[^.]{0,160}/gi)].map(m=>m[0]);
 for(const paragraph of doc?.paragraphs||[])if(/(?:stock|share)/i.test(paragraph)&&/(?:retroactiv|retrospect)/i.test(paragraph)&&/reverse (?:stock )?split/i.test(paragraph))clauses.push(paragraph.slice(0,1800));
 if(clauses.length)return {status:'source_reconciled',anchor:f.filed,basis:'primary_filing_retrospective_share_clause',clauses:clauses.slice(0,4),actions:changed.actions};
 return {status:'unresolved',reason:'post_observation_action_basis_not_proven',actions:changed.actions};
 }
 const lb=basis(latest),attempts=[];
 for(const old of older){const ob=basis(old);if(lb.status!=='source_reconciled'||ob.status!=='source_reconciled'){attempts.push({older:compact(old),latest_basis:lb,older_basis:ob});continue;}
 const commonBasis=lb.anchor>ob.anchor?lb.anchor:ob.anchor; const lf=factor(lb.anchor,commonBasis),of=factor(ob.anchor,commonBasis);if(!lf.value||!of.value){attempts.push({older:compact(old),latest_factor:lf,older_factor:of});continue;}
 const latestAdjusted=latest.val/lf.value,oldAdjusted=old.val/of.value;
 if(old.outstanding_upper_bound_only){const lower=latestAdjusted/oldAdjusted-1;if(lower<.25){attempts.push({older:compact(old),reason:'issued_share_upper_bound_does_not_resolve_threshold',growth_lower_bound:lower});continue;}
 return {status:age(latest.end,at.slice(0,10))<=200?'source_reconciled_threshold_bound':'stale_reported_observation',growth:null,growth_lower_bound:lower,growth_upper_bound:null,threshold:.25,threshold_pass:true,exact_growth_available:false,
 reason:'Outstanding shares cannot exceed issued shares; the conservative growth lower bound already exceeds the fixed 25% threshold.',latest:compact(latest),older_issued_upper_bound:compact(old),latest_basis:lb,older_basis:ob,latest_factor:lf,older_factor:of,latest_adjusted:latestAdjusted,earlier_outstanding_upper_bound_adjusted:oldAdjusted};}

 return {status:age(latest.end,at.slice(0,10))<=200?'source_reconciled':'stale_reported_observation',growth:latestAdjusted/oldAdjusted-1,latest:compact(latest),older:compact(old),latest_basis:lb,older_basis:ob,latest_factor:lf,older_factor:of,latest_adjusted:latestAdjusted,older_adjusted:oldAdjusted,denominator:short(latest)};
 }
 return {status:'unresolved_share_unit_basis',latest:compact(latest),attempts};
}
module.exports={clock,publicRows,dedup,cash,totalFlows,financial,shares,compact};
