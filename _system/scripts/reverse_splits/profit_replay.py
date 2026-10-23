"""Conditional daily short portfolios with persistent share and loan liabilities.

No historical locate or execution claim. Daily references/capacities are modeled;
missing paths remain marked obligations, including beyond the intended exit.
"""
from __future__ import annotations

import bisect
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from .profit_data import distribution, fingerprint, read, write
from .profit_prices import (CASES, PriceStore, collateral, execution_fraction, fee,
                            margin, marginal_credit, prepare_opportunities)
from .net_edge_v3 import settlement_day

SIGNALS = [
    ('financing_all', 'Financing disclosures'), ('financing_cash', 'Financing + cash pressure'),
    ('financing_supply', 'Financing + reconciled supply'), ('financing_both', 'Financing + cash + supply'),
    ('deficiency_all', 'First deficiency episodes'), ('deficiency_capital', 'Equity / market-value deficiency'),
    ('deficiency_cash', 'Capital deficiency + cash pressure'), ('split', 'Reverse-split disclosure baseline'),
]


def selected(event, signal):
    f = event.get('features', {})
    if f.get('review_excluded') is True:return False
    family = event['family']
    cash = event.get('financials', {}).get('cash_pressure') is True
    supply = f.get('terms_verified') is True and (f.get('quantified_saleable_supply') or 0) >= .1 * (f.get('shares_before') or math.inf)
    if signal.startswith('financing'):
        return family == 'financing' and f.get('first_state_disclosure',True) and event['event_status'] in {'terms_disclosed','amendment_terms_disclosed','primary_terms_reconciled'} and (
            signal == 'financing_all' or signal == 'financing_cash' and cash or signal == 'financing_supply' and supply or signal == 'financing_both' and cash and supply)
    if signal.startswith('deficiency'):
        capital = f.get('deficiency_type') in {'equity','mvls','mvphs'}
        return family == 'deficiency' and event['episode_start'] and (
            signal == 'deficiency_all' or signal == 'deficiency_capital' and capital or signal == 'deficiency_cash' and capital and cash)
    return signal == 'split' and family == 'split'


def forecast_labels(opportunities, prices, signal, horizon):
    labels=[]
    for o in opportunities:
        if not selected(o['event'],signal): continue
        r=prices.gross_label(o['event'],horizon)
        if r:
            r['available_index']=prices.index[r['exit_day']]+20
            r['cash_pressure']=o['event'].get('financials',{}).get('cash_pressure')
            labels.append(r)
    labels.sort(key=lambda r:(r['available_index'],r['event_id']))
    forecasts={}
    for o in opportunities:
        if o['entry_index'] is None or not selected(o['event'],signal):continue
        pool=[r for r in labels if r['available_index']<o['entry_index'] and r['issuer']!=o['event']['issuer']]
        if len({r['issuer'] for r in pool})<30:continue
        # Shrink the cash-pressure subgroup toward all prior other issuers.
        global_mean=float(np.mean([r['gross_return'] for r in pool]))
        local=[r['gross_return'] for r in pool if r['cash_pressure']==o['event'].get('financials',{}).get('cash_pressure')]
        estimate=(sum(local)+20*global_mean)/(len(local)+20)
        forecasts[o['event']['id']]={'gross':estimate,'training_issuers':len({r['issuer'] for r in pool}),
                                    'last_label':max(r['exit_day'] for r in pool)}
    return forecasts


def choose_budget(target, forecast, horizon, price, case):
    if forecast is None:return 0.
    choices=[q for q in [2500,5000,10000,25000,50000] if q<=target]
    c=CASES[case]
    scores=[]
    for amount in choices:
        qty=math.floor(amount/price)
        if qty<=0:continue
        carry=collateral(qty,price)*c['borrow_apr']*(horizon*7/5)/360
        costs=amount*execution_fraction(amount,c)+carry+2*fee(qty,price,'2026-10-22',False)
        # Half the forecast is reserved against estimation error; no 0.5% magic buffer.
        score=amount*forecast['gross']*.5-costs
        scores.append((score,amount))
    best=max(scores,default=(0,0))
    return best[1] if best[0]>0 else 0.


