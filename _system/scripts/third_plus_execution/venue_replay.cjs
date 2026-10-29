'use strict';
// Venue-event execution sensitivity. National-price eligibility and borrow are conditional; never a verified NBBO replay.
const EPS=1e-8;
const REQUIRED=['identity','venue_book','eligible_trades','market_status','dated_price_grid','feed_continuity','receipt_clock','route_rules'];
const sum=xs=>xs.reduce((a,b)=>a+b,0);
function gaps(s,start,end){
 if(!s)return ['session_missing'];
 const out=REQUIRED.filter(k=>s.evidence?.[k]!==true);
 if(s.schema!=='third_plus_venue_session.v2')out.push('schema');
 if(s.synthetic===true)out.push('synthetic');
 if(!(s.capture_start_ms<=start&&s.capture_end_ms>=end))out.push('window');
 if(s.volume_scope!=='single_venue')out.push('volume_scope');
 if(!s.source_hashes?.length||s.source_hashes.some(h=>!/^[a-f0-9]{64}$/.test(h)))out.push('source_hashes');
 if(s.event_count===undefined?(!Array.isArray(s.events)||!s.events.length&&!s.empty_observed):(!s.event_count&&!s.empty_observed))out.push('events');
 return out;
}
function validate(s){
 for(const b of s.borrow||[])if(!b.confirmation||!Number.isFinite(b.available_ms)||!(b.expires_ms>b.available_ms)||!Number.isInteger(b.quantity)||b.quantity<0)throw Error('Invalid borrow evidence');
 if(s.locate_cost_usd!==undefined&&(!Number.isFinite(s.locate_cost_usd)||s.locate_cost_usd<0))throw Error('Invalid locate cost');
 let last=-Infinity;
 const allowed=new Set(['market','trade']);
 for(const e of s.events){
  if(!allowed.has(e.type)||!Number.isFinite(e.ts_ms)||!Number.isFinite(e.available_ms)||e.available_ms<e.ts_ms||e.available_ms<last)throw Error('Invalid event clock/type');
  last=e.available_ms;
  if(e.net_edge_per_share!==undefined&&(!Number.isFinite(e.net_edge_available_ms)||e.net_edge_available_ms>e.available_ms||!/^[a-f0-9]{64}$/.test(e.net_edge_source_sha256||'')))throw Error('Future or unproven edge forecast');
  if(e.type==='trade'&&(!e.trade_id||!e.venue||!(e.price>0)||!Number.isInteger(e.size)||e.size<1))throw Error('Invalid trade');
  if(e.type==='market'&&(!e.liquidity_id||!e.venue||!(e.tick>0)||!e.grid_id||!['clear','restricted','unknown'].includes(e.status)))throw Error('Invalid market state');
 }
}
function fee(q,p,date,sell){
 if(!q)return 0;
 const sec=[['2023-01-01',22.9],['2023-02-27',8],['2024-05-22',27.8],['2025-05-14',0],['2026-04-04',20.6]].filter(([d])=>d<=date).at(-1)?.[1]??22.9;
 const taf=date>='2026-10-01'&&date<='2026-12-31'?0:date>='2026-01-01'?.000195:date>='2024-01-01'?.000166:.000145;
 const cap=date>='2026-01-01'?9.79:date>='2024-01-01'?8.30:7.27;
 return Math.ceil((Math.min(Math.max(.005*q,1),.01*q*p)+q*.000003+(sell?q*p*sec/1e6+Math.min(q*taf,cap):0))*100-EPS)/100;
}
function above(bid,tick){return (Math.floor((bid+EPS*tick)/tick)+1)*tick;}
function permitted(m,policy){
 const p=above(m.bid,m.tick);
 return policy==='E1'?Math.max(m.ask,p):p<m.ask-EPS?p:Math.max(m.ask,p);
}
function replay(session,opt){
 const o={policy:'E2',side:'sell',participation:.1,latency_ms:500,child_usd:2000,cooldown_ms:5000,stale_ms:1000,rolling_ms:60000,hidden_queue_shares:0,borrow_mode:'conditional',...opt};
 const cacheKey=JSON.stringify([o.policy,o.side,o.participation,o.latency_ms,o.child_usd,o.start_ms,o.end_ms,o.quantity,o.target_usd,o.borrow_mode,o.hidden_queue_shares,o.edge_filter,o.net_edge_per_share,o.cooldown_ms,o.stale_ms,o.rolling_ms]);
 if(session?._results?.has(cacheKey))return session._results.get(cacheKey);
 if(!['E0','E1','E2','E3'].includes(o.policy)||!['sell','buy'].includes(o.side)||!(o.participation>0&&o.participation<=.1)||!(o.end_ms>o.start_ms)||!(o.latency_ms>0)||!(o.child_usd>0&&o.child_usd<=2000))throw Error('Invalid replay parameters');
 const missing=gaps(session,o.start_ms,o.end_ms);
 if(missing.length)return {status:'data_missing',gaps:missing,fills:[],journal:[],fees:0};
 validate(session);
 if(o.policy==='E3'&&(session.native_repricing?.verified!==true||session.native_repricing.mode!=='nasdaq_slide_down'||!(session.native_repricing.minimum_sell_price>0)||!Number.isFinite(session.native_repricing.available_ms)||session.native_repricing.available_ms>o.start_ms))return {status:'route_unverified',gaps:['native_repricing'],fills:[],journal:[],fees:0};
 const fills=[],journal=[],seen=new Set(),flow=[],depthUsed=new Map(),scheduled=[];
 let m=null,child=null,now=o.start_ms,i=0,totalFlow=0,filled=0,fees=0,lastAction=-Infinity,number=0,target=o.quantity??null,arrivalMid=null,reason=null,closed=false,borrowExceptions=0;
 let activeBorrow=o.borrow_mode==='conditional'?{quantity:Infinity,expires_ms:Infinity}:null;
 const borrowEvents=(session.borrow||[]).slice().sort((a,b)=>a.available_ms-b.available_ms);let bi=0;
 const log=(type,x={})=>journal.push({at_ms:now,type,...x});
 const healthy=()=>m&&m.feed_ok===true&&(session.continuity_mode==='complete_capture'||now-m.available_ms<=o.stale_ms)&&m.trading===true&&(o.side==='buy'||m.status!=='unknown')&&m.bid>0&&m.ask>=m.bid;
 const reserved=()=>child?child.remaining:0;
 const budget=()=>Math.max(0,Math.floor(o.participation*totalFlow+EPS)-filled-reserved());
 function rollingBudget(){
  while(flow.length&&flow[0].time<now-o.rolling_ms)flow.shift();
  const own=sum(fills.filter(f=>f.at_ms>=now-o.rolling_ms).map(f=>f.quantity));
  return Math.max(0,Math.floor(o.participation*sum(flow.map(f=>f.size))+EPS)-own-reserved());
 }
 const borrowOK=()=>o.side==='buy'||activeBorrow&&activeBorrow.expires_ms>now&&activeBorrow.quantity>=filled+reserved();
 function terminal(c,type){
  if(c.filled)fees+=fee(c.filled,c.proceeds/c.filled,session.date,o.side==='sell');
  log(type,{child_id:c.id,filled:c.filled,remaining:c.remaining});if(child===c)child=null;
 }
 function cancel(why){
  if(!child||child.state==='pending_cancel')return;
  child.state='pending_cancel';scheduled.push({at:now+o.latency_ms,kind:'cancel',id:child.id});
  log('cancel_requested',{child_id:child.id,reason:why,reserved:child.remaining});lastAction=now;
 }
 function fill(c,q,p,tradeId){
  if(!Number.isInteger(q)||q<0||q>c.remaining)throw Error('Invalid fill quantity');
  if(!q)return;
  if(o.side==='sell'&&o.borrow_mode==='verified'&&(!activeBorrow||now>=activeBorrow.expires_ms||filled+q>activeBorrow.quantity)){borrowExceptions++;log('borrow_exception',{child_id:c.id,quantity:q});}
  c.remaining-=q;c.filled+=q;c.proceeds+=q*p;filled+=q;
  fills.push({at_ms:now,quantity:q,price:p,child_id:c.id,trade_id:tradeId,side:o.side});
  log('fill',{child_id:c.id,quantity:q,price:p,pending_cancel:c.state==='pending_cancel'});
  if(c.remaining===0)terminal(c,'filled');
 }
 function buyFromBook(c){
  if(!c||o.side!=='buy'||!healthy()||m.ask>c.price+EPS)return;
  const key=m.venue+'|'+m.liquidity_id,used=depthUsed.get(key)||0;
  const q=Math.min(c.remaining,Math.max(0,Math.floor(m.ask_capacity??m.ask_size??0)-used));
  if(q){depthUsed.set(key,used+q);fill(c,q,m.ask,'book:'+key);}
 }
 function ack(c){
  if(!healthy()||!borrowOK()||Math.abs(c.price/m.tick-Math.round(c.price/m.tick))>1e-6||o.side==='sell'&&m.status==='restricted'&&c.price<=m.bid+EPS){terminal(c,'rejected');return;}
  c.initial_display_above_bid=session.route_rules?.initial_display_exception===true&&c.price>m.bid+EPS;c.displayed_ms=now;
  c.queue=Math.max(0,Number(m.book?.[String(c.price)]??(Math.abs(c.price-m.ask)<EPS?m.ask_size:0))||0)+o.hidden_queue_shares;
  if(c.state!=='pending_cancel')c.state='working';
  log('ack',{child_id:c.id,price:c.price,queue_ahead:c.queue,initial_display_above_bid:c.initial_display_above_bid});
  buyFromBook(c);
 }
 function decide(){
  if(now<o.start_ms||closed)return;
  if(now>=o.end_ms){closed=true;reason='deadline';cancel('deadline');return;}
  if(!healthy()||!borrowOK()){cancel(!healthy()?'invalid_market':'borrow_expired');return;}
  if(o.side==='sell'&&o.borrow_mode==='verified'&&activeBorrow.expires_ms<=now+o.latency_ms){cancel('borrow_expiring');return;}
  if(target===null){arrivalMid=(m.bid+m.ask)/2;target=Math.floor((o.target_usd||100000)/arrivalMid);log('parent_budget',{quantity:target,arrival_mid:arrivalMid});}
  if(o.side==='sell'&&o.policy==='E0'&&m.status==='restricted'){reason='ssr_skip';closed=true;cancel(reason);return;}
  const edge=o.side==='buy'?Number.MAX_VALUE:m.net_edge_per_share??o.net_edge_per_share;
  if(o.edge_filter!==false&&(!Number.isFinite(edge)||edge<=0)){reason='edge_unavailable_or_nonpositive';cancel(reason);return;}
  if(child){
   if(child.state==='working'){
    if(o.side==='sell'&&m.status==='restricted'&&child.price<=m.bid+EPS&&!child.initial_display_above_bid)cancel('price_test');
    else if(now-lastAction>=o.cooldown_ms){
     const desired=o.side==='buy'?m.ask:permitted(m,m.status==='clear'||o.policy==='E0'?'E1':o.policy);
     const change=o.side==='buy'?Math.abs(desired-child.price)>EPS:
       o.policy==='E3'&&m.status==='restricted'?false:desired<child.price-EPS||desired>child.price+EPS&&m.bid<child.price-EPS;
     if(change)cancel('discretionary_reprice');
    }
   }
   return;
  }
  if(filled>=target||now-lastAction<o.cooldown_ms)return;
  const rawPrice=o.side==='buy'?m.ask:permitted(m,m.status==='clear'||o.policy==='E0'?'E1':o.policy);
  const price=o.policy==='E3'&&m.status==='restricted'?Math.max(rawPrice,session.native_repricing.minimum_sell_price):rawPrice;
  const dollarShares=o.side==='buy'?Infinity:Math.max(0,Math.floor(((o.target_usd||100000)-sum(fills.map(f=>f.quantity*f.price)))/price+EPS));
  const qty=Math.min(target-filled,dollarShares,o.side==='buy'?Math.max(1,Math.floor(o.child_usd/price)):Math.floor(o.child_usd/price),budget(),rollingBudget(),o.side==='buy'?Infinity:Math.max(0,Math.floor(activeBorrow.quantity-filled)));
  if(qty<1)return;
  const expectedCost=fee(qty,price,session.date,o.side==='sell')+(o.locate_cost_per_child||0);
  if(o.edge_filter!==false&&edge*qty<=expectedCost){log('child_edge_rejected',{quantity:qty});return;}
  child={id:'child-'+(++number),price,remaining:qty,filled:0,proceeds:0,state:'pending_new',queue:Infinity,displayed_ms:Infinity,initial_display_above_bid:false};
  scheduled.push({at:now+o.latency_ms,kind:'ack',id:child.id});lastAction=now;log('submit',{child_id:child.id,quantity:qty,price});
 }
 function onMarket(e){
  if(m&&e.ts_ms<m.ts_ms){log('out_of_order_market_ignored');return;}
  m=e;
  if(o.side==='sell'&&o.policy==='E3'&&m.status==='restricted'&&healthy()&&child?.displayed_ms<=now){
   const price=Math.max(above(m.bid,m.tick),session.native_repricing.minimum_sell_price);
   if(price<child.price-EPS){child.price=price;child.displayed_ms=now;child.queue=Math.max(0,Number(m.book?.[String(price)]??(Math.abs(price-m.ask)<EPS?m.ask_size:0))||0)+o.hidden_queue_shares;child.initial_display_above_bid=session.route_rules?.initial_display_exception===true&&price>m.bid+EPS;log('native_reprice',{child_id:child.id,price,queue_ahead:child.queue});}
  }
  buyFromBook(child?.displayed_ms<=now?child:null);
 }
 function onTrade(e){
  const key=e.venue+'|'+e.trade_id;
  if(seen.has(key))return;seen.add(key);
  if(!e.regular||e.own_execution===true||e.ts_ms<o.start_ms)return;
  totalFlow+=e.size;flow.push({time:now,size:e.size});
  if(o.side!=='sell'||!child||child.displayed_ms>e.ts_ms||!healthy()||e.ts_ms<m.ts_ms||e.venue!==m.venue||e.aggressor!=='B'||e.price+EPS<child.price)return;
  if(m.status==='restricted'&&child.price<=m.bid+EPS&&!child.initial_display_above_bid)return;
  const ahead=Math.min(child.queue,e.size);child.queue-=ahead;
  fill(child,Math.min(child.remaining,e.size-ahead),child.price,key);
 }
 while(i<session.events.length&&session.events[i].available_ms<o.start_ms){const e=session.events[i++];if(e.type==='market')m=e;}
 while(bi<borrowEvents.length&&borrowEvents[bi].available_ms<=now){activeBorrow=borrowEvents[bi++];}
 decide();
 const final=o.end_ms+o.latency_ms*2+1;
 while(now<=final){
  const nextData=i<session.events.length?session.events[i].available_ms:Infinity;
  const nextBorrow=bi<borrowEvents.length?borrowEvents[bi].available_ms:Infinity;
  const nextAction=scheduled.length?Math.min(...scheduled.map(x=>x.at)):Infinity;
  const stale=session.continuity_mode!=='complete_capture'&&child&&child.state!=='pending_cancel'&&m?m.available_ms+o.stale_ms+1:Infinity;
  const cooldown=!closed&&healthy()&&now<lastAction+o.cooldown_ms?lastAction+o.cooldown_ms:Infinity;
  const expiry=child&&child.state!=='pending_cancel'&&o.borrow_mode==='verified'&&activeBorrow?Math.max(now,activeBorrow.expires_ms-o.latency_ms):Infinity;
  const next=Math.min(nextData,nextBorrow,nextAction,stale,cooldown,expiry,!closed?o.end_ms:Infinity);
  if(!Number.isFinite(next)||next>final)break;
  if(next<now)throw Error('Replay clock moved backwards');now=next;
  while(i<session.events.length&&session.events[i].available_ms===now){const e=session.events[i++];if(e.type==='market')onMarket(e);else onTrade(e);}
  while(bi<borrowEvents.length&&borrowEvents[bi].available_ms<=now){activeBorrow=borrowEvents[bi++];if(!activeBorrow.confirmation||!Number.isInteger(activeBorrow.quantity)||activeBorrow.quantity<0)throw Error('Invalid borrow evidence');}
  const due=scheduled.filter(x=>x.at<=now);for(const action of due){scheduled.splice(scheduled.indexOf(action),1);if(!child||child.id!==action.id)continue;if(action.kind==='cancel')terminal(child,'canceled');else ack(child);}
  decide();
  if(filled>(target??Infinity)||filled+reserved()>(target??Infinity)||filled+reserved()>Math.floor(o.participation*totalFlow+EPS))throw Error('Reservation invariant violated');
  if(closed&&!child)break;
 }
 if(child)throw Error('Pending child failed to reconcile');
 const proceeds=sum(fills.map(f=>f.quantity*f.price));
 const result={status:filled?'filled':reason==='ssr_skip'?'ssr_skip':'no_fill',reason,fills,journal:session._results?[]:journal,fees,target_shares:target,arrival_mid:arrivalMid,filled_shares:filled,notional:proceeds,mean_fill:filled?proceeds/filled:null,fill_fraction:target?filled/target:null,observed_external_volume:totalFlow,children:number,borrow_exceptions:borrowExceptions,borrow_mode:o.borrow_mode,locate_cost:session.locate_cost_usd||0};
 session?._results?.set(cacheKey,result);return result;
}
module.exports={replay,gaps,validate,permitted,above,fee,REQUIRED};
