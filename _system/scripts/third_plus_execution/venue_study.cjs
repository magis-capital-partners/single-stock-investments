'use strict';
// All-name venue-event sensitivities, separate from qualified NBBO evidence and legacy opening fills.
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const A=require('./venue_archive.cjs'),P=require('./venue_portfolio.cjs'),R=require('./venue_replay.cjs'),{sha}=require('./archive.cjs');
const Bars=require('./bar_replay.cjs'),Qualified=require('./replay.cjs'),Identity=require('./identity.cjs'),Benchmark=require('./benchmark.cjs');
const Costs=require('./historical_costs.cjs');
const ROOT=path.resolve(__dirname,'../../..'),REL='_system/data/reverse_splits/third_plus_signal_study/';
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),write=(f,x)=>{fs.mkdirSync(path.dirname(f),{recursive:true});fs.writeFileSync(f,JSON.stringify(x)+'\n');};
const eventMetadata=e=>Object.fromEntries(['id','ticker','name','issuer','event_date','entry_day','ordinal'].map(k=>[k,e[k]]));
function loadContext(sourceRoot){
 const file=path.join(ROOT,'_system/scripts/reverse_split_repeat_study.cjs');
 let code=fs.readFileSync(file,'utf8');
 if(!code.includes("const ROOT = path.resolve(__dirname, '../..')"))throw Error('Frozen loader root seam changed');
 code=code.replace("const ROOT = path.resolve(__dirname, '../..')",'const ROOT = '+JSON.stringify(sourceRoot));
 const m=new Module(file,module);m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file));m._compile(code,file);return m.exports.load();
}
function publicSummary(x){
 if(!x.summary)return null;
 const s=x.summary;
 return {status:x.status,net_pnl:s.net_pnl,max_drawdown_dollars:s.max_drawdown_dollars,entered:s.entered,issuers:s.issuers,
  attempted:s.attempted,no_fill:s.no_fill,not_attempted:s.not_attempted,ssr_skipped:s.ssr_skipped,partial:s.partial,full:s.full,
  entry_dollars:s.entry_dollars,mean_position:s.mean_position,open_positions:s.open_positions,open_liability:s.open_liability,
  immature_positions:s.immature_positions,children:s.children,borrow_cost:s.borrow_cost,commissions_and_fees:s.commissions_and_fees,
  locate_cost:s.locate_cost,extra_impact_cost:s.extra_impact_cost,fractional_cleanup_positions:s.fractional_cleanup_positions,surplus_long_asset:s.surplus_long_asset,missing_exit_sessions:s.missing_exit_sessions,monthly:s.common_monthly.map(m=>[m.month,m.pnl]),
  pnl_without_best_issuer:s.pnl_without_best_issuer,pnl_without_best5_issuers:s.pnl_without_best5_issuers};
}
function summarizeOpportunity(event,x,position,previous){
 const entry=x?.entry;
 return {...eventMetadata(event),previous_decision:previous,execution_status:!x?'data_missing':x.status,
  attempted:!!entry?.children,filled:!!entry?.filled_shares,entry_dollars:entry?.notional??null,
  target_fraction:entry?.fill_fraction??null,children:entry?.children??null,
  exit_status:!position||!position.entry_units?'no_position':position.closed?'covered':position.deadline>=position.last_calendar_index?'immature':'open_residual',
  planned_exit:position?.planned_exit??null,closed:position?.closed??null,
  evaluated:!!x&&x.status!=='execution_data_missing',fill_basis:entry?.evidence||null,quote_basis:entry?.quote_basis||null,
  conditional:true,reason:entry?.reason??x?.reasons?.join(', ')??null};
}
function protocol(){return {
 schema:'third_plus_venue_protocol.v3',declared_date:'2026-10-27',target_usd:100000,nav_usd:10000000,maximum_names:3,horizon_sessions:20,
 primary:{policy:'E2',minutes:60,participation:.1,latency_ms:500,edge_filter:false,evidence_mode:'verified',borrow_mode:'verified'},
 risk_limits:{per_name_fraction:.0025,gross_fraction:.01,squeeze_loss_fraction:.02,margin_fraction:.8},
 purpose:'Attempt every frozen signal-qualified candidate only when its original security, quotes, trading status, borrow and costs can be established. Unknown access is unavailable evidence, never a rejection or a zero-profit trade.',
 evidence:'The available archive contains venue bars and sampled venue quotes. It does not establish historical borrow, consolidated NBBO, queue priority, loan terms or dated broker margin. Verified account performance is withheld until those inputs exist.',
 assumptions:[
  'No synthetic bid/ask or fixed 1.72% spread replaces missing quotes. Missing, stale or partial quote capture is an evidence gap, not a no-fill.',
  'No uniform within-bar volume distribution. Optional bar diagnostics require fresh observed quotes and a whole bar strictly beyond the resting limit after acknowledgement; queue and capture remain unverified.',
  'Both buy and sell fills respect the working limit. Pending cancellations keep reservations. Bar data cannot establish observed fills or national-price compliance.',
  'Verified account mode requires archived usable borrow quantity, rate and expiry, loan recall terms, consolidated national quotes, venue book/trades and dated margin evidence. Unknown values remain unavailable; no fixed borrow APR is a historical observation.',
  'Dated issuer-bound primary filings follow TNFA into QCLS and distinguish DBGI OTC trading, its later Nasdaq return, and PIXY suspension. No delisting implies a zero liability or an assumed broker release.',
  'Account equity becomes unknown at the first unresolved live-position price or execution gap. Later admissions, P&L and drawdown are withheld, rather than running indefinitely on frozen marks and occupied slots.',
  'The three-issuer limit and explicit account risk budgets apply to the account. Independent entry diagnostics omit slot competition and cannot be summed as executable account capacity.',
  'Morning account equity and pending parent reservations determine admission. Future no-fills, proceeds and closing marks cannot change an earlier morning decision. Paid fractional-cover surplus remains a marked long asset.',
  'A separate 20-session official-auction price benchmark follows verified symbol continuity and split factors. It excludes costs and execution and reports missing/immature outcomes; complete-price-case averages are selected-sample diagnostics, not strategy returns.',
  'The 21 signals and 24 settings are retrospective comparisons, not an untouched validation set. No best historical setting is promoted.',
  'Historical borrow, OTC executions and actual broker settlements cannot be reconstructed by inventing observations. No broker, ThetaData or paid acquisition is used.'
 ],production_authority:'none',broker_connections:0,theta_access:0};}
