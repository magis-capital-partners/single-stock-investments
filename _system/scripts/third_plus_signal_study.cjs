#!/usr/bin/env node
'use strict';
// Complete offline third-plus signal study. No broker/network/scheduler capability.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),cp=require('node:child_process');
const B=require('./reverse_split_repeat_study.cjs'),F=require('./third_plus_signal/features.cjs'),S=require('./third_plus_signal/statistics.cjs');
const E=require('./third_plus_signal/engine.cjs'),J=require('./third_plus_signal/forward.cjs'),R=require('./third_plus_signal/report.cjs');
const ROOT=path.resolve(__dirname,'../..'),DATA=path.join(ROOT,'_system/data/reverse_splits');
const OUT=path.join(DATA,'third_plus_signal_study'),PRIVATE=path.join(DATA,'local/third_plus_signal_study');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
function write(f,x){fs.mkdirSync(path.dirname(f),{recursive:true});const text=typeof x==='string'?x:JSON.stringify(x,null,2)+'\n';fs.writeFileSync(f+'.tmp',text);fs.renameSync(f+'.tmp',f);}
function fileHash(f){
 const h=crypto.createHash('sha256'),fd=fs.openSync(f,'r'),buf=Buffer.allocUnsafe(1024*1024);
 try{let n;while((n=fs.readSync(fd,buf,0,buf.length,null))>0)h.update(buf.subarray(0,n));}finally{fs.closeSync(fd);}return h.digest('hex');
}
const digest=x=>J.hash(x),rel=f=>path.relative(ROOT,f).replace(/\\/g,'/');
function publicSummary(s){const {issuer_concentration,...rest}=s;return rest;}
function sourceFiles(){return [__filename,path.join(__dirname,'third_plus_signal_study.test.cjs'),path.join(__dirname,'reverse_split_repeat_study.cjs'),...['features','statistics','engine','forward','report'].map(n=>path.join(__dirname,'third_plus_signal',n+'.cjs'))];}
function tests(){
 const file=path.join(__dirname,'third_plus_signal_study.test.cjs');
 const result=cp.spawnSync(process.execPath,['--test','--test-reporter=tap',file],{cwd:ROOT,windowsHide:true,encoding:'utf8',maxBuffer:8e6});
 fs.mkdirSync(PRIVATE,{recursive:true});write(path.join(PRIVATE,'test_output.log'),(result.stdout||'')+(result.stderr||''));
 const state={passed:result.status===0,status:result.status,at:new Date().toISOString(),pass_count:Number((result.stdout||'').match(/# pass (\d+)/)?.[1]||0),source_hashes:Object.fromEntries(sourceFiles().map(f=>[rel(f),fileHash(f)]))};
 write(path.join(PRIVATE,'tests.json'),state);if(!state.passed)throw new Error('Study tests failed; see local test_output.log');return state;
}
function freeze(plan){
 const protocol={schema:'third_plus_signal_study.protocol.v1',frozen_at:new Date().toISOString(),plan_sha256:fileHash(path.join(OUT,'plan.json')),plan,
   implementation:{primary:{horizon:20,cost:'base',cap:.01,nav:1000000,maximumNames:3,ssrMode:'strict',causalCarry:true},
    replication_horizon:10,common_maturity_sessions:20,primary_new_claims:11,core_arms:F.ARMS.map(x=>x.id),
    amendment_before_new_returns:[
     'Use a declared $1m reference NAV for the fixed-budget primary; it is not an assertion about the user account.',
     'Restricted/unknown SSR is skipped in the primary. Legacy 50% passive capture is an unsupported execution sensitivity, not verified fills.',
     'Source leads remain unverified until two independent outcome-blinded source-bound reviews are imported.',
     'No historical research promotion while any selected position is unresolved; this is a stricter evidence gate, not an inferred zero-value exit.',
     'A 20% completed-close risk exit and up-to-three-bar failed-rebound test are implemented, but run only for finalists.',
     'S1 is conditional on cached funding coverage; any observed unresolved financing blocks pro forma selection.'
    ],rule_thresholds:'Exactly the seven original fixed thresholds; no threshold search.'},
   source_hashes:Object.fromEntries(sourceFiles().map(f=>[rel(f),fileHash(f)]))};
 const target=path.join(OUT,'protocol_frozen.json');
 if(fs.existsSync(target)){
   const old=read(target);
   if(old.plan_sha256!==protocol.plan_sha256)throw new Error('Frozen plan changed; use an explicit new protocol version');
   return old;
 }
 fs.writeFileSync(target,JSON.stringify(protocol,null,2)+'\n',{flag:'wx'});return protocol;
}
function build(){
 fs.mkdirSync(OUT,{recursive:true});fs.mkdirSync(PRIVATE,{recursive:true});
 const plan=read(path.join(OUT,'plan.json')),protocol=freeze(plan),testState=tests();
 console.log('Protocol frozen; '+testState.pass_count+' tests passed. Loading existing caches.');
 const ctx=B.load(),inputCandidates=ctx.candidates.filter(r=>r.ordinal>=3),commonFirst=inputCandidates.filter(r=>r.day).map(r=>r.day).sort()[0];
 const inputFiles=[path.join(DATA,'local/profit_program/20261022_v1/effective_events.local.json'),
  path.join(DATA,'local/profit_program/20261022_v1/corporate_action_repairs.json'),
  path.join(path.dirname(ctx.prices.db.location()),'event_outcomes.parts.json'),ctx.prices.db.location(),path.join(path.dirname(ctx.prices.db.location()),'input.sqlite')];
 for(const f of inputFiles.slice())if(fs.existsSync(f+'-wal'))inputFiles.push(f+'-wal');
 const initialStats=new Map(inputFiles.map(f=>[f,{size:fs.statSync(f).size,mtime:fs.statSync(f).mtimeMs}]));
 const baselines=[];
 for(const horizon of [10,20]){
   const r=B.replay(ctx,{horizon,cost:'base',cap:null,financial:'all',ordinal:'extended',fastStats:true});
   const expected=horizon===10?80279.43124008452:685851.8802611388,delta=r.summary.net_pnl-expected;
   if(Math.abs(delta)>.01)throw new Error('Legacy baseline did not reproduce: '+horizon);
   baselines.push({horizon,net:r.summary.net_pnl,expected,delta});
 }
 console.log('Both legacy baselines reproduced exactly.');
 const audit=F.build(ctx,ROOT,PRIVATE),featureIndex=new Map(audit.snapshots.map(r=>[r.id,r]));
 write(path.join(PRIVATE,'features.local.json'),audit.snapshots);
 write(path.join(PRIVATE,'financing_source_review_queue.local.json'),audit.leadAudit);
 write(path.join(PRIVATE,'source_hashes.local.json'),{sources:audit.sourceHashes,facts:audit.factHashes});
 const arms=F.ARMS,models=[],modelMap=new Map(),performanceCache=new Map();
 const commonOpts={financial:'all',ordinal:'extended',fastStats:true,causalCarry:true};
 let count=0;
 function run(id,options,rows=inputCandidates,meta={}){
   const opts={...commonOpts,...options};
   const key=digest({opts,rows:rows.map(r=>[r.id,r.day,r.maturity_index??r.i??null,r.exit_index_override??null])});
   let raw=performanceCache.get(key);
   if(!raw){
     raw=S.normalise(B.replay({...ctx,candidates:rows},opts),commonFirst);
     performanceCache.set(key,raw);write(path.join(PRIVATE,'ledgers',key+'.local.json'),raw);
   }
   const result={...raw,summary:{...raw.summary},id,...meta,ledger_sha256:key};
   models.push(result);modelMap.set(id,result);
   if(++count%25===0)console.log('Completed '+count+' model definitions; '+performanceCache.size+' unique portfolio replays.');
   return result;
 }
 const selected=(id,covered=false)=>inputCandidates.filter(r=>F.armState(featureIndex.get(r.id),id,covered).state==='pass');
 const primaryOpts={horizon:20,cost:'base',cap:.01,nav:1000000,maximumNames:3,ssrMode:'strict'};
 const primary=[],coveredResults=new Map(),replication=[];
 for(const arm of arms){
   primary.push(run('primary_'+arm.id,primaryOpts,selected(arm.id),{kind:'primary',arm:arm.id}));
   coveredResults.set(arm.id,run('covered_'+arm.id,primaryOpts,selected(arm.id,true),{kind:'covered_baseline',arm:arm.id}));
   replication.push(run('replication_'+arm.id,{...primaryOpts,horizon:10},selected(arm.id),{kind:'replication',arm:arm.id}));
 }
 const fullBase=primary.find(r=>r.arm==='baseline'),rows=[];
 for(const r of primary){
   const vs_all=S.comparison(r,fullBase),vs_covered=S.comparison(r,coveredResults.get(r.arm));
   vs_all.baseline_drawdown=fullBase.summary.max_drawdown_dollars;
   rows.push({arm:r.arm,result:r,vs_all,vs_covered,p:Math.max(vs_all.p_conservative,vs_covered.p_conservative)});
 }
 const tested=rows.filter(r=>!['baseline','score60'].includes(r.arm));
 S.holm(tested);
 const primaryReport=rows.map(r=>{
   const comparator=['baseline','score60'].includes(r.arm);
   const decision=comparator?{status:'reference',reasons:[]}:S.eligibleForPromotion(r.result,r.vs_all,r.vs_covered,r.holm_p);
   return {arm:r.arm,summary:publicSummary(r.result.summary),vs_all:r.vs_all,vs_covered:r.vs_covered,holm_p:comparator?null:r.holm_p,decision};
 });
 const finalists=primaryReport.filter(r=>r.decision.status==='research_candidate').sort((a,b)=>b.summary.net_pnl-a.summary.net_pnl).slice(0,2).map(r=>r.arm);
 const sensitivities=[],accounts=[],diagnostics=[];
 for(const arm of arms)for(const horizon of [10,20]){
   for(const cap of [null,.001,.01,.05])for(const ssrMode of ['strict','proxy']){
     sensitivities.push(run(['capacity',arm.id,horizon,cap,ssrMode].join('_'),{horizon,cost:'base',cap,ssrMode},selected(arm.id),{kind:'capacity',arm:arm.id}).summary);
   }
   for(const cost of ['lower_cost','depth_base','stress']){
     sensitivities.push(run(['cost',arm.id,horizon,cost].join('_'),{...primaryOpts,horizon,cost},selected(arm.id),{kind:'cost',arm:arm.id}).summary);
   }
   for(const nav of [500000,1000000,5000000,10000000]){
     accounts.push(run(['account',arm.id,horizon,nav].join('_'),{...primaryOpts,horizon,nav},selected(arm.id),{kind:'account',arm:arm.id}).summary);
   }
   diagnostics.push({...run(['provider',arm.id,horizon].join('_'),{...primaryOpts,horizon,ordinal:'provider'},selected(arm.id),{kind:'provider_only_history',arm:arm.id}).summary,arm:arm.id,kind:'provider_only_history'});
 }
 for(const horizon of [10,20]){
   const reported=inputCandidates.filter(r=>featureIndex.get(r.id).signals.reported_runway.state==='pass');
   diagnostics.push({...run('reported_runway_'+horizon,{...primaryOpts,horizon},reported,{kind:'unadjusted_reported_runway_exploratory',arm:'reported_runway'}).summary,arm:'reported_runway',kind:'unadjusted_reported_runway_exploratory'});
 }
 // Strict verified execution is a separate zero-entry account, never inferred from proxies.
 const verified=run('verified_execution',{...primaryOpts,evidence:'verified'},inputCandidates,{kind:'verified_execution',arm:'baseline'});
 const shiftedCandidates=ctx.candidates.map(r=>E.shiftCandidate(ctx,r,1)),shiftedCtx={...ctx,candidates:shiftedCandidates};
 const shiftedAudit=F.build(shiftedCtx,ROOT,PRIVATE),shiftIndex=new Map(shiftedAudit.snapshots.map(s=>[s.id,s]));
 write(path.join(PRIVATE,'one_session_delay_features.local.json'),shiftedAudit.snapshots);
 for(const arm of arms){
   const rows=shiftedCandidates.filter(r=>r.ordinal>=3&&F.armState(shiftIndex.get(r.id),arm.id).state==='pass');
   diagnostics.push({...run('clock_delay_'+arm.id,{...primaryOpts,maturitySessions:21},rows,{kind:'one_extra_session_clock_delay',arm:arm.id}).summary,arm:arm.id,kind:'one_extra_session_clock_delay'});
 }
 const controls=arms.filter(a=>a.id.startsWith('S')).map(arm=>{
   const data=fullBase.positions.filter(p=>p.closed).map(p=>{
     const f=featureIndex.get(p.id),sig=f.signals[arm.id];
     return {issuer:p.issuer,year:p.year,y:p.net_return,pass:sig.state==='unknown'?null:sig.state==='pass',price:p.entry_price,adv:p.adv_dollars,ratio:f.control.ratio,ordinal:p.ordinal};
   });
   return {arm:arm.id,...S.controlledSignal(data)};
 });
 const issuerFirst=new Map();
 for(const r of inputCandidates.filter(r=>r.day).sort((a,b)=>a.day.localeCompare(b.day)))if(!issuerFirst.has(r.issuer))issuerFirst.set(r.issuer,r.day);
 const issuerDiagnostics=primary.map(r=>({arm:r.arm,new_vs_returning:['first_eligible_event','returning_issuer'].map(kind=>{
   const p=r.positions.filter(p=>(p.day===issuerFirst.get(p.issuer))===(kind==='first_eligible_event'));
   return {kind,n:p.length,issuers:new Set(p.map(p=>p.issuer)).size,net:S.sum(p.map(p=>p.pnl)),unresolved:p.filter(p=>p.units>1e-9).length};
 })}));
 const ordinalDiagnostics=primary.map(r=>({arm:r.arm,strata:['3','4','5+'].map(label=>{
   const p=r.positions.filter(p=>label==='3'?p.ordinal===3:label==='4'?p.ordinal===4:p.ordinal>=5);
   return {ordinal:label,n:p.length,issuers:new Set(p.map(p=>p.issuer)).size,net:S.sum(p.map(p=>p.pnl))};
 })}));
 const wf=E.walkForward(ctx,primary,featureIndex,run);
 const timing_stage={reason:finalists.length?'Finalist-only timing/exit experiments, with matching delayed controls.':'No historical finalist passed all gates; the implemented timing/exit stage is not searched on rejected rules.',models:[]};
 for(const arm of finalists){
   const candidates=selected(arm),confirmation=E.delayConfirmation(ctx,candidates);
   const fresh=F.build({...ctx,candidates:confirmation.rows},ROOT,PRIVATE),fi=new Map(fresh.snapshots.map(s=>[s.id,s]));
   const confirmed=confirmation.rows.filter(r=>F.armState(fi.get(r.id),arm).state==='pass');
   const delayed=run('confirmation_'+arm,{...primaryOpts,maturitySessions:23},confirmed,{kind:'failed_rebound_next_open',arm});
   const baselineDelay=run('matched_delay_'+arm,{...primaryOpts,maturitySessions:23},candidates.map(r=>E.shiftCandidate(ctx,r,3)),{kind:'unconditional_three_session_delay',arm});
   const anchored=run('anchored_exit_'+arm,{...primaryOpts,maturitySessions:23},confirmed.map(r=>({...r,exit_index_override:ctx.candidates.find(x=>x.id===r.id).i+19})),{kind:'matched_signal_to_exit_window',arm});
   const stop=run('close_risk_exit_'+arm,{...primaryOpts,stopCloseFraction:.2},candidates,{kind:'next_open_after_20pct_close_breach',arm});
   timing_stage.models.push(...[delayed,baselineDelay,anchored,stop].map(r=>({...publicSummary(r.summary),arm,kind:r.kind})));
   write(path.join(PRIVATE,'confirmation_'+arm+'.local.json'),confirmation.audit);
 }
 const shadowPolicy={schema:'third_plus_signal_shadow.v1',registered_at:new Date().toISOString(),research_only:true,production_authority:'none',
   protocol_sha256:digest(protocol),finalists,mode:finalists.length?'observe_finalists':'abstain_no_validated_finalist',
   minimum_review:{eligible_decisions:50,distinct_issuers:30},thresholds:plan.signals.map(x=>({id:x.id,rule:x.rule})),
   enrollment:'Manual only; source/issuer bindings, independent reviews where required and timestamped broker evidence. No scheduler or order route.'};
 const dataVersion=digest({protocol:digest(protocol),features:audit.factHashes,financing_sources:audit.sourceHashes,reviews:fs.existsSync(path.join(PRIVATE,'financing_reviews.local.json'))?fileHash(path.join(PRIVATE,'financing_reviews.local.json')):null,code:Object.fromEntries(sourceFiles().map(f=>[rel(f),fileHash(f)]))});
 const registrationKey=digest({protocol:digest(protocol),dataVersion,finalists});
 const registrationFile=path.join(OUT,'forward_policies',registrationKey+'.json');
 const frozenPolicy=fs.existsSync(registrationFile)?read(registrationFile):{...shadowPolicy,data_version:dataVersion};
 if(!fs.existsSync(registrationFile))write(registrationFile,frozenPolicy);
 write(path.join(OUT,'forward_policy.json'),{...frozenPolicy,sha256:digest(frozenPolicy),registration_key:registrationKey});
 const journal=path.join(PRIVATE,'forward_shadow.jsonl');if(!fs.existsSync(journal))fs.writeFileSync(journal,'',{flag:'wx'});
 for(const [f,st]of initialStats){const now=fs.statSync(f);if(now.size!==st.size||now.mtimeMs!==st.mtime)throw new Error('Input changed during study: '+rel(f));}
 const manifest={schema:'third_plus_signal_manifest.v1',protocol_sha256:digest(protocol),source_hashes:Object.fromEntries(sourceFiles().map(f=>[rel(f),fileHash(f)])),
   input_hashes:Object.fromEntries(inputFiles.map(f=>[rel(f),fileHash(f)])),feature_source_hashes:audit.sourceHashes,companyfacts_hashes:audit.factHashes,
   code_matches_registered_freeze:JSON.stringify(protocol.source_hashes)===JSON.stringify(Object.fromEntries(sourceFiles().map(f=>[rel(f),fileHash(f)]))),
   dataset_rows:inputCandidates.length,price_asof:ctx.prices.last,new_downloads_usd:0};
 const revisionFile=path.join(OUT,'implementation_revision.json');
 manifest.implementation_revision=fs.existsSync(revisionFile)?read(revisionFile):null;
 manifest.all_code_changes_accounted_for=Object.entries(manifest.source_hashes).every(([file,sha])=>protocol.source_hashes[file]===sha||manifest.implementation_revision?.code_changes.some(c=>c.file===file&&c.registered_sha256===protocol.source_hashes[file]&&c.current_sha256===sha));
 if(!manifest.all_code_changes_accounted_for)throw new Error('Implementation revision must account for code changes against the frozen protocol');
 write(path.join(OUT,'manifest.json'),manifest);
 const primaryModels=primaryReport.map(x=>({...x}));
 const doc={schema:'third_plus_signal_study.results.v1',built_at:new Date().toISOString(),price_asof:ctx.prices.last,protocol_sha256:digest(protocol),
   coverage_candidates:audit.snapshots.length,coverage:audit.coverage,common_first:commonFirst,common_months:fullBase.summary.common_monthly.length,
   audit:{independent_financing_reviews:audit.reviews_count,financing_documents:audit.leadAudit.length,completion_claim_documents:audit.leadAudit.filter(x=>x.completed_claims.length).length,source_hashes:Object.keys(audit.sourceHashes).length,companyfacts_issuers:Object.keys(audit.factHashes).length,
     reason_counts:Object.fromEntries(['S1','S2','S3','S4','S5','S6','S7'].map(k=>[k,Object.fromEntries([...S.grouped(audit.snapshots,s=>s.signals[k].reason)].map(([reason,v])=>[reason,v.length]))]))},
   primary:primaryModels,replication:replication.map(r=>({...publicSummary(r.summary),arm:r.arm})),
   sensitivities:sensitivities.map((s,i)=>({...publicSummary(s),arm:models.find(r=>r.summary===s)?.arm||null})),
   accounts:accounts.map(s=>({...publicSummary(s),arm:models.find(r=>r.summary===s)?.arm||null})),
   diagnostics:diagnostics.map(publicSummary),controls,issuer_diagnostics:issuerDiagnostics,ordinal_diagnostics:ordinalDiagnostics,
   walk_forward:{decisions:wf.decisions,summary:publicSummary(wf.result.summary)},timing_stage,finalists,
   verified_execution:publicSummary(verified.summary),forward:J.summary(journal),
   validation:{tests:testState,baselines,unique_portfolio_replays:performanceCache.size,model_definitions:models.length,holdout_files_opened:0},
   status:'completed_offline_research',production_authority:'none'};
 doc.data_version=dataVersion;write(path.join(OUT,'summary.json'),doc);
 write(path.join(OUT,'runs',dataVersion,'summary.json'),doc);
 write(path.join(OUT,'feature_dictionary.json'),{signals:plan.signals,arms,pass_fail_unknown:true,coverage:audit.coverage,notes:plan.missing_data});
 write(path.join(OUT,'experiment_register.json'),{protocol_sha256:digest(protocol),primary_claims:tested.map(r=>({arm:r.arm,raw_p:r.p,holm_p:r.holm_p})),
   models:models.map(r=>({id:r.id,kind:r.kind,arm:r.arm,options:{horizon:r.summary.horizon,cap:r.summary.cap,cost:r.summary.cost,nav:r.summary.nav||null,ssrMode:r.summary.ssrMode||null},ledger_sha256:r.ledger_sha256,entered:r.summary.entered})),
   all_experiments_reported:true});
 const report=R.markdown(doc);write(path.join(OUT,'REPORT.md'),report);
 write(path.join(OUT,'runs',dataVersion,'REPORT.md'),report);
 write(path.join(OUT,'runs',dataVersion,'manifest.json'),manifest);
 write(path.join(OUT,'REPORT.html'),R.html(doc,report,primary.filter(r=>['baseline','S3','S5','S7'].includes(r.arm))));
 write(path.join(OUT,'implementation_status.json'),{status:'implemented_and_executed',built_at:doc.built_at,code_tests_passed:testState.passed,models:models.length,
   completed:['as_of_features','source_audit','13_core_arms','covered_baselines','capacity_cost_capital_sensitivities','Holm_and_bootstrap','causal_walk_forward','finalist_gated_timing_exits','manual_immutable_shadow_journal','reproduction_and_reports'],
   evidence_gaps:['Independent financing reviews absent unless imported','Historical approved locates and actual fills absent','No verified PIT security master','No new prospective observations fabricated'],
   finalists,production_authority:'none',new_market_data_spend_usd:0});
 ctx.prices.close();
 console.log(JSON.stringify({saved:rel(OUT),models:models.length,unique:performanceCache.size,finalists,
   primary:doc.primary.map(r=>({arm:r.arm,n:r.summary.entered,issuers:r.summary.issuers,net:r.summary.net_pnl,delta:r.vs_all.incremental_net,status:r.decision.status})),
   tests:testState.pass_count},null,2));
 return doc;
}
function importReviews(file){
 const incoming=read(file);if(!Array.isArray(incoming))throw new Error('Review input must be an array');
 const target=path.join(PRIVATE,'financing_reviews.local.json'),existing=fs.existsSync(target)?F.loadReviews(target):[],all=existing.slice();
 for(const r of incoming){const old=all.find(v=>v.issuer===r.issuer&&v.deal_id===r.deal_id);
   if(old&&digest(old)!==digest(r))throw new Error('Cannot rewrite a frozen financing review');if(!old)all.push(r);}
 fs.mkdirSync(PRIVATE,{recursive:true});const temp=target+'.validate';fs.writeFileSync(temp,JSON.stringify(all));
 try{F.loadReviews(temp);const ctx=B.load();try{const real=fs.existsSync(target)?fs.readFileSync(target):null;write(target,all);try{F.build(ctx,ROOT,PRIVATE);}catch(e){if(real)fs.writeFileSync(target,real);else fs.unlinkSync(target);throw e;}}finally{ctx.prices.close();}}
 finally{fs.unlinkSync(temp);}
 return {imported:all.length-existing.length,total:all.length,next:'Run build to create a new versioned study; original protocol remains frozen.'};
}
function args(argv){const r={command:argv[0]||'help'};for(let i=1;i<argv.length;i+=2){if(!argv[i].startsWith('--')||!argv[i+1])throw new Error('Expected --option value');r[argv[i].slice(2)]=argv[i+1];}return r;}
function main(){
 const opts=args(process.argv.slice(2));
 if(opts.command==='build')return build();
 if(opts.command==='verify')return console.log(JSON.stringify(tests(),null,2));
 if(opts.command==='review-import'){if(!opts.input)throw new Error('--input required');return console.log(JSON.stringify(importReviews(path.resolve(opts.input)),null,2));}
 if(opts.command==='shadow-import'){if(!opts.input)throw new Error('--input required');const records=read(path.resolve(opts.input));if(!Array.isArray(records))throw new Error('Input must be an array');
 const folder=path.join(OUT,'forward_policies'),registered=new Set(fs.existsSync(folder)?fs.readdirSync(folder).filter(f=>f.endsWith('.json')).map(f=>digest(read(path.join(folder,f)))):[]);
 for(const r of records)if(r.kind==='enrollment'&&!registered.has(r.policy_sha256))throw new Error('Enrollment policy was not registered by this study');
 return console.log(JSON.stringify(J.append(path.join(PRIVATE,'forward_shadow.jsonl'),records),null,2));}
 if(opts.command==='shadow-status')return console.log(JSON.stringify(J.summary(path.join(PRIVATE,'forward_shadow.jsonl')),null,2));
 console.log('Offline study: build | verify | review-import --input FILE | shadow-import --input FILE | shadow-status. No broker or order command.');
}
module.exports={build,tests,importReviews,fileHash,freeze,publicSummary};
if(require.main===module)try{main();}catch(e){console.error(e.stack||e);process.exitCode=1;}
