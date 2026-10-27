'use strict';
const R=require('./replay.cjs');
const S=require('../third_plus_signal/statistics.cjs');
const DAY=86400000,sum=xs=>xs.reduce((a,b)=>a+b,0);
const iso=ms=>new Date(ms).toISOString().slice(0,10);
const next=d=>new Date(Date.parse(d+'T12:00:00Z')+DAY).toISOString().slice(0,10);
function entryWindow(s,minutes){return [s.open_ms+60000,s.open_ms+60000+minutes*60000];}
function readiness(candidates,sessions,o){
 return candidates.map(c=>{
  if(!c.day)return {id:c.id,reasons:['missing_original_session']};
  const s=sessions.get(c.id),w=s?entryWindow(s,o.minutes):[0,1];
  const reasons=R.gaps(s,...w);
  if(s&&(s.event_id!==c.id||s.issuer!==c.issuer||s.date!==c.day))reasons.push('identity_join');
  if(s&&(!Number.isFinite(s.open_ms)||!Number.isFinite(s.close_ms)||w[1]>=s.close_ms))reasons.push('calendar');
  if(s&&o.policy==='E3'&&(!s.native_repricing?.verified||s.native_repricing.mode!=='nasdaq_slide_down'||!(s.native_repricing.minimum_sell_price>0)||!Number.isFinite(s.native_repricing.available_ms)||s.native_repricing.available_ms>w[0]))reasons.push('native_repricing');
  if(s&&o.borrow_mode==='verified'&&(!s.borrow?.length||s.borrow.some(b=>!b.confirmation)))reasons.push('borrow_history');
  if(s&&(!Number.isFinite(s.edge_per_share)||!Number.isFinite(s.edge_available_ms)||s.edge_available_ms>w[0]||!/^[a-f0-9]{64}$/.test(s.edge_source_sha256||'')))reasons.push('edge_forecast');
  return {id:c.id,reasons:[...new Set(reasons)]};
 });
}
function replayPortfolio(ctx,sessions,options={}){
 const o={policy:'E2',minutes:60,participation:.1,latency_ms:500,borrow_mode:'conditional',target_usd:100000,nav:10000000,maximum_names:3,horizon:20,borrow_apr:.5,...options};
 const candidates=ctx.candidates.slice().sort((a,b)=>a.day?.localeCompare(b.day)||a.id.localeCompare(b.id));
 const coverage=readiness(candidates,sessions,o);
 if(coverage.some(x=>x.reasons.length)||candidates.some(c=>!c.day)){
  return {status:'not_estimable',coverage,positions:[],daily:[],summary:null,audit:candidates.map(c=>({id:c.id,status:!c.day?'missing_session':coverage.find(x=>x.id===c.id).reasons.length?'execution_data_missing':'portfolio_path_unknown',reasons:coverage.find(x=>x.id===c.id)?.reasons||['missing_original_session']}))};
 }
 const positions=[],audit=[],daily=[],missingExits=[];
 let cash=0,previous=0,peak=0,dd=0;
 const {prices}=ctx,days=prices.days,index=prices.index,byDay=new Map();
 for(const c of candidates){const a=byDay.get(c.day)||[];a.push(c);byDay.set(c.day,a);}
 const change=(p,k,v)=>{p[k]=(p[k]||0)+v;cash+=v;};
 function mark(p,d){
  const factor=ctx.factor(p.ticker,p.day,d);
  if(!(factor>0)){p.unresolved_identity=true;return;}
  p.mark*=factor/p.factor;p.factor=factor;p.open_mark=p.mark;
  if(Date.parse(d)-Date.parse(p.last_mark)>7*DAY)p.unresolved_identity=true;
  const pt=prices.point(p.ticker,d);
  if(pt&&!p.unresolved_identity){p.mark=pt.close;p.last_mark=d;}
 }
 for(let d=days[0];d<=prices.last;d=next(d)){
  const idx=index.get(d),isSession=idx!==undefined;
  for(const p of positions){
   if(p.units>1e-9||p.loan_units>1e-9)mark(p,d);
   for(const loan of p.loans)if(loan.day===d)p.loan_units+=loan.units;
   for(const ret of p.returns)if(ret.day===d)p.loan_units=Math.max(0,p.loan_units-ret.units);
   if(p.loan_units>1e-9)change(p,'borrow',-p.loan_units/p.factor*Math.ceil(1.02*(p.open_mark||p.mark))*o.borrow_apr/360);
  }
  if(!isSession)continue;
  for(const c of byDay.get(d)||[]){
   const open=positions.filter(p=>p.units>1e-9);
   if(open.some(p=>p.issuer===c.issuer)){audit.push({id:c.id,status:'issuer_open'});continue;}
   if(open.length>=o.maximum_names){audit.push({id:c.id,status:'name_limit'});continue;}
   const s=sessions.get(c.id),[start,end]=entryWindow(s,o.minutes);
   const x=R.replay(s,{...o,start_ms:start,end_ms:end,net_edge_per_share:s.edge_per_share});
   if(['data_missing','route_unverified'].includes(x.status))throw Error('Preflight/replay coverage mismatch');
   const p={...c,units:x.filled_shares||0,entry_units:x.filled_shares||0,loan_units:0,loans:[],returns:[],factor:1,mark:prices.point(c.ticker,d)?.close||x.mean_fill||0,last_mark:d,entry_proceeds:x.notional||0,entry_fees:x.fees||0,borrow:0,covers:0,fees:0,locate:0,deadline:idx+o.horizon-1,planned_exit:days[idx+o.horizon-1]||null,entry:x,cover_replays:[]};
   positions.push(p);cash+=p.entry_proceeds;change(p,'fees',-(x.fees||0));change(p,'locate',-(x.locate_cost||0));
   for(const f of x.fills)p.loans.push({day:ctx.settlement(iso(f.at_ms)),units:f.quantity});
   audit.push({id:c.id,status:x.filled_shares?'entered':x.status,entry:x});
  }
  // Entries precede afternoon covers; no position is removed by an invented close.
  for(const p of positions){
   if(p.units<=1e-9||idx<p.deadline)continue;
   if(p.unresolved_identity){missingExits.push({id:p.id,date:d,reason:'identity'});continue;}
   const key=p.id+'|'+d,s=sessions.get(key);
   if(!s){missingExits.push({id:p.id,date:d,reason:'exit_session_missing'});continue;}
   if(s.event_id!==p.id||s.issuer!==p.issuer||s.date!==d){missingExits.push({id:p.id,date:d,reason:'exit_identity_join'});continue;}
   const start=s.close_ms-90*60000,end=s.close_ms-15*60000;
   const x=R.replay(s,{...o,policy:'E1',side:'buy',borrow_mode:'conditional',quantity:Math.floor(p.units/p.factor+1e-9),start_ms:start,end_ms:end,net_edge_per_share:Number.MAX_VALUE});
   if(x.status==='data_missing'){missingExits.push({id:p.id,date:d,reason:x.gaps.join(',')});continue;}
   p.cover_replays.push(x);
   for(const f of x.fills){const units=f.quantity*p.factor;p.units=Math.max(0,p.units-units);p.returns.push({day:ctx.settlement(iso(f.at_ms)),units});}
   change(p,'covers',-(x.notional||0));change(p,'fees',-(x.fees||0));
   if(p.units<=1e-9)p.closed=d;
  }
  const liability=sum(positions.map(p=>p.units/p.factor*p.mark)),pnl=cash-liability;
  peak=Math.max(peak,pnl);dd=Math.min(dd,pnl-peak);
  daily.push({date:d,pnl,change:pnl-previous,liability,names:positions.filter(p=>p.units>1e-9).length});previous=pnl;
 }
 // Accrue known finite loan-return tail; never settle open inventory implicitly.
 const closedLoans=positions.filter(p=>p.units<=1e-9&&p.loan_units>1e-9);
 for(const p of closedLoans)for(let d=next(prices.last),n=0;p.loan_units>1e-9;d=next(d),n++){
  if(n>10)throw Error('Unresolved settlement tail');
  for(const ret of p.returns)if(ret.day===d)p.loan_units=Math.max(0,p.loan_units-ret.units);
  if(p.loan_units>1e-9)change(p,'borrow',-p.loan_units/p.factor*Math.ceil(1.02*(p.open_mark||p.mark))*o.borrow_apr/360);
 }
 for(const p of positions){p.open_liability=p.units/p.factor*p.mark;p.pnl=p.entry_proceeds+p.covers+p.fees+p.borrow+p.locate-p.open_liability;}
 const net=sum(positions.map(p=>p.pnl));
 if(Math.abs(net-(cash-sum(positions.map(p=>p.open_liability))))>.001)throw Error('Portfolio cash mismatch');
 if(daily.length){daily.at(-1).change+=net-daily.at(-1).pnl;daily.at(-1).pnl=net;}
 peak=0;dd=0;for(const d of daily){peak=Math.max(peak,d.pnl);dd=Math.min(dd,d.pnl-peak);}
 const monthly=S.months(daily,ctx.first||days[0]),issuers=[...S.grouped(positions,p=>p.issuer)].map(([issuer,ps])=>({issuer,pnl:sum(ps.map(p=>p.pnl))}));
 const actual=positions.filter(p=>p.entry_units>0),partial=actual.filter(p=>p.entry.fill_fraction<.95);
 const borrowExceptions=sum(positions.map(p=>p.entry.borrow_exceptions||0));
 const status=borrowExceptions?'incomplete_borrow_evidence':missingExits.length?'incomplete_exit_evidence':'conditional_simulation';
 const summary={...o,net_pnl:net,gross_marked_pnl:net-sum(positions.map(p=>p.fees+p.borrow+p.locate)),borrow_cost:-sum(positions.map(p=>p.borrow)),commissions_and_fees:-sum(positions.map(p=>p.fees)),locate_cost:-sum(positions.map(p=>p.locate)),max_drawdown_dollars:dd,entered:actual.length,issuers:new Set(actual.map(p=>p.issuer)).size,admitted_parent_decisions:positions.length,attempted:positions.filter(p=>p.entry.children>0).length,no_fill:positions.filter(p=>p.entry.children>0&&!p.entry_units).length,not_attempted:positions.filter(p=>!p.entry.children&&p.entry.status!=='ssr_skip').length,ssr_skipped:positions.filter(p=>p.entry.status==='ssr_skip').length,partial:partial.length,full:actual.length-partial.length,entry_dollars:sum(actual.map(p=>p.entry_proceeds)),mean_position:actual.length?sum(actual.map(p=>p.entry_proceeds))/actual.length:null,open_positions:actual.filter(p=>p.units>1e-9).length,open_liability:sum(positions.map(p=>p.open_liability)),immature_positions:actual.filter(p=>p.deadline>=days.length).length,common_monthly:monthly,common_mean_monthly:S.mean(monthly.map(m=>m.pnl)),issuer_concentration:issuers,children:sum(positions.map(p=>p.entry.children||0)),missing_exit_sessions:missingExits.length,borrow_exceptions:borrowExceptions,broker_verified_entries:0,margin_capacity_applied:false,sleeve_cap_applied:false,pnl_without_best_issuer:net-Math.max(0,...issuers.map(x=>x.pnl)),pnl_without_best5_issuers:net-sum(issuers.map(x=>x.pnl).sort((a,b)=>b-a).slice(0,5))};
 return {status,coverage,summary,positions,daily,audit,missing_exits:missingExits};
}
module.exports={replayPortfolio,readiness,entryWindow};
