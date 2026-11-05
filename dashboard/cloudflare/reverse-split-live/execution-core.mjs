// Counterfactual fills only. Pure functions; no network or broker dependency.
import {SHADOW_POLICIES,at,finite,commission,sessions} from './shadow-core.mjs';
import {etDay,DAY} from './core.mjs';
export const EXECUTION_VERSION='ibkr_executable_shadow.v1';
export const EXECUTION_POLICIES=Object.freeze(['capacity','executable'].flatMap(lane=>[10,25,50,100].map(bps=>Object.freeze({
  ...SHADOW_POLICIES.find(p=>p.id==='rs_immediate_mini.v1'),id:`rs_ibkr_${lane}_${bps}bps.v1`,label:`IBKR · ${lane} · ${bps} bps`,version:EXECUTION_VERSION,lane,broker:'IBKR',
  target_notional:null,reference_equity:null,name_stress_loss_fraction:null,sleeve_stress_loss_fraction:null,maximum_names:null,
  quote_depth_fraction:1,price_budget_bps:bps,borrow_apr:null,borrow_cutoff_apr:null,benchmark:'arrival_mid',slippage_bps:10,
  fee_schedule:'illustrative_0.005_per_share_min_1_max_1pct_not_account_verified',impact_model:'unmeasured',primary:false,indicative:true,
}))));

