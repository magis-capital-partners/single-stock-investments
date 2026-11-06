// Criteria are recorded before the observation week; profits never override data failures.
import {digest,putState} from './shadow-service.mjs';
import {etDay} from './core.mjs';
export const REVIEW_PLAN=Object.freeze({
  id:'rs_shadow_review_2026-11-06.v1',starts_at:'2026-11-06T14:25:00Z',review_at:'2026-11-13T21:30:00Z',timezone:'America/New_York',
  observation_days:['2026-11-06','2026-11-09','2026-11-10','2026-11-11','2026-11-12','2026-11-13'],
  minimum_consecutive_complete_sessions:5,minimum_minute_coverage:.95,maximum_evaluation_gap_seconds:60,
  capture_to_receipt_p95_ms:2000,quote_age_p95_ms:5000,receipt_to_evaluation_p95_ms:5000,
  maximum_entry_quote_age_seconds:15,source_freshness_seconds:120,financial_source_freshness_seconds:600,
  required_evidence:['primary_announcement','verified_common_share_identity','point_in_time_financial_inputs','verified_prior_splits','fresh_supported_quote','dated_IBKR_borrow_allocation','margin','short_sale_restriction','trading_status'],
  cost_tests:['observed_daily_borrow','commissions','cover_cost_reserve','missing_cost_days','recall_and_buy_in_uncertainty'],
  sensitivity_tests:['entry_delay_30_seconds','entry_delay_60_seconds','entry_delay_300_seconds','price_budget_10_25_50_100_bps','unavailable_borrow_excluded'],
  hosting:'GitHub existing service; AWS deferred until user reviews successful observation evidence',
  promotion:'Operational pass permits a hosting review only. No live orders or capital approval. A quiet week or selected-venue capacity P&L cannot validate broker execution or profitability.',
  policy_changes:'Frozen original strategy retained. Any new filter or timing policy requires a separate prospective version.',
  authority:'none',research_only:true,orders:0,broker_connections:0,
});
const state=async(env,key)=>JSON.parse((await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first())?.value||'null');
export async function initializeReview(env,now=new Date().toISOString()){
  const old=await state(env,'shadow_review_plan'),canonical=JSON.stringify(REVIEW_PLAN),sha256=await digest(canonical);
  if(old){if(old.sha256!==sha256||JSON.stringify(old.plan)!==canonical)throw new Error('Shadow review criteria changed; a new prospective version is required');return old;}
  const record={plan:REVIEW_PLAN,sha256,registered_at:now,registered_before_start:Date.parse(now)<Date.parse(REVIEW_PLAN.starts_at)};
  const raw=JSON.stringify(record);await env.EVIDENCE.put('review/plans/'+REVIEW_PLAN.id+'-'+sha256+'-'+await digest(raw)+'.json',new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
  await putState(env,'shadow_review_plan',record,now);return record;
}
export function gradeReview({registration,history=[],validation,events=[],tracks=[],sourceGaps=0,failedJobs=0,now=new Date().toISOString()}={}){
  const plan=registration?.plan||REVIEW_PLAN,completed=history.filter(r=>plan.observation_days.includes(r.day)&&r.id==='rs_live_path_'+r.day+'.v3'&&r.day<=etDay(now)).map(r=>({...r}));
  if(validation?.plan&&Date.parse(now)>=Date.parse(validation.plan.end_at)&&plan.observation_days.includes(validation.plan.day)&&!completed.some(r=>r.day===validation.plan.day))completed.push({id:validation.plan.id,day:validation.plan.day,status:validation.status});
  completed.sort((a,b)=>a.day.localeCompare(b.day));let consecutive=0;
  for(const day of plan.observation_days){if(day>etDay(now))break;const r=completed.find(r=>r.day===day);if(!r){if(day<etDay(now))consecutive=0;continue;}consecutive=r.status==='passed_market_data_checks'?consecutive+1:0;}
  const forward=events.filter(e=>Date.parse(e.first_seen_at)>=Date.parse(plan.starts_at)&&Date.parse(e.first_seen_at)<=Date.parse(now)),byEvent=new Map();
  for(const t of tracks.filter(t=>Date.parse(t.enrolled_at)>=Date.parse(plan.starts_at)&&t.state!=='retrospective'))if(!byEvent.has(t.event_id))byEvent.set(t.event_id,t);
  const entered=tracks.filter(t=>t.entry_shares>0&&Date.parse(t.enrolled_at)>=Date.parse(plan.starts_at)),executable=entered.filter(t=>t.lane==='executable'),conditional=entered.filter(t=>t.lane==='capacity');
  const operational=registration?.registered_before_start===true&&consecutive>=plan.minimum_consecutive_complete_sessions&&!sourceGaps&&!failedJobs;
  return {id:plan.id,generated_at:now,plan,registration,completed_sessions:completed,consecutive_passing_sessions:consecutive,required_sessions:plan.minimum_consecutive_complete_sessions,
    operational_status:!registration?.registered_before_start?'criteria_not_registered_before_start':operational?'passed_observation_checks':Date.parse(now)<Date.parse(plan.review_at)?'observing':'insufficient_or_failed_checks',
    forward_announcements:forward.length,forward_issuers:new Set(forward.map(e=>e.cik).filter(Boolean)).size,forward_decisions:byEvent.size,executable_entries:executable.length,conditional_entries:conditional.length,
    distinct_entered_events:new Set(entered.map(t=>t.event_id)).size,open_positions:entered.filter(t=>t.remaining_shares>0).length,incomplete_cost_positions:entered.filter(t=>t.pnl?.complete_net_pnl==null).length,
    trading_evidence_status:!entered.length?'no_forward_fills_to_validate':!executable.length?'conditional_capacity_only':executable.some(t=>t.remaining_shares>0)?'positions_still_open':'review_closed_positions_and_complete_costs',
    unresolved_source_gaps:sourceGaps,failed_jobs:failedJobs,aws_decision:'deferred_for_user_review',live_trading_approved:false,authority:'none',research_only:true};
}
export async function reviewTick(env,now=new Date().toISOString()){
  if(Date.parse(now)<(env.nextReviewTick||0))return;env.nextReviewTick=Date.parse(now)+60000;
  const registration=await initializeReview(env,now),validation=await state(env,'validation_summary'),history=await state(env,'validation_history')||[];
  const events=(await env.DB.prepare('SELECT payload FROM rs_events WHERE first_seen_at>=?').bind(REVIEW_PLAN.starts_at).all()).results.map(r=>JSON.parse(r.payload));
  const tracks=(await env.DB.prepare("SELECT payload FROM rs_execution_tracks WHERE state<>'retrospective'").all()).results.map(r=>JSON.parse(r.payload));
  const sourceGaps=(await env.DB.prepare('SELECT count(*) AS n FROM rs_source_gaps WHERE resolved_at IS NULL AND end_at>=?').bind(REVIEW_PLAN.starts_at).first()).n,failedJobs=(await env.DB.prepare("SELECT count(*) AS n FROM rs_jobs WHERE state='failed' AND created_at>=?").bind(REVIEW_PLAN.starts_at).first()).n;
  const summary=gradeReview({registration,validation,history,events,tracks,sourceGaps,failedJobs,now});await putState(env,'shadow_review_summary',summary,now);return summary;
}
