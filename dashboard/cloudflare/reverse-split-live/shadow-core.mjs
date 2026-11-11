// Prospective, deterministic simulations. This module cannot send orders.
import {etDay,DAY} from './core.mjs';
import calendar from './sessions.json' with {type:'json'};

export const SHADOW_VERSION='reverse_split_shadow.v1';
const common={version:SHADOW_VERSION,research_only:true,authority:'none',minimum_ordinal:2,minimum_score:60,minimum_signals:3,max_period_age_days:200,hold_sessions:5,exit_lead_seconds:60,target_notional:25000,reference_equity:1000000,name_stress_loss_fraction:.005,sleeve_stress_loss_fraction:.02,adverse_shock:2,maximum_names:3,maximum_entry_age_seconds:900,entry_window_seconds:900,quote_age_seconds:15,quote_depth_fraction:.05,slippage_bps:10,borrow_apr:.5,minimum_notional:100,commission_per_share:.005,commission_minimum:1,calendar_version:calendar.version,stop:null,profit_target:null};
const fullMarketPolicies=[
  {...common,id:'rs_immediate.v1',label:'Immediate intraday · primary',timing:'immediate',primary:true},
  {...common,id:'rs_wait5m.v1',label:'Wait five minutes',timing:'wait5m'},
  {...common,id:'rs_next_open.v1',label:'Next eligible open',timing:'next_open'},
  {...common,id:'rs_split_open.v1',label:'Split-day open',timing:'split_open'},
  {...common,id:'rs_post_split.v1',label:'Session after split',timing:'post_split'},
  {...common,id:'rs_repeat_all_scores.v1',label:'Repeat splits · no score threshold',timing:'immediate',minimum_score:0,control:true},
  {...common,id:'rs_third_plus.v1',label:'Third or later · score ≥60',timing:'immediate',minimum_ordinal:3,control:true},
];
// Existing policy objects stay byte-for-byte identical. Mini is a new experiment.
export const SHADOW_POLICIES=Object.freeze([...fullMarketPolicies,...fullMarketPolicies.map(p=>({...p,id:p.id.replace('.v1','_mini.v1'),label:p.label.replace(' · primary','')+' · Mini indicative',primary:false,quote_feed:'databento_mini',quote_coverage:'selected_venues_not_sip_nbbo',indicative:true}))].map(Object.freeze));
export const sessions=calendar.sessions;
export const finite=x=>typeof x==='number'&&Number.isFinite(x);
export const at=x=>Number.isFinite(Date.parse(x))?Date.parse(x):null;
export const iso=x=>new Date(x).toISOString();
export function sessionAt(value){const t=at(value);return sessions.find(s=>t>=at(s.open)&&t<at(s.close))||null;}
export function nextSession(value){const t=at(value);return sessions.find(s=>at(s.close)>t)||null;}
export function plannedEntry(event,policy,signalAt){
  const t=at(signalAt);if(t===null)return null;
  if(policy.timing==='immediate'||policy.timing==='wait5m'){
    const ready=t+(policy.timing==='wait5m'?300000:0),current=sessionAt(iso(ready));
    return current?iso(ready):sessions.find(s=>at(s.open)>=ready)?.open||null;
  }
  if(policy.timing==='next_open')return sessions.find(s=>at(s.open)>=t+300000)?.open||null;
  const day=event.trading_date||event.effective_date,index=sessions.findIndex(s=>s.day>=day);
  return index<0?null:sessions[index+(policy.timing==='post_split'?1:0)]?.open||null;
}
export function plannedExit(entryAt,hold=5){const day=etDay(entryAt),index=sessions.findIndex(s=>s.day===day);return index<0?null:sessions[index+hold-1]?.close||null;}
export function signalGate(event,policy,now){
  if([event.first_seen_at,event.published_at,event.analyzed_at].filter(Boolean).some(x=>at(x)===null||at(x)>at(now)+2000))return {state:'waiting',reason:'source_or_analysis_clock_in_future'};
  if(!event.cik||!event.ticker||event.multiple_securities)return {state:'waiting',reason:'issuer_or_security_unresolved'};
  if(event.status!=='scheduled')return {state:['cancelled','authorization','historical'].includes(event.status)?'rejected':'waiting',reason:'announcement_'+(event.status||'unresolved')};
  if(event.implementation_conditions?.length)return {state:'waiting',reason:'implementation_conditions_unresolved'};
  if(!event.effective_date)return {state:'waiting',reason:'split_date_unresolved'};
  const ordinal=Number(event.ordinal_min||0);if(ordinal<policy.minimum_ordinal)return {state:'waiting',reason:'prior_split_history_unresolved_or_below_threshold'};
  const f=event.financials||{},count=f.signal_count??Object.keys(f.signals||{}).length;
  if(!finite(f.score)||count<policy.minimum_signals||!f.period)return {state:'waiting',reason:'fundamentals_incomplete'};
  const age=(Date.parse(etDay(now))-Date.parse(f.period))/DAY;
  if(age<0||age>policy.max_period_age_days)return {state:'waiting',reason:'fundamentals_stale'};
  if(f.score<policy.minimum_score)return {state:'rejected',reason:'score_below_threshold'};
  return {state:'eligible',reason:'signal_pass'};
}
export function quoteGate(q,now,policy){
  if(!q)return 'quote_unavailable';
  if(policy.quote_feed==='databento_mini'){
    if(q.provider!=='databento_mini'||q.dataset!=='EQUS.MINI'||q.coverage!=='selected_venues_not_sip_nbbo'||q.delayed!==false)return 'live_databento_mini_quote_required';
  }else if(q.consolidated!==true||q.delayed===true)return 'live_consolidated_quote_required';
  const ts=at(q.quote_at),observed=at(q.observed_at),t=at(now);
  if(ts===null||observed===null||ts>t+2000||observed>t+2000||t-ts>policy.quote_age_seconds*1000)return 'quote_stale_or_future';
  if(![q.bid,q.ask,q.bid_size,q.ask_size].every(finite)||q.bid<=0||q.ask<q.bid||q.bid_size<=0||q.ask_size<=0)return 'quote_invalid';
  return null;
}
export function feasibility(evidence,now,notional,shares){
  const current=kind=>evidence.filter(e=>e.kind===kind&&at(e.observed_at)<=at(now)&&at(e.valid_until)>=at(now)).sort((a,b)=>at(b.observed_at)-at(a.observed_at))[0];
  const locate=current('locate'),ssr=current('ssr'),margin=current('margin');
  const checks={locate:locate?.approved===true&&locate.shares>=shares&&finite(locate.apr)?'supported':'unverified',ssr:ssr?.restricted===false?'supported':ssr?.restricted===true?'restricted':'unverified',margin:margin?.approved===true&&finite(margin.available_notional)&&margin.available_notional>=notional?'supported':'unverified'};
  return {state:Object.values(checks).every(x=>x==='supported')?'supplied_evidence_supports_size':'unverified',checks,evidence_ids:[locate,ssr,margin].filter(Boolean).map(x=>x.id),broker_execution_verified:false};
}
export function entryCapacity(track,quote,policy,peers=[]){
  const active=peers.filter(x=>x.id!==track.id&&x.policy_id===track.policy_id&&x.remaining_shares>0);
  if(active.some(x=>x.cik===track.cik))return {shares:0,reason:'issuer_already_open'};
  if(!track.remaining_shares&&active.length>=policy.maximum_names)return {shares:0,reason:'maximum_open_names'};
  const exposure=active.reduce((n,x)=>n+(x.mark_price||x.entry_price)*x.remaining_shares,0),own=(track.entry_shares||0)*(track.entry_price||0),name=policy.reference_equity*policy.name_stress_loss_fraction/policy.adverse_shock;
  const budget=Math.max(0,Math.min(policy.target_notional,name,policy.reference_equity*policy.sleeve_stress_loss_fraction/policy.adverse_shock-exposure)-own);
  const displayed=Math.max(0,quote.bid_size*policy.quote_depth_fraction-(track.depth_spent?.['short:'+quote.bid]||0));
  return {shares:Math.max(0,Math.floor(Math.min(budget/quote.bid,displayed))),risk_notional_cap:name,reason:budget>0?'bounded_quote_simulation':'stress_budget_exhausted'};
}
export function commission(shares,price,p){return Math.min(Math.max(p.commission_minimum,p.commission_per_share*shares),shares*price*.01);}
export function pnl(track){
  if(!track.entry_shares)return null;
  if(track.action_unresolved||!finite(track.mark_price))return null;
  return (track.entry_proceeds||0)-(track.cover_cost||0)-track.remaining_shares*track.mark_price-(track.commissions||0)-(track.borrow_cost||0);
}
export function validateEvidence(raw,now){
  if(!raw||!['locate','ssr','margin','corporate_action'].includes(raw.kind)||typeof raw.event_id!=='string'||!raw.event_id||raw.event_id.length>160)throw new Error('Invalid evidence type or event');
  if(!/^https:\/\//.test(raw.source_url||'')||typeof raw.reference!=='string'||!raw.reference||raw.reference.length>300)throw new Error('Evidence requires a source and reference');
  if(at(raw.observed_at)===null||at(raw.observed_at)>at(now)+2000||at(raw.valid_until)===null||at(raw.valid_until)<=at(raw.observed_at))throw new Error('Invalid evidence availability window');
  if(raw.kind==='locate'&&(!Number.isInteger(raw.shares)||raw.shares<=0||!finite(raw.apr)||raw.apr<0||typeof raw.approved!=='boolean'))throw new Error('Invalid locate');
  if(raw.kind==='ssr'&&typeof raw.restricted!=='boolean')throw new Error('Invalid short-sale restriction evidence');
  if(raw.kind==='margin'&&(!finite(raw.available_notional)||raw.available_notional<0||typeof raw.approved!=='boolean'))throw new Error('Invalid margin evidence');
  if(raw.kind==='corporate_action'&&(!finite(raw.split_from)||raw.split_from<=0||!finite(raw.split_to)||raw.split_to<=0||!/^\d{4}-\d{2}-\d{2}$/.test(raw.execution_date||'')))throw new Error('Invalid corporate action');
  return {...raw,approval_basis:'owner_supplied_evidence',broker_execution_verified:false};
}