export function currentEvidence(rows,kind,now){return rows.filter(e=>e.kind===kind&&e.broker==='IBKR'&&e.scope==='reverse_split'&&at(e.observed_at)!==null&&at(e.observed_at)<=at(now)&&at(e.valid_until)!==null&&at(e.valid_until)>=at(now)).sort((a,b)=>at(b.observed_at)-at(a.observed_at))[0];}
export function brokerGates(rows,now){
  const locate=currentEvidence(rows,'locate',now),margin=currentEvidence(rows,'margin',now),ssr=currentEvidence(rows,'ssr',now),status=currentEvidence(rows,'trading_status',now);
  const reasons=[];
  if(!locate||locate.approved!==true||!Number.isInteger(locate.shares)||locate.shares<=0||!finite(locate.apr)||locate.apr<0||!locate.allocation_id)reasons.push('ibkr_locate_approval_missing');
  if(!margin||margin.approved!==true||!finite(margin.available_notional)||margin.available_notional<=0||!margin.allocation_id)reasons.push('ibkr_margin_approval_missing');
  if(!ssr||ssr.restricted!==false)reasons.push(ssr?.restricted?'ssr_restricted':'ssr_status_unknown');
  if(!status||status.halted!==false)reasons.push(status?.halted?'security_halted':'halt_status_unknown');
  return {reasons,locate,margin,ssr,status,evidence_ids:[locate,margin,ssr,status].filter(Boolean).map(x=>x.id)};
}
export function borrowAt(rows,now,{maxAge=1800000}={}){
  const r=rows.filter(r=>r.broker==='IBKR'&&['indicative','coverage'].includes(r.kind)&&at(r.observed_at)!==null&&at(r.observed_at)<=at(now)).sort((a,b)=>at(b.observed_at)-at(a.observed_at))[0];
  return r?.kind==='indicative'&&r.status==='quoted'&&finite(r.apr)&&r.apr>=0&&at(r.as_of)!==null&&at(r.as_of)<=at(now)&&at(now)-at(r.as_of)<=maxAge?r:null;
}
// Credit actual positive size changes captured before IPC throttling. A new timestamp
// or reconnect never resets already consumed shares. Counter absence is conservative.
export function bookAvailable(t,q,side){
  t.book ||= {};const price=side==='short'?q.bid:q.ask,size=side==='short'?q.bid_size:q.ask_size,key=side+':'+price;
  if(!t.book[key]&&Object.keys(t.book).length>=512)return {shares:0,key,reason:'book_price_history_limit'};
  const credit=q.raw?.book_credit?.[side],epoch=q.raw?.book_epoch||'no_counter';let b=t.book[key];
  if(!b)b=t.book[key]={total:size,spent:0,epoch,counter:finite(credit)?credit:null};
  else if(b.epoch!==epoch){b.total=Math.max(b.total,size);b.epoch=epoch;b.counter=finite(credit)?credit:null;}
  else if(finite(credit)&&finite(b.counter)&&credit>=b.counter){b.total+=credit-b.counter;b.counter=credit;}
  return {shares:Math.floor(Math.max(0,Math.min(size,b.total-b.spent))),key};
}
export function spendBook(t,key,shares){t.book[key].spent+=shares;}
export function priceCapacity(t,q,p){
  const price=q.bid*(1-p.slippage_bps/10000),floor=(t.arrival_mid||((q.bid+q.ask)/2))*(1-p.price_budget_bps/10000);
  if(!t.entry_shares&&price<floor)return {shares:0,price,reason:'spread_and_slippage_exceed_price_budget'};
  const headroom=(t.entry_proceeds||0)-floor*(t.entry_shares||0);
  return {shares:price>=floor?Number.MAX_SAFE_INTEGER:Math.max(0,Math.floor((headroom+1e-8)/(floor-price))),price,reason:'observed_book_capacity'};
}
export function availableCapacity(t,q,p,borrow,evidence,peers,now){
  const book=bookAvailable(t,q,'short'),price=priceCapacity(t,q,p),gate=brokerGates(evidence,now);
  if(peers.some(x=>x.id!==t.id&&x.policy_id===t.policy_id&&x.cik===t.cik&&x.remaining_shares>0))return {shares:0,reason:'issuer_already_open',gate};
  if(!borrow)return {shares:0,reason:'fresh_ibkr_fee_and_inventory_missing',gate};
  if(!Number.isInteger(borrow.available_shares)||borrow.available_shares<=0)return {shares:0,reason:'ibkr_inventory_unavailable',gate};
  if(p.lane==='executable'&&gate.reasons.length)return {shares:0,reason:gate.reasons[0],gate};
  // The same account inventory / margin allocation cannot be counted twice within a cohort.
  const others=peers.filter(x=>x.id!==t.id&&x.policy_id===t.policy_id);
  const borrowed=others.filter(x=>x.ticker===t.ticker).reduce((n,x)=>n+(x.remaining_shares||0),0)+(t.remaining_shares||0);
  let shares=Math.min(book.shares,price.shares,Math.max(0,borrow.available_shares-borrowed));
  if(p.lane==='executable'){
    const allocatedBorrow=others.filter(x=>x.locate_allocation_id===gate.locate.allocation_id).reduce((n,x)=>n+(x.remaining_shares||0),0);
    const allocatedMargin=others.filter(x=>x.margin_allocation_id===gate.margin.allocation_id).reduce((n,x)=>n+(x.remaining_shares||0)*Math.max(x.entry_price||0,x.mark_price||0),0);
    shares=Math.min(shares,Math.max(0,gate.locate.shares-allocatedBorrow-(t.remaining_shares||0)),Math.max(0,(gate.margin.available_notional-allocatedMargin-(t.remaining_shares||0)*q.ask)/q.ask));
  }
  return {shares:Math.max(0,Math.floor(shares)),price:price.price,key:book.key,gate,reason:price.shares===0?price.reason:book.shares===0?'displayed_book_consumed':'observed_liquidity_and_borrow_bound'};
}
export function fill(t,side,shares,price,q,p,now){
  const fee=commission(shares,price,p);t.fills ||= [];
  if(side==='short'){t.entry_shares+=shares;t.remaining_shares+=shares;t.entry_proceeds+=shares*price;t.entry_price=t.entry_proceeds/t.entry_shares;t.entry_at ||= now;}
  else{t.remaining_shares=Math.max(0,t.remaining_shares-shares);t.cover_cost+=shares*price;}
  t.commissions+=fee;
  const f={side,shares,price,at:now,quote_at:q.quote_at,observed_at:q.observed_at,commission:fee,simulated:true,broker_execution_verified:false,quote_snapshot:{ticker:q.ticker,security_id:q.security_id,cik:q.cik,bid:q.bid,ask:q.ask,bid_size:q.bid_size,ask_size:q.ask_size,provider:q.provider,dataset:q.dataset,coverage:q.coverage,source_url:q.source_url,raw:q.raw}};t.fills.push(f);return f;
}
export function chargedRateProxy(rows,day,conid,now,accountScope){
  if(!conid)return null;
  const candidates=rows.filter(r=>r.kind==='charged'&&r.day===day&&String(r.conid)===String(conid)&&r.account_scope&&finite(r.apr)&&r.apr>=0&&at(r.observed_at)<=at(now));
  const scopes=[...new Set(candidates.map(r=>r.account_scope))];
  const scope=accountScope||(scopes.length===1?scopes[0]:null);if(!scope)return null;
  const latest=new Map();for(const r of candidates.filter(r=>r.account_scope===scope).sort((a,b)=>at(a.observed_at)-at(b.observed_at)))latest.set(r.position_day_key||r.id,r);
  const selected=[...latest.values()],weight=r=>Number(r.reported_quantity)*Number(r.reported_price);
  if(!selected.length||selected.some(r=>!finite(weight(r))||weight(r)<=0))return null;
  const total=selected.reduce((n,r)=>n+weight(r),0);
  return {apr:selected.reduce((n,r)=>n+weight(r)*r.apr,0)/total,account_scope:scope,ids:selected.map(r=>r.id).sort(),source:'reported_account_rate_proxy',observed_at:selected.map(r=>r.observed_at).sort().at(-1),new_loan_rate_guaranteed:false};
}
export function accrueBorrow(t,rows,now){
  if(!t.entry_at)return;
  t.borrow_ledger ||= [];
  const through=etDay(t.exit_at||now);
  for(let ms=Date.parse(etDay(t.entry_at)+'T12:00:00Z');ms<=Date.parse(through+'T12:00:00Z');ms+=DAY){
    const day=new Date(ms).toISOString().slice(0,10),oldIndex=t.borrow_ledger.findIndex(x=>x.day===day),old=t.borrow_ledger[oldIndex];
    // Freeze a day's liability from the shares actually outstanding at the last
    // supported daily mark. Future observations never change the entry decision.
    const closedDay=day<etDay(now)||Boolean(t.exit_at);if(!closedDay)continue;
    let daily=(t.daily_marks||[]).find(m=>m.day===day),carried=false;
    if(!daily&&!sessions.some(s=>s.day===day)){daily=(t.daily_marks||[]).filter(m=>m.day<day).sort((a,b)=>a.day.localeCompare(b.day)).at(-1);carried=!!daily;}
    const chargedShares=carried?(daily?.end_shares??daily?.shares??null):(daily?.borrow_shares??null),mark=daily?.price;
    const rate=rows.filter(r=>r.kind==='indicative'&&r.status==='quoted'&&finite(r.apr)&&r.apr>=0&&etDay(r.as_of)===day&&at(r.observed_at)<=at(now)).sort((a,b)=>at(b.as_of)-at(a.as_of))[0];
    const conid=rate?.conid||old?.conid||(!t.applied_actions?.length?t.ibkr_entry_conid:null),proxy=chargedRateProxy(rows,day,conid,now,t.borrow_account_scope);
    if(old&&finite(old.cost)&&(!proxy||JSON.stringify(old.reported_rate_ids)===JSON.stringify(proxy.ids)))continue;
    const apr=proxy?.apr??rate?.apr??old?.apr??null,price=mark??old?.mark_price??null,shares=chargedShares??old?.shares??null;
    const item={day,shares,mark_price:price,conid:conid||null,apr,rate_id:proxy?null:rate?.id||null,rate_source:proxy?.source||'public_indicative',reported_rate_ids:proxy?.ids||[],reported_account_scope:proxy?.account_scope||null,rate_observed_at:proxy?.observed_at||rate?.observed_at||null,ex_post:!!proxy||(!!rate&&at(rate.observed_at)>at(t.entry_at)),carried_non_session_mark:carried,basis:'modeled_daily_max_shares_IBKR_102pct_rounded_USD_360_not_settled_statement',cost:shares===0?0:finite(apr)&&finite(price)&&finite(shares)?shares*Math.ceil(price*1.02)*apr/360:null,actually_charged:false,new_loan_rate_guaranteed:false};
    if(oldIndex>=0)t.borrow_ledger[oldIndex]=item;else t.borrow_ledger.push(item);
  }
}
export function executionPnl(t){
  if(!t.entry_shares||t.action_unresolved)return {gross_pnl:null,estimated_net_pnl:null,complete_net_pnl:null,actual_net_pnl:null,cost_gaps:[]};
  const gross=!t.remaining_shares?t.entry_proceeds-t.cover_cost:finite(t.mark_price)?t.entry_proceeds-t.cover_cost-t.remaining_shares*t.mark_price:null;
  const known=t.borrow_ledger?.filter(r=>finite(r.cost)).reduce((n,r)=>n+r.cost,0)||0,missing=t.borrow_ledger?.filter(r=>!finite(r.cost)).length||0;
  const pending=(t.remaining_shares>0||t.exit_at)&&!t.borrow_ledger?.some(x=>x.day===etDay(t.exit_at||t.mark_at));
  const gaps=['account_commission_schedule_unverified','regulatory_fees_unverified','dividend_and_special_distribution_status_unverified','recall_buyin_and_cash_settlement_costs_unverified'];
  if(missing||pending)gaps.push('borrow_daily_cost_incomplete');
  const pendingCost=!pending?0:finite(t.current_borrow_apr)&&finite(t.mark_price)?t.remaining_shares*Math.ceil(1.02*t.mark_price)*t.current_borrow_apr/360:null;
  const reserve=t.remaining_shares>0?commission(t.remaining_shares,t.mark_price,{commission_minimum:1,commission_per_share:.005})+t.remaining_shares*t.mark_price*.001:0;
  const reconciliation=t.cost_reconciliation,complete=t.state==='closed'&&finite(gross)&&reconciliation&&at(reconciliation.covers_fills_through)>=at(t.fills.at(-1)?.at)?gross-Object.values(reconciliation.costs).reduce((n,x)=>n+x,0):null;
  const partial=finite(gross)?gross-(t.commissions||0)-known-pendingCost-reserve:null;
  if(pending&&pendingCost===null)gaps.push('current_day_borrow_rate_missing');
  return {gross_pnl:gross,known_borrow_cost:known,missing_borrow_days:missing,pending_borrow_cost_estimate:pendingCost,pending_borrow_rate_id:t.current_borrow_rate_id||null,cover_cost_reserve:reserve,partial_cost_pnl:partial,estimated_net_pnl:missing||(pending&&pendingCost===null)?null:partial,complete_net_pnl:complete,reconciled_cost_basis:complete!==null?reconciliation.basis:null,actual_net_pnl:null,cost_gaps:complete!==null?[]:gaps};
}
export function cutoffStudy(tracks){return [0.1,.25,.5,1,2,null].map(cutoff=>{
  const rows=tracks.filter(t=>t.entry_shares&&finite(t.entry_borrow_apr)&&(cutoff===null||t.entry_borrow_apr<=cutoff)),closed=rows.filter(t=>t.state==='closed'&&finite(t.pnl?.estimated_net_pnl));
  return {cutoff_apr:cutoff,entered:rows.length,closed:closed.length,closed_estimated_pnl:closed.length?closed.reduce((n,t)=>n+t.pnl.estimated_net_pnl,0):null,missing_entry_rate:tracks.filter(t=>t.entry_shares&&!finite(t.entry_borrow_apr)).length,selection_basis:'rate_known_at_entry',decision:'research_only_no_automatic_live_cutoff'};
});}
