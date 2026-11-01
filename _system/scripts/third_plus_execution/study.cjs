#!/usr/bin/env node
'use strict';
// Full offline comparison runner. Missing execution paths never become no-fill observations.
const fs=require('node:fs'),path=require('node:path');
const A=require('./archive.cjs'),P=require('./portfolio.cjs'),S=require('../third_plus_signal/statistics.cjs');
const ROOT=path.resolve(__dirname,'../../..'),REL='_system/data/reverse_splits/third_plus_signal_study/',OUT=path.join(ROOT,REL,'ssr_execution_v1');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),fileSha=f=>A.sha(fs.readFileSync(f)),write=(f,x)=>fs.writeFileSync(f,JSON.stringify(x,null,2)+'\n');
const CODE=['replay.cjs','portfolio.cjs','archive.cjs','study.cjs','publish.cjs','cache_audit.py'];
function protocol(){return {
 schema:'third_plus_ssr_backtest.protocol.v1',status:'implemented_research_only',
 signal:'All 21 frozen signal arms; default third-plus + saved S7 rally veto + S4 dilution >=25%',
 nav_usd:10000000,target_initial_usd:100000,maximum_issuers:3,
 margin_capacity_admission:false,sleeve_risk_admission:false,minimum_future_sessions:0,
 horizon_sessions:20,arrival:'09:31 ET on original eligible date',windows_minutes:[30,60],
 participation_rates:[.05,.1],latency_ms:[100,500,2000],primary_latency_ms:500,
 child_usd:2000,working_children_per_issuer:1,cooldown_seconds:5,feed_health_seconds:1,
 rolling_flow_seconds:60,borrow_apr:.5,borrow_stress_apr:1.5,
 primary_comparisons:12,matched_controls:4,borrow_evidence_modes:['conditional','verified'],
 policies:[{id:'E0',label:'Matched SSR skip'},{id:'E1',label:'Displayed offer'},{id:'E2',label:'Permitted inside price'},{id:'E3',label:'Native SSR repricer'}],
 clear_status_policy:'E1 displayed offer in every policy, including E0; same edge/clock/volume/cost assumptions',
 queue:'Eligible chosen-venue buyer prints after acknowledgement consume queue ahead before own quantity. No cancellation credit. Hidden-liquidity uncertainty remains; these are conditional simulations.',
 cover:'Original signal-anchored 20th session; 90 to 15 minutes before close, same 5/10% causal-flow budget. Unfilled balance retries the next observed session and remains a liability; no final-print completion.',
 parent_budget:'Freeze floor($100,000 / first valid arrival midpoint) shares; no expansion after decline. Report actual proceeds separately.',
 flow:'Only regular deduplicated external direct-venue prints; observe before reserving, reserve filled + working + pending-cancel shares. Rolling budget also applies.',
 edge:'Source-available fixed edge forecast required in archive. No return-based fit or optimal schedule is inferred from the current caches.',
 source_policy:'Certified source attributes are ingest attestations, not independent proof of simulated fills. No sampled-bar or 50%-capture substitute.',
 uncertainty:'For complete primary-latency paths compare to matched E0 using issuer bootstrap and six-month calendar blocks, then Holm over 12 comparisons per rule. Missing paths and unresolved exit evidence withhold selection claims.',
 production_authority:'none',data_purchase_usd:0,holdout_access:false
};}
function grid(p){
 const out=[];
 for(const borrow_mode of p.borrow_evidence_modes)for(const latency_ms of p.latency_ms)for(const minutes of p.windows_minutes)for(const participation of p.participation_rates)for(const {id:policy}of p.policies){
 const id=policy+'_'+minutes+'m_'+Math.round(participation*100)+'pct_'+latency_ms+'ms_'+borrow_mode;
 out.push({id,policy,minutes,participation,latency_ms,borrow_mode});
 }
 return out;
}
function signalState(e,rule){
 const states=rule.requires.map(k=>e.signals[k]||'unknown');
 return states.includes('fail')?'fail':states.includes('unknown')?'unknown':'pass';
}
function compact(result){
 if(!result.summary)return null;
 const s={...result.summary};delete s.issuer_concentration;
 return s;
}
function build(sourceRoot){
 fs.mkdirSync(OUT,{recursive:true});
 const parent=read(path.join(ROOT,REL,'fundamental_filters_v3/decision_audit.json')),frozen=read(path.join(ROOT,REL,'fundamental_filters_v3/summary.json')),cache=read(path.join(OUT,'cache_audit.json'));
 if(cache.sources.cohort!==fileSha(path.join(ROOT,REL,'fundamental_filters_v3/decision_audit.json'))||cache.sources.auditor!==fileSha(path.join(__dirname,'cache_audit.py')))throw Error('Stale cache audit');
 const p=protocol(),pf=path.join(OUT,'protocol.json');
 if(fs.existsSync(pf)&&JSON.stringify(read(pf))!==JSON.stringify(p))throw Error('Frozen execution protocol changed; use a new version');
 if(!fs.existsSync(pf))write(pf,p);
 const archiveDir=path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/ssr_execution_v1/archive');
 const archive=A.loadArchive(archiveDir);
 const loader=require(path.join(sourceRoot,'_system/scripts/reverse_split_repeat_study.cjs'));
 const parentManifest=read(path.join(ROOT,REL,'fundamental_filters_v3/manifest.json'));
 for(const [file,hash]of Object.entries(parentManifest.freeze.inputs)){
  if(/holdout|sealed/i.test(file))throw Error('Sealed input prohibited');
  if(fileSha(path.join(sourceRoot,file))!==hash)throw Error('Frozen source changed: '+file);
 }
 const ctx=loader.load(),all=ctx.candidates.filter(c=>c.ordinal>=3),byId=new Map(all.map(c=>[c.id,c]));
 if(all.length!==210||parent.events.some(e=>!byId.has(e.id)))throw Error('Cohort changed');
 const definitions=grid(p),rules={},rawResults=new Map(),local=path.dirname(archiveDir),requestList=[];
 fs.mkdirSync(path.join(local,'ledgers'),{recursive:true});
 try{
 for(const rule of frozen.protocol.arms){
  const selected=parent.events.filter(e=>signalState(e,rule)==='pass').map(e=>byId.get(e.id));
  const models=[],full=new Map();
  for(const g of definitions){
   const x=P.replayPortfolio({...ctx,candidates:selected,first:frozen.common_first},archive.sessions,{...g,target_usd:p.target_initial_usd,nav:p.nav_usd,maximum_names:p.maximum_issuers,horizon:p.horizon_sessions,borrow_apr:p.borrow_apr});
   const row={...g,status:x.status,selected:selected.length,data_ready:x.coverage.filter(r=>!r.reasons.length).length,missing_entry_evidence:x.coverage.filter(r=>r.reasons.length).length,summary:compact(x),comparison:null};
   // Empty evidence is not a zero-cost, zero-position strategy result.
   if(x.status==='not_estimable'&&row.summary!==null)throw Error('Missing path has financial result');
   if(archive.sessions.size)write(path.join(local,'ledgers',rule.id+'_'+g.id+'.local.json'),x);
   models.push(row);full.set(g.id,x);
  }
  const claims=[];
  for(const row of models.filter(r=>r.policy!=='E0'&&r.latency_ms===500&&r.borrow_mode==='conditional')){
   const control=full.get('E0_'+row.minutes+'m_'+Math.round(row.participation*100)+'pct_500ms_conditional'),x=full.get(row.id);
   if(x.status==='conditional_simulation'&&control.status==='conditional_simulation'){
    row.comparison=S.comparison(x,control);claims.push({row,p:row.comparison.p_conservative});
   }else claims.push({row,p:1,unavailable:true});
  }
  S.holm(claims);for(const claim of claims)if(!claim.unavailable)claim.row.comparison.holm_p=claim.holm_p;
  const primary=full.get('E2_60m_10pct_500ms_conditional');
  const stress=archive.sessions.size?P.replayPortfolio({...ctx,candidates:selected,first:frozen.common_first},archive.sessions,{policy:'E2',minutes:60,participation:.1,latency_ms:500,borrow_apr:1.5,borrow_mode:'conditional'}):null;
  const primaryAudit=new Map(primary.audit.map(r=>[r.id,r]));
  rules[rule.id]={label:rule.label,selected:selected.length,models,
   candidate_decisions:parent.events.map(e=>{const signal=signalState(e,rule),x=primaryAudit.get(e.id);return {id:e.id,status:signal==='pass'?x?.status||'execution_data_missing':'signal_'+signal,reasons:x?.reasons||[]};}),
   borrow_stress:{apr:1.5,status:stress?.status||'not_estimable',summary:stress?compact(stress):null},
   evidence_decision:'No optimal execution or profitability claim. All current history is explored; calibrated fills and future evidence remain required.'};
  console.log('Execution matrix: '+rule.id+' / '+models.length+' definitions');
 }
 const family=Object.values(rules).flatMap(r=>r.models.filter(m=>m.policy!=='E0'&&m.latency_ms===500&&m.borrow_mode==='conditional').map(row=>({row,p:row.comparison?.p_conservative??1})));
 S.holm(family);for(const claim of family)if(claim.row.comparison)claim.row.comparison.holm_across_all_21_arms=claim.holm_p;
 for(const e of parent.events){
  const c=byId.get(e.id),idx=ctx.prices.index.get(e.entry_day),due=idx===undefined?null:ctx.prices.days[idx+19]||null;
  requestList.push({id:e.id,ticker:e.ticker,issuer:e.issuer,entry_date:e.entry_day,entry_window_et:'09:30:59–10:31:01 plus declared latency/race buffer',planned_exit_date:due,exit_window_et:'90 to 15 minutes before actual session close plus latency/race buffer',schemas:['consolidated_nbbo','chosen_venue_book','eligible_trade_events','market_status','dated_price_grid','receipt_clock'],borrow:'historical usable approval, quantity, expiry, costs and recall terms',cost_quote_usd:null,download_authorized_usd:0,followup:'If partial cover remains, same window on each following session through cutoff; never invent closure.'});
 }
 }finally{ctx.prices.close();}
 write(path.join(local,'requests.local.json'),{schema:'third_plus_execution_requests.v1',events:requestList,cost_status:'not_quoted_no_purchase',new_market_data_usd:0});
 const sourceFiles=[...CODE.map(n=>'_system/scripts/third_plus_execution/'+n),REL+'fundamental_filters_v3/decision_audit.json',REL+'fundamental_filters_v3/summary.json',REL+'fundamental_filters_v3/manifest.json',REL+'requested_sizing_v1/summary.json',REL+'ssr_execution_v1/cache_audit.json',REL+'ssr_execution_v1/protocol.json'];
 const sources=Object.fromEntries(sourceFiles.map(f=>[f,fileSha(path.join(ROOT,f))]));
 const version=A.sha(JSON.stringify({sources,archive:archive.hash,files:archive.files}));
 const doc={schema:'third_plus_ssr_backtest.v1',data_version:version,parent_study:frozen.data_version,market_through:frozen.price_asof,first:frozen.common_first,months:frozen.common_months,protocol:p,events:parent.events,rules,cache_audit:cache,archive:{status:archive.status,sessions:archive.sessions.size,index_sha256:archive.hash},validation:{rules:Object.keys(rules).length,model_definitions:Object.values(rules).reduce((n,r)=>n+r.models.length,0),primary_comparisons_per_rule:12,matched_controls_per_rule:4,actual_broker_fills:0,new_market_data_usd:0,broker_connections:0,holdout_files_opened:0},gaps:{required_entry_sessions:requestList.filter(r=>r.entry_date).length,planned_exit_within_cutoff:requestList.filter(r=>r.planned_exit_date).length,unpriced_request_events:requestList.length,cost_quote_usd:null},sources,production_authority:'none'};
 write(path.join(OUT,'summary.json'),doc);
 write(path.join(OUT,'manifest.json'),{schema:'third_plus_ssr_backtest.manifest.v1',data_version:version,summary_sha256:fileSha(path.join(OUT,'summary.json')),sources,archive_index_sha256:archive.hash});
 return doc;
}
module.exports={build,protocol,grid,signalState,CODE};
if(require.main===module){const i=process.argv.indexOf('--source-root');if(i<0)throw Error('--source-root required');build(path.resolve(process.argv[i+1]));}
