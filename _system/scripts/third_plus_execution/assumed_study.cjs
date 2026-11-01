'use strict';
const fs=require('node:fs'),path=require('node:path');
const Engine=require('./assumed_backtest.cjs'),Archive=require('./venue_archive.cjs'),{loadContext}=require('./venue_study.cjs'),{sha}=require('./archive.cjs');
const ROOT=path.resolve(__dirname,'../../..'),REL='_system/data/reverse_splits/third_plus_signal_study/';
const read=f=>JSON.parse(fs.readFileSync(path.join(ROOT,f),'utf8'));
const DECISIONS=['outside_signal','filled','no_fill','ssr_skip','name_limit','issuer_open','not_yet_eligible'];
const SOURCES=['assumed_backtest.cjs','assumed_study.cjs','identity.cjs','replay.cjs','venue_archive.cjs','venue_study.cjs'].map(f=>'_system/scripts/third_plus_execution/'+f).concat(['dashboard/third-plus-assumed.js',REL+'fundamental_filters_v3/decision_audit.json',REL+'ssr_execution_v2/security_lifecycle.v1.json','dashboard/data/third_plus_study.json','_system/scripts/reverse_split_repeat_study.cjs','_system/scripts/short_framework/adapters.cjs']);
function protocol(){return {
 mode:'assumption_based_full_backtest',tradability:'Every signal-qualified security is assumed borrowable and accessible, including SSR, OTC and distressed names. No historical borrow or national-quote proof is required in this mode.',
 ...Engine.DEFAULTS,scenarios:Engine.SCENARIOS,
 assumptions:[
  'Frozen 210-event cohort, 21 original signal definitions, 24 execution settings and three declared cost/fill scenarios. Signal unknowns retain their frozen classification; the all-candidate signal includes the entire cohort.',
  'The base keeps a $100,000 maximum short, $10 million reference equity, three concurrent issuers, entry from 09:31 for 60 minutes, 10% participation and 20 trading sessions including entry. No additional $25,000 risk cap is imposed.',
  'All borrow and venue access is assumed available. No loan recalls or forced margin liquidation in base; a collateral estimate of 200% of marked short value with a $2.50/share floor is reported, together with days exceeding reference equity. Excess collateral has no interest benefit; proceeds and idle cash interest are zero.',
  'Existing receipt-verified one-second Nasdaq bars and fresh sampled quotes take priority. Missing quotes use the preceding completed bar close with an assumed half-spread of 86 basis points in base. A tick above the bid estimates the improved offer, including under SSR; E1 joins the ask and E0 skips restricted names.',
  'Price-volume location within an OHLC range is assumed uniform, with 50% capture of eligible volume in base. Flat bars are handled exactly. This is an estimated fill allocation, not observed trades or queue evidence. Filled shares plus live reservations never exceed cumulative or rolling-minute participation limits.',
  'Children are capped at $2,000, have 500 ms acknowledgement/cancellation delay and reprice no faster than five seconds. Both sides fill at their working limit. Spread and separately charged impact/fees are included once.',
  'Missing or empty venue capture assumes external flow using a flat known opening price and uniform prior ADV across the session, while respecting any captured halt for that security. Unknown ADV assumes $1 million daily dollar volume. Neither final-day volume nor future closes size the morning entry. Price fallback is official open, daily open, completed prearrival bar, split-adjusted prior close, then a flagged $5 proxy.',
  'Cover orders begin in the last 90 minutes and stop 15 minutes before close on trading session 20; partial covers retry for at most three sessions. A missing captured cover uses that day’s observed close with estimated spread and prior-ADV flow, interpreted as a closing-price execution proxy. Any final residual closes at the observed close plus spread and 2% in base.',
  'When a cover price is unavailable, or a security has left Nasdaq, assume closeout at the last known split-adjusted nominal price plus spread and 10% in base. Missing marks carry that adjusted price until closeout. The separate stress case increases this premium to 50%; neither case assumes bankruptcy makes a short liability zero.',
  'Source-bound TNFA→QCLS continuity, venue transitions and reverse split factors apply to marks and quantities. Whole-share cover overbuy is paid for and the excess sold at an estimated bid with fees. Unresolved factors carry the last known factor and are counted.',
  'Borrow is charged on settled stock loans on calendar days using 102% collateral rounded up per share and APR/360; T+2 before May 28, 2024 and T+1 afterwards. Returns stop financing at cover settlement. Base APR is 50%, plus a one-time $0.01/share locate fee (minimum $5) and 10 bp impact per side. These are assumptions, not sourced historical lending rates.',
  'Same-day parent orders reserve slots until their windows finish, even when later unfilled. Fixed identifier order breaks ties. Positions covered later that day cannot free a morning slot. The independent all-candidate result removes slot competition and reports the concurrency and collateral it would require.',
  'Results stop at the frozen October 12, 2026 market cutoff. Not-yet-eligible events remain listed and immature positions remain open and marked; no future prices or exits are fabricated. Closing drawdown uses every daily mark, while the chart shows monthly changes.',
  'Favorable and stress assumptions are combined scenarios, not confidence bounds. All settings are retrospective comparisons. The historical-evidence audit remains separate from this authorized assumption-based simulation.'
 ],references:[{label:'IBKR fixed commissions',url:'https://www.interactivebrokers.com/en/pricing/commissions-stocks.php'},{label:'IBKR short sale cost methodology',url:'https://www.interactivebrokers.com/en/pricing/short-sale-cost.php'}]};}
