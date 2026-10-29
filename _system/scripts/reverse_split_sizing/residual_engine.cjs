'use strict';
// Isolated extension of the frozen repeat-split engine. Source hash is in the manifest.
// Diagnostic extension: tiny positions below minimumNameExposure do not consume name slots.
// Every residual liability, margin requirement and carry charge is still retained.
const A=require('../short_framework/adapters.cjs');
const B=require('../reverse_split_repeat_study.cjs');
const S=require('../third_plus_signal/statistics.cjs');
const {sum,mean,quant,grouped:groups}=S;
const DAY=86400000;
const enrichSummary=B.enrichSummary;
const CASES={
  ideal:{execution:0,apr:0,fees:false},
  friction_only:{execution:0,apr:.5,fees:true},
  lower_cost:{execution:.01,apr:.2,fees:true},
  base:{execution:.0172,apr:.5,fees:true},
  depth_base:{execution:null,apr:.5,fees:true},
  stress:{execution:.0425,apr:1.5,fees:true},
};
const SEC=[['2020-02-18',22.1],['2021-02-25',5.1],['2022-05-14',22.9],['2023-02-27',8],['2024-05-22',27.8],['2025-05-14',0],['2026-04-04',20.6]];
function fee(q,p,day,sell,settle=day){
  const value=q*p,comm=Math.min(Math.max(.005*q,1),.01*value),allowance=q*.000003;
  let cost=comm+allowance;
  if(sell){const sec=SEC.filter(([d])=>d<=settle).at(-1)?.[1]??22.1;
    const [taf,cap]=day>='2026-10-01'&&day<='2026-12-31'?[0,0]:day>='2026-01-01'?[.000195,9.79]:day>='2024-01-01'?[.000166,8.3]:day>='2023-01-01'?[.000145,7.27]:day>='2022-01-01'?[.000130,6.49]:[.000119,5.95];
    cost+=value*sec/1e6+Math.min(q*taf,cap);}
  return Math.ceil(cost*100-1e-10)/100;
}
function execution(c,n){return c.execution===null?Math.min(.8,.0172+.0423*Math.sqrt(n/25000)):c.execution;}
const collateral=(q,p)=>Math.abs(q)*Math.ceil(1.02*p);
const margin=(q,p)=>Math.abs(q)*Math.max(p,p<5?Math.max(2.5,p):Math.max(5,.3*p));
function replay(ctx, opts){
  const {prices,auction,factor,settlement}=ctx,c=CASES[opts.cost],cap=opts.cap??null,h=opts.horizon;
  const filter=r=>opts.ordinal==='provider'?r.provider_ordinal>=3:opts.ordinal==='all'?true:r.ordinal>=3;
  const cutoff=prices.days.length-(opts.maturitySessions||Math.max(20,h));
  if(!c||!Number.isInteger(h)||h<1||h>60||cap!==null&&(!(cap>0)||cap>1)||opts.nav!==undefined&&(!(opts.nav>0)||!Number.isFinite(opts.nav)))throw new Error('Invalid replay options');
  const universe=ctx.candidates.filter(filter).filter(r=>opts.financial==='all'||opts.financial==='scored'&&r.scored||opts.financial==='score60'&&r.scored&&r.score>=60);
  const funnel={selected:universe.length,common_maturity_excluded:0,missing_entry:0,missing_liquidity:0,overlap:0,zero_capacity:0,entered:0,ssr_rejected:0,risk_capacity:0,verified_evidence_missing:0};
  const byDay=new Map();
  for(const r of universe){
    if(r.i===undefined||(r.maturity_index??r.i)>cutoff){funnel.common_maturity_excluded++;continue;}
    if(!r.entry_price||!prices.point(r.ticker,r.day)){funnel.missing_entry++;continue;}
    if(cap!==null&&!r.liquidity_complete){funnel.missing_liquidity++;continue;}
    const a=byDay.get(r.day)||[];a.push(r);byDay.set(r.day,a);
  }
  const positions=[],daily=[];let cash=0,peak=0,maxDD=0,previous=0;
  const allDays=prices.days,dayIndex=prices.index;
  let day=opts.startDate||allDays[0],peakExposure=0,peakMargin=0,peakNames=0,staleSessions=0,loanTail=0,riskBreachSessions=0;
  function applyCash(p,category,value){cash+=value;p[category]=(p[category]||0)+value;}
  function mark(p,ds){
    const f=factor(p.ticker,p.day,ds);
    if(f===null){p.action_conflict=true;return;}
    const old=p.factor;p.factor=f;
    p.mark*=f/old;p.open_mark=p.mark;
    if(opts.stopCloseFraction&&p.units>1e-9&&p.open_mark/p.factor>=p.entry_price*(1+opts.stopCloseFraction))p.stop_due=ds;
    if((Date.parse(ds)-Date.parse(p.last_mark))/DAY>7)p.identity_unresolved=true;
    if(p.identity_unresolved)return;
    const point=prices.point(p.ticker,ds),a=auction(p.ticker,ds);
    if(point){p.mark=a.close||point.close;p.last_mark=ds;if(p.units>1e-9)p.max_adverse_price_return=Math.max(p.max_adverse_price_return||0,point.high/p.factor/p.entry_price-1);}
  }
  for(;day<=prices.last;day=A.dateAfter(day)){
    const idx=dayIndex.get(day),session=idx!==undefined;
    // Mark and accrue loans on every calendar day, including weekends.
    for(const p of positions){
      if(p.units>1e-9||p.loan_units>1e-9)mark(p,day);
      if(p.loan_start===day)p.loan_units+=p.entry_units;
      for(const ret of p.pending_returns)if(ret.day===day)p.loan_units=Math.max(0,p.loan_units-ret.units);
      let billed=p.loan_units;
      if(day===p.loan_start&&billed<=1e-9&&p.borrow_days===0)billed=p.entry_units;
      if(billed>1e-9&&day>=p.loan_start){
        const charge=collateral(billed/p.factor,opts.causalCarry?p.open_mark:p.mark)*c.apr/360;
        applyCash(p,'borrow',-charge);p.borrow_days++;
      }
    }
    if(!session)continue;
    for(const r of (byDay.get(day)||[]).sort((a,b)=>a.id.localeCompare(b.id))){
      if(positions.some(p=>p.issuer===r.issuer&&p.units>1e-9)){funnel.overlap++;continue;}
      const point=prices.point(r.ticker,day),ssr=prices.ssrQuery.get(r.ticker,day);
      if(opts.evidence==='verified'){funnel.verified_evidence_missing++;continue;}
      if(opts.ssrMode==='strict'&&ssr?.restricted!==0){funnel.ssr_rejected++;continue;}
      const target=r.raw_target??opts.target??25000;let qty=Math.floor(target/r.entry_price);
      if(opts.nav){
        const open=positions.filter(p=>p.units>1e-9),exposure=sum(open.map(p=>p.units/p.factor*(p.open_mark||p.mark))),required=sum(open.map(p=>margin(p.units/p.factor,p.open_mark||p.mark)));
        const equity=opts.nav+cash-exposure,budget=Math.min(.0025*equity,Math.max(0,.01*equity-(opts.otherStressLoss||0)/2-exposure));
        if(open.filter(p=>p.units/p.factor*(p.open_mark||p.mark)>=(opts.minimumNameExposure||0)).length>=(opts.maximumNames||3)){funnel.risk_capacity++;continue;}
        qty=Math.min(qty,Math.floor(budget/r.entry_price),Math.floor(Math.max(0,.8*equity-required)/margin(1,r.entry_price)));
        if(qty<=0){funnel.risk_capacity++;continue;}
      }
      if(cap!==null){
        qty=Math.min(qty,Math.floor(cap*r.adv_shares),Math.floor(cap*point.volume*(ssr?.restricted===0?1:.5)));
      }
      if(qty<1){funnel.zero_capacity++;continue;}
      const spread=execution(c,qty*r.entry_price)/2,fill=r.entry_price*(1-spread);
      const p={...r,horizon:h,entry_units:qty,units:qty,loan_units:0,factor:1,mark:auction(r.ticker,day).close||point.close,last_mark:day,
        open_mark:r.entry_price,max_adverse_price_return:Math.max(0,point.high/r.entry_price-1),
        entry_reference_notional:qty*r.entry_price,entry_proceeds:qty*fill,entry_fill:fill,deadline:r.exit_index_override??idx+h-1,
        planned_exit:allDays[r.exit_index_override??idx+h-1],loan_start:settlement(day),pending_returns:[],borrow:0,borrow_days:0,fees:0,
        covers:0,execution_cost:qty*(r.entry_price-fill),stale_sessions:0,cover_children:0,filled_fraction:qty*r.entry_price/target};
      positions.push(p);cash+=p.entry_proceeds;
      if(c.fees)applyCash(p,'fees',-fee(qty,fill,day,true,p.loan_start));
      funnel.entered++;
    }
    // Close at the session close; for h1 the entry session is also the exit session.
    for(const p of positions){
      if(p.units<=1e-9||idx<p.deadline&&!p.stop_due)continue;
      if(p.identity_unresolved||p.action_conflict){p.overdue=true;continue;}
      const point=prices.point(p.ticker,day),close=p.stop_due?auction(p.ticker,day).open:auction(p.ticker,day).close;
      if(p.stop_due)p.exit_price_basis='next_session_open_after_prior_close_threshold';
      if(!point||!close){p.overdue=true;continue;}
      let q=p.units/p.factor;
      if(cap!==null)q=Math.min(Math.floor(q+1e-10),Math.floor(cap*point.volume));
      if(q<=0){p.overdue=true;continue;}
      const units=Math.min(p.units,q*p.factor),spread=execution(c,q*close)/2,fill=close*(1+spread);
      applyCash(p,'covers',-q*fill);
      if(c.fees)applyCash(p,'fees',-fee(q,fill,day,false));
      p.execution_cost+=q*(fill-close);p.units=Math.max(0,p.units-units);
      p.pending_returns.push({day:settlement(day),units,nominal:close});
      p.cover_children++;p.last_cover=day;
      if(p.units<=1e-9)p.closed=day;else p.overdue=true;
    }
    let liability=0,exposure=0,required=0,names=0,stale=0;
    for(const p of positions)if(p.units>1e-9){
      const v=p.units/p.factor*p.mark;liability+=v;exposure+=v;required+=margin(p.units/p.factor,p.mark);names++;
      if(p.last_mark!==day){p.stale_sessions++;stale+=v;}
    }
    const pnl=cash-liability;if(opts.nav&&(2*exposure+(opts.otherStressLoss||0)>.02*(opts.nav+pnl)||required>.8*(opts.nav+pnl)))riskBreachSessions++;peak=Math.max(peak,pnl);maxDD=Math.min(maxDD,pnl-peak);
    peakExposure=Math.max(peakExposure,exposure);peakMargin=Math.max(peakMargin,required);peakNames=Math.max(peakNames,names);staleSessions+=+(stale>0);
    daily.push({date:day,pnl,change:pnl-previous,liability,exposure,margin:required,names,stale});previous=pnl;
  }
  // Known modeled covers still owe carry until modeled loan return. Accrue that
  // finite tail at the last mark; unresolved open shorts are not called settled.
  for(const p of positions)if(p.units<=1e-9&&p.loan_units>1e-9){
    for(let d=A.dateAfter(prices.last);p.loan_units>1e-9;d=A.dateAfter(d)){
      for(const ret of p.pending_returns)if(ret.day===d)p.loan_units=Math.max(0,p.loan_units-ret.units);
      if(p.loan_units>1e-9){const z=collateral(p.loan_units/p.factor,p.mark)*c.apr/360;applyCash(p,'borrow',-z);loanTail+=z;}
      if((Date.parse(d)-Date.parse(prices.last))/DAY>10)throw new Error('Settlement tail did not resolve');
    }
  }
  if(daily.length){daily.at(-1).pnl-=loanTail;daily.at(-1).change-=loanTail;}
  for(const p of positions){
    p.open_liability=p.units/p.factor*p.mark;
    p.pnl=p.entry_proceeds+p.covers+p.fees+p.borrow-p.open_liability;
    p.net_return=p.pnl/p.entry_reference_notional;
    p.gross_pnl=p.pnl-p.fees-p.borrow+p.execution_cost;
  }
  const net=sum(positions.map(p=>p.pnl));
  if(Math.abs(net-(cash-sum(positions.map(p=>p.open_liability))))>.01)throw new Error('Cash/position accounting mismatch');
  let runningPeak=0,drawdown=0;for(const d of daily){runningPeak=Math.max(runningPeak,d.pnl);drawdown=Math.min(drawdown,d.pnl-runningPeak);}
  const active=positions.length?daily.filter(d=>d.date>=positions[0].day):[];
  const monthly=[...groups(active,d=>d.date.slice(0,7))].map(([month,ds])=>({month,pnl:sum(ds.map(d=>d.change)),entries:positions.filter(p=>p.day.startsWith(month)).length}));
  const yearly=[...groups(active,d=>d.date.slice(0,4))].map(([year,ds])=>({year,pnl:sum(ds.map(d=>d.change)),entries:positions.filter(p=>p.day.startsWith(year)).length}));
  const closed=positions.filter(p=>p.units<=1e-9),issuerPnls=[...groups(positions,p=>p.issuer)].map(([issuer,ps])=>({issuer,pnl:sum(ps.map(p=>p.pnl)),n:ps.length}));
  const first=positions[0]?.day,years=first?(Date.parse(prices.last)-Date.parse(first))/DAY/365.25:0;
  const returns=positions.map(p=>({...p,ret:p.net_return}));
  const summary={...opts,price_asof:prices.last,funnel,first_entry:first,last_entry:positions.at(-1)?.day,
    entered:positions.length,issuers:new Set(positions.map(p=>p.issuer)).size,closed:closed.length,
    net_pnl:net,gross_pnl:sum(positions.map(p=>p.gross_pnl)),borrow_cost:-sum(positions.map(p=>p.borrow)),
    commissions_and_fees:-sum(positions.map(p=>p.fees)),execution_cost:sum(positions.map(p=>p.execution_cost)),settlement_tail_accrual:loanTail,
    mean_position:mean(positions.map(p=>p.entry_reference_notional)),median_position:quant(positions.map(p=>p.entry_reference_notional),.5),
    mean_net_return:mean(positions.map(p=>p.net_return)),median_net_return:quant(positions.map(p=>p.net_return),.5),
    win_rate_closed:mean(closed.map(p=>+(p.pnl>0))),profit_factor_closed:sum(closed.filter(p=>p.pnl>0).map(p=>p.pnl))/-sum(closed.filter(p=>p.pnl<0).map(p=>p.pnl)),
    max_drawdown_dollars:drawdown,worst_day:Math.min(...daily.map(d=>d.change)),best_day:Math.max(...daily.map(d=>d.change)),
    worst_trade:positions.length?Math.min(...positions.map(p=>p.pnl)):null,best_trade:positions.length?Math.max(...positions.map(p=>p.pnl)):null,
    risk_breach_sessions:riskBreachSessions,peak_exposure:peakExposure,peak_margin:peakMargin,peak_open_names:peakNames,
    nav_for_200pct_squeeze_at_2pct_loss_budget:2*peakExposure/.02,
    open_positions:positions.filter(p=>p.units>1e-9).length,open_liability:sum(positions.map(p=>p.open_liability)),stale_sessions:staleSessions,
    overdue_positions:positions.filter(p=>p.overdue).length,fractional_residuals:positions.filter(p=>p.units>0&&p.units/p.factor<1).length,
    action_conflicts:positions.filter(p=>p.action_conflict).length,identity_unresolved:positions.filter(p=>p.identity_unresolved).length,
    mean_monthly_since_first_entry:mean(monthly.map(x=>x.pnl)),median_month:quant(monthly.map(x=>x.pnl),.5),
    positive_months:monthly.filter(x=>x.pnl>0).length,total_months:monthly.length,best_month:monthly.length?Math.max(...monthly.map(x=>x.pnl)):null,
    worst_month:monthly.length?Math.min(...monthly.map(x=>x.pnl)):null,annualized_pnl:years?net/years:null,trades_per_year:years?positions.length/years:null,
    pooled_net_return:sum(positions.map(p=>p.entry_reference_notional))?net/sum(positions.map(p=>p.entry_reference_notional)):null,
    issuer_bootstrap_mean_trade_return_95:opts.fastStats?null:clusterCI(returns),
    top5_issuer_profit_share:net?sum(issuerPnls.slice().sort((a,b)=>b.pnl-a.pnl).slice(0,5).map(x=>x.pnl))/net:null,
    pnl_without_best_issuer:net-(issuerPnls.length?Math.max(...issuerPnls.map(x=>x.pnl)):0),
    pnl_without_best5_issuers:net-sum(issuerPnls.slice().sort((a,b)=>b.pnl-a.pnl).slice(0,5).map(x=>x.pnl)),
    monthly,yearly,broker_verified_entries:0,borrow_availability_verified:false,account_capital_limit_applied:!!opts.nav,
    negative_marked_trades:positions.filter(p=>p.pnl<0).length};
  return enrichSummary({summary,daily,positions});
}

module.exports={replay,CASES,fee,margin,collateral};
