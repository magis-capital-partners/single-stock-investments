"""Repair forced patient-cover completions on the frozen historical entries.

This is an obligation audit, not a reoptimized portfolio or observed fills.
Unfilled entry dollars are not increased. Future covers remain volume-constrained
daily price proxies; missing/partial/fractional liabilities remain open.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
import math

import numpy as np

from .net_edge_v3 import settlement_day
from .profit_data import digest, read, write
from .profit_prices import CASES, PriceStore, collateral, execution_fraction, fee, margin, marginal_credit
from .profit_replay import metrics


def opening_obligation(row,arrays,target,case):
    from _system.scripts import short_patient_execution as old
    old_case=next(c for c in old.CASES if c['id']==case)
    legacy=old.replay_one(row,arrays,target,60,old_case,'flow',.05)
    if not legacy['filled']:return None
    ts=arrays['ts'];valid=arrays['valid'];closed=int(datetime.fromisoformat(row['closed']).timestamp())
    qty=legacy['filled']
    remaining=legacy['residual']
    cash=legacy['net_pnl']
    final_indices=np.flatnonzero(valid & (ts>=closed-15*60))
    final=int(final_indices[-1]) if len(final_indices) else int(np.flatnonzero(valid)[-1])
    mark=float(arrays['ask'][final])
    if remaining:
        forced_price=mark*(1+old_case['residual_cover'])
        child_fee=old.child_fees(np.array([remaining]),np.array([forced_price]),np.array([closed]),
                                 int(datetime.fromisoformat(row['opened']).timestamp()),False)
        # Undo only the unsupported buy, its child fee and its assigned impact.
        cash+=remaining*forced_price+child_fee+old_case['impact']*remaining*forced_price
    return {'id':row['key'],'issuer':row['issuer'],'ticker':row['ticker'],'entry_day':row['date'],
        'entry_units':qty,'units':float(remaining),'settled_units':0.,'factor':1.,'last_nominal':mark,
        'last_mark_day':row['date'],'pending':[],'cash':float(cash),'entry_notional':legacy['notional'],
        'legacy_pnl':legacy['net_pnl'],'initial_residual':remaining,'borrow':0.,'credit':0.,
        'future_cover_cash':0.,'future_fees':0.,'stale_sessions':0,'action_unresolved':False,
        'closed_on':row['date'] if not remaining else None,'last_cover_day':None,'identity_unresolved':False}


def liability_replay(openings,prices,case):
    incoming={}
    for p in openings:incoming.setdefault(p['entry_day'],[]).append(p)
    positions=[];cash=0.;daily=[];calendar=[];previous=10_000_000.;totals=Counter()
    start=min(incoming,default='2023-01-03');last=prices.days[-1]
    day=date.fromisoformat(start)
    while day<=date.fromisoformat(last):
        ds=day.isoformat();session=ds in prices.index
        for p in positions:
            if p['units']>0 and (day-date.fromisoformat(p['last_mark_day'])).days>7:p['identity_unresolved']=True
            factor=p['factor'] if p['identity_unresolved'] else prices.factor(p['ticker'],p['entry_day'],ds)
            old_factor=p['factor']
            if factor:p['factor']=factor
            else:p['action_unresolved']=True
            p['loan_mark']=p['last_nominal']*p['factor']/old_factor
            p['last_nominal']=p['loan_mark']
            for effective,units in p['pending']:
                if effective==ds:p['settled_units']+=units
        loan_collats=[collateral(max(0.,p['settled_units'])/p['factor'],p['loan_mark']) for p in positions]
        total=sum(loan_collats)
        credit=marginal_credit(total)/360
        cash+=credit;totals['credit']+=credit
        for p,c in zip(positions,loan_collats):
            borrow=c*CASES[case]['borrow_apr']/360;cash-=borrow;p['borrow']+=borrow;totals['borrow']+=borrow
            p['credit']+=credit*c/total if total else 0.
        for p in incoming.get(ds,[]):
            p['pending']=[(settlement_day(ds,prices.future_days).isoformat(),p['units'])]
            positions.append(p);cash+=p['cash']
        if session:
            for p in positions:
                if p['units']<=0 or ds<=p['entry_day']:continue
                if p['action_unresolved'] or p['identity_unresolved']:continue
                point=prices.point(p['ticker'],ds)
                if not point:p['stale_sessions']+=1;continue
                p['last_nominal']=point['c'];p['last_mark_day']=ds
                shares=min(math.floor(p['units']/p['factor']+1e-10),math.floor(.05*point['v']))
                if not shares:continue
                reference=point['ref'];fill=reference*(1+execution_fraction(shares*reference,case)/2)
                cost=fee(shares,fill,ds,False);amount=shares*fill+cost
                cash-=amount;p['future_cover_cash']+=shares*fill;p['future_fees']+=cost
                units=shares*p['factor'];p['units']=max(0.,p['units']-units)
                p['pending'].append((settlement_day(ds,prices.future_days).isoformat(),-units))
                p['last_cover_day']=ds
                if p['units']<=1e-8:p['units']=0.;p['closed_on']=ds
            liability=sum(p['units']/p['factor']*p['last_nominal'] for p in positions)
            required=sum(margin(p['units']/p['factor'],p['last_nominal']) for p in positions)
            coll=sum(collateral(p['units']/p['factor'],p['last_nominal']) for p in positions)
            stale=sum(p['units']/p['factor']*p['last_nominal'] for p in positions if p['units']>0 and p['last_mark_day']!=ds)
        else:
            liability=sum(p['units']/p['factor']*p['last_nominal'] for p in positions)
        value=10_000_000+cash-liability
        calendar.append((ds,value-previous));previous=value
        if session:daily.append({'date':ds,'pnl':value-10_000_000,'liability':liability,'margin':required,'collateral':coll,
                                 'exposure':liability,'stale_liability':stale,'open_issuers':sum(p['units']>0 for p in positions)})
        day+=timedelta(days=1)
    for p in positions:
        p['fees']=p['future_fees']
        p['marked_pnl']=p['cash']-p['future_cover_cash']-p['future_fees']-p['units']/p['factor']*p['last_nominal']-p['borrow']+p['credit']
    result=metrics(daily,calendar,positions,10_000_000)
    result.update({'case':case,'entered':len(positions),'unresolved_positions':sum(p['units']>0 for p in positions),
        'fractional_liabilities':sum(0<p['units']/p['factor']<1 for p in positions),
        'unresolved_security_identity_positions':sum(p['identity_unresolved'] for p in positions),
        'open_liability':daily[-1]['liability'] if daily else 0.,'borrow_cost':totals['borrow'],'proceeds_interest':totals['credit'],
        'stale_mark_sessions':sum(r['stale_liability']>0 for r in daily),
        'peak_margin':max((r['margin'] for r in daily),default=0.),'peak_collateral':max((r['collateral'] for r in daily),default=0.)})
    return result,daily,positions


def build_patient(args):
    source=args.source_root/'_system/data/reverse_splits/local/patient_execution/20261020_v1'
    prepared=read(source/'prepared.local.json')
    events=read(args.work/'effective_events.local.json')
    present={e['ticker'] for e in events}
    extras=[{'ticker':r['ticker'],'family':'price_adapter','features':{}} for r in prepared['rows'] if r['ticker'] not in present]
    prices=PriceStore(args.source_root,events+extras,first='2023-01-03')
    arrays=[]
    for row in prepared['rows']:
        path=Path(row['prepared']).resolve()
        if not path.is_relative_to(source.resolve()):raise ValueError('Prepared path outside patient cache')
        with np.load(path) as a:arrays.append({k:a[k].copy() for k in a.files})
    models=[]
    reference=Path(__file__).resolve().parents[2]/'data/reverse_splits/patient_execution_2026-10-20.json'
    legacy=read(reference)
    for target in [25000,50000]:
        for case in CASES:
            openings=[p for row,a in zip(prepared['rows'],arrays) if (p:=opening_obligation(row,a,target,case))]
            result,daily,positions=liability_replay(openings,prices,case)
            old=next(m for m in legacy['models'] if m['target']==target and m['case']==case and m['minutes']==60 and m['mode']=='flow' and m.get('participation',.05)==.05)
            result.update(target=target,legacy_annual_pnl=old['annual_pnl'],legacy_net_pnl=old['net_pnl'])
            write(args.work/'patient_repaired'/f'{target}_{case}.local.json',{'daily':daily,'positions':positions})
            models.append(result)
            print('Patient liability repair',target,case,'unresolved',result['unresolved_positions'],flush=True)
    write(args.work/'patient_liabilities.json',{'schema_version':'short_patient_liabilities.v1','models':models,
        'prepared_manifest_sha256':digest(source/'source_manifest.local.json'),
        'method':'Frozen one-hour/5%-flow entries and supported intraday covers retained. Unsupported buybacks, their fees and impact are undone. Residuals are marked as open shorts and subsequent daily covers use 5% recorded-volume capacity and cost sensitivities. Borrow/credit accrue on settled calendar days. Missing and fractional liabilities remain open. This obligation audit does not reapply entry admission or shared risk limits and is not observed execution.'})
