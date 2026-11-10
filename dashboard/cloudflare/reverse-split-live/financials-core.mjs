// Financial evidence and coverage only. Registered numerical strategy rules stay fixed.
import {ALIASES,monetaryFacts,scoreFundamentals,trailingYear,etDay,DAY} from './core.mjs';
export const FINANCIAL_VERSION='reverse_split_financials.v1';
export const METRICS=Object.freeze(Object.keys(ALIASES));
const flows=new Set(['revenues','net_income','operating_income','cfo']);
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const time=v=>Number.isFinite(Date.parse(v))?Date.parse(v):null;
const isoDate=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&time(v)!==null&&new Date(Date.parse(v)).toISOString().slice(0,10)===v;
const primaryTotal=r=>r.metric==='revenues'&&r.kind==='html_table'&&r.statement_total===true&&/^total (?:net )?revenues?$/i.test(r.original_label||'');
const useful=r=>({metric:r.metric,start:r.start||null,end:r.end,value:r.value,currency:r.currency,source_url:r.source_url,source_sha256:r.source_sha256,locator:r.locator,kind:r.kind,filed:r.filed,published_at:r.published_at,observed_at:r.observed_at,original_tag:r.original_tag,rounding_tolerance:r.rounding_tolerance,owner_reviewed:r.owner_reviewed});
export function eligibleFact(r,cik,asOf){
  return !!r&&METRICS.includes(r.metric)&&String(Number(r.cik))===String(Number(cik))&&r.scope==='consolidated'&&r.confidence==='verified'&&finite(r.value)&&/^[A-Z]{3}$/.test(r.currency||'')&&isoDate(r.end)&&(!r.start||isoDate(r.start))&&(flows.has(r.metric)?!!r.start:!r.start)&&(!r.start||r.start<=r.end)&&r.end<=etDay(asOf)&&isoDate(r.filed)&&time(r.published_at)!==null&&time(r.observed_at)!==null&&time(r.published_at)<=time(asOf)&&time(r.observed_at)<=time(asOf)&&/^https:\/\//.test(r.source_url||'')&&/^[a-f0-9]{64}$/.test(r.source_sha256||'')&&typeof r.locator==='string'&&r.locator.length>0;
}
export function reconcileFacts(rows){
  const groups=new Map(),facts=[],conflicts=[];
  for(const r of rows){const key=[r.metric,r.start||'',r.end,r.currency].join('|');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
  for(const [key,values] of groups){
    const reviewed=values.filter(r=>r.owner_reviewed===true).sort((a,b)=>b.observed_at.localeCompare(a.observed_at));
    if(reviewed.length){facts.push(reviewed[0]);continue;}
    const latest=values.map(r=>r.filed).sort().at(-1);let current=values.filter(r=>r.filed===latest);
    const totals=current.filter(primaryTotal);if(totals.length)current=totals;
    // Entity-wide tagged facts preserve the registered concept priorities.
    // An untagged note/table is never allowed to replace a tagged statement.
    const structured=current.filter(r=>r.kind==='inline_xbrl');if(structured.length){const rank=r=>{const n=ALIASES[r.metric].indexOf(String(r.original_tag||'').split(':').at(-1));return n<0?100:n;},best=Math.min(...structured.map(rank));current=structured.filter(r=>rank(r)===best);}
    const reference=current[0];
    const differs=current.some(r=>Math.abs(r.value-reference.value)>Math.max(Number(r.rounding_tolerance)||0,Number(reference.rounding_tolerance)||0,1e-6));
    if(differs){conflicts.push({key,reason:'conflicting_values_same_period',values:current.map(useful)});continue;}
    const rank={inline_xbrl:0,html_table:1,pdf_table:2,owner_review:0};
    facts.push(current.sort((a,b)=>(rank[a.kind]??9)-(rank[b.kind]??9))[0]);
  }
  return {facts,conflicts};
}
export function buildFinancialProfile({cik,ticker=null,company=null,companyfacts,facts=[],sources=[],as_of,instrument=null,errors=[]}={}){
  if(!/^\d{1,10}$/.test(String(cik))||time(as_of)===null)throw new Error('Financial profile identity and clock required');
  const baseline=monetaryFacts({...companyfacts,verified_metric_facts:[]},as_of).metrics;
  const accepted=facts.filter(r=>eligibleFact(r,cik,as_of)).filter(r=>r.owner_reviewed||r.kind==='inline_xbrl'||primaryTotal(r)||!(baseline[r.metric]||[]).some(x=>x.unit===r.currency&&(x.start||null)===(r.start||null)&&x.end===r.end&&x.filed>=r.filed)),reconciled=reconcileFacts(accepted),conceptResolutions=[];
  reconciled.facts=reconciled.facts.filter(r=>{
    if(r.owner_reviewed)return true;
    const same=(baseline[r.metric]||[]).filter(x=>x.unit===r.currency&&(x.start||null)===(r.start||null)&&x.end===r.end),latest=same.map(x=>x.filed).sort().at(-1);
    if(!latest||latest<r.filed)return true;
    if(latest>r.filed)return false;
    const priority=Math.min(...same.filter(x=>x.filed===latest).map(x=>x.rank));
    const preferred=same.filter(x=>x.filed===latest&&x.rank===priority);
    const alternatives=[];
    if(primaryTotal(r))for(const ns of ['us-gaap','ifrs-full','dei'])for(const tag of ALIASES[r.metric])for(const value of companyfacts?.facts?.[ns]?.[tag]?.units?.[r.currency]||[])if(value.filed===latest&&(value.start||null)===(r.start||null)&&value.end===r.end)alternatives.push({...value,tag:ns+':'+tag});
    // A face-statement TOTAL can identify which of several standard API tags
    // is the consolidated measure. Require independent same-filing tagged
    // agreement; a note table or an unmatched total never overrides the API.
    if(primaryTotal(r)&&preferred.some(x=>Math.abs(x.val-r.value)>Math.max(Number(r.rounding_tolerance)||0,1e-6))&&alternatives.some(x=>Math.abs(x.val-r.value)<=Math.max(Number(r.rounding_tolerance)||0,1e-6))){conceptResolutions.push({version:'primary_consolidated_total.v1',metric:r.metric,start:r.start,end:r.end,value:r.value,source_sha256:r.source_sha256,locator:r.locator,superseded_concepts:preferred.map(x=>({tag:x.tag,value:x.val,accession:x.accn})),matching_concepts:alternatives.filter(x=>Math.abs(x.val-r.value)<=Math.max(Number(r.rounding_tolerance)||0,1e-6)).map(x=>x.tag)});return true;}
    if(preferred.some(x=>Math.abs(x.val-r.value)>Math.max(Number(r.rounding_tolerance)||0,1e-6)))reconciled.conflicts.push({key:[r.metric,r.start||'',r.end,r.currency].join('|'),reason:'filing_disagrees_with_companyfacts',values:[useful(r),...preferred.map(x=>({value:x.val,tag:x.tag,accession:x.accn,filed:x.filed}))]});
    return false;
  });
  const raw={...(companyfacts||{cik,facts:{}}),verified_metric_facts:reconciled.facts};
  let policy=scoreFundamentals(raw,as_of,cik),available=scoreFundamentals(raw,as_of,cik,{maxAgeDays:Infinity});
  const {metrics}=monetaryFacts(raw,as_of),anchor=available.period||policy.period;
  const metricRows={};
  for(const metric of METRICS){
    const value=flows.has(metric)?available.flows?.[metric]:available.balances?.[metric];
    const sourceRows=(available.evidence||[]).filter(r=>r.metric===metric||ALIASES[metric].includes(String(r.tag||'').split(':').at(-1)));
    metricRows[metric]={status:finite(value)?(value===0?'reported_zero':'verified'):'not_recovered',value:finite(value)?value:null,currency:available.currency||policy.currency||null,period:anchor,inputs:sourceRows.map(r=>({value:r.val,start:r.start||null,end:r.end,tag:r.tag,filed:r.filed,accession:r.accn||null,source_url:r.source_url||`https://data.sec.gov/api/xbrl/companyfacts/CIK${String(cik).padStart(10,'0')}.json`,source_sha256:r.source_sha256||null,locator:r.locator||r.tag}))};
  }
  const prior={};for(const metric of ['revenues','operating_income']){
    const ends=[...new Set((metrics[metric]||[]).filter(r=>anchor&&(Date.parse(anchor)-Date.parse(r.end))/DAY>=350&&(Date.parse(anchor)-Date.parse(r.end))/DAY<=380).map(r=>r.end))].sort().reverse();
    for(const end of ends){const value=trailingYear(metrics[metric],end);if(value){prior[metric]=value.value;break;}}
    const end=ends.find(end=>trailingYear(metrics[metric],end)),priorFlow=end?trailingYear(metrics[metric],end):null;
    metricRows[metric+'_prior_ttm']={status:finite(prior[metric])?(prior[metric]===0?'reported_zero':'verified'):'insufficient_history',value:prior[metric]??null,currency:available.currency||null,period:end||null,inputs:(priorFlow?.evidence||[]).map(r=>({value:r.val,start:r.start||null,end:r.end,tag:r.tag,filed:r.filed,accession:r.accn||null,source_url:r.source_url||`https://data.sec.gov/api/xbrl/companyfacts/CIK${String(cik).padStart(10,'0')}.json`,source_sha256:r.source_sha256||sources.find(s=>s.form==='SEC_COMPANYFACTS')?.sha256||null,locator:r.locator||r.tag}))};
  }
  const dependencies={accrual_ratio:['net_income','cfo','total_assets'],profit_without_cash:['net_income','cfo'],cash_burn:['cfo','cash'],leverage:['long_term_debt','total_assets'],revenue_turn:['revenues','revenues_prior_ttm'],margin_trend:['revenues','operating_income','revenues_prior_ttm','operating_income_prior_ttm']};
  const components=Object.fromEntries(Object.entries(dependencies).map(([key,needed])=>{const missing=needed.filter(k=>!finite(metricRows[k]?.value));const notApplicable=!missing.length&&((key==='profit_without_cash'&&metricRows.net_income.value<=0)||(key==='cash_burn'&&metricRows.cfo.value>=0)||(key==='revenue_turn'&&metricRows.revenues_prior_ttm.value<=0)||(key==='margin_trend'&&(metricRows.revenues.value<=0||metricRows.revenues_prior_ttm.value<=0)));return [key,{status:available.signals?.[key]?'calculated':missing.length?'missing_inputs':notApplicable?'not_applicable':'invalid_denominator',missing,needed}];}));
  let status=policy.score!==null?'current':policy.status==='stale_or_missing_period'?(policy.period?'stale':'missing_data'):'insufficient_components';
  const type=instrument?.type,excluded=type&&type!=='CS';
  if(excluded){status='not_applicable';policy={...policy,score:null,status:'instrument_not_in_operating_company_strategy'};}
  if(reconciled.conflicts.length&&!excluded){status='needs_review';policy={...policy,score:null,status:'financial_source_conflict'};}
  const issuer=scoreFundamentals(raw,as_of,cik),issuerFinancials={score:reconciled.conflicts.length?null:issuer.score,status:reconciled.conflicts.length?'financial_source_conflict':issuer.status,signal_count:issuer.signal_count||0,period:issuer.period,currency:issuer.currency,signals:issuer.signals,method:issuer.method,cutoff:as_of};
  const coverage={status,reason:policy.status,period:anchor||null,age_days:anchor?Math.floor((Date.parse(etDay(as_of))-Date.parse(anchor))/DAY):null,available_score:available.score,policy_score:policy.score,signal_count:available.signal_count||0,issuer_financial_status:issuerFinancials.status,metrics:metricRows,components,conflicts:reconciled.conflicts,concept_resolutions:conceptResolutions,required_inputs:METRICS.length+2,verified_inputs:Object.values(metricRows).filter(r=>finite(r.value)).length,instrument,missing_does_not_mean_zero:true};
  return {schema:FINANCIAL_VERSION,cik:String(Number(cik)),ticker,company,observed_at:as_of,policy_financials:{...policy,coverage:undefined,evidence_layer:FINANCIAL_VERSION},issuer_financials:issuerFinancials,coverage,facts:reconciled.facts,sources,errors};
}
export function validateReviewedFacts(input,sources,now){
  if(!input||!/^\d{1,10}$/.test(String(input.cik))||!Array.isArray(input.facts)||input.facts.length<1||input.facts.length>30||typeof input.reason!=='string'||input.reason.trim().length<3)throw new Error('Review identity, facts and reason required');
  return input.facts.map(r=>{
    const source=sources.find(s=>s.sha256===r.source_sha256);if(!source)throw new Error('Review source is not a captured issuer document');
    if(!finite(r.value))throw new Error('Review values must be finite numeric amounts');
    const fact={...r,cik:String(Number(input.cik)),scope:'consolidated',confidence:'verified',kind:'owner_review',owner_reviewed:true,observed_at:now,source_url:source.url,published_at:source.published_at,filed:source.filed,form:source.form};
    if(!eligibleFact(fact,input.cik,now))throw new Error('Review has invalid periods, units, source clocks or locator');
    return fact;
  });
}
