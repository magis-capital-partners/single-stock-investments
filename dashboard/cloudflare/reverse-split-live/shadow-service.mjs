import {SHADOW_POLICIES,SHADOW_VERSION,signalGate,plannedEntry,plannedExit,sessionAt,nextSession,quoteGate,entryCapacity,commission,feasibility,pnl,at,iso,finite,validateEvidence} from './shadow-core.mjs';
import {etDay,DAY} from './core.mjs';
const stamp=()=>new Date().toISOString(),parse=r=>JSON.parse(r.payload);
export async function digest(value){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(n=>n.toString(16).padStart(2,'0')).join('');}
async function getState(env,key){const r=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first();return r?JSON.parse(r.value):null;}
export async function putState(env,key,value,now=stamp()){await env.DB.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(key,JSON.stringify(value),now).run();}
export async function initializeShadow(env,now=stamp()){
  for(const p of SHADOW_POLICIES){const old=await env.DB.prepare('SELECT payload FROM rs_shadow_policies WHERE id=?').bind(p.id).first();if(old&&JSON.stringify(JSON.parse(old.payload))!==JSON.stringify(p))throw new Error('Registered shadow policy changed; create a new version');if(!old){await env.DB.prepare('INSERT INTO rs_shadow_policies VALUES(?,?,?)').bind(p.id,now,JSON.stringify(p)).run();await putState(env,'shadow_policy_registered_at',now,now);}}
  const started=await getState(env,'shadow_started_at');if(!started)await putState(env,'shadow_started_at',now,now);
}
async function record(env,t,kind,now,data,key){const id=await digest(t.id+':'+kind+':'+(key||now)+':'+JSON.stringify(data));await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_records VALUES(?,?,?,?,?,?)').bind(id,t.id,t.event_id,kind,now,JSON.stringify(data)).run();}
async function persist(env,t,kind,now,data={}){t.updated_at=now;await env.DB.prepare('INSERT INTO rs_shadow_tracks(id,event_id,policy_id,cik,ticker,enrolled_at,signal_at,due_at,state,reason,updated_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,signal_at=excluded.signal_at,due_at=excluded.due_at,state=excluded.state,reason=excluded.reason,updated_at=excluded.updated_at,payload=excluded.payload').bind(...['id','event_id','policy_id','cik','ticker','enrolled_at','signal_at','due_at','state','reason','updated_at'].map(k=>t[k]??null),JSON.stringify(t)).run();if(kind)await record(env,t,kind,now,data);}
export async function enrollShadow(env,event,now=stamp()){
  if(env.SHADOW_ENABLED!=='true')return;
  const start=await getState(env,'shadow_started_at');if(!start)throw new Error('Shadow enrollment requires a registered policy');
  for(const p of SHADOW_POLICIES){
    const registration=await env.DB.prepare('SELECT registered_at FROM rs_shadow_policies WHERE id=?').bind(p.id).first(),policyStart=p.indicative?registration.registered_at:start;
    const id=p.id+':'+event.id,row=await env.DB.prepare('SELECT payload FROM rs_shadow_tracks WHERE id=?').bind(id).first();
    let t=row?parse(row):{id,event_id:event.id,policy_id:p.id,cik:event.cik||null,ticker:event.ticker||null,company:event.company||null,enrolled_at:now,first_seen_at:event.first_seen_at,published_at:event.published_at,signal_at:null,due_at:null,state:'waiting',reason:'analysis_pending',entry_shares:0,remaining_shares:0,entry_proceeds:0,cover_cost:0,commissions:0,borrow_cost:0,borrow_days:[],used_quotes:[],applied_actions:[],fills:[],feasibility:{state:'unverified'},research_only:true,authority:'none'};
    if(!row)await record(env,t,'enrolled',now,{event,policy_id:p.id,registered_start:policyStart});
    if(['closed','rejected','missed','retrospective'].includes(t.state))continue;
    const before=[t.state,t.reason,t.signal_at,t.ticker].join('|');t.ticker=event.ticker||t.ticker;t.cik=event.cik||t.cik;t.effective_date=event.effective_date;t.trading_date=event.trading_date||null;
    if(at(event.first_seen_at)<at(policyStart)){t.state='retrospective';t.reason='detected_before_forward_registration';}
    else if(event.status==='cancelled'){t.state=t.remaining_shares?'exit_pending':'rejected';t.reason='announcement_cancelled';t.exit_requested_at=now;}
    else if(!t.signal_at){
      const gate=signalGate(event,p,now);t.state=gate.state==='rejected'?'rejected':'waiting';t.reason=gate.reason;
      if(gate.state==='eligible'){
        t.signal_at=now;t.decision_snapshot={score:event.financials.score,period:event.financials.period,signals:event.financials.signals,ordinal_min:event.ordinal_min,sources:event.sources,analyzed_at:event.analyzed_at,checks:event.checks};t.due_at=plannedEntry(event,p,now);
        const stale=event.published_at&&at(now)-at(event.published_at)>p.maximum_entry_age_seconds*1000;
        if(stale){t.state='missed';t.reason='announcement_already_old_when_ready';}
        else if(!t.due_at){t.state='missed';t.reason='exchange_calendar_exhausted';}
        else if(!['split_open','post_split'].includes(p.timing)&&etDay(t.due_at)>=event.effective_date){t.state='missed';t.reason='no_pre_split_entry_window';}
        else{t.state='armed';t.reason=at(t.due_at)>at(now)?'waiting_for_entry_clock':'waiting_for_fresh_quote';}
      }else if(at(now)-at(event.first_seen_at)>p.maximum_entry_age_seconds*1000){t.state='missed';t.reason='filters_not_resolved_in_entry_window';}
    }else if(['armed','partial_entry'].includes(t.state)&&!t.entry_shares){
      const gate=signalGate(event,p,now);if(gate.state!=='eligible'){t.state=gate.state==='rejected'?'rejected':'waiting';t.reason='signal_revised_before_entry';t.signal_at=null;}
    }
    if(!row||before!==[t.state,t.reason,t.signal_at,t.ticker].join('|'))await persist(env,t,'decision',now,{state:t.state,reason:t.reason,signal_at:t.signal_at,due_at:t.due_at,decision_snapshot:t.decision_snapshot});
  }
  await env.DB.prepare('INSERT INTO rs_shadow_enrollments VALUES(?,?,?) ON CONFLICT(event_id) DO UPDATE SET event_at=excluded.event_at,processed_at=excluded.processed_at').bind(event.id,event.analyzed_at||event.first_seen_at,now).run();
}
function chargeBorrow(t,p,now){
  if(!t.remaining_shares||!t.mark_price)return;
  const end=etDay(now),start=t.borrow_days.at(-1)||etDay(t.entry_at);
  for(let d=Date.parse(start+'T12:00:00Z');d<=Date.parse(end+'T12:00:00Z');d+=DAY){const day=iso(d).slice(0,10);if(t.borrow_days.includes(day))continue;t.borrow_days.push(day);t.borrow_cost+=t.remaining_shares*Math.ceil(1.02*t.mark_price)*p.borrow_apr/360;}
}
async function evidenceFor(env,eventId){return (await env.DB.prepare('SELECT payload FROM rs_shadow_evidence WHERE event_id=? ORDER BY observed_at').bind(eventId).all()).results.map(parse);}
export async function processShadowTrack(env,t,q,peers,now=stamp(),actions={records:[],complete:false}){
  const p=SHADOW_POLICIES.find(x=>x.id===t.policy_id);if(!p)throw new Error('Unknown shadow policy');
  if(!['armed','partial_entry','open','exit_pending'].includes(t.state))return t;
  const evidence=await evidenceFor(env,t.event_id),day=etDay(now),active=Boolean(t.remaining_shares),preState=t.state;
  if(active){
    // Corporate-action uncertainty freezes marks rather than fabricating a split-day profit.
    const actionRows=[...actions.records.map(a=>({...a,id:a.id||a.execution_date+':'+a.split_from+':'+a.split_to})),...evidence.filter(x=>x.kind==='corporate_action'&&at(x.observed_at)<=at(now))];
    for(const a of actionRows.filter(a=>a.execution_date>etDay(t.entry_at)&&a.execution_date<=day).sort((a,b)=>a.execution_date.localeCompare(b.execution_date))){
      const actionKey=[a.execution_date,a.split_from,a.split_to].join(':');if(t.applied_actions.includes(actionKey))continue;
      if(a.ticker&&a.ticker!==t.ticker)continue;
      if(!finite(a.split_from)||!finite(a.split_to)||a.split_from<=0||a.split_to<=0)continue;
      const factor=a.split_to/a.split_from;t.remaining_shares*=factor;t.mark_price=t.mark_price/factor;t.applied_actions.push(actionKey);t.last_action_date=a.execution_date;
      await record(env,t,'corporate_action',now,{...a,remaining_shares:t.remaining_shares,fractional_liability:!Number.isInteger(t.remaining_shares)});
    }
    t.action_unresolved=Boolean(t.effective_date&&t.effective_date>etDay(t.entry_at)&&day>=t.effective_date&&(!actions.complete||!t.last_action_date));
    if(t.action_unresolved){t.reason='corporate_action_unresolved';t.net_pnl=null;await persist(env,t,preState!==t.state?'state':null,now);return t;}
    if(at(now)>=at(t.exit_due_at)-p.exit_lead_seconds*1000||t.exit_requested_at){t.state='exit_pending';t.exit_requested_at ||= now;t.reason=t.reason==='announcement_cancelled'?'announcement_cancelled':'time_exit_due';}
  }
  if(!active&&at(now)>at(t.due_at)+p.entry_window_seconds*1000){t.state='missed';t.reason='entry_window_expired_without_supported_quote';await persist(env,t,'missed',now,{reason:t.reason});return t;}
  if(at(now)<at(t.due_at))return t;
  const session=sessionAt(now),failure=quoteGate(q,now,p);
  if(!session||failure||q?.cik!==t.cik||q?.type!=='CS'||q?.currency!=='usd'||(t.security_id&&t.security_id!==q?.security_id)){
    const reason=!session?'regular_session_closed':failure||(q?.cik!==t.cik?'quote_issuer_mismatch':t.security_id&&t.security_id!==q?.security_id?'security_identity_changed':'security_type_or_currency_unresolved');
    if(active){chargeBorrow(t,p,now);t.mark_stale=true;t.net_pnl=pnl(t);}if(t.reason!==reason||active){t.reason=reason;await persist(env,t,'observation_blocked',now,{reason});}return t;
  }
  t.mark_price=q.ask;t.mark_at=q.quote_at;t.quote_source=q.source_url;t.quote_provider=q.provider;t.quote_coverage=q.coverage||'consolidated';t.indicative=p.indicative===true;
  if(active)chargeBorrow(t,p,now);
  const current=kind=>evidence.filter(e=>e.kind===kind&&at(e.observed_at)<=at(now)&&at(e.valid_until)>=at(now)).at(-1);
  const blocked=current('ssr')?.restricted===true?'short_sale_restriction_active':current('locate')?.approved===false?'borrow_denied':current('margin')?.approved===false?'margin_denied':null;
  if(blocked&&['armed','partial_entry'].includes(t.state)){t.reason=blocked;t.feasibility=feasibility(evidence,now,t.remaining_shares*q.ask,t.remaining_shares);await persist(env,t,'entry_blocked',now,{reason:blocked});return t;}
  const quoteKey=q.id+':'+(t.state==='exit_pending'?'cover':'entry');
  if(t.state==='exit_pending'&&!t.used_quotes.includes(quoteKey)){
    const shares=Math.min(Math.floor(t.remaining_shares+1e-8),Math.floor(Math.max(0,q.ask_size*p.quote_depth_fraction-(t.depth_spent?.['cover:'+q.ask]||0))));
    if(shares>0){const price=q.ask*(1+p.slippage_bps/10000),fee=commission(shares,price,p);t.depth_spent ||= {};t.depth_spent['cover:'+q.ask]=(t.depth_spent['cover:'+q.ask]||0)+shares;t.remaining_shares=Math.max(0,t.remaining_shares-shares);t.cover_cost+=shares*price;t.commissions+=fee;t.used_quotes.push(quoteKey);const fill={side:'cover',at:now,quote_at:q.quote_at,quote_id:q.id,shares,price,commission:fee,simulated:true};t.fills.push(fill);await record(env,t,'simulated_cover',now,fill);if(t.remaining_shares<1e-8){t.state='closed';t.exit_at=now;t.reason='simulated_position_closed';}else t.reason=t.remaining_shares<1?'fractional_liability_requires_settlement_evidence':'partial_cover';}
  }else if(['armed','partial_entry'].includes(t.state)&&at(now)<=at(t.due_at)+p.entry_window_seconds*1000&&!t.used_quotes.includes(quoteKey)){
    const capacity=entryCapacity(t,q,p,peers),shares=capacity.shares;
    if(shares>0&&(t.entry_shares||shares*q.bid>=p.minimum_notional)){
      const price=q.bid*(1-p.slippage_bps/10000),fee=commission(shares,price,p),prior=t.entry_shares;t.security_id ||= q.security_id;t.entry_shares+=shares;t.remaining_shares+=shares;t.entry_proceeds+=shares*price;t.entry_price=(prior*(t.entry_price||0)+shares*price)/t.entry_shares;t.commissions+=fee;t.entry_at ||= now;t.exit_due_at ||= plannedExit(t.entry_at,p.hold_sessions);t.used_quotes.push(quoteKey);t.state='partial_entry';t.reason='quote_bounded_simulated_entry';t.risk_notional_cap=capacity.risk_notional_cap;
      t.depth_spent ||= {};t.depth_spent['short:'+q.bid]=(t.depth_spent['short:'+q.bid]||0)+shares;const fill={side:'short',at:now,quote_at:q.quote_at,quote_id:q.id,shares,price,commission:fee,simulated:true};t.fills.push(fill);chargeBorrow(t,p,now);await record(env,t,'simulated_short',now,fill);
    }else t.reason=shares*q.bid<p.minimum_notional?'observed_depth_below_minimum_size':capacity.reason;
  }
  if(t.state==='partial_entry'&&at(now)>at(t.due_at)+p.entry_window_seconds*1000){t.state='open';t.reason='entry_window_closed';}
  t.public_borrow=evidence.filter(e=>e.kind==='public_borrow'&&at(e.observed_at)<=at(now)).at(-1)||null;t.feasibility=feasibility(evidence,now,t.remaining_shares*q.ask,t.remaining_shares);t.net_pnl=pnl(t);t.mark_stale=false;
  await persist(env,t,preState!==t.state?'state':null,now,{state:t.state,reason:t.reason});return t;
}
export async function shadowTick(env,options={}){
  const now=options.now||stamp(),event=options.event||null;
  if(env.SHADOW_ENABLED!=='true')return;
  if(event)await enrollShadow(env,event,now);
  else for(const r of (await env.DB.prepare("SELECT e.payload FROM rs_events e LEFT JOIN rs_shadow_enrollments s ON s.event_id=e.id WHERE s.event_id IS NULL OR s.processed_at<? OR COALESCE(e.analyzed_at,e.first_seen_at)>s.event_at OR (s.processed_at<? AND EXISTS(SELECT 1 FROM rs_shadow_tracks t WHERE t.event_id=e.id AND t.state='waiting')) ORDER BY e.first_seen_at DESC LIMIT 200").bind(await getState(env,'shadow_policy_registered_at')||'',iso(at(now)-60000)).all()).results)await enrollShadow(env,parse(r),now);
  const rows=(await env.DB.prepare("SELECT payload FROM rs_shadow_tracks WHERE state IN ('armed','partial_entry','open','exit_pending') ORDER BY CASE WHEN state='exit_pending' THEN 0 ELSE 1 END,due_at LIMIT 250").all()).results.map(parse),quotes=new Map(),actionCache=new Map();
  for(const t of rows){
    if(!t.ticker||at(t.due_at)>at(now))continue;
    const policy=SHADOW_POLICIES.find(p=>p.id===t.policy_id);
    if(!t.remaining_shares&&at(now)>at(t.due_at)+policy.entry_window_seconds*1000){await processShadowTrack(env,t,null,rows,now);continue;}
    const quoteKey=t.ticker+':'+(policy.quote_feed||'consolidated');
    if(!quotes.has(quoteKey)&&quotes.size>=24)continue;
    let q=quotes.get(quoteKey);
    if(!quotes.has(quoteKey)){
      try{q=await env.market.quote(t.ticker,policy);q.id=await digest(q.provider+':'+q.ticker+':'+q.quote_at+':'+JSON.stringify(q.raw));await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_quotes VALUES(?,?,?,?,?)').bind(q.id,q.ticker,q.quote_at||now,q.observed_at,JSON.stringify(q)).run();}catch(e){q=null;await putState(env,'shadow_quote_error',{at:now,message:e.message},now);}quotes.set(quoteKey,q);
    }
    let actions={records:[],complete:false};
    if(t.remaining_shares&&t.effective_date<=etDay(now)){
      if(!actionCache.has(t.ticker)){try{actionCache.set(t.ticker,await env.market.actions(t.ticker,etDay(t.entry_at)));}catch{actionCache.set(t.ticker,actions);}}
      actions=actionCache.get(t.ticker);
    }
    await processShadowTrack(env,t,q,rows,options.now?now:stamp(),actions);
  }
  await summarizeShadow(env,now);
}
export async function summarizeShadow(env,now=stamp()){
  const tracks=(await env.DB.prepare('SELECT payload FROM rs_shadow_tracks').all()).results.map(parse),policies=[];
  for(const p of SHADOW_POLICIES){const rows=tracks.filter(t=>t.policy_id===p.id),entered=rows.filter(t=>t.entry_shares>0),closed=rows.filter(t=>t.state==='closed'),unresolved=entered.filter(t=>t.action_unresolved||!finite(t.net_pnl));
    const marked=entered.filter(t=>finite(t.net_pnl)),net=marked.reduce((a,t)=>a+t.net_pnl,0),stale=entered.filter(t=>t.remaining_shares>0&&(t.mark_stale||at(now)-at(t.mark_at)>p.quote_age_seconds*1000)),summary={id:p.id,label:p.label,primary:!!p.primary,control:!!p.control,indicative:!!p.indicative,quote_coverage:p.quote_coverage||'consolidated',enrolled:rows.length,armed:rows.filter(t=>t.state==='armed').length,entered:entered.length,issuers:new Set(entered.map(t=>t.cik)).size,open:entered.filter(t=>t.remaining_shares>0).length,closed:closed.length,missed:rows.filter(t=>t.state==='missed').length,rejected:rows.filter(t=>t.state==='rejected').length,waiting:rows.filter(t=>t.state==='waiting').length,retrospective:rows.filter(t=>t.state==='retrospective').length,known_net_pnl:marked.length?net:null,unresolved_marks:unresolved.length,stale_marks:stale.length,closed_net_pnl:closed.length?closed.reduce((n,t)=>n+t.net_pnl,0):null,win_rate:closed.length?closed.filter(t=>t.net_pnl>0).length/closed.length:null,borrow_cost:entered.reduce((n,t)=>n+t.borrow_cost,0),commissions:entered.reduce((n,t)=>n+t.commissions,0),broker_verified_fills:0};policies.push(summary);
    if(entered.length){const point={day:etDay(now),policy_id:p.id,known_net_pnl:marked.length?net:null,unresolved_marks:unresolved.length,stale_marks:stale.length,open:summary.open,closed:summary.closed};await env.DB.prepare('INSERT INTO rs_shadow_daily VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').bind(p.id+':'+point.day,p.id,point.day,JSON.stringify(point)).run();}
  }
  const latencies=tracks.filter(t=>t.policy_id==='rs_immediate.v1'&&t.signal_at).map(t=>(at(t.signal_at)-at(t.first_seen_at))/1000).filter(finite).sort((a,b)=>a-b);
  const summary={version:SHADOW_VERSION,research_only:true,authority:'none',generated_at:now,started_at:await getState(env,'shadow_started_at'),policies,observed_events:new Set(tracks.map(t=>t.event_id)).size,median_analysis_seconds:latencies.length?latencies[Math.floor(latencies.length/2)]:null,p95_analysis_seconds:latencies.length?latencies[Math.min(latencies.length-1,Math.floor(latencies.length*.95))]:null,active_policy_id:env.market?.activePolicy||'rs_immediate.v1',market_data:env.market?.health||{status:'not_configured'},public_borrow:await getState(env,'shadow_borrow_health'),quote_error:await getState(env,'shadow_quote_error'),execution_ready:false,limitations:['Databento Mini is a selected-venue indicative BBO, not SIP NBBO; its portfolios and quote coverage are separate from the original full-market policies.','Quotes bound displayed-size simulations, not queue position, trade/halt verification or market impact. A new timestamp alone does not replenish consumed displayed size.','Borrow is assumed at 50% APR; costs use rounded collateral and at least one modeled calendar day. Regulatory, locate, dividend, cash-settlement and forced-buy-in fees are not fully observed or included.','Locates, short-sale status and margin remain unverified unless dated owner-supplied evidence exists.','Open liabilities, stale marks and unresolved corporate actions remain in the ledger.','Future-session calendar covers scheduled NYSE sessions through 2028; unexpected closures require calendar correction.']};
  await putState(env,'shadow_summary',summary,now);return summary;
}
