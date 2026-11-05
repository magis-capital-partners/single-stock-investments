import {digest,putState} from './shadow-service.mjs';
import {at,finite,sessionAt,sessions} from './shadow-core.mjs';
import {putSummaryIfChanged} from './summary-state.mjs';
export const VALIDATION_PLAN=Object.freeze({id:'rs_live_path_2026-11-05.v2',previous_plan_id:'rs_live_path_2026-11-05.v1',day:'2026-11-05',timezone:'America/New_York',start_at:'2026-11-05T14:25:00Z',end_at:'2026-11-05T21:10:00Z',benchmarks:['AAPL','SPY','IWM'],quote_gate_seconds:15,targets:{capture_to_client_p95_ms:2000,quote_age_p95_ms:5000,evaluation_after_receipt_p95_ms:15000,minimum_minute_coverage:.95,maximum_evaluation_gap_ms:60000},sampling:'first_receipt_each_five_seconds_plus_current_book_each_monitor_pass',minimum_regular_samples_per_benchmark:100,authority:'none',research_only:true,broker_connections:0,orders:0});
const stats=values=>{const a=values.filter(finite).sort((x,y)=>x-y);return {count:a.length,p50:a.length?a[Math.floor((a.length-1)*.5)]:null,p95:a.length?a[Math.floor((a.length-1)*.95)]:null,max:a.length?a.at(-1):null};};
export async function initializeValidation(env,now=new Date().toISOString()){
  const old=await env.DB.prepare("SELECT value FROM rs_state WHERE key='validation_plan'").first(),plan=old?JSON.parse(old.value):null;
  if(plan&&plan.id!==VALIDATION_PLAN.id){
    const samples=JSON.parse((await env.DB.prepare("SELECT value FROM rs_state WHERE key='validation_samples'").first())?.value||'[]');
    if(plan.id!==VALIDATION_PLAN.previous_plan_id||samples.length||at(now)>=at(plan.start_at))throw new Error('Cannot replace an underway validation plan');
    const raw=JSON.stringify(plan);await env.EVIDENCE.put('validation-plans/'+plan.id+'-'+await digest(raw)+'.json',new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
    await putState(env,'validation_plan',VALIDATION_PLAN,now);return;
  }
  if(plan&&JSON.stringify(plan)!==JSON.stringify(VALIDATION_PLAN))throw new Error('Validation plan changed; version required');
  if(!old)await putState(env,'validation_plan',VALIDATION_PLAN,now);
}
export function quoteLatency(q,now){
  const raw=q.raw||{},capture=at(q.quote_at),receipt=at(q.observed_at),evaluated=at(now);let exchangeToCapture=null;
  try{const event=BigInt(raw.ts_event_ns),recv=BigInt(raw.ts_recv_ns);if(event>0n&&recv>=event)exchangeToCapture=Number(recv-event)/1e6;}catch{}
  return {ticker:q.ticker,quote_at:q.quote_at,received_at:q.observed_at,evaluated_at:now,capture_to_client_ms:receipt-capture,quote_age_ms:evaluated-capture,receipt_to_evaluation_ms:evaluated-receipt,exchange_to_capture_ms:exchangeToCapture,spread_bps:10000*(q.ask-q.bid)/((q.ask+q.bid)/2),bid_size:q.bid_size,ask_size:q.ask_size,size_units:q.size_units,identity_verified:!!q.security_id,coverage:q.coverage,clock_invalid:receipt<capture-2000||evaluated<receipt-2000};
}
export function validationSummary(samples,now,plan=VALIDATION_PLAN){
  const regular=samples.filter(s=>s.regular_session),symbols=[...new Set(samples.map(s=>s.ticker))];
  const session=sessions.find(s=>s.day===plan.day),open=at(session.open),close=at(session.close),through=Math.min(close,Math.max(open,at(now))),expectedMinutes=Math.max(0,Math.ceil((through-open)/60000));
  const rows=symbols.map(ticker=>{
    const all=regular.filter(s=>s.ticker===ticker),books=all.filter(s=>s.sample_kind!=='timed_receipt'),valid=books.filter(s=>!s.error&&!s.clock_invalid),unique=[...new Map(valid.map(s=>[s.quote_at,s])).values()],receipts=all.filter(s=>s.sample_kind==='timed_receipt'&&!s.clock_invalid);
    const minutes=new Set(valid.map(s=>s.evaluated_at.slice(0,16))),ticks=[...new Set(books.map(s=>at(s.evaluated_at)).filter(t=>t>=open&&t<=through))].sort((a,b)=>a-b),gaps=[ticks.length?ticks[0]-open:through-open,...ticks.slice(1).map((t,i)=>t-ticks[i]),ticks.length?through-ticks.at(-1):0];
    return {ticker,attempts:books.length,unique_quotes:unique.length,timed_receipts:receipts.length,errors:books.filter(s=>s.error).length,clock_failures:all.filter(s=>s.clock_invalid).length,capture_to_client_ms:stats(receipts.map(s=>s.capture_to_client_ms)),quote_age_ms:stats(valid.map(s=>s.quote_age_ms)),receipt_to_evaluation_ms:stats(receipts.map(s=>s.receipt_to_evaluation_ms)),spread_bps:stats(valid.map(s=>s.spread_bps)),minute_coverage:expectedMinutes?Math.min(1,minutes.size/expectedMinutes):null,covered_minutes:minutes.size,expected_minutes:expectedMinutes,maximum_evaluation_gap_ms:Math.max(0,...gaps),last_sample:books.at(-1)||null};
  });
  const complete=at(now)>=at(plan.end_at),sufficient=plan.benchmarks.every(t=>{const r=rows.find(r=>r.ticker===t);return r?.unique_quotes>=plan.minimum_regular_samples_per_benchmark&&r?.timed_receipts>=plan.minimum_regular_samples_per_benchmark&&r.minute_coverage>=plan.targets.minimum_minute_coverage;}),failed=rows.some(r=>plan.benchmarks.includes(r.ticker)&&(r.clock_failures||r.maximum_evaluation_gap_ms>plan.targets.maximum_evaluation_gap_ms||r.capture_to_client_ms.p95>plan.targets.capture_to_client_p95_ms||r.quote_age_ms.p95>plan.targets.quote_age_p95_ms||r.receipt_to_evaluation_ms.p95>plan.targets.evaluation_after_receipt_p95_ms||r.errors/Math.max(1,r.attempts)>.05));
  return {plan,generated_at:now,status:at(now)<at(plan.start_at)?'scheduled':!complete?'running':!sufficient?'insufficient_data':failed?'failed_targets':'passed_market_data_checks',symbols:rows,regular_samples:regular.length,total_samples:samples.length,broker_connections:0,orders:0,announcement_to_entry_validation:'awaiting_first_forward_qualifying_announcement',impact_validation:'not_measured_by_quotes',coverage:'selected_venues_not_sip_nbbo',latency_clock:'Databento ts_recv capture to runner receipt; exchange event delay shown separately when available'};
}
export async function validationTick(env,now=new Date().toISOString()){
  const p=VALIDATION_PLAN;
  if(at(now)<at(p.start_at)){env.market?.drainTelemetry?.();await putSummaryIfChanged(env,'validation_summary',validationSummary([],now),now);return;}
  const old=JSON.parse((await env.DB.prepare("SELECT value FROM rs_state WHERE key='validation_samples'").first())?.value||'[]');
  if(at(now)<=at(p.end_at)){
    const names=(await env.DB.prepare("SELECT DISTINCT ticker FROM rs_execution_tracks WHERE state IN ('armed','partial_entry','open','exit_pending')").all()).results.map(r=>r.ticker).filter(Boolean);
    const minute=now.slice(0,16),sampleNames=env.validationActiveMinute===minute?[]:names,identities=new Map();env.validationActiveMinute=minute;
    for(const ticker of [...new Set([...p.benchmarks,...sampleNames])]){
      let sample;try{const q=await (env.market.observe?env.market.observe(ticker):env.market.quote(ticker,{quote_feed:'databento_mini'}));sample=quoteLatency(q,new Date().toISOString());}catch{sample={ticker,evaluated_at:now,error:'fresh_quote_or_identity_unavailable'};}
      sample.sample_kind='latest_book';sample.regular_session=!!sessionAt(now);old.push(sample);identities.set(ticker,sample.identity_verified);
    }
    const telemetry=env.market.drainTelemetry?.()||{samples:[],dropped:0},evaluated=new Date().toISOString();
    for(const row of telemetry.samples.filter(r=>at(r.observed_at)>=at(p.start_at)&&at(r.observed_at)<=at(p.end_at))){const sample=quoteLatency({...row,raw:row,size_units:'shares',coverage:'selected_venues_not_sip_nbbo',security_id:identities.get(row.ticker)?'verified_benchmark_identity':null},evaluated);sample.sample_kind='timed_receipt';sample.regular_session=!!sessionAt(row.observed_at);old.push(sample);}
    if(telemetry.dropped)await putState(env,'validation_overflow',{at:now,reason:'timed_receipt_buffer_overflow',dropped:telemetry.dropped});
    // One bounded session requires <12k samples for the benchmark group. Any
    // overflow is archived and flagged, rather than silently counted as a pass.
    if(old.length>30000){await putState(env,'validation_overflow',{at:now,limit:30000});return;}
    await putState(env,'validation_samples',old,now);
  }else env.market?.drainTelemetry?.();
  const minute=now.slice(0,16),last=JSON.parse((await env.DB.prepare("SELECT value FROM rs_state WHERE key='validation_archive_minute'").first())?.value||'null');
  if(minute!==last&&old.length){const pending=old.filter(x=>x.evaluated_at.slice(0,16)<minute&&(!last||x.evaluated_at.slice(0,16)>=last));if(pending.length){const raw=JSON.stringify(pending),key=`validation/${p.id}/${minute.replaceAll(':','-')}-${await digest(raw)}.json`;await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});}await putState(env,'validation_archive_minute',minute,now);}
  const summary=validationSummary(old,now);
  const paths=(await env.DB.prepare("SELECT payload FROM rs_execution_tracks WHERE state<>'retrospective' AND json_extract(payload,'$.signal_at') IS NOT NULL ORDER BY updated_at DESC LIMIT 50").all()).results.map(r=>JSON.parse(r.payload));
  summary.announcement_paths=paths.map(t=>({ticker:t.ticker,policy_id:t.policy_id,published_at:t.published_at,first_seen_at:t.first_seen_at,ready_at:t.signal_at,entry_at:t.entry_at||null,publication_to_receipt_ms:t.published_at?at(t.first_seen_at)-at(t.published_at):null,receipt_to_ready_ms:at(t.signal_at)-at(t.first_seen_at),ready_to_counterfactual_entry_ms:t.entry_at?at(t.entry_at)-at(t.signal_at):null,broker_verified:false}));
  if(paths.length)summary.announcement_to_entry_validation=paths.some(t=>t.lane==='executable'&&t.entry_shares)?'counterfactual_path_observed_not_broker_execution':'forward_signal_observed_no_broker_eligible_fill';
  if(await env.DB.prepare("SELECT value FROM rs_state WHERE key='validation_overflow'").first())summary.status='insufficient_data_overflow';await putSummaryIfChanged(env,'validation_summary',summary,now);
}
