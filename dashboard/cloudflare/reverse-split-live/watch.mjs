// A bounded continuous process: scheduler delays do not set the in-process polling cadence.
import {openCheckpoint} from './checkpoint.mjs';
import {scheduled,dispatch,consume,enqueue,sourceURL,recordEvent} from './worker.mjs';
import {initializeShadow,shadowTick,putState,digest} from './shadow-service.mjs';
import {classifyAnnouncement,etDay} from './core.mjs';
import {pollIBKRBorrow} from './borrow-service.mjs';
import {initializeExecution,executionTick} from './execution-service.mjs';
import {initializeValidation,validationTick,flushValidationSamples} from './validation-service.mjs';
import {pollFlexBorrow} from './flex-borrow.mjs';
import {installFinancialImport,importFinancialProfiles} from './financials-import.mjs';
import {createEvaluationLoop} from './evaluation-loop.mjs';
import {initializeReview,reviewTick} from './review-service.mjs';
import {preparedManifest} from './prepared-universe.mjs';
import {ensureRemoteReadIndexes} from './read-indexes.mjs';
import {recordSessionHealth,archiveDailyHealth} from './session-health.mjs';
const now=()=>new Date().toISOString();
export const researchWriteBudget=(day,registrationDay)=>day===registrationDay?70000:40000;
export const needsStartupReconciliation=(last,at=Date.now())=>Number.isFinite(Date.parse(last))&&at-Date.parse(last)>15*60000;
export async function watchCollector(env,{interval=1,maximumMs=300*60000,sleep=ms=>new Promise(r=>setTimeout(r,ms)),shouldStop=()=>false}={}){
  const remote=env.controlDB,token=crypto.randomUUID(),started=Date.now();let lease,checkpoint,stopping=false,ticks=0,jobs=0,lastSaved=0,lastRecordCount=0,lastHeartbeat=0,lastImport=0,lastNews=0,lastBorrow=0,lastSources=0,lastFullEvaluation=0,budgetDay,baseline={},flexTask=null,financialTask=null,sourceTask=null,newsTask=null,borrowTask=null,evaluation,unsubscribe,leaseTimer,leaseError,renewing=Promise.resolve(),saving=Promise.resolve(),evaluationSavePending=false;let activeSymbols=new Set();
  let evaluationTimer;const stop=()=>{stopping=true;};process.once('SIGTERM',stop);process.once('SIGINT',stop);
  const heartbeat=async(status,error=null)=>{const value={mode:'continuous_external',status,started_at:new Date(started).toISOString(),heartbeat_at:now(),interval_seconds:interval,source_poll_target_seconds:15,quote_evaluation:'event_driven_serialized',ticks,jobs,error,maximum_minutes:Number.isFinite(maximumMs)?maximumMs/60000:null,broker_connections:0,pipeline_version:'readiness_completion.2026-11-09.v1',pipeline_commit:process.env.RS_PIPELINE_COMMIT||null,storage_usage:{scope:'collector_only_not_account_total',day:budgetDay,rows_read:Number(baseline.rows_read||0)+(env.usage?.rows_read||0),rows_written:Number(baseline.rows_written||0)+(env.usage?.rows_written||0),read_ceiling:450000,write_ceiling:researchWriteBudget(budgetDay,env.EXECUTION_REGISTRATION_DAY)},market_data:env.market?.health||null,publication:env.publicationHealth||null,restored_financial_scores:env.financialScoreCache?.size||0};await putState({DB:remote},'shadow_runtime',value);await putState(env,'shadow_runtime',value);await recordSessionHealth(env,value);await env.EVIDENCE.put('collector-dashboard/runtime.json',new TextEncoder().encode(JSON.stringify(value)),{httpMetadata:{contentType:'application/json'}});lastHeartbeat=Date.now();};
  async function budget(){const day=now().slice(0,10);if(day!==budgetDay){budgetDay=day;baseline=JSON.parse((await remote.prepare('SELECT value FROM rs_state WHERE key=?').bind('collector_usage:'+day).first())?.value||'{}');Object.assign(env.usage,{rows_read:0,rows_written:0,queries:0});}return Number(baseline.rows_read||0)+env.usage.rows_read<450000&&Number(baseline.rows_written||0)+env.usage.rows_written<researchWriteBudget(day,env.EXECUTION_REGISTRATION_DAY);}
  const renewLease=()=>{renewing=renewing.then(async()=>{const next=String(Date.now()+600000)+':'+token,ok=await remote.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_lease' AND value=? RETURNING value").bind(next,now(),lease).first();if(!ok)throw new Error('Collector lease lost');lease=next;}).catch(e=>{leaseError=e;stopping=true;});return renewing;};
  async function save(){
    const task=saving.catch(()=>{}).then(saveInternal);saving=task;return task;
  }
  async function saveInternal(){
    const current=await remote.prepare("SELECT value FROM rs_state WHERE key='collector_lease'").first();if(current?.value?.split(':').at(-1)!==token||Number(current.value.split(':')[0])<=Date.now())throw new Error('Collector lease lost; stopping before publication');
    await flushValidationSamples(env);await checkpoint.save({publicationMode:env.PUBLICATION_MODE,backgroundViews:true});lastSaved=Date.now();
    await remote.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind('collector_usage:'+budgetDay,JSON.stringify({rows_read:Number(baseline.rows_read||0)+env.usage.rows_read,rows_written:Number(baseline.rows_written||0)+env.usage.rows_written}),now()).run();
  }
  try{
    await remote.prepare("INSERT OR IGNORE INTO rs_state VALUES('collector_lease','0',?)").bind(now()).run();lease=String(Date.now()+600000)+':'+token;
    const claimed=await remote.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_lease' AND CAST(value AS INTEGER)<=? RETURNING value").bind(lease,now(),Date.now()).first();
    if(!claimed)return {skipped:true,reason:'Another collector owns the bounded lease'};
    leaseTimer=setInterval(renewLease,120000);env.collectorLeaseOwner=token;env.assertCollectorLease=()=>{if(leaseError)throw leaseError;if(Date.now()>=Number(lease.split(':')[0]))throw new Error('Collector lease expired');};
    await ensureRemoteReadIndexes(remote);checkpoint=await openCheckpoint(env);env.PUBLICATION_MODE='r2';env.FAST_MONITOR=true;env.ENABLE_DELAY_STUDY=true;env.eventSerial=new Map();env.EXPECTED_CADENCE_SECONDS='15';installFinancialImport(env);await env.restoreFinancialScores();await initializeShadow(env);await initializeExecution(env);await initializeValidation(env);await initializeReview(env);await budget();
    evaluation=createEvaluationLoop({shouldEvaluate:ticker=>!stopping&&(activeSymbols.has(ticker)||(['AAPL','SPY','IWM'].includes(ticker)&&env.validationPlan&&Date.now()>=Date.parse(env.validationPlan.start_at)&&Date.now()<=Date.parse(env.validationPlan.end_at))),onError:error=>console.error(JSON.stringify({event:'quote_evaluation_degraded',error:error.message})),evaluate:async event=>{
      const full=!!event||Date.now()-lastFullEvaluation>=15000,options={...(event?{event}:{}),pricesOnly:!full};await shadowTick(env,options);await executionTick(env,options);await validationTick(env);await reviewTick(env);
      if(full){lastFullEvaluation=Date.now();activeSymbols=new Set((await env.DB.prepare("SELECT ticker FROM rs_shadow_tracks WHERE state IN ('armed','partial_entry','open','exit_pending') UNION SELECT ticker FROM rs_execution_tracks WHERE state IN ('armed','partial_entry','open','exit_pending')").all()).results.map(r=>r.ticker));}
      if(full){const recent=(await env.DB.prepare('SELECT ticker FROM rs_events WHERE first_seen_at>=? AND ticker IS NOT NULL').bind(new Date(Date.now()-900000).toISOString()).all()).results.map(r=>r.ticker);env.market?.reconcileSymbols?.([...activeSymbols,...recent]);}
      const count=(await env.DB.prepare('SELECT (SELECT count(*) FROM rs_shadow_records)+(SELECT count(*) FROM rs_execution_records) AS count').first()).count;
      if(!stopping&&count!==lastRecordCount&&Date.now()-lastSaved>=5000&&!evaluationSavePending){evaluationSavePending=true;save().then(()=>{lastRecordCount=count;}).catch(error=>console.error(JSON.stringify({event:'quote_checkpoint_deferred',error:error.message}))).finally(()=>{evaluationSavePending=false;});}
    }});unsubscribe=env.market?.onQuote?.(ticker=>evaluation.notify(ticker));evaluationTimer=setInterval(()=>{if(!stopping)evaluation.notify(null);},1000);
    const lastTick=(await env.DB.prepare("SELECT value FROM rs_state WHERE key='last_completed_tick'").first())?.value;
    const sourceGap=await env.DB.prepare("SELECT id FROM rs_source_gaps WHERE resolved_at IS NULL AND source_id LIKE 'sec-%' LIMIT 1").first();if(needsStartupReconciliation(lastTick)||sourceGap)await enqueue(env,'reconcile',{day:etDay(now())},12,'startup-gap:'+etDay(now())+':'+lastTick);
    env.onShadowDecision=async event=>{
      const enrolled=await env.DB.prepare("SELECT state,payload FROM rs_shadow_tracks WHERE event_id=? UNION ALL SELECT state,payload FROM rs_execution_tracks WHERE event_id=?").bind(event.id,event.id).all();
      if(enrolled.results.length&&enrolled.results.every(r=>r.state==='retrospective'&&!JSON.parse(r.payload).entry_shares))return;
      await evaluation.run(event);
      const active=await env.DB.prepare("SELECT id FROM rs_execution_tracks WHERE event_id=? AND (state IN ('armed','partial_entry','open','exit_pending') OR json_extract(payload,'$.entry_shares')>0) UNION ALL SELECT id FROM rs_shadow_tracks WHERE event_id=? AND (state IN ('armed','partial_entry','open','exit_pending') OR json_extract(payload,'$.entry_shares')>0) LIMIT 1").bind(event.id,event.id).first();
      // Repeated untraded historical revisions are routine work. Opportunities
      // and any traded-position revisions commit before this callback returns.
      if(active){if(!borrowTask)borrowTask=pollIBKRBorrow(env).then(()=>evaluation.run()).catch(error=>console.error(JSON.stringify({event:'borrow_refresh_deferred',error:error.message}))).finally(()=>{borrowTask=null;});await save();}
    };
    await heartbeat('starting');
    if(env.market?.health?.status!=='not_configured')try{await env.market.quote('AAPL');}catch(e){await putState(env,'shadow_quote_error',{at:now(),message:e.message});}
    await evaluation.run();borrowTask=pollIBKRBorrow(env).catch(()=>{}).finally(()=>{borrowTask=null;});await save();
    while(!stopping&&!shouldStop()&&Date.now()-started<maximumMs){
      const cycle=Date.now();
      if(Number(lease.split(':')[0])-Date.now()<480000)await renewLease();env.assertCollectorLease();
      // Frequent research state is checkpointed to private object storage. The
      // database allowance never suspends detection, quotes, exits or validation.
      await budget();
      env.deadline=Date.now()+45000;
      try{
        if(Date.now()-lastImport>15000){const records=(await remote.prepare("SELECT payload FROM rs_shadow_evidence WHERE kind IN ('locate','margin','ssr','trading_status','cost_reconciliation','corporate_action') AND observed_at>=? ORDER BY observed_at LIMIT 1000").bind(new Date(Date.now()-7*86400000).toISOString()).all()).results;for(const r of records){const e=JSON.parse(r.payload);await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(e.id,e.event_id,e.kind,e.observed_at,r.payload).run();}if(!financialTask)financialTask=Promise.all([importFinancialProfiles(env),preparedManifest(env).then(m=>putState(env,'prepared_summary',m?.summary||{status:'not_prepared'}))]).catch(e=>console.error(JSON.stringify({event:'financial_import_retry',error:e.message}))).finally(()=>{financialTask=null;});lastImport=Date.now();}
        // Price and exit work precede filing backlogs. Source polling has a bounded deadline.
        await evaluation.run();
        if(!sourceTask&&Date.now()-lastSources>=15000){lastSources=Date.now();sourceTask=scheduled({cron:new Date().getUTCHours()===8?'17 8 * * *':'continuous'},{...env,DEFER_DISPATCH:true,deadline:Date.now()+12000}).catch(error=>console.error(JSON.stringify({event:'source_poll_degraded',error:error.message}))).finally(()=>{sourceTask=null;});}
        if(!newsTask&&Date.now()-lastNews>60000&&env.market?.health?.status!=='not_configured'){
          lastNews=Date.now();newsTask=(async()=>{
          try{for(const item of await env.market.news()){
            if(!item.article_url||!item.published_utc)continue;
            try{sourceURL(item.article_url);await enqueue(env,'news',{url:item.article_url,title:item.title,published_at:item.published_utc,first_seen_at:now()},15,'news:'+await digest(item.article_url));}
            catch{const parsed=classifyAnnouncement((item.title||'')+'\n'+(item.description||''),{published_at:item.published_utc});if(parsed){const id='market-news:'+item.id,exists=await env.DB.prepare('SELECT id FROM rs_events WHERE id=?').bind(id).first();if(!exists)await recordEvent(env,{...parsed,status:'needs_review',reason:'Provider summary requires primary-source and issuer verification',id,cik:null,ticker:item.tickers?.length===1?item.tickers[0]:null,company:item.title,published_at:item.published_utc,first_seen_at:now(),sources:[{url:item.article_url,sha256:await digest(JSON.stringify(item)),source:'market_news_summary'}],clock_basis:'Market-news publication and first receipt; first public release may be earlier'});}}
          }}catch(e){await putState(env,'shadow_news_error',{at:now(),message:e.message});}
          })().finally(()=>{newsTask=null;});
        }
        let handled=0;
        while(!stopping&&Date.now()-cycle<Math.max(1000,interval*1000)&&handled<2){if(!env.pending.length)await dispatch(env,{minimumPriority:10});if(!env.pending.length)await dispatch(env,{maximumPriority:9});const body=env.pending.shift();if(!body)break;const row=await env.DB.prepare('SELECT priority FROM rs_jobs WHERE id=?').bind(body.id).first();await consume({messages:[{body,ack(){}}]},{...env,deadline:Date.now()+(row?.priority>=10?15000:25000)});jobs++;handled++;}
        if(Date.now()-lastBorrow>60000){if(!borrowTask)borrowTask=pollIBKRBorrow(env).catch(()=>{}).finally(()=>{borrowTask=null;});if(!flexTask)flexTask=pollFlexBorrow(env).catch(()=>{}).finally(()=>{flexTask=null;});lastBorrow=Date.now();}
        ticks++;if(Date.now()-lastHeartbeat>=60000){await archiveDailyHealth(env);}
        if(Date.now()-lastHeartbeat>=60000)await heartbeat('running');
        const records=(await env.DB.prepare('SELECT (SELECT count(*) FROM rs_shadow_records)+(SELECT count(*) FROM rs_execution_records) AS count').first()).count;
        const active=await env.DB.prepare("SELECT id FROM rs_execution_tracks WHERE state IN ('armed','partial_entry','open','exit_pending') UNION ALL SELECT id FROM rs_shadow_tracks WHERE state IN ('armed','partial_entry','open','exit_pending') LIMIT 1").first();
        if(Date.now()-lastSaved>=(active?60000:120000)||(records!==lastRecordCount&&Date.now()-lastSaved>=5000)){await save();lastRecordCount=records;}
      }catch(e){await heartbeat('degraded',e.message);if(/lease lost/i.test(e.message))throw e;console.error(JSON.stringify({event:'shadow_cycle_degraded',error:e.message}));}
      await sleep(Math.max(1000,interval*1000-(Date.now()-cycle)));
    }
    env.assertCollectorLease();await heartbeat('handoff');await save();return {ticks,jobs,started_at:new Date(started).toISOString(),finished_at:now(),mode:'continuous_shadow'};
  }finally{
    process.removeListener('SIGTERM',stop);process.removeListener('SIGINT',stop);clearInterval(evaluationTimer);unsubscribe?.();
    try{if(sourceTask)await sourceTask;if(newsTask)await newsTask;if(borrowTask)await borrowTask;env.onShadowDecision=null;await evaluation?.close();if(flexTask)await flexTask;if(financialTask)await financialTask;if(env.financialLoads?.size)await Promise.allSettled([...env.financialLoads.values()]);if(checkpoint){try{await save();await checkpoint.flush();}finally{checkpoint.close();}}}finally{
    clearInterval(leaseTimer);await renewing;delete env.assertCollectorLease;delete env.collectorLeaseOwner;env.DB=remote;await remote.prepare("UPDATE rs_state SET value='0',updated_at=? WHERE key='collector_lease' AND value=?").bind(now(),lease||'').run();
    }
  }
}
