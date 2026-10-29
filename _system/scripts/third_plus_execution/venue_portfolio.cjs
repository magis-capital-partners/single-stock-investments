'use strict';
const R=require('./venue_replay.cjs');
const S=require('../third_plus_signal/statistics.cjs');
const Identity=require('./identity.cjs');
const DAY=86400000,sum=xs=>xs.reduce((a,b)=>a+b,0);
const iso=ms=>new Date(ms).toISOString().slice(0,10);
const next=d=>new Date(Date.parse(d+'T12:00:00Z')+DAY).toISOString().slice(0,10);
function entryWindow(s,minutes){return [s.open_ms+60000,Math.min(s.open_ms+60000+minutes*60000,s.close_ms-15*60000)];}
function readiness(candidates,sessions,o){
 const engine=o.engine||R;
 return candidates.map(c=>{
  if(!c.day)return {id:c.id,reasons:['missing_original_session']};
  const s=sessions.get(c.id),w=s?entryWindow(s,o.minutes):[0,1];
  const reasons=o.evidence_mode==='verified'&&s&&s.schema!=='third_plus_execution_session.v1'?['qualified_capture_missing']:engine.gaps(s,...w);
  if(s&&(s.event_id!==c.id||s.issuer!==c.issuer||s.date!==c.day))reasons.push('identity_join');
  if(s&&(!Number.isFinite(s.open_ms)||!Number.isFinite(s.close_ms)||w[1]>=s.close_ms))reasons.push('calendar');
  if(s&&o.policy==='E3'&&(!s.native_repricing?.verified||s.native_repricing.mode!=='nasdaq_slide_down'||!(s.native_repricing.minimum_sell_price>0)||!Number.isFinite(s.native_repricing.available_ms)||s.native_repricing.available_ms>w[0]))reasons.push('native_repricing');
  if(s&&o.borrow_mode==='verified'&&(!s.borrow?.length||s.borrow.some(b=>!b.confirmation)))reasons.push('borrow_history');
  if(s&&o.evidence_mode==='verified'){
   if(!s.borrow?.length||s.borrow.some(b=>!b.confirmation||!Number.isFinite(b.apr)||!Number.isFinite(b.available_ms)||!Number.isFinite(b.expires_ms)||!Number.isInteger(b.quantity)))reasons.push('borrow_history');
   if(s.evidence?.consolidated_nbbo!==true)reasons.push('national_prices');
   if(s.evidence?.eligible_trades!==true||s.evidence?.venue_book!==true)reasons.push('queue_and_trade_history');
   if(s.evidence?.dated_margin!==true)reasons.push('margin_history');
   if(s.evidence?.loan_recall_terms!==true)reasons.push('loan_terms');
   if(s.evidence?.corporate_action_settlement!==true)reasons.push('settlement_evidence');
  }
  if(o.edge_filter!==false&&s&&(!Number.isFinite(s.edge_per_share)||!Number.isFinite(s.edge_available_ms)||s.edge_available_ms>w[0]||!/^[a-f0-9]{64}$/.test(s.edge_source_sha256||'')))reasons.push('edge_forecast');
  return {id:c.id,reasons:[...new Set(reasons)]};
 });
}
function replayPortfolio(ctx,sessions,options={}){
 const o={policy:'E2',minutes:60,participation:.1,latency_ms:500,borrow_mode:'conditional',target_usd:100000,nav:10000000,maximum_names:3,horizon:20,borrow_apr:.5,edge_filter:false,...options};
 const engine=o.engine||R;
 let candidates=ctx.candidates.slice().sort((a,b)=>a.day?.localeCompare(b.day)||a.id.localeCompare(b.id));
 const coverage=readiness(candidates,sessions,o);
 if(o.evidence_mode==='verified')for(const row of coverage){
  if(typeof ctx.borrowTerms!=='function')row.reasons.push('dated_borrow_costs');
  if(typeof ctx.marginAt!=='function')row.reasons.push('dated_margin_costs');
 }
 if(!o.independent_events&&coverage.some(x=>x.reasons.length)){
  return {status:'not_estimable',coverage,positions:[],daily:[],summary:null,audit:candidates.map(c=>({id:c.id,status:!c.day?'missing_session':coverage.find(x=>x.id===c.id).reasons.length?'execution_data_missing':'portfolio_path_unknown',reasons:coverage.find(x=>x.id===c.id)?.reasons||['missing_original_session']}))};
 }
 const excluded=coverage.filter(x=>x.reasons.length);
 const positions=[],audit=excluded.map(x=>({id:x.id,status:x.reasons.includes('missing_original_session')?'missing_session':'execution_data_missing',reasons:x.reasons})),daily=[],missingExits=[];
 candidates=candidates.filter(c=>!excluded.some(x=>x.id===c.id));
 let cash=0,previous=0,peak=0,dd=0;
 const {prices}=ctx,days=prices.days,index=prices.index,byDay=new Map();
 for(const c of candidates){if(!c.day)continue;const a=byDay.get(c.day)||[];a.push(c);byDay.set(c.day,a);}
 const change=(p,k,v)=>{p[k]=(p[k]||0)+v;cash+=v;};
 function mark(p,d){
  const security=Identity.resolve(p,d),factor=Identity.factor(ctx,p,d);
  p.current_ticker=security.ticker;p.venue=security.venue;
  if(!(factor>0)){p.unresolved_identity=true;return false;}
  p.mark*=factor/p.factor;p.factor=factor;p.open_mark=p.mark;
  if(security.venue!=='NASDAQ'){p.unresolved_identity=true;p.mark_gap='venue_exit';return false;}
  const pt=prices.point(security.ticker,d),official=ctx.auction?.(security.ticker,d)?.close;
  // A data gap is recoverable. It never permanently disables a later sourced
  // mark, and never becomes evidence of an uncloseable real-world short.
  if(pt){p.mark=official||pt.close;p.last_mark=d;p.unresolved_identity=false;return true;}
  if(index.has(d)){p.mark_gap='price_history';return false;}
  return true;
 }
 let pathGap=null,riskBreaches=0;
 for(let d=days[0];d<=prices.last;d=next(d)){
  const idx=index.get(d),isSession=idx!==undefined;
  for(const p of positions){
   if(p.units>1e-9||p.loan_units>1e-9||p.surplus_long_units>1e-9){
    const marked=mark(p,d);
    if(!marked&&isSession){missingExits.push({id:p.id,date:d,reason:p.mark_gap||'identity'});pathGap||={date:d,id:p.id,reason:p.mark_gap||'identity'};}
   }
   for(const loan of p.loans)if(loan.day===d)p.loan_units+=loan.units;
   for(const ret of p.returns)if(ret.day===d)p.loan_units=Math.max(0,p.loan_units-ret.units);
   if(p.loan_units>1e-9){
    const terms=o.evidence_mode==='verified'?ctx.borrowTerms(p,d):{apr:o.borrow_apr};
    if(!terms||!Number.isFinite(terms.apr)||terms.apr<0){pathGap||={date:d,id:p.id,reason:'dated_borrow_costs'};missingExits.push(pathGap);}
    else change(p,'borrow',-p.loan_units/p.factor*Math.ceil(1.02*(p.open_mark||p.mark))*terms.apr/360);
   }
  }
  if(!isSession)continue;
  if(pathGap)break; // Later admissions and returns are unknown; no zombie slots.
  const arrivalEquity=o.nav+cash-sum(positions.map(p=>(p.units-(p.surplus_long_units||0))/p.factor*(p.open_mark||p.mark)));
  for(const c of byDay.get(d)||[]){
   // All parents start at the same fixed arrival. A later no-fill cannot free
   // a slot retroactively for another parent at that earlier timestamp.
   const open=positions.filter(p=>p.units>1e-9||p.day===d);
   if(!o.independent_events&&open.some(p=>p.issuer===c.issuer)){audit.push({id:c.id,status:'issuer_open'});continue;}
   if(open.length>=o.maximum_names){audit.push({id:c.id,status:'name_limit'});continue;}
   const gross=sum(open.map(p=>p.day===d?p.reserved_budget:p.units/p.factor*p.open_mark));
   const margins=open.map(p=>p.day===d?p.reserved_budget:o.evidence_mode==='verified'?ctx.marginAt(p,d):p.units/p.factor*Math.max(p.open_mark,p.open_mark<5?2.5:5));
   const margin=margins.every(Number.isFinite)?sum(margins):NaN;
   if(!Number.isFinite(margin)){pathGap={date:d,id:c.id,reason:'dated_margin_costs'};missingExits.push(pathGap);break;}
   const equity=arrivalEquity;
   const budget=o.risk_limits?Math.max(0,Math.min(o.target_usd,equity*o.risk_limits.per_name_fraction,equity*o.risk_limits.gross_fraction-gross,(equity*o.risk_limits.squeeze_loss_fraction-2*gross)/2,(equity*o.risk_limits.margin_fraction-margin)/Math.max(1,2.5/(c.entry_price||1)))):o.target_usd;
   if(budget<1){audit.push({id:c.id,status:'risk_capacity'});continue;}
   const s=sessions.get(c.id),[start,end]=entryWindow(s,o.minutes);
   const x=engine.replay(s,{...o,target_usd:budget,start_ms:start,end_ms:end,net_edge_per_share:s.edge_per_share,initial_price:c.entry_price});
   if(['data_missing','route_unverified'].includes(x.status))throw Error('Preflight/replay coverage mismatch');
   const p={...c,units:x.filled_shares||0,entry_units:x.filled_shares||0,loan_units:0,loans:[],returns:[],factor:1,mark:ctx.auction?.(c.ticker,d)?.close||prices.point(c.ticker,d)?.close||x.mean_fill||0,last_mark:d,entry_proceeds:x.notional||0,entry_fees:x.fees||0,borrow:0,covers:0,fees:0,locate:0,deadline:idx+o.horizon-1,planned_exit:days[idx+o.horizon-1]||null,entry:x,cover_replays:[]};
   p.reserved_budget=budget;p.open_mark=x.arrival_mid||c.entry_price||x.mean_fill;
   positions.push(p);cash+=p.entry_proceeds;change(p,'fees',-(x.fees||0));change(p,'locate',-(x.locate_cost||0));change(p,'impact',-p.entry_proceeds*(o.impact_bps||0)/10000);
   for(const f of x.fills)p.loans.push({day:ctx.settlement(iso(f.at_ms)),units:f.quantity});
   audit.push({id:c.id,status:x.filled_shares?'entered':x.status,entry:x});
  }
  // Entries precede afternoon covers; no position is removed by an invented close.
  for(const p of positions){
   if(p.units<=1e-9||idx<p.deadline)continue;
   if(p.unresolved_identity){pathGap={id:p.id,date:d,reason:'identity'};missingExits.push(pathGap);break;}
   const key=p.id+'|'+d,s=sessions.get(key);
   if(!s){pathGap={id:p.id,date:d,reason:'exit_session_missing'};missingExits.push(pathGap);break;}
   if(s.event_id!==p.id||s.issuer!==p.issuer||s.date!==d){pathGap={id:p.id,date:d,reason:'exit_identity_join'};missingExits.push(pathGap);break;}
   const start=s.close_ms-90*60000,end=s.close_ms-15*60000;
   // A whole-share overbuy can finish a fractional short. Pay for the full share;
   // retain the paid-for surplus as a marked long asset, not an invented
   // cash-in-lieu broker settlement or a zero-value asset.
   const x=engine.replay(s,{...o,policy:'E1',side:'buy',borrow_mode:'conditional',quantity:Math.ceil(p.units/p.factor-1e-9),start_ms:start,end_ms:end,net_edge_per_share:Number.MAX_VALUE,initial_price:ctx.auction?.(Identity.resolve(p,d).ticker,d)?.open});
   if(x.status==='data_missing'){pathGap={id:p.id,date:d,reason:x.gaps.join(',')};missingExits.push(pathGap);break;}
   p.cover_replays.push(x);
   for(const f of x.fills){const units=Math.min(p.units,f.quantity*p.factor),surplus=Math.max(0,f.quantity*p.factor-units);p.surplus_long_units=(p.surplus_long_units||0)+surplus;p.units=Math.max(0,p.units-units);p.returns.push({day:ctx.settlement(iso(f.at_ms)),units});}
   change(p,'covers',-(x.notional||0));change(p,'fees',-(x.fees||0));change(p,'impact',-(x.notional||0)*(o.impact_bps||0)/10000);
   if(p.units<=1e-9)p.closed=d;
  }
  if(pathGap)break;
  const liability=sum(positions.map(p=>p.units/p.factor*p.mark)),longAsset=sum(positions.map(p=>(p.surplus_long_units||0)/p.factor*p.mark)),pnl=cash-liability+longAsset;
  peak=Math.max(peak,pnl);dd=Math.min(dd,pnl-peak);
  daily.push({date:d,pnl,change:pnl-previous,liability,names:positions.filter(p=>p.units>1e-9).length});previous=pnl;
  if(o.risk_limits&&(2*liability>o.risk_limits.squeeze_loss_fraction*(o.nav+pnl)||liability>o.risk_limits.gross_fraction*(o.nav+pnl)))riskBreaches++;
 }
 const known=new Set(audit.map(x=>x.id));
 for(const c of candidates)if(!known.has(c.id))audit.push({id:c.id,status:'portfolio_path_unknown',reasons:[pathGap?.reason||'earlier_path_missing']});
 // Accrue known finite loan-return tail; never settle open inventory implicitly.
 const closedLoans=pathGap?[]:positions.filter(p=>p.units<=1e-9&&p.loan_units>1e-9);
 for(const p of closedLoans)for(let d=next(prices.last),n=0;p.loan_units>1e-9;d=next(d),n++){
  if(n>10)throw Error('Unresolved settlement tail');
  for(const ret of p.returns)if(ret.day===d)p.loan_units=Math.max(0,p.loan_units-ret.units);
  if(p.loan_units>1e-9){
   const terms=o.evidence_mode==='verified'?ctx.borrowTerms(p,d):{apr:o.borrow_apr};
   if(!terms||!Number.isFinite(terms.apr)||terms.apr<0){pathGap={date:d,id:p.id,reason:'dated_borrow_costs'};missingExits.push(pathGap);break;}
   change(p,'borrow',-p.loan_units/p.factor*Math.ceil(1.02*(p.open_mark||p.mark))*terms.apr/360);
  }
 }
 for(const p of positions){p.open_liability=p.units/p.factor*p.mark;p.surplus_long_asset=(p.surplus_long_units||0)/p.factor*p.mark;p.pnl=p.entry_proceeds+p.covers+p.fees+p.borrow+p.locate+(p.impact||0)-p.open_liability+p.surplus_long_asset;}
 const net=sum(positions.map(p=>p.pnl));
 if(Math.abs(net-(cash-sum(positions.map(p=>p.open_liability))+sum(positions.map(p=>p.surplus_long_asset))))>.001)throw Error('Portfolio cash mismatch');
 if(daily.length){daily.at(-1).change+=net-daily.at(-1).pnl;daily.at(-1).pnl=net;}
 peak=0;dd=0;for(const d of daily){peak=Math.max(peak,d.pnl);dd=Math.min(dd,d.pnl-peak);}
 const monthly=S.months(daily,ctx.first||days[0]),issuers=[...S.grouped(positions,p=>p.issuer)].map(([issuer,ps])=>({issuer,pnl:sum(ps.map(p=>p.pnl))}));
 const actual=positions.filter(p=>p.entry_units>0),partial=actual.filter(p=>p.entry.fill_fraction<.95);
 const borrowExceptions=sum(positions.map(p=>p.entry.borrow_exceptions||0));
 const status=borrowExceptions?'incomplete_borrow_evidence':missingExits.length||excluded.length?'incomplete_exit_evidence':riskBreaches?'risk_breach_unresolved':'conditional_venue_simulation';
 const cleanup={fractional_cleanup_positions:positions.filter(p=>p.surplus_long_units>1e-9).length,surplus_long_asset:sum(positions.map(p=>p.surplus_long_asset)),extra_impact_cost:-sum(positions.map(p=>p.impact||0))};
 const summary={...o,net_pnl:net,gross_marked_pnl:net-sum(positions.map(p=>p.fees+p.borrow+p.locate+(p.impact||0))),borrow_cost:-sum(positions.map(p=>p.borrow)),commissions_and_fees:-sum(positions.map(p=>p.fees)),locate_cost:-sum(positions.map(p=>p.locate)),max_drawdown_dollars:dd,entered:actual.length,issuers:new Set(actual.map(p=>p.issuer)).size,admitted_parent_decisions:positions.length,attempted:positions.filter(p=>p.entry.children>0).length,no_fill:positions.filter(p=>p.entry.children>0&&!p.entry_units).length,not_attempted:positions.filter(p=>!p.entry.children&&p.entry.status!=='ssr_skip').length,ssr_skipped:positions.filter(p=>p.entry.status==='ssr_skip').length,partial:partial.length,full:actual.length-partial.length,entry_dollars:sum(actual.map(p=>p.entry_proceeds)),mean_position:actual.length?sum(actual.map(p=>p.entry_proceeds))/actual.length:null,open_positions:actual.filter(p=>p.units>1e-9).length,open_liability:sum(positions.map(p=>p.open_liability)),immature_positions:actual.filter(p=>p.deadline>=days.length).length,common_monthly:monthly,common_mean_monthly:S.mean(monthly.map(m=>m.pnl)),issuer_concentration:issuers,children:sum(positions.map(p=>p.entry.children||0)),missing_exit_sessions:missingExits.length,borrow_exceptions:borrowExceptions,broker_verified_entries:0,margin_capacity_applied:false,sleeve_cap_applied:false,pnl_without_best_issuer:net-Math.max(0,...issuers.map(x=>x.pnl)),pnl_without_best5_issuers:net-sum(issuers.map(x=>x.pnl).sort((a,b)=>b-a).slice(0,5))};
 Object.assign(summary,cleanup,{risk_breach_sessions:riskBreaches,margin_capacity_applied:!!o.risk_limits,sleeve_cap_applied:!!o.risk_limits,completed_through:daily.at(-1)?.date||null,first_path_gap:pathGap});
 // An accounting prefix is useful for debugging, not a full-period result.
 const incomplete=missingExits.length||excluded.length||riskBreaches;
 return {status,coverage,summary:incomplete?null:summary,diagnostic_summary:incomplete?{entered:actual.length,first_path_gap:pathGap,completed_through:daily.at(-1)?.date||null,open_positions:actual.filter(p=>p.units>1e-9).length}:null,positions,daily:incomplete?[]:daily,audit,missing_exits:missingExits};
}
module.exports={replayPortfolio,readiness,entryWindow};
