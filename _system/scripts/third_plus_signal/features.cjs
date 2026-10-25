'use strict';
// Offline as-of features. Source leads never become independently reviewed deals.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const A=require('../short_framework/adapters.cjs');
const DAY=86400000;
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const date=x=>x?.slice(0,10);
const delta=(a,b)=>(Date.parse(b)-Date.parse(a))/DAY;
const atDay=(d,clock='00:00:00')=>A.nyClock(d,clock);
const state=(value,reason,extra={})=>({state:value===null?'unknown':value?'pass':'fail',reason,...extra});
const unknown=(reason,extra={})=>state(null,reason,extra);
function andStates(values){
  if(values.some(v=>v.state==='fail'))return state(false,'at_least_one_condition_failed');
  if(values.some(v=>v.state==='unknown'))return unknown('at_least_one_condition_unknown');
  return state(true,'all_conditions_pass');
}
const ARMS=[
  {id:'baseline',requires:[]},{id:'score60',requires:['score60']},
  ...Array.from({length:7},(_,i)=>({id:'S'+(i+1),requires:['S'+(i+1)]})),
  {id:'C1',requires:['S1','S2']},{id:'C2',requires:['S1','S2','S7']},
  {id:'C3',requires:['S1','S2','S5','S7']},{id:'C4',requires:['S5','S6','S7']},
];
function armState(snapshot,id,covered=false){
  const arm=ARMS.find(a=>a.id===id);if(!arm)throw new Error('Unknown arm '+id);
  if(!arm.requires.length)return state(true,'unfiltered');
  if(covered)return arm.requires.every(s=>snapshot.signals[s]&&snapshot.signals[s].state!=='unknown')?state(true,'same_covered_universe'):unknown('feature_coverage_missing');
  return andStates(arm.requires.map(s=>snapshot.signals[s]||unknown('feature_missing')));
}
function publicFacts(raw,namespace,tag,unit,at){
  return (raw.facts?.[namespace]?.[tag]?.units?.[unit]||[]).filter(r=>finite(r.val)&&r.end&&r.filed&&r.accn
    &&r.end<=date(at)&&Date.parse(atDay(A.dateAfter(r.filed)))<=Date.parse(at))
    .map(r=>({...r,tag:namespace+':'+tag,unit,known_at:atDay(A.dateAfter(r.filed))}));
}
function uniquePeriods(rows){
  const m=new Map();for(const r of rows){const k=(r.start||'')+'/'+r.end,prev=m.get(k);
    if(!prev||r.filed>prev.filed)m.set(k,r);else if(r.filed===prev.filed&&r.val!==prev.val)m.set(k,{...r,conflict:true});}
  return [...m.values()].filter(r=>!r.conflict);
}
function ttmFlow(rows,anchor){
  rows=uniquePeriods(rows);
  const annual=rows.filter(r=>r.start&&r.end===anchor&&delta(r.start,r.end)>=300&&delta(r.start,r.end)<=400).sort((a,b)=>b.filed.localeCompare(a.filed))[0];
  if(annual)return {value:annual.val,evidence:[annual],basis:'reported_annual'};
  const currents=rows.filter(r=>r.start&&r.end===anchor&&delta(r.start,r.end)>=60&&delta(r.start,r.end)<300);
  for(const cur of currents.sort((a,b)=>b.filed.localeCompare(a.filed))){
    const year=rows.filter(r=>r.start&&delta(r.start,r.end)>=300&&delta(r.start,r.end)<=400&&Math.abs(delta(r.end,cur.start)-1)<=10)
      .sort((a,b)=>b.end.localeCompare(a.end))[0];
    if(!year)continue;
    const old=rows.filter(r=>r.start===year.start&&r.end<year.end&&Math.abs(delta(r.end,cur.end)-365.25)<=20&&Math.abs(delta(r.start,r.end)-delta(cur.start,cur.end))<=20)
      .sort((a,b)=>b.filed.localeCompare(a.filed))[0];
    if(old)return {value:year.val+cur.val-old.val,evidence:[year,cur,old],basis:'annual_plus_current_YTD_minus_prior_YTD'};
  }
  return null;
}
function financialSnapshot(raw,at){
  if(!raw)return {status:'missing_companyfacts'};
  const units=[...new Set([...Object.keys(raw.facts?.['us-gaap']?.CashAndCashEquivalentsAtCarryingValue?.units||{}),...Object.keys(raw.facts?.['ifrs-full']?.CashAndCashEquivalents?.units||{})])].filter(u=>/^[A-Z]{3}$/.test(u));
  const choices=[];
  for(const unit of units){
    const cash=uniquePeriods(publicFacts(raw,'us-gaap','CashAndCashEquivalentsAtCarryingValue',unit,at).concat(publicFacts(raw,'ifrs-full','CashAndCashEquivalents',unit,at)))
      .filter(r=>!r.start&&r.val>=0&&delta(r.end,date(at))>=0&&delta(r.end,date(at))<=200).sort((a,b)=>b.end.localeCompare(a.end)||b.filed.localeCompare(a.filed))[0];
    if(!cash)continue;
    const flows=publicFacts(raw,'us-gaap','NetCashProvidedByUsedInOperatingActivities',unit,at).concat(publicFacts(raw,'ifrs-full','CashFlowsFromUsedInOperatingActivities',unit,at));
    const cfo=ttmFlow(flows,cash.end);
    choices.push({cash:cash.val,period:cash.end,currency:unit,cash_fact:cash,cfo:cfo?.value??null,cfo_evidence:cfo?.evidence||[],cfo_basis:cfo?.basis||null});
  }
  if(choices.length!==1)return {status:choices.length?'ambiguous_currency':'missing_fresh_unrestricted_cash'};
  const f=choices[0];return {...f,status:finite(f.cfo)?'source_bound':'missing_comparable_TTM_CFO',reported_runway:finite(f.cfo)&&f.cfo<0?f.cash/-f.cfo:null};
}
function sharesFeature(raw,at,actions,sourceText){
  if(!raw)return unknown('missing_companyfacts');
  const rows=publicFacts(raw,'us-gaap','CommonStockSharesOutstanding','shares',at).filter(r=>!r.start&&r.val>0);
  const latestEnd=rows.map(r=>r.end).sort().at(-1);
  if(!latestEnd||delta(latestEnd,date(at))>200)return unknown('missing_fresh_period_end_common_shares');
  const latest=rows.filter(r=>r.end===latestEnd).sort((a,b)=>b.filed.localeCompare(a.filed))[0];
  // Same filing prevents mixing old units with a later restatement.
  const older=rows.filter(r=>r.accn===latest.accn&&delta(r.end,latest.end)>=150&&delta(r.end,latest.end)<=240)
    .sort((a,b)=>Math.abs(delta(a.end,latest.end)-182)-Math.abs(delta(b.end,latest.end)-182))[0];
  if(!older)return unknown('no_same_filing_six_month_comparison',{latest_end:latestEnd});
  const crossed=[...actions].filter(([d,a])=>older.end<d&&d<=latest.filed&&a.factor!==1);
  if(crossed.some(([,a])=>a.factor===null))return unknown('share_action_conflict');
  const text=sourceText(latest.accn);
  const restated=/all (?:share|stock|per.share|common stock).{0,180}(?:retroactiv|retrospect|adjusted|restated)|(?:share|stock).{0,100}(?:retroactively|retrospectively) (?:adjusted|restated)/i.test(text||'');
  if(crossed.length&&!restated)return unknown('cross_action_share_units_require_primary_review',{latest_end:latestEnd,earlier_end:older.end});
  const growth=latest.val/older.val-1;
  return state(growth>=.25,'same_filing_period_end_shares',{value:growth,known_at:latest.known_at,source_facts:[older,latest],basis:crossed.length?'primary_clause_retroactive_basis':'no_intervening_action'});
}
function normalize(raw){
  return raw.replace(/<(script|style)\b[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]+>/g,' ')
    .replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&').replace(/\s+/g,' ').trim();
}
function leadClaim(text){
  const matches=[];
  const re=/(?:closed|completed|consummated|issued and sold|received (?:aggregate |gross |net )?proceeds)[^.!?]{0,700}/gi;
  let m;while((m=re.exec(text))&&matches.length<12){
    const start=Math.max(0,m.index-180),clause=text.slice(start,m.index+Math.min(m[0].length,700));
    if(/(?:expects?|expected|plans?|intends?|will|may|subject to)[^.!?]{0,120}$/i.test(text.slice(Math.max(0,m.index-120),m.index)))continue;
    if(!/common stock|ordinary shares|warrants|convertible|equity|securities purchase/i.test(clause))continue;
    if(/(?:expects? to|expected to|will be|subject to|may be).{0,90}(?:closed|completed)/i.test(clause))continue;
    const proceeds=[...clause.matchAll(/net proceeds[^$]{0,60}\$\s*([\d,.]+)\s*(million|thousand|billion)?/gi)].map(x=>Number(x[1].replace(/,/g,''))*({million:1e6,thousand:1e3,billion:1e9}[x[2]?.toLowerCase()]||1));
    matches.push({locator:'normalized_text['+start+':'+(start+clause.length)+']',excerpt:clause,net_proceeds_candidates:proceeds});
  }
  return {completed_claims:matches,manual_independent_review_complete:false};
}
function loadReviews(file){
  if(!fs.existsSync(file))return [];
  const doc=read(file);if(!Array.isArray(doc))throw new Error('Reviews must be an array');
  const seen=new Set();
  for(const r of doc){
    const identity=r.issuer+'/'+r.deal_id;if(seen.has(identity))throw new Error('Duplicate financing deal review');seen.add(identity);
    if(!r.issuer||!r.deal_id||!r.known_at||!r.source_sha256||!r.locator||!r.source_url?.startsWith('https://'))throw new Error('Incomplete financing review');
    if(!Number.isFinite(Date.parse(r.known_at))||!/(Z|[+-]\d\d:\d\d)$/.test(r.known_at))throw new Error('Review public clock must be aware');
    if(!Array.isArray(r.reviewers)||new Set(r.reviewers).size<2||r.outcome_blinded!==true)throw new Error('Independent blinded reviews required');
    if(!['completed','not_dilutive','terminated'].includes(r.state)||r.identity_reconciled!==true||r.cash_reconciled!==true||r.share_units_reconciled!==true||r.saleability_reconciled!==true)throw new Error('Incomplete economic reconciliation');
    if(!/^[A-Z]{3}$/.test(r.currency||''))throw new Error('Reviewed cash currency required');
    if(r.closed_date&&(!/^\d{4}-\d{2}-\d{2}$/.test(r.closed_date)||r.closed_date>date(r.known_at)))throw new Error('Closing date must precede public completed-state clock');
    if(r.net_cash_change!==null&&!finite(r.net_cash_change))throw new Error('Invalid reconciled cash change');
    if(r.state==='completed'&&(!(r.saleable_shares>0)||!r.closed_date))throw new Error('Completed financing needs saleable shares and closing date');
  }
  return doc;
}
function build(ctx,root,privateDir){
  const local=path.join(root,'_system/data/reverse_splits/local'),cache=path.join(local,'profit_program/20261022_v1');
  const eventIndex=new Map(ctx.events.map(e=>[e.id,e])),byIssuer=new Map();
  for(const e of ctx.events.filter(e=>e.family==='financing')){
    const a=byIssuer.get(e.issuer)||[];a.push(e);byIssuer.set(e.issuer,a);
  }
  const run=path.dirname(ctx.prices.db.location()),db=new DatabaseSync(path.join(run,'input.sqlite'),{readOnly:true});
  const rawRows=db.prepare('SELECT accession,cik,filed_at,available_at,text_file,form,source_json FROM disclosures').all();db.close();
  const filingIndex=new Map(rawRows.map(r=>[r.accession.replace(/-/g,''),r]));
  const sourceCache=new Map(),sourceHashes=new Map();
  function source(accn,cik){
    const key=String(accn||'').replace(/-/g,'');if(!key)return null;
    const row=filingIndex.get(key);if(!row||String(Number(row.cik))!==String(Number(cik)))return null;
    if(!sourceCache.has(key)){
      const f=path.resolve(root,row.text_file||'');
      if(!f.startsWith(path.resolve(local)+path.sep))throw new Error('Source path outside local cache');
      if(!fs.existsSync(f)){sourceCache.set(key,null);return null;}
      const bytes=fs.readFileSync(f),h=sha(bytes),text=normalize(bytes.toString('utf8'));
      sourceHashes.set(path.relative(root,f).replace(/\\/g,'/'),h);
      sourceCache.set(key,{text,sha256:h,known_at:row.available_at||atDay(A.dateAfter(row.filed_at)),file:row.text_file,cik:String(Number(row.cik)),accession:key});
    }return sourceCache.get(key);
  }
  const reviewFile=path.join(privateDir,'financing_reviews.local.json'),reviews=loadReviews(reviewFile);
  // Every imported review must bind to the cached bytes and issuer, never only a ticker.
  for(const r of reviews){const doc=source(r.accession,r.issuer.replace('cik/',''));if(!doc||doc.sha256!==r.source_sha256||Date.parse(doc.known_at)>Date.parse(r.known_at))throw new Error('Review source/hash/clock mismatch');}
  const factCache=new Map(),factHashes=new Map(),leadAudit=new Map(),snapshots=[];
  function facts(cik){
    if(!factCache.has(cik)){
      const f=path.join(local,'raw/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json');
      if(!fs.existsSync(f)){factCache.set(cik,null);return null;}
      const bytes=fs.readFileSync(f),raw=JSON.parse(bytes),h=sha(bytes);
      if(Number(raw.cik)!==Number(cik))throw new Error('Companyfacts issuer mismatch');
      factHashes.set(path.relative(root,f).replace(/\\/g,'/'),h);
      // Retain just required standard facts rather than whole issuer files.
      const keep={cik:raw.cik,facts:{}};
      for(const ns of ['us-gaap','ifrs-full']){keep.facts[ns]={};
        for(const tag of ['CashAndCashEquivalentsAtCarryingValue','CashAndCashEquivalents','NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities','CommonStockSharesOutstanding'])if(raw.facts?.[ns]?.[tag])keep.facts[ns][tag]=raw.facts[ns][tag];}
      factCache.set(cik,keep);
    }return factCache.get(cik);
  }
  const allHistory=ctx.events.filter(e=>e.family==='split').map(e=>({issuer:e.issuer,ticker:e.ticker,day:e.event_date,known_at:e.known_at,source_url:e.source_url}))
    .concat(ctx.catalogue.filter(e=>['primary_schedule_matched','structured_corporate_action'].includes(e.verification)&&e.issuer?.startsWith('cik/')&&e.ratio>0&&e.ratio<1).map(e=>({issuer:e.issuer,ticker:e.ticker,day:e.ex_date,known_at:e.available_at,source_url:e.source_url})));
  for(const r of ctx.candidates.filter(r=>r.ordinal>=3)){
    const e=eventIndex.get(r.id),raw=facts(e.cik),at=r.day?atDay(r.day,'09:25:00'):null;
    const s={id:r.id,issuer:r.issuer,ticker:r.ticker,entry_day:r.day,event_date:r.event_date,decision_at:at,
      identity_status:e.identity_status,signals:{},financial:null,price_asof:null,source_claims:[],control:{ratio:e.features.ratio,ordinal:r.ordinal,year:r.year,price:r.entry_price,adv:r.adv_dollars}};
    if(!at){for(const k of ['S1','S2','S3','S4','S5','S6','S7','score60','reported_runway'])s.signals[k]=unknown('no_decision_session');snapshots.push(s);continue;}
    const atMs=Date.parse(at),fin=financialSnapshot(raw,at),leads=(byIssuer.get(r.issuer)||[]).filter(x=>x.known_at&&Date.parse(x.known_at)<=atMs&&Date.parse(x.known_at)>=atMs-60*DAY);
    for(const lead of leads){
      if(!leadAudit.has(lead.id)){
        const doc=source(lead.accession,e.cik),claim=doc?leadClaim(doc.text):{completed_claims:[],manual_independent_review_complete:false};
        leadAudit.set(lead.id,{id:lead.id,issuer:lead.issuer,accession:lead.accession,known_at:lead.known_at,provider_state:lead.event_status,source_url:lead.source_url,source_sha256:doc?.sha256||null,source_present:!!doc,source_clock_valid:!!doc&&Date.parse(doc.known_at)<=Date.parse(lead.known_at),...claim});
      }
      s.source_claims.push(lead.id);
    }
    const usableReviews=reviews.filter(v=>v.issuer===r.issuer&&Date.parse(v.known_at)<=atMs),recentReviews=usableReviews.filter(v=>Date.parse(v.known_at)>=atMs-60*DAY);
    s.signals.S2=recentReviews.some(v=>v.state==='completed')?state(true,'independently_reconciled_completed_dilution',{deal_ids:recentReviews.filter(v=>v.state==='completed').map(v=>v.deal_id)}):unknown('no_independent_financing_or_complete_absence_review',{cached_leads:leads.length,provider_flag:!!e.features.prior_financing_flag});
    // Cash feature is an estimate conditional on cache coverage. Observed but
    // unresolved financing blocks the pro forma signal; absence is never S2=false.
    const afterBalance=(byIssuer.get(r.issuer)||[]).filter(x=>fin.period&&x.known_at&&Date.parse(x.known_at)<=atMs&&date(x.known_at)>fin.period&&x.features.first_state_disclosure!==false&&['terms_disclosed','amendment_terms_disclosed','primary_terms_reconciled'].includes(x.event_status));
    const unresolved=afterBalance.filter(x=>!usableReviews.some(v=>v.accession?.replace(/-/g,'')===x.accession?.replace(/-/g,'')));
    const providerUnresolved=e.features.prior_financing_flag===true&&!recentReviews.length;
    let cash=fin.cash;
    for(const v of usableReviews.filter(v=>v.state==='completed'&&v.closed_date>fin.period)){
      if(v.net_cash_change===null||v.currency!==fin.currency){unresolved.push({id:v.deal_id});continue;}cash+=v.net_cash_change;
    }
    const runway=finite(cash)&&fin.cfo<0?cash/-fin.cfo:null;
    s.financial={...fin,pro_forma_cash:cash,pro_forma_runway:runway,funding_unresolved:unresolved.length>0||providerUnresolved,funding_coverage:'partial_cached_sources'};
    s.signals.S1=fin.status!=='source_bound'?unknown(fin.status):unresolved.length||providerUnresolved?unknown('known_or_provider_flagged_funding_requires_pro_forma_reconciliation'):
      state(fin.cfo<0&&runway<.5,'latest_reported_cash_plus_reconciled_known_flows',{value:runway,coverage_assumption:'No completeness claim; undiscovered financing may alter this conditional estimate.'});
    s.signals.reported_runway=fin.status==='source_bound'?state(fin.cfo<0&&fin.reported_runway<.5,'unadjusted_reported_runway_diagnostic',{value:fin.reported_runway}):unknown(fin.status);
    const prior=allHistory.filter(h=>h.issuer===r.issuer&&h.day<r.event_date&&h.known_at&&Date.parse(h.known_at)<=atMs).sort((a,b)=>b.day.localeCompare(a.day))[0];
    s.signals.S3=prior&&prior.ticker===r.ticker?state(delta(prior.day,r.event_date)<=180,'same_CIK_and_symbol_prior_effective_date',{value:delta(prior.day,r.event_date),prior_day:prior.day,identity:'provisional_same_symbol_not_verified_security_master'}):unknown('prior_security_continuity_unresolved');
    s.signals.S4=sharesFeature(raw,at,ctx.actions.get(r.ticker)||new Map(),acc=>source(acc,e.cik)?.text);
    const di=ctx.prices.index.get(r.day),priorDay=ctx.prices.days[di-1],ep=ctx.prices.point(r.ticker,r.event_date);
    s.price_asof=priorDay;
    const regularEx=ctx.prices.index.has(r.event_date);
    s.signals.S5=regularEx&&r.event_date<r.day&&ep&&ep.high>ep.low?
      state(ep.close<ep.open&&(ep.close-ep.low)/(ep.high-ep.low)<=.25,'completed_effective_day_OHLC',{value:(ep.close-ep.low)/(ep.high-ep.low),known_at:atDay(r.event_date,'16:01:00')}):unknown('missing_or_zero_range_effective_day_bar');
    function adjustedReturn(first,last){
      const a=ctx.prices.point(r.ticker,first),b=ctx.prices.point(r.ticker,last),factor=ctx.factor(r.ticker,first,last);
      if(!a||!b||!factor)return null;return b.close/factor/a.close-1;
    }
    const d20=ctx.prices.days[di-21],ret20=d20&&priorDay?adjustedReturn(d20,priorDay):null;
    const complete20=di>=21&&ctx.prices.days.slice(di-21,di).every(d=>ctx.prices.point(r.ticker,d));
    s.signals.S6=complete20&&finite(ret20)?state(ret20<=-.2,'20_completed_session_adjusted_close_return',{value:ret20}):unknown('incomplete_adjusted_20_session_history');
    const returns=[];for(let i=di-5;i<di;i++){if(i<1){returns.push(null);continue;}returns.push(adjustedReturn(ctx.prices.days[i-1],ctx.prices.days[i]));}
    s.signals.S7=returns.length===5&&returns.every(finite)?state(Math.max(...returns)<.5,'no_prior_five_session_50pct_close_rally',{value:Math.max(...returns)}):unknown('incomplete_adjusted_five_session_history');
    s.signals.score60=r.scored?state(r.score>=60,'existing_as_filed_score',{value:r.score}):unknown('financial_score_unavailable');
    snapshots.push(s);
  }
  const coverage=Object.fromEntries(['score60','S1','S2','S3','S4','S5','S6','S7','reported_runway'].map(k=>[k,Object.fromEntries(['pass','fail','unknown'].map(v=>[v,snapshots.filter(s=>s.signals[k]?.state===v).length]))]));
  return {snapshots,coverage,leadAudit:[...leadAudit.values()],sourceHashes:Object.fromEntries(sourceHashes),factHashes:Object.fromEntries(factHashes),reviews_count:reviews.length};
}
module.exports={ARMS,state,unknown,andStates,armState,financialSnapshot,publicFacts,ttmFlow,sharesFeature,normalize,leadClaim,loadReviews,build};
