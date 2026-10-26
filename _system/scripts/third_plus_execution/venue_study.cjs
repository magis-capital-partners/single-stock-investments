'use strict';
// All-name venue-event sensitivities, separate from qualified NBBO evidence and legacy opening fills.
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const A=require('./venue_archive.cjs'),P=require('./venue_portfolio.cjs'),R=require('./venue_replay.cjs'),{sha}=require('./archive.cjs');
const Bars=require('./bar_replay.cjs');
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
  locate_cost:s.locate_cost,extra_impact_cost:s.extra_impact_cost,fractional_cleanup_positions:s.fractional_cleanup_positions,uncredited_surplus_asset_reserve:s.uncredited_surplus_asset_reserve,missing_exit_sessions:s.missing_exit_sessions,monthly:s.common_monthly.map(m=>[m.month,m.pnl]),
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
 schema:'third_plus_venue_protocol.v2',declared_date:'2026-10-26',target_usd:100000,nav_usd:10000000,maximum_names:3,horizon_sessions:20,
 primary:{policy:'E2',minutes:60,participation:.1,latency_ms:500,edge_filter:false,impact_bps:10},
 purpose:'Attempt every signal-qualified event under SSR and retain observed-model partial/no-fill outcomes. A separate independent opportunity ledger removes slot competition only for attribution.',
 methods:'E0 matched SSR skip; E1 join venue offer; E2 improve one permitted venue tick. No automatic profitability selection.',
 evidence:'Actual timestamped Nasdaq book and trade records. Venue BBO is not NBB. Legal eligibility remains conditional on broker/venue handling. This is not a qualified consolidated-NBBO or borrow-verified backtest.',
 assumptions:['Historical usable borrow is assumed; fees use 50% APR with 150% stress.','National-price eligibility is conditional; source venue quotes are never renamed NBBO.','Unknown trade aggressors use a disclosed pretrade quote classifier.','Displayed queue is consumed by subsequent buying flow; no bar-touch or fixed whole-order capture percentage.','No own-order price impact is observed; add 10bp per executed side and 30bp stress.','No new edge forecast filter; frozen signals and fixed execution deadlines decide attempts.','Source gaps and missing covers retain liabilities and incomplete-result labels.','Three issuer slots stay in the account model; independent opportunities are separate counterfactuals and cannot be summed as executable account capacity.'],
 production_authority:'none',broker_connections:0,theta_access:0};}