def model_id(signal,horizon,target,case,sizing,exit_policy):
    return f'{signal}__h{horizon}__{target}__{case}__{sizing}__{exit_policy}'


def replay(opportunities,prices,*,signal,horizon,target,case,sizing='fixed',exit_policy='time',forecasts=None,nav=10_000_000):
    c=CASES[case]
    candidates=defaultdict(list)
    funnel=Counter()
    for o in opportunities:
        if not selected(o['event'],signal):continue
        funnel['selected_discoveries']+=1
        if o['entry_index'] is None or o['coverage_status']!='ready_for_conditional_daily_replay':
            funnel['missing_price_or_liquidity']+=1;continue
        candidates[prices.days[o['entry_index']]].append(o)
    positions=[]; closed=[]; trade_records=[]
    cash=0.; previous_nav=nav
    daily=[]; calendar_pnl=[]; gap_before=0
    counters=Counter(); totals=Counter(); equity_peak=nav; worst_dd=0.
    peak_margin=peak_collateral=peak_exposure=peak_stress=0.
    margin_breaches=0; stale_days=0
    first=date.fromisoformat(prices.days[0]);last=date.fromisoformat(prices.days[-1])
    day=first
    while day<=last:
        ds=day.isoformat();is_session=ds in prices.index
        idx=prices.index.get(ds)
        # Corporate actions change current share units; never cash out a fractional remainder.
        for p in positions:
            if (day-date.fromisoformat(p['last_mark_day'])).days>7:p['identity_unresolved']=True
            previous_factor=p['factor']
            factor=p['factor'] if p['identity_unresolved'] else prices.factor(p['ticker'],p['entry_day'],ds)
            if factor is None:
                p['action_unresolved']=True
            else:p['factor']=factor
            p['loan_mark']=p['last_nominal']*p['factor']/previous_factor
            # Carry the mechanical split adjustment even if the new quote is absent.
            # Missing post-action prices must not erase the short liability.
            p['last_nominal']=p['loan_mark']
            point=None if p['identity_unresolved'] else prices.point(p['ticker'],ds)
            if point:p['last_nominal']=point['c'];p['last_mark_day']=ds
            for effective,units in p['pending']:
                if effective==ds:p['settled_units']+=units
        # Accrue on settled calendar days using the prior/current available mark.
        # This is a stated mark-path sensitivity, not reconstructed account charges.
        collats=[collateral(max(0.,p['settled_units'])/p['factor'],p['loan_mark']) for p in positions]
        total_coll=sum(collats)
        credit=marginal_credit(total_coll,nav=nav)/360
        totals['proceeds_interest']+=credit;cash+=credit
        for p,col in zip(positions,collats):
            loan=col*c['borrow_apr']/360
            p['borrow']+=loan;p['credit']+=credit*col/total_coll if total_coll else 0.
            totals['borrow_cost']+=loan;cash-=loan
        if is_session:
            # Covers precede new entries; order is deterministic and uses no future return.
            for p in positions:
                if p['units']<=0:continue
                if idx>=p['deadline']:p['exit_instruction']=p['exit_instruction'] or 'time'
                point=None if p['identity_unresolved'] else prices.point(p['ticker'],ds)
                if not point:
                    if idx>=p['deadline']:p['overdue']=True
                    p['stale_sessions']+=1;continue
                if p['action_unresolved']:continue
                factor=p['factor'];reference=point['ref']
                price_entry_basis=point['c']/factor
                bracket=False
                if exit_policy=='bracket' and idx>p['entry_index']:
                    if point['h']/factor>=p['reference_entry']*1.2:
                        p['exit_instruction']='stop';reference=max(point['o'],p['reference_entry']*1.2*factor);bracket=True
                    elif point['l']/factor<=p['reference_entry']*.8:
                        p['exit_instruction']='profit_target';reference=min(point['o'],p['reference_entry']*.8*factor);bracket=True
                if idx>=p['deadline']:p['exit_instruction']=p['exit_instruction'] or 'time'
                if exit_policy=='progressive' and idx>p['entry_index'] and idx>=p['deadline']-2:
                    desired=p['units']/max(1,p['deadline']-idx+1)
                elif p['exit_instruction']:desired=p['units']
                else:continue
                available=math.floor(.05*point['v'])
                actual=min(math.floor(p['units']/factor+1e-10),available,math.ceil(desired/factor))
                if actual>0:
                    units=actual*factor
                    spread=execution_fraction(actual*reference,c)/2
                    fill=reference*(1+spread)
                    cost=fee(actual,fill,ds,False)
                    cash-=actual*fill+cost
                    p['cover_cash']+=actual*fill;p['fees']+=cost
                    p['units']=max(0.,p['units']-units)
                    p['pending'].append((settlement_day(ds,prices.future_days).isoformat(),-units))
                    p['execution_cost']+=actual*(fill-reference)
                    totals['execution_cost']+=actual*(fill-reference);totals['commissions_and_fees']+=cost
                    p['last_cover_day']=ds;p['cover_children']+=1
                    if bracket:p['barrier_fill_assumed']=True
                if p['units']<=1e-8:
                    p['units']=0.;p['closed_on']=ds
                elif idx>=p['deadline']:
                    p['overdue']=True
            positions_to_keep=[]
            for p in positions:
                if p['units']<=0 and p['settled_units']<=1e-8 and all(x[0]<=ds for x in p['pending']):closed.append(p)
                else:positions_to_keep.append(p)
            positions=positions_to_keep
            for o in sorted(candidates.get(ds,[]),key=lambda o:(-(o['liquidity']['adv_dollars']),o['event']['id'])):
                e=o['event']
                if any(p['issuer']==e['issuer'] for p in positions):funnel['overlapping_issuer']+=1;continue
                point=prices.point(e['ticker'],ds);liq=o['liquidity'];budget=float(target)
                if sizing=='net_edge':
                    prediction=(forecasts or {}).get(e['id'])
                    budget=choose_budget(target,prediction,horizon,liq['last_price'],case)
                    if budget<=0:funnel['no_prior_net_edge']+=1;continue
                restricted=prices.ssr.get((e['ticker'],ds),True)
                budget=min(budget,.05*liq['adv_dollars'])
                reference=point['ref']
                capacity=math.floor(.05*point['v']*(c['ssr_capture'] if restricted else 1))
                current_exposure=sum(p['units']/p['factor']*p['last_nominal'] for p in positions)
                # A 2% NAV reserve for a +200% rise; exposure risk is recalculated daily.
                budget=min(budget,max(0.,.02*nav/2-current_exposure))
                shares=min(math.floor(budget/reference),capacity)
                if shares<=0:funnel['no_fill_or_risk_capacity']+=1;continue
                mark_margin=sum(margin(p['units']/p['factor'],p['last_nominal']) for p in positions)
                max_shares=math.floor(max(0.,.8*nav-mark_margin)/margin(1,reference))
                shares=min(shares,max_shares)
                if shares<=0:funnel['margin_capacity']+=1;continue
                frac=execution_fraction(shares*reference,c)
                fill=reference*(1-frac/2)
                charge=settlement_day(ds,prices.future_days).isoformat()
                cost=fee(shares,fill,ds,True,charge)
                proceeds=shares*fill
                cash+=proceeds-cost
                p={'id':e['id'],'issuer':e['issuer'],'ticker':e['ticker'],'entry_day':ds,'entry_index':idx,
                    'deadline':idx+horizon-1,'reference_entry':reference,'entry_notional':proceeds,
                    'planned_exit_day':prices.future_days[idx+horizon-1],
                    'entry_units':shares,'units':float(shares),'settled_units':0.,'factor':1.,
                    'pending':[(charge,float(shares))],'last_nominal':point['c'],'last_mark_day':ds,
                    'borrow':0.,'credit':0.,'fees':cost,'cover_cash':0.,'execution_cost':shares*(reference-fill),
                    'exit_instruction':None,'overdue':False,'stale_sessions':0,'last_cover_day':None,
                    'cover_children':0,'closed_on':None,'action_unresolved':False,'identity_unresolved':False,'barrier_fill_assumed':False,
                    'ssr_assumed':(e['ticker'],ds) not in prices.ssr}
                positions.append(p);trade_records.append(p)
                funnel['entered']+=1
                totals['entry_notional']+=proceeds;totals['execution_cost']+=p['execution_cost'];totals['commissions_and_fees']+=cost
                counters['partial_entries']+=int(proceeds<.95*target)
                counters['ssr_unknown_entries']+=int(p['ssr_assumed'])
            exposure=sum(p['units']/p['factor']*p['last_nominal'] for p in positions)
            required=sum(margin(p['units']/p['factor'],p['last_nominal']) for p in positions)
            coll=sum(collateral(p['units']/p['factor'],p['last_nominal']) for p in positions)
            peak_exposure=max(peak_exposure,exposure);peak_margin=max(peak_margin,required);peak_collateral=max(peak_collateral,coll);peak_stress=max(peak_stress,2*exposure)
            if required>.8*nav or 2*exposure>.02*nav:
                margin_breaches+=1
                for p in positions:
                    if p['units']>0:p['exit_instruction']='shared_risk_instruction'
            stale=sum(p['units']/p['factor']*p['last_nominal'] for p in positions if p['units']>0 and p['last_mark_day']!=ds)
            stale_days+=int(stale>0)
        liability=sum(p['units']/p['factor']*p['last_nominal'] for p in positions)
        value=nav+cash-liability
        equity_peak=max(equity_peak,value);worst_dd=min(worst_dd,value-equity_peak)
        incremental=value-previous_nav;previous_nav=value
        calendar_pnl.append((ds,incremental))
        if is_session:
            daily.append({'date':ds,'pnl':value-nav,'liability':liability,'margin':required,'collateral':coll,
                          'exposure':exposure,'stale_liability':stale,'open_issuers':sum(p['units']>0 for p in positions)})
        day+=timedelta(days=1)
    for p in trade_records:
        p['marked_pnl']=p['entry_notional']-p['cover_cash']-p['units']/p['factor']*p['last_nominal']-p['fees']-p['borrow']+p['credit']
    result=metrics(daily,calendar_pnl,trade_records,nav)
    result.update({'id':model_id(signal,horizon,target,case,sizing,exit_policy),'signal':signal,'horizon':horizon,
        'target':target,'case':case,'sizing':sizing,'exit_policy':exit_policy,'funnel':dict(funnel),
        'totals':dict(totals),'counts':dict(counters),'peak_margin':peak_margin,'peak_collateral':peak_collateral,
        'peak_exposure':peak_exposure,'squeeze_loss_200':peak_stress,'risk_breach_sessions':margin_breaches,
        'stale_mark_sessions':stale_days,'open_liability':daily[-1]['liability'] if daily else 0.,
        'unresolved_positions':sum(p['units']>0 for p in positions),'observed_broker_fills':0,
        'modeled_closed':sum(p['units']<=0 for p in trade_records),'entered':len(trade_records),
        'overdue_cover_positions':sum(p['overdue'] for p in trade_records),
        'fractional_action_liabilities':sum(0<p['units']/p['factor']<1 for p in positions),
        'corporate_action_positions':sum(p['factor']!=1 for p in trade_records),
        'unresolved_corporate_action_positions':sum(p['action_unresolved'] for p in trade_records),
        'unresolved_security_identity_positions':sum(p['identity_unresolved'] for p in trade_records),
        'cover_completion_share':1-sum(p['units'] for p in positions)/sum((p['entry_units'] for p in trade_records),start=1e-30),
        'tail_stresses':{'additional_20pct_liability_loss':.2*(daily[-1]['liability'] if daily else 0.),
                         'additional_100pct_liability_loss':daily[-1]['liability'] if daily else 0.},
        'completeness':'conditional_daily_proxy_with_unresolved_liabilities' if any(p['units']>0 for p in positions) else 'conditional_daily_proxy',
    })
    return result,daily,trade_records


