import {EXECUTION_POLICIES,EXECUTION_VERSION,availableCapacity,borrowAt,bookAvailable,spendBook,fill,accrueBorrow,executionPnl,cutoffStudy} from './execution-core.mjs';
import {signalGate,plannedEntry,plannedExit,sessionAt,quoteGate,at,finite} from './shadow-core.mjs';
import {digest,putState} from './shadow-service.mjs';
import {etDay} from './core.mjs';
import {putSummaryIfChanged} from './summary-state.mjs';
const stamp=()=>new Date().toISOString(),parse=r=>JSON.parse(r.payload);
async function audit(env,t,kind,now,data){const payload=JSON.stringify(data),id=await digest(t.id+':'+kind+':'+now+':'+payload);await env.DB.prepare('INSERT OR IGNORE INTO rs_execution_records VALUES(?,?,?,?,?)').bind(id,t.id,now,kind,payload).run();}
async function save(env,t,now){t.updated_at=now;await env.DB.prepare('INSERT INTO rs_execution_tracks VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,state=excluded.state,updated_at=excluded.updated_at,payload=excluded.payload').bind(t.id,t.event_id,t.policy_id,t.ticker,t.state,now,JSON.stringify(t)).run();}
export async function initializeExecution(env,now=stamp()){
  for(const p of EXECUTION_POLICIES){const old=await env.DB.prepare('SELECT payload FROM rs_execution_policies WHERE id=?').bind(p.id).first();if(old&&JSON.stringify(parse(old))!==JSON.stringify(p))throw new Error('Executable policy changed; register a new version');if(!old)await env.DB.prepare('INSERT INTO rs_execution_policies VALUES(?,?,?)').bind(p.id,now,JSON.stringify(p)).run();}
  const registered=(await env.DB.prepare('SELECT min(registered_at) AS at FROM rs_execution_policies').first()).at;
  env.EXECUTION_REGISTRATION_DAY=registered.slice(0,10);
}
export async function enrollExecution(env,event,now=stamp()){
  for(const p of EXECUTION_POLICIES){
    const id=p.id+':'+event.id,old=await env.DB.prepare('SELECT payload FROM rs_execution_tracks WHERE id=?').bind(id).first();
    const t=old?parse(old):{id,event_id:event.id,policy_id:p.id,lane:p.lane,broker:'IBKR',ticker:event.ticker,cik:event.cik,company:event.company,first_seen_at:event.first_seen_at,published_at:event.published_at,enrolled_at:now,state:'waiting',reason:'analysis_pending',entry_shares:0,remaining_shares:0,entry_proceeds:0,cover_cost:0,commissions:0,fills:[],borrow_ledger:[],daily_marks:[],applied_actions:[],research_only:true,authority:'none',broker_execution_verified:false};
    if(['retrospective','rejected','missed','closed'].includes(t.state))continue;
    const before=JSON.stringify(t),registered=(await env.DB.prepare('SELECT registered_at FROM rs_execution_policies WHERE id=?').bind(p.id).first()).registered_at;
    t.effective_date=event.effective_date;
    if(t.entry_shares&&((event.ticker&&event.ticker!==t.ticker)||(event.cik&&event.cik!==t.cik)))t.identity_revision_unresolved=true;
    else{t.ticker=event.ticker||t.ticker;t.cik=event.cik||t.cik;}
    if(at(event.first_seen_at)<at(registered)){t.state='retrospective';t.reason='detected_before_forward_registration';}
    else if(event.status==='cancelled'){t.state=t.remaining_shares?'exit_pending':'rejected';t.exit_requested_at ||= now;t.reason='announcement_cancelled';}
    else if(t.entry_shares&&t.state==='partial_entry'&&signalGate(event,p,now).state!=='eligible'){t.state='open';t.reason='signal_revised_stop_adding';}
    else if(!t.entry_shares){
      const gate=signalGate(event,p,now);
      if(gate.state!=='eligible'){t.state=gate.state;t.reason=gate.reason;t.signal_at=null;}
      else if(!t.signal_at){
        t.signal_at=now;t.due_at=plannedEntry(event,p,now);t.decision_snapshot={score:event.financials.score,ordinal_min:event.ordinal_min,period:event.financials.period,signals:event.financials.signals,analyzed_at:event.analyzed_at,sources:event.sources};
        const oldNews=event.published_at&&at(now)-at(event.published_at)>p.maximum_entry_age_seconds*1000;
        if(oldNews||!t.due_at||etDay(t.due_at)>=event.effective_date){t.state='missed';t.reason=oldNews?'announcement_already_old_when_ready':'no_pre_split_entry_window';}
        else{t.state='armed';t.reason='waiting_for_fresh_quote_and_ibkr_evidence';}
      }
      if(t.state==='waiting'&&at(now)-at(event.first_seen_at)>p.maximum_entry_age_seconds*1000){t.state='missed';t.reason='filters_not_resolved_in_entry_window';}
    }
    if(!old||before!==JSON.stringify(t)){await save(env,t,now);await audit(env,t,'decision',now,{state:t.state,reason:t.reason,registered_at:registered,decision_snapshot:t.decision_snapshot});}
  }
}
export async function processExecution(env,t,q,peers,borrowRows,evidence,now=stamp(),actions={records:[],complete:false}){
  const p=EXECUTION_POLICIES.find(x=>x.id===t.policy_id);if(!p)throw new Error('Unknown executable policy');
  if(t.state==='closed'){
    const previousBorrow=JSON.stringify(t.borrow_ledger);accrueBorrow(t,borrowRows,now);
    const r=evidence.filter(e=>e.kind==='cost_reconciliation'&&e.broker==='IBKR'&&e.scope==='reverse_split'&&e.policy_id===t.policy_id&&at(e.observed_at)<=at(now)&&['commissions','borrow','regulatory','locate','dividends','cash_settlement','buyin'].every(k=>finite(e.costs?.[k]))).sort((a,b)=>at(b.observed_at)-at(a.observed_at))[0];
    if(r&&t.cost_reconciliation?.id!==r.id){t.cost_reconciliation=r;t.pnl=executionPnl(t);await save(env,t,now);await audit(env,t,'cost_reconciliation',now,{evidence_id:r.id,pnl:t.pnl});}
    else if(JSON.stringify(t.borrow_ledger)!==previousBorrow){t.pnl=executionPnl(t);await save(env,t,now);await audit(env,t,'borrow_reconciliation',now,{borrow_ledger:t.borrow_ledger,pnl:t.pnl});}return t;
  }
  const before=JSON.stringify(t),day=etDay(now);let reason;
  if(t.remaining_shares){
    for(const a of actions.records.filter(a=>a.execution_date>etDay(t.entry_at)&&a.execution_date<=day)){
      const key=[a.execution_date,a.split_from,a.split_to].join(':');if(t.applied_actions.includes(key)||!finite(a.split_from)||!finite(a.split_to)||a.split_from<=0||a.split_to<=0)continue;
      if(a.ticker&&a.ticker!==t.ticker)continue;
      const factor=a.split_to/a.split_from;t.remaining_shares*=factor;t.mark_price/=factor;t.applied_actions.push(key);t.last_action_date=a.execution_date;t.book={};await audit(env,t,'corporate_action',now,{...a,remaining_shares:t.remaining_shares,fractional_liability:t.remaining_shares%1!==0});
    }
    t.action_unresolved=!!(t.effective_date>etDay(t.entry_at)&&day>=t.effective_date&&(!actions.complete||!t.last_action_date));
    if(t.action_unresolved)reason='corporate_action_unresolved';
    if(t.identity_revision_unresolved){t.action_unresolved=true;reason='security_identity_revision_unresolved';}
    if(at(now)>=at(t.exit_due_at)-p.exit_lead_seconds*1000||t.exit_requested_at){t.state='exit_pending';t.exit_requested_at ||= now;}
    if(t.state==='partial_entry'&&at(now)>at(t.due_at)+p.entry_window_seconds*1000)t.state='open';
  }
  if(!t.remaining_shares&&at(now)>at(t.due_at)+p.entry_window_seconds*1000){t.state='missed';reason='entry_window_expired';}
  reason ||= at(now)<at(t.due_at)?'waiting_for_entry_clock':!sessionAt(now)?'regular_session_closed':quoteGate(q,now,p);
  if(!reason&&(q.cik!==t.cik||q.type!=='CS'||q.currency!=='usd'||!q.security_id||(t.security_id&&t.security_id!==q.security_id)))reason='security_identity_unverified_or_changed';
  if(!reason){
    t.security_id ||= q.security_id;t.mark_price=q.ask;t.mark_at=q.quote_at;t.mark_stale=false;t.quote_coverage=q.coverage;
    const idx=t.daily_marks.findIndex(m=>m.day===day),mark={day,price:q.ask,shares:t.remaining_shares,borrow_shares:Math.max(t.daily_marks[idx]?.borrow_shares||0,t.remaining_shares),at:q.quote_at};if(idx<0)t.daily_marks.push(mark);else t.daily_marks[idx]=mark;
    const clock=t.state==='exit_pending'?t.exit_requested_at:t.due_at;
    if(['armed','partial_entry','exit_pending'].includes(t.state)&&at(q.observed_at)<at(clock))reason='waiting_for_post_decision_quote';
    else if(t.state==='exit_pending'){
      const book=bookAvailable(t,q,'cover'),shares=Math.floor(Math.min(t.remaining_shares+1e-8,book.shares));
      if(shares>0){const f=fill(t,'cover',shares,q.ask*(1+p.slippage_bps/10000),q,p,now);spendBook(t,book.key,shares);await audit(env,t,'counterfactual_cover',now,f);if(t.remaining_shares<1e-8){t.state='closed';t.exit_at=now;}reason=t.remaining_shares%1?'fractional_liability_retained':t.remaining_shares?'partial_cover':'counterfactual_closed';}
      else reason=t.remaining_shares<1?'fractional_liability_retained':'cover_book_consumed';
    }else if(['armed','partial_entry'].includes(t.state)&&at(now)<=at(t.due_at)+p.entry_window_seconds*1000){
      t.arrival_mid ||= (q.bid+q.ask)/2;
      const borrow=borrowAt(borrowRows,now),capacity=availableCapacity(t,q,p,borrow,evidence,peers,now);t.gates={reasons:capacity.gate?.reasons||[],evidence_ids:capacity.gate?.evidence_ids||[],public_borrow_id:borrow?.id||null};
      if(capacity.shares>0&&(t.entry_shares||capacity.shares*capacity.price>=p.minimum_notional)){
        t.entry_borrow_apr ??= p.lane==='executable'?capacity.gate.locate.apr:borrow.apr;t.entry_borrow_id ||= p.lane==='executable'?capacity.gate.locate.id:borrow.id;
        t.ibkr_entry_conid ||= borrow.conid||null;t.borrow_account_scope ||= capacity.gate.locate?.account_scope||null;
        if(capacity.gate?.locate){t.locate_allocation_id=capacity.gate.locate.allocation_id;t.margin_allocation_id=capacity.gate.margin?.allocation_id;}
        const f=fill(t,'short',capacity.shares,capacity.price,q,p,now);spendBook(t,capacity.key,capacity.shares);t.exit_due_at ||= plannedExit(t.entry_at,p.hold_sessions);t.state='partial_entry';
        f.borrow_id=borrow.id;f.evidence_ids=t.gates.evidence_ids;await audit(env,t,'counterfactual_short',now,f);reason=p.lane==='capacity'?'conditional_capacity_not_broker_approved':'dated_ibkr_evidence_supported_counterfactual';
      }else reason=capacity.reason;
    }
  }else if(t.remaining_shares)t.mark_stale=true;
  const daily=t.daily_marks.find(m=>m.day===day);if(daily){daily.borrow_shares=Math.max(daily.borrow_shares,t.remaining_shares);daily.end_shares=t.remaining_shares;}
  const reconciliation=evidence.filter(e=>e.kind==='cost_reconciliation'&&e.broker==='IBKR'&&e.scope==='reverse_split'&&e.policy_id===t.policy_id&&at(e.observed_at)<=at(now)&&['commissions','borrow','regulatory','locate','dividends','cash_settlement','buyin'].every(k=>finite(e.costs?.[k]))).sort((a,b)=>at(b.observed_at)-at(a.observed_at))[0];if(reconciliation)t.cost_reconciliation=reconciliation;
  const todayRate=borrowRows.filter(r=>r.kind==='indicative'&&r.status==='quoted'&&finite(r.apr)&&r.apr>=0&&etDay(r.as_of)===day&&at(r.observed_at)<=at(now)).sort((a,b)=>at(b.as_of)-at(a.as_of))[0];t.current_borrow_apr=todayRate?.apr??null;t.current_borrow_rate_id=todayRate?.id||null;
  t.reason=reason||'marked';accrueBorrow(t,borrowRows,now);t.pnl=executionPnl(t);t.entry_deterioration_bps=t.entry_shares?10000*(1-t.entry_price/t.arrival_mid):null;
  if(JSON.stringify(t)!==before){await save(env,t,now);const old=JSON.parse(before);if(JSON.stringify(old.borrow_ledger)!==JSON.stringify(t.borrow_ledger))await audit(env,t,'borrow_accrual',now,{borrow_ledger:t.borrow_ledger});if(t.reason!==old.reason)await audit(env,t,'status',now,{state:t.state,reason:t.reason,gates:t.gates});}return t;
}
export async function executionTick(env,{now=stamp(),event}={}){
  if(env.SHADOW_ENABLED!=='true')return;
  if(event)await enrollExecution(env,event,now);
  else{
    for(const r of (await env.DB.prepare('SELECT payload FROM rs_events').all()).results){const e=parse(r),key='execution_enrolled:'+e.id,value=e.analyzed_at||e.first_seen_at,old=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first(),waiting=await env.DB.prepare("SELECT id FROM rs_execution_tracks WHERE event_id=? AND state='waiting' LIMIT 1").bind(e.id).first();if(old?.value!==JSON.stringify(value)||waiting){await enrollExecution(env,e,now);await putState(env,key,value,now);}}
  }
  const tracks=(await env.DB.prepare('SELECT payload FROM rs_execution_tracks').all()).results.map(parse),quotes=new Map(),borrows=new Map(),evidenceCache=new Map(),actions=new Map();
  for(const t of tracks.filter(t=>['armed','partial_entry','open','exit_pending','closed'].includes(t.state))){
    if(!borrows.has(t.ticker))borrows.set(t.ticker,(await env.DB.prepare('SELECT payload FROM rs_borrow_observations WHERE ticker=? ORDER BY day DESC,observed_at DESC LIMIT 1500').bind(t.ticker).all()).results.map(parse));
    if(!evidenceCache.has(t.event_id))evidenceCache.set(t.event_id,(await env.DB.prepare('SELECT payload FROM rs_shadow_evidence WHERE event_id=? ORDER BY observed_at DESC LIMIT 500').bind(t.event_id).all()).results.map(parse));
    if(t.state!=='closed'&&!quotes.has(t.ticker))try{quotes.set(t.ticker,await env.market.quote(t.ticker,EXECUTION_POLICIES[0]));}catch{quotes.set(t.ticker,null);}
    if(t.remaining_shares&&t.effective_date<=etDay(now)&&!actions.has(t.ticker))try{actions.set(t.ticker,await env.market.actions(t.ticker,etDay(t.entry_at)));}catch{actions.set(t.ticker,{records:[],complete:false});}
    await processExecution(env,t,quotes.get(t.ticker),tracks,borrows.get(t.ticker),evidenceCache.get(t.event_id),now,actions.get(t.ticker));
  }
  const policies=[];
  for(const p of EXECUTION_POLICIES){
    const rows=tracks.filter(t=>t.policy_id===p.id),entered=rows.filter(t=>t.entry_shares),closed=entered.filter(t=>t.state==='closed'),known=entered.filter(t=>finite(t.pnl?.estimated_net_pnl));
    const summary={...p,enrolled:rows.length,retrospective:rows.filter(t=>t.state==='retrospective').length,entered:entered.length,open:entered.filter(t=>t.remaining_shares).length,closed:closed.length,entry_notional:entered.reduce((n,t)=>n+t.entry_proceeds,0),estimated_net_pnl:known.length?known.reduce((n,t)=>n+t.pnl.estimated_net_pnl,0):null,complete_net_pnl:null,actual_net_pnl:null,stale_marks:entered.filter(t=>t.remaining_shares&&(t.mark_stale||at(now)-at(t.mark_at)>15000)).length,unresolved_cost_positions:entered.filter(t=>t.pnl?.cost_gaps?.length).length,cutoffs:cutoffStudy(rows),blocked_reasons:Object.entries(rows.filter(t=>['armed','partial_entry','missed','waiting'].includes(t.state)).reduce((a,t)=>(a[t.reason]=(a[t.reason]||0)+1,a),{})).map(([reason,count])=>({reason,count}))};policies.push(summary);
    if(entered.length)await env.DB.prepare('INSERT INTO rs_execution_daily VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').bind(p.id+':'+etDay(now),p.id,etDay(now),JSON.stringify({policy_id:p.id,day:etDay(now),estimated_net_pnl:summary.estimated_net_pnl,stale_marks:summary.stale_marks,unresolved_cost_positions:summary.unresolved_cost_positions})).run();
  }
  const capacity=tracks.filter(t=>t.lane==='capacity'&&t.entry_shares),days=new Set(capacity.map(t=>etDay(t.entry_at))),issuers=new Set(capacity.map(t=>t.cik)),enough=days.size>=30&&issuers.size>=20;
  const curve=policies.filter(p=>p.lane==='capacity'),max=Math.max(0,...curve.map(p=>p.entry_notional)),recommendation=enough&&max?curve.find(p=>p.entry_notional>=max*.9)?.price_budget_bps:null;
  await putSummaryIfChanged(env,'execution_summary',{version:EXECUTION_VERSION,generated_at:now,broker:'IBKR',research_only:true,authority:'none',execution_ready:false,policies,price_budget_judgement:{recommended_bps:recommendation,status:recommendation?'research_candidate_needs_impact_validation':'insufficient_live_observations',sessions:days.size,issuers:issuers.size,minimum_sessions:30,minimum_issuers:20,rule:'Smallest tested budget retaining 90% of observed conditional notional; no causal market-impact claim.'},limits:{fixed_dollar_cap:null,fixed_name_count_cap:null,remaining_constraints:['observed displayed liquidity','arrival-mid price budget including 10bps modeled slippage','fresh IBKR public inventory and fee','executable lane additionally requires IBKR locate, margin, SSR and halt evidence']},borrow_source:'IBKR_public_indications_reconciled_to_unique_matching_account_and_conid_reported_rate_proxies',borrow_cost_engine:'ibkr_observed_daily.v2',impact_model:'unmeasured_selected_venue_L1',actual_broker_fills:0},now);
}