function build(sourceRoot){
 const parent=read(REL+'fundamental_filters_v3/decision_audit.json'),study=read('dashboard/data/third_plus_study.json'),ctx=loadContext(sourceRoot),archive=Archive.load(path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/ssr_execution_v2'));
 const candidates=new Map(ctx.candidates.filter(c=>c.ordinal>=3).map(c=>[c.id,c]));
 if(parent.events.length!==210||parent.events.some(e=>!candidates.has(e.id)))throw Error('Frozen candidate set changed');
 const settings=[];for(const scenario of Object.keys(Engine.SCENARIOS))for(const policy of ['E0','E1','E2'])for(const minutes of [30,60,240,390])for(const participation of [.05,.1])settings.push({id:[scenario,policy,minutes,participation].join('_'),scenario,policy,minutes,participation});
 const results=new Map(settings.map(o=>[o.id,[]]));
 try{
  for(const [j,e]of parent.events.entries()){
   const c=candidates.get(e.id);
   for(const o of settings)results.get(o.id).push(Engine.trade(ctx,archive.sessions,c,{...Engine.SCENARIOS[o.scenario],...o}));
   if((j+1)%10===0)console.log('Assumed full paths',j+1,'/ 210');
  }
  const rules={};
  for(const rule of study.rules){
   const selected=new Set(parent.events.filter(e=>rule.requires.every(k=>e.signals[k]==='pass')).map(e=>e.id)),models=[];
   let opportunities=[];
   for(const o of settings){
    const trades=results.get(o.id).filter(t=>selected.has(t.id)),account=Engine.portfolio(ctx,trades,{first:study.first}),all=Engine.portfolio(ctx,trades,{first:study.first,independent:true,maximum_names:Infinity});
    const primary=o.scenario==='base'&&o.policy==='E2'&&o.minutes===60&&o.participation===.1;
    if(primary){const choices=new Map(account.decisions.map(d=>[d.id,d.status]));opportunities=parent.events.map(e=>{const t=results.get(o.id).find(t=>t.id===e.id);return {id:e.id,ticker:e.ticker,issuer:e.issuer,name:e.name,event_date:e.event_date,entry_day:t.day,selected:selected.has(e.id),account_decision:choices.get(e.id)||'outside_signal',independent_decision:t.status,modeled_entry_usd:selected.has(e.id)?t.entry?.notional||0:null,entry_basis:t.entry?.source_basis||null,quote_basis:t.entry?.quote_basis||null,initial_basis:t.initial_basis||null,planned_exit:t.planned_exit,close_day:t.close_day,proxy_exit:t.proxy_exit||false,proxy_mark_sessions:t.proxy_marks||0};});}
    const choices=new Map(account.decisions.map(d=>[d.id,d.status])),decisions=parent.events.map(e=>DECISIONS.indexOf(choices.get(e.id)||'outside_signal'));
    if(decisions.some(x=>x<0))throw Error('Unknown assumed decision');
    delete account.decisions;delete all.decisions;models.push({...o,account,all_candidates:all,decisions});
   }
   rules[rule.id]={label:rule.label,requires:rule.requires,selected:selected.size,models,opportunities};console.log('Aggregated assumed signal',rule.id,selected.size);
  }
  const sources=Object.fromEntries(SOURCES.map(f=>[f,sha(fs.readFileSync(path.join(ROOT,f)))]));
  const d={schema:'third_plus_assumed_backtest.v1',first:study.first,market_through:study.market_through,protocol:protocol(),rules,decision_codes:DECISIONS,archive:{index_sha256:archive.hash,sessions:archive.sessions.size,counts:archive.counts},sources,production_authority:'none',historical_fills_verified:false,acquisition_cost_usd:0};
  d.data_version=sha(JSON.stringify(d));const body=JSON.stringify(d)+'\n';
  fs.writeFileSync(path.join(ROOT,'dashboard/data/third_plus_assumed_backtest.json'),body);
  fs.writeFileSync(path.join(ROOT,'dashboard/data/third_plus_assumed_manifest.json'),JSON.stringify({schema:'third_plus_assumed_manifest.v1',payload:'third_plus_assumed_backtest.json',sha256:sha(body),data_version:d.data_version})+'\n');
  return d;
 }finally{ctx.prices.close();}
}
function check(){
 const d=read('dashboard/data/third_plus_assumed_backtest.json'),m=read('dashboard/data/third_plus_assumed_manifest.json');
 if(sha(fs.readFileSync(path.join(ROOT,'dashboard/data/'+m.payload)))!==m.sha256)throw Error('Assumed publication digest changed');
 const {data_version,...unsigned}=d;if(data_version!==sha(JSON.stringify(unsigned))||data_version!==m.data_version)throw Error('Assumed data version changed');
 for(const [f,h]of Object.entries(d.sources))if(sha(fs.readFileSync(path.join(ROOT,f)))!==h)throw Error('Stale assumed source '+f);
 require('../../../dashboard/third-plus-assumed.js').validate(d);console.log('Verified complete assumed publication',data_version);return d;
}
module.exports={build,check,protocol};if(require.main===module){if(process.argv.includes('--check'))check();else{const i=process.argv.indexOf('--source-root');if(i<0)throw Error('--source-root required');build(path.resolve(process.argv[i+1]));}}
