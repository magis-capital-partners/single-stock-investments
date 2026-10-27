'use strict';
// Explicit counterfactual execution. Estimates never enter the evidence archive.
const Identity=require('./identity.cjs'),{fee,above}=require('./replay.cjs');
const DAY=86400000,EPS=1e-8,sum=a=>a.reduce((s,x)=>s+x,0);
const next=d=>new Date(Date.parse(d+'T12:00:00Z')+DAY).toISOString().slice(0,10);
const SCENARIOS={
 base:{label:'Base assumptions',borrow_apr:.5,half_spread_bps:86,capture:.5,impact_bps:10,locate_per_share:.01,locate_min:5,residual_premium:.02,missing_exit_premium:.10},
 favorable:{label:'Lower costs / better fills',borrow_apr:.1,half_spread_bps:43,capture:.75,impact_bps:5,locate_per_share:0,locate_min:0,residual_premium:.005,missing_exit_premium:0},
 stress:{label:'Higher costs / weaker fills',borrow_apr:1.5,half_spread_bps:172,capture:.25,impact_bps:30,locate_per_share:.03,locate_min:15,residual_premium:.05,missing_exit_premium:.5}
};
const DEFAULTS={policy:'E2',minutes:60,participation:.1,target_usd:100000,horizon:20,maximum_names:3,nav:10000000,latency_ms:500,child_usd:2000,reprice_ms:5000,exit_attempts:3};
function clock(date,hour,minute){
 const fmt=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',timeZoneName:'shortOffset'}),z=fmt.formatToParts(new Date(date+'T12:00:00Z')).find(x=>x.type==='timeZoneName').value;
 const offset=Number(z.replace('GMT',''));return Date.parse(date+'T00:00:00Z')+((hour-offset)*60+minute)*60000;
}
function window(s,date,side,minutes){
 const open=s?.open_ms??clock(date,9,30),close=s?.close_ms??clock(date,16,0);
 return side==='sell'?[open+60000,Math.min(open+(1+minutes)*60000,close-15*60000)]:[close-90*60000,close-15*60000];
}
function proxyBars(start,end,price,adv){
 // Missing capture: flat intraday price and uniform *prior* ADV, not final-day volume.
 const bars=[];let old=0;const perSecond=Math.max(0,adv)/23400;
 for(let t=start-1000;t<end;t+=1000){const total=Math.floor((t-start+2000)/1000*perSecond),v=total-old;old=total;bars.push([t/1000,price,price,price,price,v]);}
 return bars;
}
function eligible(bar,limit,sell){
 const hi=bar[2],lo=bar[3];
 if(hi-lo<EPS)return sell?+(lo>=limit-EPS):+(hi<=limit+EPS);
 // Assumed uniform price-volume distribution, explicitly a scenario, not observed trades.
 return Math.max(0,Math.min(1,sell?(hi-limit)/(hi-lo):(limit-lo)/(hi-lo)));
}
function execute(session,date,initial,adv,options={}){
 const o={...DEFAULTS,...SCENARIOS.base,...options},sell=o.side!=='buy',[start,end]=window(session,date,sell?'sell':'buy',o.minutes);
 const sourceBars=session?.bars||[],sourceGap=!sourceBars.length||session?.data_gaps?.length>0;
 const bars=sourceGap?proxyBars(start,end,initial,adv):sourceBars,quotes=sourceGap?[]:session?.quotes||[];
 // A missing tape does not erase an observed halt on this security. Status for
 // an uncaptured successor or a departed venue does not describe its new market.
 const states=session?.data_gaps?.some(g=>['symbol_capture_missing','venue_exit'].includes(g))?[]:session?.statuses||[];
 let mid=initial,qi=0,si=0,quote=null,restricted=session?.opening_restricted!==0,trading=true,filled=0,notional=0,fees=0,child=null,lastAction=-Infinity,children=0,volume=0,rollingVolume=0,rollingFills=0,fi=0,vi=0,carry=0,observedQuotes=0,estimatedQuotes=0;
 const fills=[],flow=[];let target=o.quantity??null,arrival=null;
 function market(t){
  while(qi<quotes.length&&quotes[qi][0]*1000<=t)quote=quotes[qi++];
  while(si<states.length&&states[si].available_ms<=t){const s=states[si++];if(s.restricted==='Y'||s.restricted==='N')restricted=s.restricted==='Y';if(s.trading==='Y'||s.trading==='N')trading=s.trading==='Y';}
  if(quote&&t-quote[0]*1000<=1000&&quote[1]>0&&quote[2]>=quote[1]){observedQuotes++;return {bid:quote[1],ask:quote[2],mid:(quote[1]+quote[2])/2};}
  estimatedQuotes++;const spread=o.half_spread_bps/10000;return {bid:mid*(1-spread),ask:mid*(1+spread),mid};
 }
 function finish(){if(child?.filled)fees+=fee(child.filled,child.cash/child.filled,date,sell);child=null;carry=0;}
 function decide(t){
  if(t<start||t>=end)return;
  const m=market(t);
  if(target===null){arrival=m.mid;target=Math.floor(o.target_usd/arrival);}
  if(!trading){if(child&&!child.cancel_at)child.cancel_at=t+o.latency_ms;return;}
  if(sell&&o.policy==='E0'&&restricted)return;
  const limit=sell?(o.policy==='E0'?m.bid:o.policy==='E1'?m.ask:above(m.bid,m.bid>=1?.01:.0001)):m.ask;
  if(child){if(!child.cancel_at&&(sell&&restricted&&child.price<=m.bid+EPS||t-lastAction>=o.reprice_ms&&Math.abs(limit-child.price)>EPS))child.cancel_at=t+o.latency_ms;return;}
  if(t-lastAction<o.reprice_ms||filled>=target)return;
  while(vi<flow.length&&flow[vi][0]<t-60000)rollingVolume-=flow[vi++][1];
  while(fi<fills.length&&fills[fi].at_ms<t-60000)rollingFills-=fills[fi++].quantity;
  const budget=sell?Math.floor((o.target_usd-notional)/limit+EPS):Infinity;
  const q=Math.min(target-filled,Math.floor(o.participation*volume)-filled,Math.floor(o.participation*rollingVolume)-rollingFills,Math.max(1,Math.floor(o.child_usd/limit)),budget);
  if(q<1)return;
  child={price:limit,remaining:q,ack:t+o.latency_ms,cancel_at:null,filled:0,cash:0};children++;lastAction=t;carry=0;
 }
 let skipped=false;
 for(const bar of bars){
  const at=bar[0]*1000,done=at+1000;
  if(done<=start){mid=bar[4];continue;}if(at>=end)break;
  if(child?.cancel_at!==null&&child?.cancel_at<=at)finish();
  decide(Math.max(start,at));const m=market(at);
  if(sell&&o.policy==='E0'&&restricted){skipped=true;break;}
  if(trading){
   if(child&&child.ack<=at&&(!child.cancel_at||child.cancel_at>=done)&&(!sell||!restricted||child.price>m.bid+EPS)){
    carry+=o.participation*bar[5]*o.capture*eligible(bar,child.price,sell);
    const q=Math.min(child.remaining,Math.floor(carry+EPS));
    if(q>0){const price=child.price;fills.push({at_ms:done,quantity:q,price,limit_price:child.price});carry-=q;filled+=q;notional+=q*price;rollingFills+=q;child.remaining-=q;child.filled+=q;child.cash+=q*price;if(!child.remaining)finish();}
   }
   volume+=bar[5];rollingVolume+=bar[5];flow.push([done,bar[5]]);
  }
  if(filled+(child?.remaining||0)>Math.floor(volume*o.participation+EPS))throw Error('Assumed participation reservation exceeded');
  mid=bar[4];decide(done);
 }
 finish();
 return {status:filled?'filled':skipped?'ssr_skip':'no_fill',filled_shares:filled,notional,fees,children,fills,arrival_mid:arrival||initial,target_shares:target||0,source_basis:sourceGap?'prior_ADV_flat_price_proxy':'observed_venue_bars',quote_basis:observedQuotes?(estimatedQuotes?'sampled_and_estimated':'sampled'):'estimated',proxy:sourceGap,observedQuotes,estimatedQuotes};
}
function initialPrice(ctx,c,session){
 if(c.entry_price>0)return {price:c.entry_price,basis:'official_open'};
 const t=Identity.resolve(c,c.day).ticker,p=ctx.prices.point(t,c.day);if(p?.open>0)return {price:p.open,basis:'daily_open'};
 const before=(session?.bars||[]).filter(b=>b[0]*1000<window(session,c.day,'sell',60)[0]).at(-1);
 if(before)return {price:before[4],basis:'completed_prearrival_bar'};
 const history=ctx.prices.history?.(t);
 if(history){const prev=[...history.entries()].filter(([d,p])=>d<c.day&&p.close>0).sort((a,b)=>a[0].localeCompare(b[0])).at(-1);if(prev){const f=ctx.factor(t,prev[0],c.day);if(f>0)return {price:prev[1].close*f,basis:'split_adjusted_prior_close'};}}
 return {price:5,basis:'unpriced_security_5_dollar_proxy'};
}
function trade(ctx,sessions,c,options={}){
 const o={...DEFAULTS,...SCENARIOS.base,...options},days=ctx.prices.days,i=ctx.prices.index.get(c.day);
 if(i===undefined)return {id:c.id,issuer:c.issuer,day:c.day,status:'not_yet_eligible',daily:[],entry:null,close_day:null};
 const session=sessions.get(c.id),initial=initialPrice(ctx,c,session),adv=c.adv_shares>0?c.adv_shares:1000000/initial.price;
 const entry=execute(session,c.day,initial.price,adv,{...o,side:'sell'});
 const out={id:c.id,issuer:c.issuer,ticker:c.ticker,day:c.day,status:entry.status,entry,initial_basis:initial.basis,planned_exit:days[i+o.horizon-1]||null,close_day:null,daily:[],costs:{borrow:0,fees:entry.fees,locate:entry.filled_shares?Math.max(o.locate_min,entry.filled_shares*o.locate_per_share):0,impact:entry.notional*o.impact_bps/10000},proxy_marks:0,proxy_exit:false,residual_exit:false,split_proxy:0};
 if(!entry.filled_shares)return out;
 let factor=1,mark=entry.arrival_mid,units=entry.filled_shares,cash=entry.notional-out.costs.fees-out.costs.locate-out.costs.impact,loan=0,previousPnl=0,lastPnl=0,entrySettlement=ctx.settlement(c.day);
 const deadline=i+o.horizon-1,final=deadline+o.exit_attempts-1;
 for(let d=c.day;d<=ctx.prices.last;d=next(d)){
  const idx=ctx.prices.index.get(d),active=units>EPS,security=Identity.resolve(c,d),f=Identity.factor(ctx,c,d);
  if(!(f>0))out.split_proxy++;
  const newFactor=f>0?f:factor;
  mark*=newFactor/factor;factor=newFactor;
  // Settlement loan units are held in original-entry units and transformed on demand.
  if(d===entrySettlement)loan=entry.filled_shares;
  for(const r of out.returns||[])if(!r.applied&&r.day<=d){loan=Math.max(0,loan-r.units);r.applied=true;}
  // Current calendar day's settled loan uses the last known close, including weekends.
  if(loan>EPS){const charge=loan/factor*Math.ceil(1.02*mark)*o.borrow_apr/360;out.costs.borrow+=charge;cash-=charge;}
  const point=idx===undefined?null:ctx.prices.point(security.ticker,d),official=idx===undefined?null:ctx.auction(security.ticker,d).close;
  const observed=official>0?official:point?.close>0?point.close:null;
  if((active||loan>EPS)&&idx!==undefined){if(observed)mark=observed;else out.proxy_marks++;}
  let peakLiability=active?units/factor*Math.max(mark,point?.high||mark):0;
  if(active&&idx!==undefined&&idx>=deadline){
   const coverSession=sessions.get(c.id+'|'+d),quantity=Math.ceil(units/factor-EPS);
   // Missing daily/capture exit: assume access at the last nominal price plus adverse closeout premium.
   const unknown=!observed||security.venue!=='NASDAQ';
   const captured=coverSession?.bars?.length&&!coverSession.data_gaps?.length;
   const covers=unknown?null:execute(coverSession,d,captured?(point?.open||mark):mark,adv/factor,{...o,side:'buy',quantity});
   let bought=covers?.filled_shares||0,cost=covers?.notional||0,charges=covers?.fees||0;
   if(covers?.proxy)out.proxy_exit=true;
   // Bound the grace period. This explicitly estimates missing settlement instead of a permanent zombie.
   if(unknown||idx>=final){
    const remaining=Math.max(0,quantity-bought);
    if(remaining){const premium=unknown?o.missing_exit_premium:o.residual_premium,price=mark*(1+o.half_spread_bps/10000)*(1+premium);cost+=remaining*price;charges+=fee(remaining,price,d,false);bought+=remaining;out.proxy_exit||=unknown;out.residual_exit||=!unknown;}
   }
   if(bought){
    const matched=Math.min(units/factor,bought),surplus=bought-matched;
    cash-=cost+charges+cost*o.impact_bps/10000;out.costs.fees+=charges;out.costs.impact+=cost*o.impact_bps/10000;
    units=Math.max(0,units-matched*factor);
    // Paid whole-share overbuy is sold for a modeled bid; never silently discarded or free.
    if(surplus>EPS){const sale=surplus*mark*(1-o.half_spread_bps/10000),f=fee(surplus,sale/surplus,d,true);cash+=sale-f;out.costs.fees+=f;}
    // Borrow is returned at cover settlement; partial returns are scheduled individually below.
    const settled=ctx.settlement(d);out.returns??=[];out.returns.push({day:settled,units:matched*factor});
    if(units<EPS)out.close_day=d;
   }
  }
  const liability=units/factor*mark,pnl=cash-liability;
  if(idx!==undefined){out.daily.push({day:d,pnl,change:pnl-lastPnl,liability,margin:units/factor*Math.max(2*mark,2.5),peak_liability:peakLiability,open:units>EPS});lastPnl=pnl;}
  previousPnl=pnl;
  if(!active&&loan<EPS)break;
 }
 out.net_pnl=previousPnl;out.open_liability=out.daily.at(-1)?.liability||0;out.immature=deadline>=days.length;return out;
}
function portfolio(ctx,trades,options={}){
 const o={...DEFAULTS,...options},selected=trades.slice().sort((a,b)=>(a.day||'9999').localeCompare(b.day||'9999')||a.id.localeCompare(b.id)),accepted=[],decisions=[],reserved=new Map();
 for(const t of selected){
  if(!t.day||t.status==='not_yet_eligible'){decisions.push({id:t.id,status:'not_yet_eligible'});continue;}
  const open=accepted.filter(p=>p.entry?.filled_shares&&(!p.close_day||p.close_day>=t.day)),parents=reserved.get(t.day)||[];
  const occupied=new Set([...open.map(p=>p.issuer),...parents]);
  let status=occupied.has(t.issuer)?'issuer_open':occupied.size>=o.maximum_names?'name_limit':t.status;
  if(o.independent)status=t.status;
  decisions.push({id:t.id,status});
  if(['name_limit','issuer_open'].includes(status))continue;
  // E0 rejections occur immediately; other eventual no-fills still reserve their arrival slot.
  if(t.status!=='ssr_skip'){parents.push(t.issuer);reserved.set(t.day,parents);}
  accepted.push(t);
 }
 const changes=new Map(),liabilities=new Map(),worstHigh=new Map(),margins=new Map();
 for(const t of accepted)for(const x of t.daily){changes.set(x.day,(changes.get(x.day)||0)+x.change);liabilities.set(x.day,(liabilities.get(x.day)||0)+x.liability);worstHigh.set(x.day,(worstHigh.get(x.day)||0)+x.peak_liability);margins.set(x.day,(margins.get(x.day)||0)+(x.margin||0));}
 const monthly=new Map();let pnl=0,peak=0,dd=0,peakGross=0,peakHigh=0,peakConcurrent=0,peakMargin=0,marginBreachDays=0;
 for(const d of ctx.prices.days.filter(d=>d>=(o.first||ctx.prices.days[0]))){
  const change=changes.get(d)||0;pnl+=change;peak=Math.max(peak,pnl);dd=Math.min(dd,pnl-peak);monthly.set(d.slice(0,7),(monthly.get(d.slice(0,7))||0)+change);peakGross=Math.max(peakGross,liabilities.get(d)||0);peakHigh=Math.max(peakHigh,worstHigh.get(d)||0);peakMargin=Math.max(peakMargin,margins.get(d)||0);if((margins.get(d)||0)>o.nav+pnl)marginBreachDays++;
  peakConcurrent=Math.max(peakConcurrent,accepted.filter(t=>t.day<=d&&t.entry?.filled_shares&&(!t.close_day||t.close_day>=d)).length);
 }
 const positions=accepted.filter(t=>t.entry?.filled_shares),costs={};for(const k of ['borrow','fees','locate','impact'])costs[k]=sum(positions.map(t=>t.costs[k]));
 const byIssuer=new Map();for(const t of positions)byIssuer.set(t.issuer,(byIssuer.get(t.issuer)||0)+t.net_pnl);
 const winners=[...byIssuer.values()].sort((a,b)=>b-a);
 return {net_pnl:pnl,return_on_reference_nav:pnl/o.nav,max_drawdown_dollars:dd,entered:positions.length,attempted:accepted.length,selected:trades.length,closed:positions.filter(t=>t.close_day).length,open_positions:positions.filter(t=>!t.close_day).length,open_liability:sum(positions.map(t=>t.open_liability)),immature_positions:positions.filter(t=>t.immature).length,entry_dollars:sum(positions.map(t=>t.entry.notional)),mean_position:positions.length?sum(positions.map(t=>t.entry.notional))/positions.length:0,partial:positions.filter(t=>t.entry.filled_shares<t.entry.target_shares).length,no_fill:accepted.filter(t=>t.status==='no_fill').length,ssr_skipped:accepted.filter(t=>t.status==='ssr_skip').length,name_limit:decisions.filter(t=>t.status==='name_limit').length,issuer_open:decisions.filter(t=>t.status==='issuer_open').length,peak_gross:peakGross,peak_intraday_high_liability:peakHigh,peak_concurrent:peakConcurrent,modeled_margin_requirement:peakMargin,margin_breach_days:marginBreachDays,costs,gross_before_costs:pnl+sum(Object.values(costs)),proxy_entry:positions.filter(t=>t.entry.proxy).length,estimated_quote_entries:positions.filter(t=>t.entry.estimatedQuotes).length,proxy_exit:positions.filter(t=>t.proxy_exit).length,residual_exit:positions.filter(t=>t.residual_exit).length,proxy_mark_sessions:sum(positions.map(t=>t.proxy_marks)),unpriced_entries:positions.filter(t=>t.initial_basis==='unpriced_security_5_dollar_proxy').length,split_proxy_sessions:sum(positions.map(t=>t.split_proxy)),pnl_without_best_issuer:pnl-(winners[0]||0),pnl_without_best5_issuers:pnl-sum(winners.slice(0,5)),monthly:[...monthly],decisions};
}
module.exports={SCENARIOS,DEFAULTS,clock,window,proxyBars,eligible,execute,initialPrice,trade,portfolio};