def metrics(daily,calendar_pnl,trades,nav):
    if not daily:raise ValueError('Missing valuation calendar')
    values=np.array([0.]+[r['pnl'] for r in daily],dtype=float)
    equity=nav+values
    increments=np.diff(values)
    returns=increments/equity[:-1]
    dd=equity-np.maximum.accumulate(equity)
    dd_pct=equity/np.maximum.accumulate(equity)-1
    years=(date.fromisoformat(daily[-1]['date'])-date.fromisoformat(daily[0]['date'])).days/365.25
    years=max(years,1/365.25)
    net=float(values[-1]);cagr=(equity[-1]/nav)**(1/years)-1 if np.min(equity)>0 else None
    maxdd=float(dd.min());sd=float(returns.std());negative=np.minimum(returns,0)
    downside=float(np.sqrt(np.mean(negative**2)))
    monthly={}
    for r in daily:monthly[r['date'][:7]]=r
    month_rows=[];last=0.
    for month,r in monthly.items():month_rows.append([month,r['pnl']-last,r['pnl'],r['margin'],r['collateral']]);last=r['pnl']
    trade_pnl=[p['marked_pnl'] for p in trades]
    closed_pnl=[p['marked_pnl'] for p in trades if p['units']<=0]
    issuer_pnl=defaultdict(float)
    for p in trades:issuer_pnl[p['issuer']]+=p['marked_pnl']
    loss=-sum(x for x in closed_pnl if x<0)
    underwater=longest=0
    for x in dd:
        underwater=underwater+1 if x<-.001 else 0;longest=max(longest,underwater)
    cut=float(np.quantile(increments,.05))
    return {'net_pnl':net,'annual_pnl':net/years,'cagr':cagr,'max_drawdown_dollars':maxdd,
        'max_drawdown':float(dd_pct.min()),'calmar':cagr/abs(float(dd_pct.min())) if cagr is not None and dd_pct.min()<0 else None,
        'sharpe':float(returns.mean()/sd*math.sqrt(252)) if sd else None,
        'sortino':float(returns.mean()/downside*math.sqrt(252)) if downside else None,
        'annual_volatility':sd*math.sqrt(252),'worst_day':float(increments.min()),'best_day':float(increments.max()),
        'expected_shortfall_95_dollars':float(increments[increments<=cut].mean()),
        'win_rate_closed':sum(x>0 for x in closed_pnl)/len(closed_pnl) if closed_pnl else None,
        'profit_factor_closed':sum(x for x in closed_pnl if x>0)/loss if loss>0 else None,
        'mean_position':float(np.mean([p['entry_notional'] for p in trades])) if trades else 0.,
        'median_position':float(np.median([p['entry_notional'] for p in trades])) if trades else 0.,
        'worst_marked_trade':min(trade_pnl,default=None),'worst_issuer':min(issuer_pnl.values(),default=None),
        'longest_drawdown_sessions':longest,'trades_per_year':len(trades)/years,
        'distinct_issuers':len(issuer_pnl),'annual_pnl_ex_best_issuer':(net-max(issuer_pnl.values(),default=0))/years,
        'monthly':month_rows,'losing_month_fraction':sum(r[1]<0 for r in month_rows)/len(month_rows),
        'monthly_distribution':distribution([r[1] for r in month_rows]),'closed_trade_distribution':distribution(closed_pnl),
        'liquidation_calendar_days':distribution([(date.fromisoformat(p['closed_on'])-date.fromisoformat(p['entry_day'])).days for p in trades if p.get('closed_on')]),
        'late_cover_calendar_days':distribution([max(0,(date.fromisoformat(p['closed_on'])-date.fromisoformat(p.get('planned_exit_day',p['closed_on']))).days) for p in trades if p.get('closed_on')]),
        'start':daily[0]['date'],'end':daily[-1]['date'],'years':years,
        'periods':[{'period':str(y),'pnl':sum(v for ds,v in calendar_pnl if ds.startswith(str(y)))} for y in range(2021,2027)]}