function build(sourceRoot){
 const parent=read(path.join(ROOT,REL,'fundamental_filters_v3/decision_audit.json'));
 const study=read(path.join(ROOT,'dashboard/data/third_plus_study.json'));
 const previous=study.audit.models.requested_100k.dilution.statuses;
 const work=path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/ssr_execution_v2');
 const archive=A.load(work),ctx=loadContext(sourceRoot),byid=new Map(ctx.candidates.filter(c=>c.ordinal>=3).map(c=>[c.id,c]));
 if(parent.events.length!==210||parent.events.some(e=>!byid.has(e.id)))throw Error('Cohort identity changed');
 const rules={},p=protocol(),options={...p.primary,...(archive.mode==='bar_sensitivity'?{engine:Bars,capture:.5}: {})};
 if(archive.mode==='bar_sensitivity'){
  p.evidence='Observed one-second Nasdaq bars and available sampled venue quotes; explicit bar-based fill, queue, spread, national-price and borrow assumptions. No inferred field is presented as observed NBBO or an actual broker fill.';
  p.assumptions=p.assumptions.filter(x=>!x.startsWith('Unknown trade aggressors')&&!x.startsWith('Displayed queue'));
  p.assumptions.push('A restricted short child receives no fill when its price is at/below the contemporaneous venue/proxy bid. Broker national-price protection is still assumed, not established by these data.');
  p.assumptions.push('For bars, 50% of the estimated volume at/above the working offer supplies assumed eligible fill flow; 25%/75% sensitivities are separate. This is a fraction of bar flow, not a probability of filling the parent.');
  p.assumptions.push('Missing quote paths use the previous completed bar close with an assumed 0.86% half spread. Current bar range/volume determine modeled execution only after submission; never entry admission.');
 }
 p.assumptions.push('Fractional shorts may be covered by buying the next whole share. Full cash and fees are charged; any surplus long asset receives zero NAV credit and is reported as an uncredited reserve. No broker cash-in-lieu settlement is invented.');
 p.assumptions.push('The 240-minute and full-session extensions are exploratory access comparisons added after examining shorter-window no-fills. Full session ends 15 minutes before the actual close, including early closes. Report all windows; no untouched validation or optimality claim.');
 try{
 for(const rule of study.rules){
  const selected=parent.events.filter(e=>rule.requires.every(k=>e.signals[k]==='pass')).map(e=>byid.get(e.id));
  const models=[];
  // The current signal supplies every comparison; no observed winner changes the default.
  for(const policy of ['E0','E1','E2'])for(const minutes of [30,60,240,390])for(const participation of [.05,.1]){
   const settings={...options,policy,minutes,participation};
   const x=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,settings);
   if(policy==='E2'&&minutes===60&&participation===.1)write(path.join(work,'ledgers',rule.id+'_primary.local.json'),{positions:x.positions,missing_exits:x.missing_exits,summary:publicSummary(x)});
   const {engine,...publishedSettings}=settings;
   models.push({id:[policy,minutes,participation].join('_'),...publishedSettings,status:x.status,selected:selected.length,summary:publicSummary(x),decisions:x.audit.map(a=>({id:a.id,status:a.status,reasons:a.reasons||[]}))});
  }
  const independent=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,{...options,maximum_names:Number.MAX_SAFE_INTEGER,independent_events:true});
  const extended=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,{...options,minutes:240,maximum_names:Number.MAX_SAFE_INTEGER,independent_events:true});
  const fullSession=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,{...options,minutes:390,maximum_names:Number.MAX_SAFE_INTEGER,independent_events:true});
  const ai=new Map(independent.audit.map(x=>[x.id,x])),pi=new Map(independent.positions.map(x=>[x.id,{...x,last_calendar_index:ctx.prices.days.length}]));
  const rows=parent.events.map((e,i)=>{
   const states=rule.requires.map(k=>e.signals[k]||'unknown'),signal=states.includes('fail')?'signal_fail':states.includes('unknown')?'signal_unknown':'pass';
   return signal==='pass'?summarizeOpportunity(e,ai.get(e.id),pi.get(e.id),previous[i]):{...eventMetadata(e),previous_decision:previous[i],execution_status:signal,attempted:false,filled:false,entry_dollars:null};
  });
  const stress=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,{...options,borrow_apr:1.5,impact_bps:30,capture:.25});
  const optimistic=P.replayPortfolio({...ctx,candidates:selected,first:study.first},archive.sessions,{...options,capture:.75});
  const extAudit=new Map(extended.audit.map(a=>[a.id,a]));
  for(const row of rows){const a=extAudit.get(row.id);row.extended_attempted=!!a?.entry?.children;row.extended_filled=!!a?.entry?.filled_shares;row.extended_entry_dollars=a?.entry?.notional??null;}
  const fullAudit=new Map(fullSession.audit.map(a=>[a.id,a]));
  for(const row of rows){const a=fullAudit.get(row.id);row.full_session_attempted=!!a?.entry?.children;row.full_session_filled=!!a?.entry?.filled_shares;row.full_session_entry_dollars=a?.entry?.notional??null;}
  rules[rule.id]={label:rule.label,selected:selected.length,models,opportunities:rows,stress:{status:stress.status,summary:publicSummary(stress)},higher_capture:{status:optimistic.status,summary:publicSummary(optimistic)}};
  console.log('Venue replay',rule.id,selected.length,'selected;',rows.filter(r=>r.attempted).length,'independent attempts');
 }
 }finally{ctx.prices.close();}
 const collection=fs.existsSync(path.join(work,'collection.local.json'))?read(path.join(work,'collection.local.json')):null;
 const sourceFiles=['venue_replay.cjs','bar_replay.cjs','venue_portfolio.cjs','venue_archive.cjs','venue_study.cjs','venue_capture.py','export_venue_inputs.cjs','replay.cjs','archive.cjs'].map(f=>'_system/scripts/third_plus_execution/'+f);
 sourceFiles.push('_system/scripts/reverse_split_repeat_study.cjs','_system/scripts/third_plus_signal/statistics.cjs',REL+'fundamental_filters_v3/decision_audit.json','dashboard/data/third_plus_study.json');
 const sources=Object.fromEntries(sourceFiles.map(f=>[f,sha(fs.readFileSync(path.join(ROOT,f)))]));
 const d={schema:'third_plus_venue_backtest.v2',market_through:study.market_through,first:study.first,protocol:p,rules,
  archive:{status:archive.status,mode:archive.mode,index_sha256:archive.hash,sessions:archive.sessions.size,counts:archive.counts||null},
  acquisition:{authorized_cap_usd:collection?.authorized_cap_usd??0,reserved_cost_usd:collection?.reserved_cost_usd??0},sources,
  legacy_exclusions:{total:129,ssr:100,name_slots:28,liquidity:1},verified_borrow_entries:0,verified_nbbo_entries:0,production_authority:'none'};
 d.data_version=sha(JSON.stringify(d));
 write(path.join(ROOT,REL,'ssr_execution_v2/summary.json'),d);
 write(path.join(ROOT,'dashboard/data/third_plus_venue_execution.json'),d);
 write(path.join(ROOT,'dashboard/data/third_plus_venue_execution_manifest.json'),{schema:'third_plus_venue_manifest.v2',payload:'third_plus_venue_execution.json',data_version:d.data_version,sha256:sha(fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_venue_execution.json')))});
 return d;
}
module.exports={build,protocol,publicSummary,summarizeOpportunity,loadContext};
if(require.main===module){const i=process.argv.indexOf('--source-root');if(i<0)throw Error('--source-root required');build(path.resolve(process.argv[i+1]));}
