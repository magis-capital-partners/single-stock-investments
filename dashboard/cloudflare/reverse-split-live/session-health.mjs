import {etDay} from './core.mjs';
import {sessionAt,sessions} from './shadow-core.mjs';
import {sha} from './worker.mjs';
export async function recordSessionHealth(env,runtime,now=new Date().toISOString()){
 if(!sessionAt(now))return;
 const sources=(await env.DB.prepare('SELECT id,last_success,status,coverage_gap FROM rs_sources ORDER BY id').all()).results;
 const row={at:now,runtime_status:runtime.status,heartbeat_at:runtime.heartbeat_at,market_data:runtime.market_data,sources,publication:runtime.publication};
 await env.DB.prepare('INSERT OR IGNORE INTO rs_state VALUES(?,?,?)').bind('session_health:'+etDay(now)+':'+now.slice(11,16),JSON.stringify(row),now).run();
}
export async function archiveDailyHealth(env,now=new Date().toISOString()){
 const day=etDay(now),marker='daily_operating_review:'+day;if(await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(marker).first())return;
 const history=JSON.parse((await env.DB.prepare("SELECT value FROM rs_state WHERE key='validation_history'").first())?.value||'[]'),completed=history.find(r=>r.day===day);if(!completed)return;
 const object=await env.EVIDENCE.get(completed.key);if(!object)throw new Error('Completed validation archive unavailable; daily review deferred');const validation=await object.json();
 const health=(await env.DB.prepare('SELECT value FROM rs_state WHERE key>=? AND key<? ORDER BY key').bind('session_health:'+day+':','session_health:'+day+';').all()).results.map(r=>JSON.parse(r.value));
 const gaps=(await env.DB.prepare('SELECT * FROM rs_source_gaps WHERE start_at<=? AND end_at>=?').bind(validation.plan.end_at,validation.plan.start_at).all()).results;
 const failures=(await env.DB.prepare("SELECT id,error,created_at,updated_at FROM rs_jobs WHERE state='failed'").all()).results;
 const operationsObject=await env.EVIDENCE.get('collector-dashboard/operations.json'),operations=operationsObject?await operationsObject.json():null;
 const session=sessions.find(s=>s.day===day),expectedMinutes=session?(Date.parse(session.close)-Date.parse(session.open))/60000:null,healthCoverage={observed_minutes:health.length,expected_minutes:expectedMinutes,complete:expectedMinutes!==null&&health.length>=expectedMinutes};
 const marketDataPassed=validation.summary.status==='passed_market_data_checks';
 const report={schema:'reverse_split_daily_operating_review.v1',day,generated_at:now,status:marketDataPassed?'market_data_checks_passed_operating_review_pending':'failed_or_incomplete_operating_session',health_coverage:healthCoverage,evaluation_scope:'supplementary_evidence_original_review_criteria_unchanged',validation:{key:completed.key,sha256:await sha(JSON.stringify(validation)),summary:validation.summary},health_samples:health,gaps,failures,operations,criteria_unchanged:true,quiet_session_is_not_profitability:true,actual_broker_fills:0,actual_pnl:null,research_only:true,authority:'none',orders:0,broker_connections:0};
 const raw=JSON.stringify(report),digest=await sha(raw),key='review/operating/'+day+'-'+digest+'.json';await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});const pointer={day,key,sha256:digest,status:report.status,generated_at:now};await env.EVIDENCE.put('review/operating-latest.json',new TextEncoder().encode(JSON.stringify(pointer)),{httpMetadata:{contentType:'application/json'}});await env.DB.prepare('INSERT OR IGNORE INTO rs_state VALUES(?,?,?)').bind(marker,JSON.stringify(pointer),now).run();return pointer;
}