def monte_carlo(daily,*,trials=1000,years=5,seed=20261022):
    if not daily:return None
    pnl=np.diff([0.]+[r['pnl'] for r in daily])
    # Calendar blocks, rather than independent trades, retain within-block clustering.
    width=63;n=round(252*years);blocks=math.ceil(n/width)
    rng=np.random.default_rng(seed)
    starts=rng.integers(0,max(1,len(pnl)-width+1),size=(trials,blocks))
    indices=(starts[...,None]+np.arange(width))%len(pnl)
    paths=pnl[indices].reshape(trials,-1)[:,:n].cumsum(axis=1)
    high=np.maximum.accumulate(np.maximum(paths,0),axis=1)
    dds=(paths-high).min(axis=1)
    endings=paths[:,-1]
    quant=lambda v:{'p05':float(np.quantile(v,.05)),'p50':float(np.quantile(v,.5)),'p95':float(np.quantile(v,.95))}
    points=list(range(20,n,21))
    selected_indices=indices.reshape(trials,-1)[:,:n]
    margins=np.array([r['margin'] for r in daily])[selected_indices]
    collats=np.array([r['collateral'] for r in daily])[selected_indices]
    liabilities=np.array([r['liability'] for r in daily])[selected_indices]
    funding_breach=np.any(margins>.8*(10_000_000+paths),axis=1)
    return {'trials':trials,'years':years,'seed':seed,'block_sessions':width,
        'annual_net_dollars':quant(endings/years),'max_drawdown_dollars':quant(dds),
        'ending_pnl':quant(endings),'loss_probability':float((endings<0).mean()),
        'peak_margin':quant(margins.max(axis=1)),'peak_collateral':quant(collats.max(axis=1)),
        'funding_breach_probability':float(funding_breach.mean()),
        'ending_liability':quant(liabilities[:,-1]),
        'probability_annual_at_least_240k':float((endings/years>=240000).mean()),
        'fan':[[int(i+1),*np.quantile(paths[:,i],[.05,.5,.95]).astype(float).tolist()] for i in points],
        'limitations':'Conditional historical portfolio blocks only; preserves dependence within 63 sessions, not beyond. Does not validate modeled fills, parameter uncertainty or unobserved squeeze tails. Open liabilities retain the historical marked path; terminal gap/recall stresses are separate.'}


