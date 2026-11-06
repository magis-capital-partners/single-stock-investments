#!/usr/bin/env node
// Independent scheduled checks read only HTTPS research state. No market-data session.
import {appendFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {remoteEnvironment} from './collector.mjs';
export function monitorReport({runtime,snapshot,now=new Date().toISOString()}){
  const problems=[],at=Date.parse(now),age=value=>Number.isFinite(Date.parse(value))?Math.max(0,(at-Date.parse(value))/1000):null;
  const heartbeatAge=age(runtime?.heartbeat_at),snapshotAge=age(snapshot?.readiness?.generated_at);
  if(heartbeatAge===null||heartbeatAge>180)problems.push('collector_heartbeat_missing_or_older_than_three_minutes');
  if(snapshotAge===null||snapshotAge>600)problems.push('dashboard_snapshot_missing_or_older_than_ten_minutes');
  if(runtime?.status==='degraded')problems.push('collector_reports_degraded');
  if(snapshot?.readiness?.sources?.some(s=>s.status!=='healthy'||!s.fresh))problems.push('public_source_degraded_or_stale');
  if(snapshot?.readiness?.unresolved_source_gaps?.length)problems.push('unresolved_source_coverage_gap');
  const validation=snapshot?.validation;if(validation?.status==='insufficient_data_overflow')problems.push('validation_sample_overflow');
  if(validation?.plan&&at>=Date.parse(validation.plan.start_at)+10*60000&&at<=Date.parse(validation.plan.end_at)){
    const targets=validation.plan.targets||{},rows=validation.symbols||[];
    if(validation.plan.benchmarks.some(t=>{const r=rows.find(s=>s.ticker===t);return !r||r.minute_coverage<(targets.minimum_minute_coverage||.95)||r.maximum_evaluation_gap_ms>(targets.maximum_evaluation_gap_ms||60000)||r.clock_failures||r.capture_to_client_ms?.p95>targets.capture_to_client_p95_ms||r.quote_age_ms?.p95>targets.quote_age_p95_ms||r.receipt_to_evaluation_ms?.p95>targets.evaluation_after_receipt_p95_ms;}))problems.push('session_validation_below_registered_targets');
  }
  if(snapshot?.readiness?.jobs?.some(j=>j.state==='failed'&&j.count))problems.push('failed_analysis_jobs');
  return {schema:'reverse_split_review_monitor.v1',generated_at:now,status:problems.length?'needs_attention':'tracking',problems,heartbeat_age_seconds:heartbeatAge,snapshot_age_seconds:snapshotAge,collector:runtime,validation,review:snapshot?.review||null,readiness:snapshot?.readiness||null,research_only:true,authority:'none',broker_connections:0,orders:0,notification:'Dashboard and workflow summary; no new email or external messaging integration'};
}
export async function monitor(env){
  const row=await env.DB.prepare("SELECT value FROM rs_state WHERE key='shadow_runtime'").first(),object=await env.EVIDENCE.get('collector-dashboard/shadow.json');
  const result=monitorReport({runtime:row?JSON.parse(row.value):null,snapshot:object?await object.json():null}),raw=new TextEncoder().encode(JSON.stringify(result)),key='review/monitor/'+result.generated_at.replaceAll(':','-')+'.json';
  await env.EVIDENCE.put(key,raw,{httpMetadata:{contentType:'application/json'}});await env.EVIDENCE.put('review/monitor-latest.json',raw,{httpMetadata:{contentType:'application/json'}});return result;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  const env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:'e1cac493b315c8fd7398500dd1bfd687',database:'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:'single-stock-reverse-splits-evidence'});
  try{const result=await monitor(env);console.log(JSON.stringify(result));if(process.env.GITHUB_STEP_SUMMARY)appendFileSync(process.env.GITHUB_STEP_SUMMARY,`# Reverse-split shadow review\n\nStatus: **${result.status}**\n\n${result.problems.map(p=>'- '+p).join('\n')||'No monitored faults.'}\n\nHeartbeat age: ${result.heartbeat_age_seconds} seconds. Snapshot age: ${result.snapshot_age_seconds} seconds.\n\nAWS remains deferred; no live orders.\n`);if(result.problems.length)process.exitCode=1;}catch(e){console.error(JSON.stringify({event:'review_monitor_unavailable',error:e.message}));process.exitCode=1;}
}