function build(sourceRoot){
 const parent=read(path.join(ROOT,REL,'fundamental_filters_v3/decision_audit.json')),study=read(path.join(ROOT,'dashboard/data/third_plus_study.json'));
 const previous=study.audit.models.requested_100k.dilution.statuses;
 const work=path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/ssr_execution_v2'),archive=A.load(work),ctx=loadContext(sourceRoot),costs=Costs.load(work);
 if(costs.status==='source_bound'){ctx.borrowTerms=costs.borrowTerms;ctx.marginAt=costs.marginAt;}
 const byid=new Map(ctx.candidates.filter(c=>c.ordinal>=3).map(c=>[c.id,c]));
 if(parent.events.length!==210||parent.events.some(e=>!byid.has(e.id)))throw Error('Cohort identity changed');
 const rules={},p=protocol(),bench=new Map(),cache=new Map();
 const entry=(c,minutes=60)=>{
  const key=c.id+'|'+minutes;if(cache.has(key))return cache.get(key);
  const s=archive.sessions.get(c.id),[start,end]=s?P.entryWindow(s,minutes):[0,1],gaps=Bars.gaps(s,start,end);
  const result=gaps.length?{status:'data_missing',gaps}:Bars.replay(s,{policy:'E2',minutes,participation:.1,latency_ms:500,capture:.5,target_usd:p.target_usd,start_ms:start,end_ms:end});
  cache.set(key,result);return result;
 };
 try{
  for(const e of parent.events)bench.set(e.id,Benchmark.event(ctx,byid.get(e.id)));
  for(const rule of study.rules){
   const selected=parent.events.filter(e=>rule.requires.every(k=>e.signals[k]==='pass')).map(e=>byid.get(e.id));
   const models=[],coverageSets={},decisionSets={};
   for(const policy of ['E0','E1','E2'])for(const minutes of [30,60,240,390])for(const participation of [.05,.1]){
    const settings={...p.primary,policy,minutes,participation,risk_limits:p.risk_limits,engine:Qualified};
    const x=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,settings),{engine,...published}=settings;
    const decisions=x.audit.map(a=>({id:a.id,status:a.status,reasons:a.reasons||[]})),coverageKey=sha(JSON.stringify(x.coverage)).slice(0,20),decisionKey=sha(JSON.stringify(decisions)).slice(0,20);
    coverageSets[coverageKey]=x.coverage;decisionSets[decisionKey]=decisions;
    models.push({id:[policy,minutes,participation].join('_'),...published,status:selected.length?x.status:'no_candidates',selected:selected.length,summary:selected.length?publicSummary(x):null,coverage_set:coverageKey,decision_set:decisionKey});
   }
   const selectedIds=new Set(selected.map(c=>c.id));
   const opportunities=parent.events.map((e,i)=>{
    const c=byid.get(e.id),b=bench.get(e.id),base={...eventMetadata(e),previous_decision:previous[i],price_path_status:b.status,resolved_ticker:b.resolved_ticker||c.ticker,lineage_sources:b.source_urls||[],conditional:true};
    if(!selectedIds.has(e.id))return {...base,execution_status:rule.requires.some(k=>e.signals[k]==='fail')?'signal_fail':'signal_unknown',attempted:false,filled:false,entry_dollars:null,gaps:[]};
    const x=entry(c),extended=entry(c,240),full=entry(c,390);
    return {...base,execution_status:x.status==='data_missing'?'execution_data_missing':x.status,attempted:!!x.children,filled:!!x.filled_shares,entry_dollars:x.notional??null,children:x.children??null,
     quote_basis:archive.sessions.get(c.id)?.quote_basis||'missing',gaps:x.gaps||[],fill_basis:x.evidence||null,exit_status:'not_established',
     extended_filled:!!extended.filled_shares,extended_entry_dollars:extended.notional??null,full_session_filled:!!full.filled_shares,full_session_entry_dollars:full.notional??null};
   });
   const counts=opportunities.filter(e=>selectedIds.has(e.id)).reduce((a,e)=>(a[e.execution_status]=(a[e.execution_status]||0)+1,a),{});
   rules[rule.id]={label:rule.label,selected:selected.length,models,coverage_sets:coverageSets,decision_sets:decisionSets,opportunities,entry_diagnostics:{status:'unverified_bar_scenario',counts,performance:null},price_benchmark:Benchmark.summarize(selected.map(c=>bench.get(c.id)))};
   console.log('Evidence audit',rule.id,selected.length,'selected; verified performance',models[0].summary?'available':'unavailable');
  }
 }finally{ctx.prices.close();}
 const code=['venue_replay.cjs','bar_replay.cjs','venue_portfolio.cjs','venue_archive.cjs','venue_study.cjs','venue_capture.py','export_venue_inputs.cjs','replay.cjs','archive.cjs','identity.cjs','benchmark.cjs','historical_costs.cjs'].map(f=>'_system/scripts/third_plus_execution/'+f);
 code.push('_system/scripts/reverse_split_repeat_study.cjs','_system/scripts/short_framework/adapters.cjs','_system/scripts/third_plus_signal/statistics.cjs',REL+'fundamental_filters_v3/decision_audit.json',REL+'ssr_execution_v2/security_lifecycle.v1.json','dashboard/data/third_plus_study.json','dashboard/third-plus-venue.js','_system/scripts/third_plus_execution/venue_publish.cjs');
 const sources=Object.fromEntries(code.map(f=>[f,sha(fs.readFileSync(path.join(ROOT,f)))]));
 const d={schema:'third_plus_venue_backtest.v3',market_through:study.market_through,first:study.first,protocol:p,rules,
  archive:{status:archive.status,mode:archive.mode,index_sha256:archive.hash,sessions:archive.sessions.size,counts:archive.counts||null,historical_costs_status:costs.status,historical_costs_sha256:costs.hash},
  acquisition:{authorized_cap_usd:0,reserved_cost_usd:0},sources,lifecycle:Identity.ledger,
  result_status:'historical_execution_not_established',legacy_result_retired:true,legacy_exclusions:{total:129,ssr:100,name_slots:28,liquidity:1},verified_borrow_entries:0,verified_nbbo_entries:0,production_authority:'none'};
 d.data_version=sha(JSON.stringify(d));
 write(path.join(ROOT,REL,'ssr_execution_v2/summary.json'),d);write(path.join(ROOT,'dashboard/data/third_plus_venue_execution.json'),d);
 write(path.join(ROOT,'dashboard/data/third_plus_venue_execution_manifest.json'),{schema:'third_plus_venue_manifest.v3',payload:'third_plus_venue_execution.json',data_version:d.data_version,sha256:sha(fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_venue_execution.json')))});
 return d;
}
module.exports={build,protocol,publicSummary,summarizeOpportunity,loadContext};
if(require.main===module){const i=process.argv.indexOf('--source-root');if(i<0)throw Error('--source-root required');build(path.resolve(process.argv[i+1]));}