def build(args):
    from .profit_data import materialize_events
    code_hash=lambda:fingerprint({p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('profit_*.py')})
    code_at_start=code_hash()
    events=materialize_events(args.work,args.source_root)
    frozen=read(args.work/'protocol.json')
    prices=PriceStore(args.source_root,events,last=getattr(args,'price_through',None) or '2026-10-13',overlay=args.work/'prices_overlay.sqlite')
    opportunities=prepare_opportunities(events,prices,args.work)
    write(args.work/'coverage_counts.json',dict(Counter(o['coverage_status'] for o in opportunities)))
    models=[]
    for signal,label in SIGNALS:
        for horizon in frozen['protocol']['horizons']:
            forecasts=forecast_labels(opportunities,prices,signal,horizon)
            for target in frozen['protocol']['targets']:
                for case in CASES:
                    for sizing in frozen['protocol']['sizing']:
                        r,daily,trades=replay(opportunities,prices,signal=signal,horizon=horizon,target=target,case=case,sizing=sizing,forecasts=forecasts)
                        r['monte_carlo']=monte_carlo(daily)
                        write(args.work/'replays'/f"{r['id']}.local.json",{'daily':daily,'trades':trades})
                        models.append(r)
            print(f'Replayed {signal} / {horizon} sessions; {len(models)} comparisons',flush=True)
    # Small, predeclared exit comparisons; no optimizer searches additional brackets.
    for signal in ('financing_all','deficiency_all','split'):
        for target in frozen['protocol']['targets']:
            for case in CASES:
                for policy in ('bracket','progressive'):
                    r,daily,trades=replay(opportunities,prices,signal=signal,horizon=5,target=target,case=case,exit_policy=policy)
                    r['monte_carlo']=monte_carlo(daily)
                    write(args.work/'replays'/f"{r['id']}.local.json",{'daily':daily,'trades':trades})
                    models.append(r)
    if code_hash()!=code_at_start:raise ValueError('Research code changed during replay; rebuild before publishing')
    write(args.work/'models.json',{'schema_version':'short_profit_models.v1','models':models,'protocol_sha256':frozen['sha256'],
        'events_sha256':fingerprint(events),
        'code_sha256':code_at_start})
