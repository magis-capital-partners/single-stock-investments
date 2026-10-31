'use strict';
// Announcement accounting reuses the frozen fill engine; cover proxies cannot see the later closing price.
const E=require('./assumed_backtest.cjs'),Identity=require('./identity.cjs'),{fee}=require('./replay.cjs');
const {DEFAULTS,SCENARIOS,initialPrice,execute}=E,EPS=1e-8,DAY=86400000;
const next=d=>new Date(Date.parse(d+'T12:00:00Z')+DAY).toISOString().slice(0,10);
function coverPrice(ctx,c,day,session,mark){
 const close=ctx.sessionBounds?.get(day)?.close??E.clock(day,16,0),at=close-90*60000,ticker=Identity.resolve(c,day).ticker;
 const quote=(session?.quotes||[]).filter(x=>x[0]*1000<=at&&at-x[0]*1000<=1000&&x[1]>0&&x[2]>=x[1]).at(-1);
 if(quote)return {price:(quote[1]+quote[2])/2,basis:'precover_quote'};
 const bar=(session?.bars||[]).filter(x=>x[0]*1000+1000<=at).at(-1);if(bar)return {price:bar[4],basis:'completed_precover_bar'};
 const open=ctx.auction(ticker,day).open;if(open>0)return {price:open,basis:'known_official_open_proxy'};
 const days=ctx.prices.days.filter(d=>d<day).reverse();for(const prior of days){const p=ctx.auction(ticker,prior).close||ctx.prices.point(ticker,prior)?.close,f=ctx.factor(ticker,prior,day);if(p>0&&f>0)return {price:p*f,basis:'known_adjusted_prior_close_proxy'};}
 return {price:c.entry_price*(ctx.factor(ticker,c.day,day)||1)||5,basis:'entry_price_carried_forward_proxy'};
}
function knownHalt(session,date){if(session?.data_gaps?.some(g=>['symbol_capture_missing','venue_exit'].includes(g.kind)))return false;const end=E.window(session,date,'buy',60)[1],last=(session?.statuses||[]).filter(x=>x.available_ms<=end&&['Y','N'].includes(x.trading)).at(-1);return last?.trading==='N';}
function trade(ctx,sessions,c,options={}){
 const o={...DEFAULTS,...SCENARIOS.base,...options},days=ctx.prices.days,i=ctx.prices.index.get(c.day);
 if(i===undefined)return {id:c.id,issuer:c.issuer,day:c.day,status:'not_yet_eligible',daily:[],entry:null,close_day:null};
 const session=sessions.get(c.id),initial=initialPrice(ctx,c,session),adv=c.adv_shares>0?c.adv_shares:1000000/initial.price;
 const entry=execute(session,c.day,initial.price,adv,{...o,side:'sell'});
 const out={id:c.id,issuer:c.issuer,ticker:c.ticker,day:c.day,status:entry.status,entry,initial_basis:initial.basis,planned_exit:days[i+o.horizon-1]||null,close_day:null,daily:[],costs:{borrow:0,fees:entry.fees,locate:entry.filled_shares?Math.max(o.locate_min,entry.filled_shares*o.locate_per_share):0,impact:entry.notional*o.impact_bps/10000},proxy_marks:0,proxy_exit:false,residual_exit:false,split_proxy:0};out.costs.event_allowance=entry.notional*(o.event_allowance||0);out.costs.capital_repayment=0;
 if(!entry.filled_shares)return out;
 let factor=1,mark=entry.arrival_mid,units=entry.filled_shares,cash=entry.notional-out.costs.fees-out.costs.locate-out.costs.impact-out.costs.event_allowance,loan=0,previousPnl=0,lastPnl=0,entrySettlement=ctx.settlement(c.day);
 const deadline=i+o.horizon-1,final=deadline+o.exit_attempts-1;
 for(let d=c.day;d<=ctx.prices.last;d=next(d)){
  const idx=ctx.prices.index.get(d),active=units>EPS,security=Identity.resolve(c,d),f=Identity.factor(ctx,c,d);
  if(!(f>0))out.split_proxy++;
  const newFactor=f>0?f:factor;
  const unitChange=newFactor/factor;if(active&&unitChange>1&&(o.cash_return_days||[]).some(day=>Math.abs(Date.parse(day)-Date.parse(d))<=10*DAY)){const actual=(o.distribution_actions||[]).find(a=>a.day===d),capital=units/factor*(actual?.cash_per_old_share??mark*(1-1/unitChange));cash-=capital;out.costs.capital_repayment+=capital;}mark*=unitChange;factor=newFactor;
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
   const coverAnchor=coverPrice(ctx,c,d,coverSession,mark);
   const covers=unknown?null:execute(coverSession,d,coverAnchor.price,adv/factor,{...o,side:'buy',quantity});
   if(covers?.proxy){out.proxy_cover_price_bases??={};out.proxy_cover_price_bases[coverAnchor.basis]=(out.proxy_cover_price_bases[coverAnchor.basis]||0)+1;}
   let bought=covers?.filled_shares||0,cost=covers?.notional||0,charges=covers?.fees||0;
   if(covers?.proxy)out.proxy_exit=true;
   // Bound the grace period. This explicitly estimates missing settlement instead of a permanent zombie.
   if((unknown||idx>=final)&&!knownHalt(coverSession,d)){
    const remaining=Math.max(0,quantity-bought);
    if(remaining){const premium=unknown?o.missing_exit_premium:o.residual_premium,price=mark*(1+o.half_spread_bps/10000)*(1+premium);cost+=remaining*price;charges+=fee(remaining,price,d,false);bought+=remaining;out.proxy_exit||=unknown;out.residual_exit||=!unknown;}
   }
   if(bought){
    const matched=Math.min(units/factor,bought),surplus=bought-matched;
    cash-=cost+charges+cost*o.impact_bps/10000;out.costs.fees+=charges;out.costs.impact+=cost*o.impact_bps/10000;
    units=Math.max(0,units-matched*factor);
    // Paid whole-share overbuy is sold for a modeled bid; never silently discarded or free.
    if(surplus>EPS){const cleanupMid=Math.min(mark,cost/bought/(1+o.half_spread_bps/10000)),sale=surplus*cleanupMid*(1-o.half_spread_bps/10000),f=fee(surplus,sale/surplus,d,true);cash+=sale-f;out.costs.fees+=f;}
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
module.exports={trade,coverPrice,knownHalt};
