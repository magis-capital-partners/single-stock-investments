"""Conditional portfolio replay of the entire frozen reverse-split price sample.

Admissions use entry evidence only. Missing exits are estimated and counted,
never used to remove losing trades. CAGR and ratios use all exchange sessions,
including idle sessions, and the declared account equity rather than turnover.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

from .analysis import cluster_interval
from .capital_risk import margin, tail, stats
from .config import load_config
from .execution_research import sweep
from .expansion import digest
from .ledger import read_json, write_json
from .realism import rounded_collateral
from .portfolio_status import histories,at as status_at
from .universe_study import trading_calendar


@dataclass(frozen=True)
class Case:
    id: str
    cohort: str = 'all'
    rule: str = 'close'
    offset: int = 1
    fraction: float = .025
    dollars: float | None = None
    house: float = 1.
    extra_bps: float = 0.
    borrow_days: int = 0
    borrow_rate: float = .5
    quantile: float | None = None
    observed_entries_only: bool = False
    prior_capacity: bool = True
    current_rate_cap: float | None = None
    minimum_notional: float = 100.
    expected_cost_cap: float | None = None
    start: str | None = None
    end: str | None = None


def cases():
    out=[Case(cohort+'_'+rule,cohort=cohort,rule=rule)
         for cohort in ('all','eligible','fundamental')
         for rule in ('close','stop5','stop10','stop20','time15','time60')]
    for rule in ('close','stop10'):
        out.append(Case('entry30_'+rule,rule=rule,offset=30))
    for rule in ('close','stop10'):
        for dollars in (125,500,1250):out.append(Case('size'+str(dollars)+'_'+rule,rule=rule,dollars=dollars))
        for fraction in (.05,.10):out.append(Case('fraction'+str(fraction)+'_'+rule,rule=rule,fraction=fraction))
        for house in (.5,2.):out.append(Case('house'+str(house)+'_'+rule,rule=rule,house=house))
        for extra in (5,10,25):out.append(Case('extra'+str(extra)+'_'+rule,rule=rule,extra_bps=extra))
        for rate in (.1,.25,.5,1.,.55294892857):out.append(Case('borrow'+str(rate)+'_'+rule,rule=rule,borrow_days=1,borrow_rate=rate))
        for q in (.25,.5,.75,.9):out.append(Case('impute'+str(q)+'_'+rule,rule=rule,quantile=q))
        out.append(Case('observed_entry_'+rule,rule=rule,observed_entries_only=True))
        out.append(Case('current_cap50_'+rule,rule=rule,current_rate_cap=.5))
        out.append(Case('no_ADV_cap_'+rule,rule=rule,prior_capacity=False))
        for cohort in ('all','fundamental'):
            out.append(Case('cost1pct_'+cohort+'_'+rule,cohort=cohort,rule=rule,expected_cost_cap=.01))
        out.append(Case('recent2023_'+rule,rule=rule,start='2023-01-01'))
        out.append(Case('early2018_'+rule,rule=rule,end='2022-12-30'))
    out.extend(Case('expanded_'+rule,cohort='expanded',rule=rule) for rule in ('close','stop10'))
    return out


def commission(q,price):
    return min(max(1.,q*.005),q*price*.01)


def performance(daily, initial, start, end, rf=0.):
    """Calendar CAGR; daily Sharpe/Sortino; full-period and 36-month Calmar."""
    nav=np.array([initial]+[r['equity'] for r in daily],dtype=float)
    ret=np.divide(nav[1:]-nav[:-1],nav[:-1],out=np.zeros(len(nav)-1),where=nav[:-1]>0)
    years=(date.fromisoformat(end)-date.fromisoformat(start)).days/365.25
    bankrupt=bool(np.any(nav<=0))
    cagr=(nav[-1]/initial)**(1/years)-1 if years>0 and not bankrupt else None
    peaks=np.maximum.accumulate(nav);dd=nav/peaks-1
    mdd=float(dd.min());sd=float(np.std(ret,ddof=1)) if len(ret)>1 else 0.
    excess=ret-((1+rf)**(1/252)-1)
    downside=float(np.sqrt(np.mean(np.minimum(excess,0)**2))) if len(ret) else 0.
    # Newey-West/Bartlett long-run variance; no iid assertion.
    centered=excess-excess.mean() if len(excess) else excess
    variance=float(np.mean(centered**2)) if len(centered) else 0.
    lags=min(20,max(0,len(ret)-1))
    longvar=variance+sum(2*(1-k/(lags+1))*float(np.mean(centered[k:]*centered[:-k])) for k in range(1,lags+1))
    underwater=0;longest=0;longest_days=0;peak_at=date.fromisoformat(start)
    for d,draw in zip(daily,dd[1:]):
        day=date.fromisoformat(d['date'])
        if draw<0:
            underwater+=1;longest=max(longest,underwater);longest_days=max(longest_days,(day-peak_at).days)
        else:underwater=0;peak_at=day
    returns=np.array(ret)
    loss_tail={}
    for alpha in (.95,.99):
        k=max(1,math.ceil((100-int(alpha*100))*len(returns)/100))
        loss_tail['loss_var_'+str(int(alpha*100))]=max(0.,float(np.quantile(-returns,alpha))) if len(returns) else None
        loss_tail['loss_es_'+str(int(alpha*100))]=max(0.,float(-np.sort(returns)[:k].mean())) if len(returns) else None
    result={'start':start,'end':end,'initial_equity':initial,'ending_equity':float(nav[-1]),'net_pnl':float(nav[-1]-initial),
            'total_return':float(nav[-1]/initial-1),'cagr':float(cagr) if cagr is not None else None,
            'years':years,'sessions':len(ret),'annual_volatility':sd*math.sqrt(252),
            'sharpe_rf0':float(ret.mean()/sd*math.sqrt(252)) if sd else None,
            'sharpe_rf4pct':float((ret-((1.04)**(1/252)-1)).mean()/sd*math.sqrt(252)) if sd else None,
            'sharpe_hac_rf0':float(ret.mean()*math.sqrt(252/max(longvar,1e-30))) if longvar>0 else None,
            'sortino_rf0':float(excess.mean()/downside*math.sqrt(252)) if downside else None,
            'max_drawdown':mdd,'calmar_full_period':cagr/abs(mdd) if cagr is not None and mdd<0 else None,
            'max_underwater_sessions':longest,'max_underwater_calendar_days':longest_days,
            'current_drawdown':float(dd[-1]),'worst_day':float(ret.min()) if len(ret) else None,
            'best_day':float(ret.max()) if len(ret) else None,'active_sessions':sum(bool(d['trades']) for d in daily),
            'positive_sessions':int((ret>0).sum()),'negative_sessions':int((ret<0).sum()),
            'idle_sessions':sum(not d['trades'] for d in daily),'daily_tail':loss_tail,
            'ulcer_index':float(np.sqrt(np.mean(dd[1:]**2))),
            'omega_zero':float(np.maximum(ret,0).sum()/-np.minimum(ret,0).sum()) if np.minimum(ret,0).sum()<0 else None,
            'skew_daily':float(pd.Series(ret).skew()) if sd else None,
            'excess_kurtosis_daily':float(pd.Series(ret).kurt()) if sd else None,'bankrupt':bankrupt}
    end_date=date.fromisoformat(end)
    try:floor=end_date.replace(year=end_date.year-3)
    except ValueError:floor=end_date.replace(year=end_date.year-3,day=28)
    recent=[d for d in daily if d['date']>floor.isoformat()]
    previous=[d for d in daily if d['date']<=floor.isoformat()]
    if recent and previous:
        base=previous[-1]['equity'];curve=np.array([base]+[d['equity'] for d in recent]);rd=curve/np.maximum.accumulate(curve)-1
        length=(end_date-date.fromisoformat(previous[-1]['date'])).days/365.25
        recent_cagr=(curve[-1]/base)**(1/length)-1 if min(curve)>0 else None
        result.update(cagr_last36months=recent_cagr,max_drawdown_last36months=float(rd.min()),
                      calmar_last36months=recent_cagr/abs(rd.min()) if recent_cagr is not None and rd.min()<0 else None)
    else:result.update(cagr_last36months=None,max_drawdown_last36months=None,calmar_last36months=None)
    if bankrupt:
        for field in ('annual_volatility','sharpe_rf0','sharpe_rf4pct','sharpe_hac_rf0','sortino_rf0',
                      'calmar_full_period','calmar_last36months','cagr_last36months'):
            result[field]=None
    return result


def load_inputs(cfg,root):
    source=cfg.local_dir/'expansion'/'expansion_v2'/'runs'/'20261013T224003582762Z'
    quote_source=cfg.local_dir/'execution_research'/'20261013T224003582762Z__quotes_v1'
    frozen=read_json(source/'manifest.json',{})
    if digest(source/'prices.sqlite')!=frozen['prices_sha256']:
        raise ValueError('Frozen nominal-price snapshot changed')
    if digest(source/'current_borrow.jsonl')!=frozen['current_borrow_sha256']:
        raise ValueError('Frozen borrowing snapshot changed')
    rows=read_json(quote_source/'targets.local.json',[])
    added=read_json(root/'repair'/'targets.local.json',[])
    rows+=added
    events={};actions=defaultdict(list)
    for part in read_json(source/'event_outcomes.parts.json',{})['files']:
        p=source/part['path']
        if digest(p)!=part['sha256']:raise ValueError('Frozen event inputs changed')
        for line in p.read_text().splitlines():
            e=json.loads(line);events[e['event_id']]=e
            if e['verification'] in {'primary_schedule_matched','structured_corporate_action'}:
                actions[e.get('database_ticker',e['ticker'])].append((e['ex_date'],float(e['ratio'])))
    conn=sqlite3.connect((source/'prices.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    prior_calendar=trading_calendar('2018-03-01','2026-10-13')
    for r in rows:
        e=events[r['event_id']];r['ex_date']=e['ex_date'];r['ratio']=e['ratio']
        position=int(np.searchsorted(prior_calendar,r['date']))
        floor=prior_calendar[max(0,position-20)]
        prior=conn.execute('SELECT date,close,volume FROM prices_daily p JOIN price_provenance v USING(ticker,date) WHERE ticker=? AND date>=? AND date<? AND v.nominal=1 ORDER BY date DESC',(r['ticker'],floor,r['date'])).fetchall()
        volume=[];dollar=[];prices=[]
        for day,p,v in prior:
            if p is not None and v is not None and p>0 and v>=0:
                factor=math.prod(ratio for ex,ratio in set(actions[r['ticker']]) if day<ex<=r['date'])
                volume.append(v*factor);dollar.append(p*v);prices.append(p/factor)
        # Unknown-volume sessions contribute no verified capacity. This is a
        # conservative lower bound; it does not assert that they traded zero.
        r['prior_sessions']=len(volume);r['adv']=float(np.sum(volume)/20) if volume else None
        r['dollar_adv']=float(np.sum(dollar)/20) if dollar else None
        r['prior_volatility']=float(np.std(np.diff(np.log(prices)))) if len(prices)>2 else .1
    conn.close()
    by_year=defaultdict(Counter);reasons=Counter();by_exchange=defaultdict(Counter)
    for e in events.values():
        if e['verification'] not in {'primary_schedule_matched','structured_corporate_action'}:continue
        o=next(o for o in e['outcomes'] if o['cohort']=='ex_plus_1_h1')
        by_year[e['ex_date'][:4]]['verified_actions']+=1
        by_exchange[e.get('exchange_class') or 'unknown']['verified_actions']+=1
        by_exchange[e.get('exchange_class') or 'unknown']['priced_events' if o['status']=='observed_price_path' else 'unpriced_events']+=1
        by_year[e['ex_date'][:4]]['priced_events' if o['status']=='observed_price_path' else 'unpriced_events']+=1
        if o['status']!='observed_price_path':reasons[o.get('reason') or 'unavailable']+=1
    write_json(root/'history_audit.local.json',{'by_year':{k:dict(v) for k,v in sorted(by_year.items())},'unpriced_reasons':dict(reasons),
              'verified_actions':sum(v['verified_actions'] for v in by_year.values()),'by_exchange':{k:dict(v) for k,v in sorted(by_exchange.items())}})
    current={r['ticker']:r for r in (json.loads(line) for line in (source/'current_borrow.jsonl').read_text().splitlines())}
    books=read_json(root/'books.local.json',{});points=read_json(root/'points.local.json',{});index=read_json(root/'paths.local.json',{})
    minute=read_json(quote_source/'minute_paths.local.json',{})
    extra_books=read_json(root/'repair'/'books.local.json',{});extra_points=read_json(root/'repair'/'points.local.json',{});extra_index=read_json(root/'repair'/'paths.local.json',{})
    for r in added:
        key=r['key'];books[key]=extra_books[key];points[key]=extra_points[key]
        index[key]={**extra_index[key],'file':'repair/'+extra_index[key]['file']}
    minute.update(read_json(root/'repair'/'minute_paths.local.json',{}))
    return rows,books,points,index,minute,read_json(quote_source/'trading_status.local.json',{})['states'],current


class CostModel:
    """Nearest historical entry covariates; same issuer is always held out.

