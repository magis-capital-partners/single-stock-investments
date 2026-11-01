'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const A=require('./short_framework/adapters.cjs');
const finite=Number.isFinite,DAY=86400000;
const knownAt=r=>A.nyClock(A.dateAfter(r.known_filed_date),'00:00:00');
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
function validateReviews(reviews,sourceIndex,contractIndex=new Map()){
 const ids=new Set();for(const r of reviews){if(ids.has(r.claim_id))throw new Error('Duplicate claim review');ids.add(r.claim_id);
  if(r.independent_review!==false||r.outcome_blinded!==false)throw new Error('Single-analyst review must not invent independent/outcome-blinded attestations');
  const source=sourceIndex.get(r.accession);if(!source||'cik/'+source.cik!==r.issuer||source.filed_at!==r.known_filed_date)throw new Error('Review source identity/date mismatch');
  if(!source.parts.some(p=>p.source_sha256===r.source_sha256&&p.url===r.source_url&&p.paragraphs.some(t=>t.includes(r.quote))))throw new Error('Review quote/hash mismatch '+r.claim_id);
  for(const e of r.contract_evidence||[]){const contract=contractIndex.get(r.accession);if(!contract||contract.source_sha256!==e.source_sha256||contract.source_url!==e.source_url||!contract.parts.some(p=>p.text.includes(e.quote)))throw new Error('Contract quote/hash mismatch');}
  if(r.cash_currency){const e=r.currency_evidence,contract=contractIndex.get(r.accession);const matches=e&&(source.parts.some(p=>p.source_sha256===e.source_sha256&&p.url===e.source_url&&p.paragraphs.some(t=>t.includes(e.quote)))||(contract&&contract.source_sha256===e.source_sha256&&contract.source_url===e.source_url&&contract.parts.some(p=>p.text.includes(e.quote))));if(!matches)throw new Error('Currency evidence quote/hash mismatch');}
  if(r.closed_date&&r.closed_date>r.known_filed_date)throw new Error('Closing is after its completed-state disclosure');
  for(const e of r.additional_evidence||[])if(!source.parts.some(p=>p.source_sha256===e.source_sha256&&p.url===e.source_url&&p.paragraphs.some(t=>t.includes(e.quote))))throw new Error('Additional source quote/hash mismatch');
 }
 return true;
}
function timeRange(rows){
 const ranges=rows.map(r=>r.closed_interval||r.cash_interval||(r.closed_date?[r.closed_date,r.closed_date]:[null,r.completion_known_by||r.cash_receipt_known_by||null]));
 const lower=ranges.some(r=>r[0]===null)?null:ranges.map(r=>r[0]).sort()[0];
 const ends=ranges.map(r=>r[1]).filter(Boolean).sort();return {first_possible_cash_date:lower,last_possible_cash_date:ends.at(-1)||null,date_conflict:rows.some(r=>r.closing_date_conflict)};
}
function field(rows,key){
 const available=rows.filter(r=>finite(r[key])).sort((a,b)=>b.known_filed_date.localeCompare(a.known_filed_date));if(!available.length)return null;
 const newest=available[0].known_filed_date,atDate=available.filter(r=>r.known_filed_date===newest),values=[...new Set(atDate.map(r=>r[key]))];
 const units=[...new Set(rows.map(r=>r.cash_currency).filter(Boolean))],unitRows=rows.filter(r=>r.cash_currency===units[0]);
 const currency=units.length===1?units[0]:null;
 return values.length===1?{value:values[0],known_at:knownAt(available[0]),claim_ids:atDate.map(r=>r.claim_id),currency,currency_conflict:units.length>1,currency_evidence_claim_ids:currency?unitRows.map(r=>r.claim_id):[]}:{value:null,conflict:true,values,claim_ids:atDate.map(r=>r.claim_id)};
}
function dealsAsOf(reviews,at){
 const grouped=new Map();for(const r of reviews.filter(r=>r.deal_key&&Date.parse(knownAt(r))<=Date.parse(at))){const list=grouped.get(r.deal_key)||[];list.push(r);grouped.set(r.deal_key,list);}
 return [...grouped].map(([id,rows])=>{
  const state=rows.map(r=>r.state),net=field(rows,'net_cash'),gross=field(rows,'gross_cash'),cumulativeGross=field(rows,'gross_cash_cumulative'),cash=field(rows,'cash_consideration');
  return {id,issuer:rows[0].issuer,states:[...new Set(state)],range:timeRange(rows),cash_series:rows.some(r=>r.cash_series==='cumulative')?'cumulative':'single_economic_deal',
   net_cash:net,gross_cash:gross||cumulativeGross,cash_consideration:cash,non_cash_consideration:field(rows,'non_cash_consideration'),
   principal:field(rows,'principal_amount'),principal_cumulative:field(rows,'principal_cumulative'),stated_value:field(rows,'stated_value'),
   restricted_escrow:field(rows,'restricted_escrow'),cash_consideration_max:field(rows,'cash_consideration_max'),cash_collateral_balance:field(rows,'cash_collateral_balance'),
   settlement_options:[...new Set(rows.flatMap(r=>r.settlement_options||[]))],cash_settlement_mix_status:rows.find(r=>r.cash_settlement_mix_status)?.cash_settlement_mix_status||null,
   first_underlying_common_exercise_date:rows.map(r=>r.first_underlying_common_exercise_date).filter(Boolean).sort()[0]||null,
   collateral_scope_requires_review:rows.some(r=>r.collateral_scope_requires_review),committed_available_cash_upper:field(rows,'committed_available_cash_upper'),
   obligations:rows.flatMap(r=>[...(r.known_committed_uses||[]),...(r.known_cash_use_requires_reconciliation?[{status:'cash_use_requires_reconciliation',description:r.known_cash_use_requires_reconciliation}]:[])]),
   claim_ids:rows.map(r=>r.claim_id),known_at:rows.map(knownAt).sort()[0],review_level:'single_analyst_source_reconciliation',independent_review:false,
   saleability_status:'not_independently_reconciled',field_source_records:rows.map(r=>({claim_id:r.claim_id,accession:r.accession,known_at:knownAt(r),source_url:r.source_url,source_sha256:r.source_sha256}))};
 });
}
function caseFunding(event,reviews,reportManifest){
 const at=event.clock.at,balance=event.financial.cash.period,day=at.slice(0,10),recentFirst=new Date(Date.parse(day)-60*DAY).toISOString().slice(0,10);
 const all=dealsAsOf(reviews.filter(r=>r.issuer===event.issuer),at),post=all.filter(d=>!d.range.last_possible_cash_date||d.range.last_possible_cash_date>balance);
 const recent=all.filter(d=>d.states.includes('completed_issuer_financing')&&d.range.first_possible_cash_date&&d.range.first_possible_cash_date>=recentFirst&&d.range.last_possible_cash_date<=day);
 let identifiedNet=0;const components=[],gaps=[];
 for(const d of post){
  const after=d.range.first_possible_cash_date&&d.range.first_possible_cash_date>balance;
  const net=d.net_cash;
  if(net&&finite(net.value)&&after&&(net.value===0||net.currency===event.financial.cash.currency)){identifiedNet+=net.value;components.push({deal_id:d.id,net_cash:net.value,currency:net.currency,known_at:net.known_at});}
  else if(d.states.some(s=>['completed_issuer_financing','completed_cash_use','completed_acquisition','completed_asset_disposal','completed_asset_disposals_and_other_changes'].includes(s)))gaps.push({deal_id:d.id,reason:!after?'cash_interval_not_wholly_after_balance_date':net?.conflict?'conflicting_net_cash_values':net&&finite(net.value)&&net.currency!==event.financial.cash.currency?'cash_currency_not_bound_to_balance_currency':'net_cash_or_payment_mix_not_publicly_reconciled',gross_cash:d.gross_cash?.value??null,cash_consideration:d.cash_consideration?.value??null});
  for(const obligation of d.obligations)gaps.push({deal_id:d.id,reason:'cash_allocation_or_payment_timing_requires_reconciliation',...obligation});
 }
 const reports=reportManifest.filter(r=>r.events?.includes(event.id)&&r.filed_at<day);
 return {schema:'event_financing_reconciliation.v2',source_clock:at,balance_date:balance,current_reports_recovered:reports.filter(r=>r.status==='ok').length,current_reports_failed:reports.filter(r=>r.status!=='ok').length,
  documented_recent_completed_financings:recent.map(d=>d.id),documented_recent_count:recent.length,
  documented_financing_absence_verified:false,independent_financing_review_complete:false,original_S2_state:'unknown',
  identified_net_cash_after_balance:identifiedNet,cash_currency:event.financial.cash.currency,identified_net_components:components,reported_cash_plus_identified_components:event.financial.cash.value+identifiedNet,
  adjusted_cash_is_complete:false,unresolved_cash_items:gaps,
  review_scope:'All recovered current reports were scanned; identified completion/receipt claims were source-classified by one analyst. This does not verify absence of every transaction, exhaustive cash movements or registration/saleability.',
  deals:all};
}
module.exports={knownAt,validateReviews,timeRange,field,dealsAsOf,caseFunding};