Past observations are preferred. Warmup fallback uses a retrospective issuer
holdout and is labeled. No full-day volume, high/low or future return is a feature.
"""
    def __init__(self,rows,books):
        self.records=[];self.cache={};self.validation=[];self.scale_cache={}
        for r in rows:
            for label,b in books.get(r['key'],{}).items():
                if not b:continue
                side='bid' if label.endswith(('/entry','/decision')) else 'ask'
                for dollars in (125,500,1250):
                    q=max(1,math.floor(dollars/b['mid']));fill=sweep(b,side,q)
                    if fill is None:continue
                    spread=(b['mid']-b['bid'] if side=='bid' else b['ask']-b['mid'])/b['mid']
                    depth=(b['bid']-fill if side=='bid' else fill-b['ask'])/b['mid']
                    self.records.append({'issuer':r['issuer'],'date':r['date'],'side':side,
                        'kind':'entry' if side=='bid' else label.split('/')[1],'offset':int(label.split('/')[0]),
                        'x':self.features(r,b['mid'],q*b['mid']),'spread':spread,'depth':max(0.,depth)})
        self.x=np.array([x['x'] for x in self.records])
        self.issuers=np.array([x['issuer'] for x in self.records]);self.dates=np.array([x['date'] for x in self.records]);self.sides=np.array([x['side'] for x in self.records])
        self.kinds=np.array([x['kind'] for x in self.records]);self.offsets=np.array([x['offset'] for x in self.records])
        self.scale=np.std(self.x,axis=0) if self.records else np.ones(7)
        self.scale=np.maximum(self.scale,.25)

    @staticmethod
    def features(r,price,dollars):
        venue=r.get('dataset','XNAS.ITCH')
        volume=r.get('dollar_adv');volatility=r.get('prior_volatility')
        return np.array([math.log(max(price,.0001)),math.log(max(1000 if volume is None else volume,1)),
                         math.log(max(dollars,1)),min(.1 if volatility is None else volatility,2),
                         date.fromisoformat(r['date']).toordinal()/365.25,float(venue=='XNAS.ITCH'),float(venue=='XASE.PILLAR')])

    def estimate(self,r,side,price,dollars,quantile=None,*,rule='close',offset=1):
        key=(r['key'],side,round(price,4),round(dollars/50)*50,quantile,rule,offset)
        if key in self.cache:return self.cache[key]
        kind='entry' if side=='bid' else rule
        eligible=(self.issuers!=r['issuer'])&(self.sides==side)&(self.kinds==kind)&(self.offsets==offset)
        ids=np.flatnonzero(eligible&(self.dates<r['date']))
        basis='past_issuer_holdout'
        if len(np.unique(self.issuers[ids]))<20:
            ids=np.flatnonzero(eligible);basis='retrospective_warmup_holdout'
        if not len(ids):raise ValueError('No empirical cost donors')
        x=self.features(r,price,dollars)
        scale_key=(side,kind,offset,r['date'],basis)
        if scale_key not in self.scale_cache:
            normalizer=(self.sides==side)&(self.kinds==kind)&(self.offsets==offset)
            if basis=='past_issuer_holdout':normalizer&=self.dates<r['date']
            self.scale_cache[scale_key]=np.maximum(np.std(self.x[normalizer],axis=0),.25)
        differences=(self.x[ids]-x)/self.scale_cache[scale_key]
        ranked=ids[np.argsort(np.einsum('ij,ij->i',differences,differences))]
        # One closest donor per issuer avoids treating repeated sampled windows
        # and sizes for the same company as independent calibration examples.
        pool=[];issuers=set()
        for i in ranked:
            donor=self.records[int(i)]
            if donor['issuer'] not in issuers:pool.append(donor);issuers.add(donor['issuer'])
            if len(pool)==40:break
        # Keep spread and depth paired rather than independently assigning favorable values.
        pool=sorted(pool,key=lambda p:p['spread']+p['depth'])
        if quantile is None:
            spread=float(np.mean([p['spread'] for p in pool]));depth=float(np.mean([p['depth'] for p in pool]))
        else:
            donor=pool[min(len(pool)-1,int(quantile*(len(pool)-1)))];spread=donor['spread'];depth=donor['depth']
        result={'spread':spread,'depth':depth,'basis':basis,'donors':len(pool)}
        self.cache[key]=result;return result

    def validate(self,rows,books):
        errors=[];past_errors=[];warmup=0
        for r in rows:
            b=books.get(r['key'],{}).get('1/entry')
            if not b:continue
            est=self.estimate(r,'bid',b['mid'],500)
            actual=(b['mid']-b['bid'])/b['mid']
            errors.append(est['spread']-actual);warmup+=est['basis'].startswith('retrospective')
            if est['basis']=='past_issuer_holdout':past_errors.append(est['spread']-actual)
        round_trips={}
        for rule in ('close','stop5','stop10','stop20','time15','time60'):
            measured=[];predicted=[];past=[];insufficient=0
            for r in rows:
                e=books.get(r['key'],{}).get('1/entry');x=books.get(r['key'],{}).get('1/'+rule)
                if not e or not x:continue
                q=max(1,math.floor(500/e['mid']));sell=sweep(e,'bid',q);cover=sweep(x,'ask',q)
                if sell is None or cover is None:insufficient+=1;continue
                ee=self.estimate(r,'bid',e['mid'],q*e['mid'],rule=rule)
                ex=self.estimate(r,'ask',e['mid'],q*e['mid'],rule=rule)
                actual=((e['mid']-sell)+(cover-x['mid']))/e['mid']
                forecast=ee['spread']+ee['depth']+ex['spread']+ex['depth']
                measured.append(actual);predicted.append(forecast)
                if ee['basis']==ex['basis']=='past_issuer_holdout':past.append(forecast-actual)
            diff=np.array(predicted)-measured
            round_trips[rule]={'events':len(measured),'insufficient_observed_depth':insufficient,
                'observed_mean_cost_rog':float(np.mean(measured)) if measured else None,
                'predicted_mean_cost_rog':float(np.mean(predicted)) if predicted else None,
                'cost_MAE_rog':float(np.mean(np.abs(diff))) if measured else None,
                'cost_bias_rog':float(np.mean(diff)) if measured else None,
                'past_only_events':len(past),'past_only_MAE_rog':float(np.mean(np.abs(past))) if past else None}
        return {'events':len(errors),'entry_half_spread_MAE':float(np.mean(np.abs(errors))) if errors else None,
                'entry_half_spread_bias':float(np.mean(errors)) if errors else None,
                'past_only_events':len(past_errors),'past_only_entry_half_spread_MAE':float(np.mean(np.abs(past_errors))) if past_errors else None,
                'warmup_retrospective_predictions':warmup,'donor_records':len(self.records),
                'round_trip_forecasts_by_exit_rule':round_trips,
                'validation_basis':'Other-issuer holdouts; $500 reference with whole shares. Round-trip forecasts use entry-price covariates for both sides. Measured comparisons require sufficient observed entry and exit depth and exclude commissions, borrow and timing returns; coverage is conditional.',
                'features':['entry price','prior dollar ADV','order notional','prior volatility','year','listing venue'],
                'method':'One closest observation per other issuer, up to 40 issuers; same entry offset and exit rule. Arithmetic mean paired spread/depth is the base; paired cost quantiles are sensitivities. Earlier dates and past-only feature scaling are preferred; retrospective issuer-holdout fallback during warmup.'}


def fill(r,book,side,q,mid,model,case):
    estimated=False;remainder=False;basis=None
    if book:
        mid=book['mid'];price=sweep(book,side,q)
        spread=(mid-book['bid'] if side=='bid' else book['ask']-mid)*q
        if price is not None:depth=abs(price-book[side])*q
        else:
            # Observed portion is priced at its displayed levels; estimate the remainder.
            qty=sum(size for _,size in book[side+'_levels']);known=sweep(book,side,qty)
            est=model.estimate(r,side,mid,q*mid,case.quantile,rule=case.rule,offset=case.offset)
            rest=q-qty;proxy=mid*(1+est['spread']+est['depth'] if side=='ask' else 1-est['spread']-est['depth'])
            last=book[side+'_levels'][-1][0]
            proxy=max(proxy,last) if side=='ask' else min(proxy,last)
            price=(qty*known+rest*proxy)/q
            depth=abs(price-book[side])*q;estimated=True;remainder=True;basis=est['basis']
    else:
        est=model.estimate(r,side,mid,q*mid,case.quantile,rule=case.rule,offset=case.offset);basis=est['basis'];estimated=True
        spread=q*mid*est['spread'];depth=q*mid*est['depth']
        price=mid*(1-est['spread']-est['depth'] if side=='bid' else 1+est['spread']+est['depth'])
    if price<=0:raise ValueError('Invalid modeled fill')
    extra=q*price*case.extra_bps/10000
    price=price*(1-case.extra_bps/10000 if side=='bid' else 1+case.extra_bps/10000)
    return {'price':price,'mid':mid,'spread':spread,'depth':depth,'extra':extra,'estimated':estimated,'remainder':remainder,'basis':basis}


def path_marks(root,r,index,minute,status=None):
    p=root/index[r['key']]['file']
    if digest(p)!=index[r['key']]['sha256']:raise ValueError('Quote path changed')
    with np.load(p) as store:
        arrays={key:store[key] for key in ('ts','bid','ask','bid_size','ask_size','venues')}
    mid=(arrays['bid']+arrays['ask'])/2
    fallback=np.full(len(mid),r['open']);last=r['open']
    observed_minutes=minute.get(r['key'],{})
    ends=np.array([pd.Timestamp(t).timestamp()+60 for t in observed_minutes.get('times',[])],dtype=float)
    closes=np.array(observed_minutes.get('close',[]),dtype=float);loc=np.searchsorted(ends,arrays['ts'],side='right')-1
    valid=loc>=0;fallback[valid]=closes[loc[valid]]
    arrays['mid']=np.where(np.isfinite(mid),mid,fallback)
    arrays['ask_mark']=np.where(np.isfinite(arrays['ask']),arrays['ask'],fallback)
    arrays['imputed_mark']=~np.isfinite(mid)
    status=status or {};arrays['status_history']=status
    st=status.get('is_trading',{});positions=np.searchsorted(st.get('ts',[]),arrays['ts'],side='right')-1
    values=np.array(st.get('value',[]))
    live=np.array([values[i] if i>=0 else '' for i in positions])
    arrays['tradable_quote']=np.isfinite(mid)&(live!='N')
    # A displayed quote during a known halt is not an executable cover.
    # Retain the last completed trade mark until a tradable quote returns.
    arrays['mid']=np.where(arrays['tradable_quote'],mid,fallback)
    arrays['ask_mark']=np.where(arrays['tradable_quote'],arrays['ask'],fallback)
    arrays['imputed_mark']=~arrays['tradable_quote']
    return arrays


def tradable_cost_books(rows,books,points,status):
    filtered={};omitted=0
    for r in rows:
        selected={}
        for label,book in books.get(r['key'],{}).items():
            offset,rule=label.split('/')
            point=points[r['key']][offset+'/entry' if rule=='decision' else label]
            stamp=point['decision_at' if rule=='decision' else 'fill_at']
            if book and status_at(status.get(r['key'],{}),'is_trading',pd.Timestamp(stamp).timestamp())=='N':
                selected[label]=None;omitted+=1
            else:selected[label]=book
        filtered[r['key']]=selected
    return filtered,omitted


def available_book(path,timestamp):
    i=int(np.searchsorted(path['ts'],timestamp,side='right')-1)
    if i<0 or 'bid' not in path or not np.isfinite(path['bid'][i]) or not np.isfinite(path['ask'][i]):return None
    if status_at(path.get('status_history',{}),'is_trading',timestamp)=='N':return None
    b,a=float(path['bid'][i]),float(path['ask'][i]);bs,az=int(path['bid_size'][i]),int(path['ask_size'][i])
    return {'bid':b,'ask':a,'mid':(b+a)/2,'bid_levels':[(b,bs)],'ask_levels':[(a,az)],'sampled':True}


def exits(r,case,points,path,book_hint=None):
    point=points[r['key']][str(case.offset)+'/'+case.rule]
    entry=points[r['key']][str(case.offset)+'/entry']
    at=pd.Timestamp(point['decision_at']).timestamp()
    if case.rule.startswith('stop'):
        threshold=int(case.rule[4:])/100;ref=entry['reference_mid'];after=pd.Timestamp(entry['fill_at']).timestamp()
        hits=np.flatnonzero((path['ts']>after)&(path['mid']>=ref*(1+threshold)))
        if len(hits):at=float(path['ts'][hits[0]])
        else:at=pd.Timestamp(points[r['key']][str(case.offset)+'/close']['decision_at']).timestamp()
    triggered=case.rule.startswith('stop') and at<pd.Timestamp(r['closed']).timestamp()-1
    actual=pd.Timestamp(point['decision_at']).timestamp()
    # A fallback trade mark can locate a trigger absent from the quote-derived requests.
    book_label=str(case.offset)+'/'+case.rule if abs(at-actual)<.0001 else None
    if book_label is None:book_hint=None
    intended=at+.1;idx=min(len(path['ts'])-1,max(0,int(np.searchsorted(path['ts'],intended,side='right')-1)))
    tradable=path.get('tradable_quote',np.ones(len(path['ts']),dtype=bool))
    blocked=status_at(path.get('status_history',{}),'is_trading',intended)=='N'
    if (not tradable[idx] and not book_hint) or blocked:
        valid=np.flatnonzero((path['ts']>=intended)&tradable)
        if len(valid):idx=int(valid[0]);at=float(path['ts'][idx]);book_label=None
    actual=at+.1
    missing=not tradable[idx] and not book_hint or status_at(path.get('status_history',{}),'is_trading',actual)=='N'
    return actual,float(path['mid'][idx]),book_label,triggered,max(0,actual-intended),bool(missing)


def replay(rows,books,points,paths,states,current,model,case,protocol,calendar):
    daily_rows=defaultdict(list)
    for r in rows:
        if not protocol['start']<=r['date']<=protocol['end']:continue
        if (case.cohort=='all' and 'primary' in r['cohorts']) or case.cohort=='expanded' or case.cohort in r['cohorts']:daily_rows[r['date']].append(r)
    nav=float(protocol['initial_equity']);daily=[];trades=[];skips=Counter();coverage=Counter()
    global_intraday_peak=nav;intraday_dd=0.;max_intraday_margin=0.;margin_breaches=0
    minimum_intraday_equity=nav;intraday_insolvencies=0
    for day in calendar:
        before=nav;daytrades=[];entry_margin=0.;used_issuers=set()
        candidates=sorted(daily_rows.get(day,[]),key=lambda r:(-(r['dollar_adv'] or 0),r['issuer'],r['key']))
        for r in candidates:
            hist=paths[r['key']].get('status_history',{})
            decision_at=pd.Timestamp(points[r['key']][str(case.offset)+'/entry']['decision_at']).timestamp()
            state=dict(states.get(r['key'],{}).get('open/'+str(case.offset),{}))
            for field in ('is_trading','is_short_sell_restricted'):
                known=status_at(hist,field,decision_at)
                if known is not None:state[field]=known
            if state.get('is_short_sell_restricted')=='Y':skips['observed_SSR']+=1;continue
            if state.get('is_trading')=='N':skips['observed_not_trading']+=1;continue
            execution_at=pd.Timestamp(points[r['key']][str(case.offset)+'/entry']['fill_at']).timestamp()
            if status_at(hist,'is_trading',execution_at)=='N':skips['not_trading_at_entry_execution']+=1;continue
            if status_at(hist,'is_short_sell_restricted',execution_at)=='Y':skips['SSR_at_entry_execution']+=1;continue
            if len(daytrades)>=protocol['maximum_names']:skips['maximum_names']+=1;continue
            if r['issuer'] in used_issuers:skips['issuer_already_open']+=1;continue
            if case.current_rate_cap is not None:
                b=current.get(r['ticker'],{})
                if not b.get('available_shares') or b.get('fee_annual_fraction') is None or b['fee_annual_fraction']>case.current_rate_cap:
                    skips['current_rate_missing_or_above_cap_retrospective']+=1;continue
            entrybook=books.get(r['key'],{}).get(str(case.offset)+'/entry')
            decisionbook=books.get(r['key'],{}).get(str(case.offset)+'/decision')
            if case.observed_entries_only and not decisionbook:skips['missing_entry_book']+=1;continue
            mid=decisionbook['mid'] if decisionbook else points[r['key']][str(case.offset)+'/entry']['reference_mid']
            target=case.dollars if case.dollars is not None else max(0,before)*case.fraction
            q=math.floor(target/mid)
            if case.prior_capacity:
                if not r['adv']:skips['prior_volume_unavailable']+=1;continue
                q=min(q,math.floor(r['adv']*protocol['prior_ADV_participation']))
            if decisionbook:q=min(q,sum(size for _,size in decisionbook['bid_levels']))
            available=max(0,protocol['maximum_entry_margin_fraction']*before-entry_margin)
            q=min(q,math.floor(available/margin(1,mid,case.house)))
            if q<=0:skips['integer_capacity_or_capital']+=1;continue
            if q*mid<case.minimum_notional:skips['minimum_order_notional']+=1;continue
            if case.expected_cost_cap is not None:
                expected=model.estimate(r,'ask',mid,q*mid,rule=case.rule,offset=case.offset)
                if expected['basis']!='past_issuer_holdout':skips['cost_model_training_warmup']+=1;continue
                if not decisionbook:skips['cost_screen_entry_quote_unavailable']+=1;continue
                sell=sweep(decisionbook,'bid',q)
                estimated=(mid-sell)/mid+expected['spread']+expected['depth']
                estimated+=(commission(q,sell)+commission(q,mid))/(q*mid)+2*case.extra_bps/10000
                estimated+=rounded_collateral(q,mid)*case.borrow_rate*case.borrow_days/360/(q*mid)
                if estimated>case.expected_cost_cap:skips['expected_cost_above_cap']+=1;continue
            entry=fill(r,entrybook,'bid',q,mid,model,case)
            initial_margin=margin(q,entry['mid'],case.house)
            hint=books.get(r['key'],{}).get(str(case.offset)+'/'+case.rule)
            at,exitmid,label,stopped,delay,missing=exits(r,case,points,paths[r['key']],hint)
            exitbook=books.get(r['key'],{}).get(label) if label else None
            exitbook=exitbook or available_book(paths[r['key']],at)
            if status_at(hist,'is_trading',at)=='N':exitbook=None
            exit_=fill(r,exitbook,'ask',q,exitmid,model,case)
            comm=commission(q,entry['price'])+commission(q,exit_['price'])
            fee=rounded_collateral(q,max(entry['mid'],exit_['mid']))*case.borrow_rate*case.borrow_days/360
            pricepnl=q*(entry['price']-exit_['price']);net=pricepnl-comm-fee
            benchmark=q*(r['open']-r['close']);timing=q*((r['open']-entry['mid'])+(exit_['mid']-r['close']))
            spread=entry['spread']+exit_['spread'];depth=entry['depth']+exit_['depth'];extra=entry['extra']+exit_['extra']
            if not math.isclose(benchmark-timing-spread-depth-extra-comm-fee,net,rel_tol=1e-10,abs_tol=1e-6):raise ValueError('P&L waterfall failed')
            t={'key':r['key'],'issuer':r['issuer'],'date':day,'shares':q,'entry_mid':entry['mid'],
               'entry_mark_ask':entrybook['ask'] if entrybook else entry['mid']+entry['spread']/q,
               'entry_fill':entry['price'],'exit_fill':exit_['price'],'exit_mid':exit_['mid'],'entry_at':points[r['key']][str(case.offset)+'/entry']['fill_at'],
               'exit_at':datetime.fromtimestamp(at,timezone.utc).isoformat(),'net':net,'gross':q*entry['mid'],'margin':initial_margin,
               'gross_return':net/(q*entry['mid']),'margin_return':net/initial_margin,'benchmark':benchmark,'timing':timing,
               'spread':spread,'depth':depth,'extra':extra,'borrow':fee,'commission':comm,'stopped':stopped,
               'estimated_entry':entry['estimated'],'estimated_exit':exit_['estimated'],'estimated_exit_remainder':exit_['remainder'],
               'sampled_entry':bool(entrybook and entrybook.get('sampled')),'sampled_exit':bool(exitbook and exitbook.get('sampled')),
               'queued_exit_seconds':delay,'no_observed_exit_quote':missing,
               'entry_status_unknown':state.get('is_trading')!='Y' or state.get('is_short_sell_restricted')!='N',
               'event_clock_unverified':'eligible' not in r['cohorts'],
               'warming_estimate':entry['basis']=='retrospective_warmup_holdout' or exit_['basis']=='retrospective_warmup_holdout',
               'entry_nav':before}
            daytrades.append(t);trades.append(t);entry_margin+=initial_margin;used_issuers.add(r['issuer'])
        # All admissions use the same morning NAV. No exit profit funds another morning entry.
        if daytrades:
            ts=paths[daytrades[0]['key']]['ts'];marks=np.full(len(ts),before);requirements=np.zeros(len(ts))
            for t in daytrades:
                path=paths[t['key']];entry_at=pd.Timestamp(t['entry_at']).timestamp();exit_at=pd.Timestamp(t['exit_at']).timestamp()
                active=(ts>=entry_at)&(ts<exit_at);finished=ts>=exit_at
                comm_entry=commission(t['shares'],t['entry_fill'])
                marks[active]+=t['shares']*(t['entry_fill']-path['ask_mark'][active])-comm_entry
                marks[finished]+=t['net']
                price=path['mid'][active];floor=np.where(price<5,np.maximum(2.5,price),np.maximum(5.,.3*price))
                requirements[active]+=t['shares']*np.maximum(floor,case.house*price)
                coverage['imputed_intraday_mark_seconds']+=int((path['imputed_mark']&active).sum())
                coverage['active_mark_seconds']+=int(active.sum())
            immediate=before+sum(t['shares']*(t['entry_fill']-t['entry_mark_ask'])-commission(t['shares'],t['entry_fill']) for t in daytrades)
            closing=before+sum(t['net'] for t in daytrades)
            # Include the post-fill and fully costed closing account values.
            # The second grid otherwise misses the last 0.9s cover commission.
            marks=np.r_[immediate,marks,closing]
            requirements=np.r_[entry_margin,requirements,0.]
            peaks=np.maximum.accumulate(np.r_[global_intraday_peak,marks])[1:]
            intraday_dd=min(intraday_dd,float(np.min(marks/peaks-1)))
            global_intraday_peak=max(global_intraday_peak,float(marks.max()))
            max_intraday_margin=max(max_intraday_margin,float(requirements.max()))
            margin_breaches+=bool(np.any(requirements>marks))
            minimum_intraday_equity=min(minimum_intraday_equity,float(marks.min()))
            intraday_insolvencies+=bool(np.any(marks<=0))
        nav+=sum(t['net'] for t in daytrades)
        daily.append({'date':day,'equity':nav,'pnl':nav-before,'trades':len(daytrades),
                      'gross':sum(t['gross'] for t in daytrades),'margin':entry_margin})
    p=performance(daily,protocol['initial_equity'],protocol['start'],protocol['end'])
    p.update(max_intraday_drawdown=intraday_dd,max_intraday_margin=max_intraday_margin,
             minimum_intraday_equity=minimum_intraday_equity,intraday_insolvency_days=intraday_insolvencies,
             satisfies_modeled_intraday_margin=margin_breaches==0,
             intraday_margin_breach_days=margin_breaches,peak_entry_gross=max((d['gross'] for d in daily),default=0),
             peak_entry_margin=max((d['margin'] for d in daily),default=0),
             average_gross_to_equity=float(np.mean([d['gross']/max(d['equity']-d['pnl'],1) for d in daily])))
    p['turnover_one_sided_per_year']=sum(t['gross']/t['entry_nav'] for t in trades)/p['years'] if p['years'] else None
    p['turnover_two_sided_per_year']=sum(t['shares']*(t['entry_fill']+t['exit_fill'])/t['entry_nav'] for t in trades)/p['years'] if p['years'] else None
    session_seconds={r['key']:(pd.Timestamp(r['closed'])-pd.Timestamp(r['opened'])).total_seconds() for r in rows}
    exposure=sum(t['gross']/t['entry_nav']*(pd.Timestamp(t['exit_at'])-pd.Timestamp(t['entry_at'])).total_seconds()/session_seconds[t['key']] for t in trades)
    p['time_weighted_gross_fraction']=exposure/len(daily) if daily else None
    gross=sum(t['gross'] for t in trades);marg=sum(t['margin'] for t in trades)
    wins=[t['net'] for t in trades if t['net']>0];losses=[t['net'] for t in trades if t['net']<0]
    components={k:sum(t[k] for t in trades) for k in ('benchmark','timing','spread','depth','extra','borrow','commission','net')}
    annual=[];monthly={};peak=protocol['initial_equity']
    for d in daily:
        peak=max(peak,d['equity'])
        monthly[d['date'][:7]]={'date':d['date'],'equity':d['equity'],'drawdown':d['equity']/peak-1}
    for year in sorted({d['date'][:4] for d in daily}):
        ds=[d for d in daily if d['date'].startswith(year)];ps=[t for t in trades if t['date'].startswith(year)]
        begin=ds[0]['equity']-ds[0]['pnl'];ending=ds[-1]['equity'];g=sum(t['gross'] for t in ps);m=sum(t['margin'] for t in ps)
        annual.append({'year':year,'trades':len(ps),'return_on_equity':ending/begin-1 if begin>0 else None,
                       'net':sum(t['net'] for t in ps),'rog':sum(t['net'] for t in ps)/g if g else None,
                       'rom':sum(t['net'] for t in ps)/m if m else None,'ending_equity':ending,
                       'partial_year':protocol['start']>year+'-01-01' or protocol['end']<year+'-12-31'})
    result={'case':asdict(case),'pool_events':sum(len(v) for v in daily_rows.values()),'trades':len(trades),
            'issuers':len({t['issuer'] for t in trades}),'skipped':dict(skips),'portfolio':p,
            'capital':{'summed_gross':gross,'summed_margin':marg,'rog':sum(t['net'] for t in trades)/gross if gross else None,
                       'rom':sum(t['net'] for t in trades)/marg if marg else None,
                       'mean_trade_rog':stats(t['gross_return'] for t in trades),
                       'mean_trade_rom':stats(t['margin_return'] for t in trades)},
            'components':{k:{'dollars':v,'rog':v/gross if gross else None,'rom':v/marg if marg else None} for k,v in components.items()},
            'trade_metrics':{'win_rate':len(wins)/len(trades) if trades else None,
                'profit_factor':sum(wins)/-sum(losses) if losses else None,'average_win':float(np.mean(wins)) if wins else None,
                'average_loss':float(np.mean(losses)) if losses else None,'expectancy_dollars':float(np.mean([t['net'] for t in trades])) if trades else None,
                'stops':sum(t['stopped'] for t in trades),'queued_covers':sum(t['queued_exit_seconds']>0 for t in trades),
                'maximum_cover_delay_seconds':max((t['queued_exit_seconds'] for t in trades),default=0),
                'holding_minutes_mean':float(np.mean([(pd.Timestamp(t['exit_at'])-pd.Timestamp(t['entry_at'])).total_seconds()/60 for t in trades])) if trades else None},
            'tail':{'gross':tail(trades,'gross_return'),'margin':tail(trades,'margin_return'),
                    'mean_trade_rog_interval':cluster_interval(trades,'gross_return',cluster='issuer')},
            'coverage':{**dict(coverage),**{k:sum(bool(t[k]) for t in trades) for k in ('estimated_entry','estimated_exit','estimated_exit_remainder','entry_status_unknown','warming_estimate','sampled_entry','sampled_exit','no_observed_exit_quote','event_clock_unverified')},
                        'approved_historical_locates':0,'historical_margin_verified':0},'annual':annual,
            'monthly_equity':[{'date':protocol['start'],'equity':protocol['initial_equity'],'drawdown':0.}]+list(monthly.values()),
            'status':'conditional_model_with_estimated_fills' if any(t['estimated_entry'] or t['estimated_exit'] for t in trades) else 'conditional_displayed_book_model'}
    return result,daily,trades


def bootstrap_portfolio(daily,years,draws=2000):
    """Calendar-year block resampling of modeled daily returns, conditional sizing."""
    if not daily:return {}
    if any(d['equity']<=0 for d in daily):return {'method':'Account equity became nonpositive; annual growth/risk-ratio intervals are undefined.'}
    groups=defaultdict(list);last=daily[0]['equity']-daily[0]['pnl']
    for d in daily:groups[d['date'][:4]].append(d['equity']/last-1);last=d['equity']
    blocks=list(groups.values());rng=np.random.default_rng(20261014);cagrs=[];sharpes=[]
    for _ in range(draws):
        r=np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))])
        value=np.prod(1+r);cagrs.append(value**(252/len(r))-1 if value>0 else -1)
        sd=np.std(r,ddof=1);sharpes.append(r.mean()/sd*np.sqrt(252) if sd else np.nan)
    return {'draws':draws,'year_blocks':len(blocks),'cagr_session_annualized_interval':list(map(float,np.quantile(cagrs,[.025,.975]))),
            'sharpe_rf0_interval':list(map(float,np.nanquantile(sharpes,[.025,.975]))),
            'method':'Whole calendar-year blocks of modeled daily account returns; 252-session annualization for the resampled distribution; fixed historical policy and conditional fills. Not new independent evidence or a future-performance guarantee.'}


def stresses(trades):
    grouped=defaultdict(list)
    for t in trades:grouped[t['date']].append(t)
    if not grouped:return []
    day,basket=max(grouped.items(),key=lambda kv:sum(t['gross'] for t in kv[1]));nav=basket[0]['entry_nav']
    out=[]
    for rise in (.25,.5,1.,2.,5.):
        pnl=required=gross=0.
        for t in basket:
            q=t['shares'];price=t['entry_mid']*(1+rise);cover=price*1.05
            fee=rounded_collateral(q,price)*.5*3*7/360
            pnl+=q*(t['entry_fill']-cover)-fee-commission(q,t['entry_fill'])-commission(q,cover)
            required+=margin(q,price,2);gross+=t['gross']
        loss=max(0,-pnl)
        out.append({'observed_entry_date':day,'positions':len(basket),'rise':rise,'pnl':pnl,
                    'rog':pnl/gross if gross else None,'rom':pnl/sum(t['margin'] for t in basket),
                    'loss_on_entry_equity':loss/nav,'stressed_margin':required,'loss_plus_margin':loss+required,
                    'entry_equity':nav,'cash_shortfall':max(0,loss+required-nav),
                    'assumption':'All positions admitted that morning squeeze together before any planned exit; seven-day delay, 150% annual fee, 200% house requirement, 5% adverse cover. No stop fill assumed during the shock.'})
    return out


def population_outcomes(rows,books,points,paths,model,root):
    """All 671 hypothetical outcomes; separate from executable account admissions."""
    specs=[Case('sample'+str(size)+'_'+rule,rule=rule,dollars=size,prior_capacity=False)
           for size in (125,500,1250) for rule in ('close','stop5','stop10','stop20','time15','time60')]
    specs += [Case('sample_borrow'+str(rate)+'_'+rule,rule=rule,dollars=500,prior_capacity=False,borrow_days=1,borrow_rate=rate)
              for rate in (.1,.25,.5,1.,.55294892857) for rule in ('close','stop10')]
    specs += [Case('sample_impute'+str(quantile)+'_'+rule,rule=rule,dollars=500,prior_capacity=False,quantile=quantile)
              for quantile in (.25,.5,.75,.9) for rule in ('close','stop10')]
    outputs=[]
    for case in specs:
        sample=[]
        for r in rows:
            point=points[r['key']]['1/entry'];at=pd.Timestamp(point['fill_at']).timestamp()
            i=max(0,int(np.searchsorted(paths[r['key']]['ts'],at,side='right')-1))
            ref=float(paths[r['key']]['mid'][i])
            q=max(1,math.floor(case.dollars/ref))
            e=books.get(r['key'],{}).get('1/entry')
            entry=fill(r,e,'bid',q,ref,model,case)
            hint=books.get(r['key'],{}).get('1/'+case.rule)
            sample_points=points
            entry_halted=status_at(paths[r['key']].get('status_history',{}),'is_trading',at)=='N'
            if entry_halted:
                sample_points={r['key']:{**points[r['key']],'1/entry':{**point,'reference_mid':ref}}}
            at,mid,label,stopped,delay,missing=exits(r,case,sample_points,paths[r['key']],hint)
            x=books.get(r['key'],{}).get(label) if label else None
            x=x or available_book(paths[r['key']],at)
            if status_at(paths[r['key']].get('status_history',{}),'is_trading',at)=='N':x=None
            exit_=fill(r,x,'ask',q,mid,model,case)
            fee=rounded_collateral(q,max(entry['mid'],exit_['mid']))*case.borrow_rate*case.borrow_days/360
            comm=commission(q,entry['price'])+commission(q,exit_['price'])
            net=q*(entry['price']-exit_['price'])-comm-fee
            sample.append({'key':r['key'],'issuer':r['issuer'],'date':r['date'],'net':net,'gross':q*entry['mid'],
                'shares':q,'entry_mid':entry['mid'],'exit_mid':exit_['mid'],'entry_fill':entry['price'],'exit_fill':exit_['price'],
                'margin':margin(q,entry['mid']),'gross_return':net/(q*entry['mid']),
                'price_return':(entry['mid']-exit_['mid'])/entry['mid'],
                'price_margin_return':q*(entry['mid']-exit_['mid'])/margin(q,entry['mid']),
                'margin_return':net/margin(q,entry['mid']),'estimated_entry':entry['estimated'],
                'estimated_exit':exit_['estimated'],'estimated_exit_remainder':exit_['remainder'],
                'entry_known_not_trading':entry_halted,
                'stopped':stopped,'borrow':fee,'commission':comm,
                'spread':entry['spread']+exit_['spread'],'depth':entry['depth']+exit_['depth']})
        gross=sum(t['gross'] for t in sample);marg=sum(t['margin'] for t in sample);pnl=sum(t['net'] for t in sample)
        outputs.append({'case':asdict(case),'events':len(sample),'net_pnl':pnl,
            'summed_gross':gross,'summed_margin':marg,
            'capital_weighted_rog':pnl/gross,'capital_weighted_rom':pnl/marg,
            'gross_returns':stats(t['gross_return'] for t in sample),'margin_returns':stats(t['margin_return'] for t in sample),
            'price_returns_before_costs':stats(t['price_return'] for t in sample),
            'price_margin_returns_before_costs':stats(t['price_margin_return'] for t in sample),
            'gross_tail':tail(sample,'gross_return'),'margin_tail':tail(sample,'margin_return'),
            'mean_interval':cluster_interval(sample,'gross_return',cluster='issuer'),
            'estimated_entries':sum(t['estimated_entry'] for t in sample),'estimated_exits':sum(t['estimated_exit'] for t in sample),
            'estimated_exit_remainders':sum(t['estimated_exit_remainder'] for t in sample),
            'known_not_trading_entries':sum(t['entry_known_not_trading'] for t in sample),
            'stops':sum(t['stopped'] for t in sample),'costs':{k:sum(t[k] for t in sample)/gross for k in ('spread','depth','borrow','commission')},
            'notional_reference':case.dollars})
        write_json(root/(case.id+'.local.json'),sample)
    primary=next(s for s in outputs if s['case']['id']=='sample500_close')
    return {**primary,'scenarios':outputs,
            'auction_price_benchmark':{'gross':stats(1-r['close']/r['open'] for r in rows),
                'margin':stats((r['open']-r['close'])/margin(1,r['open']) for r in rows),
                'basis':'Original next-session official opening auction to closing auction; equal event weight; before any costs. Continuous quote entry/exit benchmarks differ.'},
            'basis':'Hypothetical target exposure with at least one whole share, completed same-day covers and assumed borrowing access; no SSR/capacity admission filter. Descriptive conditional outcomes, not the account replay.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--publish',action='store_true')
    args=parser.parse_args(argv);cfg=load_config()
    root=cfg.local_dir/'portfolio_research'/'20261013T224003582762Z__portfolio_v1'
    protocol=read_json(cfg.data_dir/'portfolio_protocol.json',{})
    if protocol.get('scenario_specs')!=[asdict(c) for c in cases()]:
        raise ValueError('Calculation cases differ from the declared comparison matrix')
    rows,books,points,index,minute,states,current=load_inputs(cfg,root)
    primary_rows=[r for r in rows if 'primary' in r['cohorts']]
    status=histories(cfg,root,rows)
    cost_books,halted_books=tradable_cost_books(rows,books,points,status)
    model=CostModel(rows,cost_books)
    paths={r['key']:path_marks(root,r,index,minute,status.get(r['key'],{})) for r in rows}
    calendar=trading_calendar(protocol['start'],protocol['end'])
    outputs=[];primary_trades=[];primary_daily=[]
    for case in cases():
        case_protocol={**protocol,'start':case.start or protocol['start'],'end':case.end or protocol['end']}
        case_calendar=[d for d in calendar if case_protocol['start']<=d<=case_protocol['end']]
        result,daily,trades=replay(rows,books,points,paths,states,current,model,case,case_protocol,case_calendar)
        result['squeeze_stresses']=stresses(trades)
        write_json(root/(case.id+'.local.json'),{'case':asdict(case),'daily':daily,'trades':trades})
        if case.id==protocol['primary_case']:
            result['uncertainty']=bootstrap_portfolio(daily,result['portfolio']['years']);primary_trades=trades;primary_daily=daily
        outputs.append(result)
        print(case.id,result['trades'],'CAGR',result['portfolio']['cagr'],'net',result['portfolio']['net_pnl'],flush=True)
    sample=population_outcomes(primary_rows,cost_books,points,paths,model,root)
    collections=[read_json(root/p/'collection.json',[]) for p in ('sessions','supplemental','depth','repair/sessions','repair/supplemental')]
    publication={'schema_version':'portfolio_research.v1','built_at':datetime.now(timezone.utc).isoformat(),
        'source_run_id':protocol['source_run_id'],'protocol':protocol,'sample':{'events':len(primary_rows),'issuers':len({r['issuer'] for r in primary_rows}),
            'issuer_keys_by_basis':dict(Counter(key.split('/')[0] for key in {r['issuer'] for r in primary_rows})),
            'event_identifier_basis':dict(Counter(r['issuer'].split('/')[0] for r in primary_rows)),
            'first_event_entry':min(r['date'] for r in primary_rows),'last_event_entry':max(r['date'] for r in primary_rows),
            'by_year':dict(sorted(Counter(r['date'][:4] for r in primary_rows).items()))},
        'expanded_sample':{'events':len(rows),'issuers':len({r['issuer'] for r in rows}),
                           'recovery':read_json(root/'repair'/'receipt.json',{})},
        'history':{'priced_start':protocol['start'],'end':protocol['end'],'oldest_entitled_venue_history':'2018-05-01',
                   'older_history_status':'No Massive Advanced, TAQ or CRSP/WRDS entitlement supplied; pre-2018 events cannot be assigned verified execution returns.',
                   'coverage_complete_universe':False,'requested_earlier_start':'2005-01-01',
                   'coverage_audit':read_json(root/'history_audit.local.json',{}),
                   'access_checked_at':read_json(root/'access_receipt.local.json',{}).get('checked_at'),
                   'degraded_target_dates_by_venue':{k:len(v) for k,v in read_json(root/'access_receipt.local.json',{}).get('degraded_target_dates',{}).items()}},
        'full_sample_cost_outcomes':sample,
        'cost_model':{**model.validate(primary_rows,cost_books),'known_not_trading_books_excluded':halted_books},'cases':outputs,'squeeze_stresses':stresses(primary_trades),
        'collection':{'requests':sum(len(c) for c in collections),'statuses':dict(Counter(r['status'] for c in collections for r in c)),
                      'quoted_usd':sum(r.get('quoted_usd',0) for c in collections for r in c if r['status'] in {'cached','downloaded'}),
                      'raw_market_data_public':False},
        'definitions':{'ROG':'Net P&L divided by summed one-sided opening gross exposure; equal-weighted per-event means are separate.',
             'issuer':'Issuer counts use SEC company identifiers where available and otherwise unresolved symbol keys. Symbol-only keys are not proof of independent legal issuers.',
             'ROM':'Net P&L divided by summed modeled entry equity requirements, excluding encumbered short proceeds and retaining FINRA floors.',
             'CAGR':'Ending account equity / $50,000, raised to 365.25 / calendar days, minus one. No external cash flows; sizing compounds with equity; idle sessions included.',
             'Sharpe':'Daily account return mean / sample standard deviation × sqrt(252), including idle sessions. Main risk-free and cash interest assumptions are zero; constant 4% alternative and HAC-adjusted ratio are sensitivities.',
             'Sortino':'Daily excess return mean / RMS downside deviation × sqrt(252); zero minimum acceptable return.',
             'Calmar':'Full-period CAGR / absolute full-period maximum closing drawdown; a separate trailing 36-month version uses that window for both quantities.',
             'intraday':'One-second tradable quote ask marks; missing quotes and known halts use only already completed minute trade closes (quote marks for recovered events). Displayed marks exclude quantity-dependent liquidation impact.',
             'quote_state':'Only completed sampling intervals are available. Valid unchanged quotes persist within the session until updated or invalidated; they do not expire merely because no interval record was printed. This assumes no unflagged missing venue updates.',
             'capacity':'0.1% of verified split-adjusted venue volume in the preceding 20 exchange sessions, divided by 20. Unobserved volume adds no verified capacity; this is a conservative lower bound, not a claim of zero trading or consolidated US ADV.',
             'execution':'Up to 15 distinct exchange feeds where their dated history is available. Delayed event-level depth uses the initial venue set; other feeds contribute sampled top quotes. Fresh mutually consistent venue states are combined; conflicting stale states are omitted. Subsecond changes between sampled quotes remain unknown. This is not full consolidated NBBO or broker fills.'},
        'limits':['All performance is conditional research, not broker-confirmed historical performance. Historical locates and house margins remain unavailable.',
                  'The all-event portfolio assumes that the split was identifiable before entry when a dated event clock is absent. Known-before-entry and fixed-fundamental cohorts are separate comparisons.',
                  'Where a decision quote is missing, the full-sample accounting uses the opening benchmark as a hypothetical price proxy; availability at one second is unverified. The observed-entry comparison removes that assumption.',
                  'Missing and insufficient-depth exits are explicitly estimated; same-session completion is an assumption. These modeled positions must not be dropped or interpreted as guaranteed covers.',
                  'Observed short-sale restrictions and nontrading states prevent account admission; unknown status is retained as an assumption. The 671 standardized cost outcomes ignore these admission restrictions.',
                  'Quote stop triggers are risk checks relative to the entry-decision midpoint, at one-second intervals after entry, followed by a delayed marketable cover. They are not guaranteed native broker stop prices.',
                  'Zero ordinary same-day borrowing assumes matched settled positions and no separate pre-borrow charge. One-day fee sensitivities do not reconstruct historical stock-loan invoices.',
                  'Current-rate-cap cases use current ticker indications, with historical issuer identity and availability unverified. Their survivor-selected subset cannot establish historical borrow-filter profitability.',
                  'Historical venue observations and complete benchmark availability create selection gaps; the sample is not a census of all reverse splits.',
                  'Provider reduced-quality dates are counted. Valid-looking observations on those dates may still be incomplete; unflagged missing updates cannot be identified from a sampled quote alone.',
                  'CAGR and risk ratios depend on the declared $50k account, small position limits, maximum three names, capacity and zero cash interest. They are not annualized ROG or ROM.',
                  'Extra impact sensitivities are uncalibrated. Static displayed depth and market moves cannot identify our causal market impact.',
                  'Margin breaches and intraday insolvency are reported without assuming a successful broker liquidation. A case with such a breach is an unconstrained conditional equity path, not an executable funded result.',
                  'Empirical cost donors require sufficient observed depth. Unavailable liquidity and historical approval failures are not identified by a matched average or cost percentile.',
                  'Retrospective warmup donors and explored history do not provide an untouched validation cohort. No automatically optimized strategy is promoted.']}
    write_json(root/'summary.json',publication)
    manifest={'schema_version':'portfolio_manifest.v1','source_run_id':protocol['source_run_id'],
              'summary_sha256':digest(root/'summary.json'),'protocol_sha256':digest(cfg.data_dir/'portfolio_protocol.json'),
              'inputs':{name:digest(root/name) for name in ('books.local.json','points.local.json','paths.local.json','status_history.local.json','access_receipt.local.json','history_audit.local.json')},
              'source_manifest_sha256':digest(cfg.local_dir/'expansion'/'expansion_v2'/'runs'/protocol['source_run_id']/'manifest.json'),
              'source_inputs':{
                  'quote_targets':digest(cfg.local_dir/'execution_research'/'20261013T224003582762Z__quotes_v1'/'targets.local.json'),
                  'minute_paths':digest(cfg.local_dir/'execution_research'/'20261013T224003582762Z__quotes_v1'/'minute_paths.local.json'),
                  'entry_status':digest(cfg.local_dir/'execution_research'/'20261013T224003582762Z__quotes_v1'/'trading_status.local.json'),
                  'prices':digest(cfg.local_dir/'expansion'/'expansion_v2'/'runs'/protocol['source_run_id']/'prices.sqlite'),
                  'current_borrow':digest(cfg.local_dir/'expansion'/'expansion_v2'/'runs'/protocol['source_run_id']/'current_borrow.jsonl')},
              'repair_inputs':{name:digest(root/'repair'/name) for name in ('targets.local.json','books.local.json','points.local.json','paths.local.json','minute_paths.local.json','receipt.json') if (root/'repair'/name).exists()},
              'collection':{name:digest(root/name/'collection.json') for name in ('sessions','supplemental','depth','repair/sessions','repair/supplemental') if (root/name/'collection.json').exists()},
              'code_hash_basis':'SHA-256 of UTF-8 source with canonical LF newlines',
              'code':{name:hashlib.sha256((Path(__file__).parent/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in ('portfolio_research.py','portfolio_data.py','portfolio_status.py','portfolio_repair.py','capital_risk.py','realism.py')},
              'raw_market_data_public':False}
    write_json(root/'manifest.json',manifest)
    if args.publish:
        write_json(cfg.data_dir/'portfolio_research.json',publication);write_json(cfg.data_dir/'portfolio_research_manifest.json',manifest)


if __name__=='__main__':main()
