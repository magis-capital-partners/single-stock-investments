"""Read-only daily price adapter and dated fee/carry primitives."""
from __future__ import annotations

import bisect
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .profit_data import NY, RUN, digest, write

CASES = {
    'bear': {'id': 'bear', 'label': 'Bear', 'spread_roundtrip': .0425, 'depth_multiplier': 1.5, 'borrow_apr': 1.5, 'ssr_capture': .25},
    'base': {'id': 'base', 'label': 'Base', 'spread_roundtrip': .0172, 'depth_multiplier': 1., 'borrow_apr': .5, 'ssr_capture': .5},
    'bull': {'id': 'bull', 'label': 'Bull', 'spread_roundtrip': .0100, 'depth_multiplier': .5, 'borrow_apr': .2, 'ssr_capture': .75},
}
SEC_RATES = [('2020-02-18',22.1),('2021-02-25',5.1),('2022-05-14',22.9),
             ('2023-02-27',8.),('2024-05-22',27.8),('2025-05-14',0.),('2026-04-04',20.6)]
FEE_SOURCES = [
    'https://www.sec.gov/rules-regulations/fee-rate-advisories',
    'https://www.sec.gov/newsroom/press-releases/2024-47',
    'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2026-18',
    'https://www.sec.gov/files/rules/sro/finra/2026/34-106409.pdf',
    'https://www.ibkrguides.com/reportingreference/reportguide/borrowfeedetails_default.htm',
    'https://www.interactivebrokers.com/en/pricing/short-sale-cost.php',
]


def reconcile_actions(actions,events,catalogue):
    # Explicit vendor corporate-action rows are usable for mechanical price
    # accounting, without promoting them to primary-reviewed trading signals.
    for action in catalogue:
        ratio=action.get('ratio')
        if action.get('verification')=='vendor_action_only' and ratio and ratio>0:
            actions.setdefault(action['ticker'],{})[action['ex_date']]=1/ratio
    for event in events:
        ratio=event.get('features',{}).get('ratio')
        if event['family']=='split' and ratio and ratio>1:
            actions.setdefault(event['ticker'],{})[event['event_date']]=ratio
    matched=0
    for action in catalogue:
        ratio=action.get('ratio')
        if action.get('verification') not in {'primary_schedule_matched','structured_corporate_action'} or not ratio or ratio<=0 or ratio==1:continue
        actions.setdefault(action['ticker'],{})[action['ex_date']]=1/ratio
        matched+=1
    return matched


def margin(qty, price, house=1.):
    floor = max(2.5, price) if price < 5 else max(5., .3 * price)
    return abs(qty) * max(floor, house * price)


def collateral(qty, price): return abs(qty) * math.ceil(1.02 * price)


def short_credit(value, nav=10_000_000):
    """Current-rate sensitivity, not a historical benchmark-rate backfill."""
    tiers = [(100000,1000000,.0263),(1000000,3000000,.0338),(3000000,math.inf,.0363)]
    return min(1.,max(0.,nav)/100000) * sum(max(0.,min(value,hi)-lo)*r for lo,hi,r in tiers)


def marginal_credit(strategy_collateral, external=100000, nav=10_000_000):
    return short_credit(external + strategy_collateral, nav) - short_credit(external, nav)


def execution_fraction(notional, case):
    """Explicit sensitivity anchored to conditional $25k static-book median.

    1.72% spread + 4.23% incremental size/depth = 5.95% at $25k in base.
    The square-root curve and transfer across dates/names are uncalibrated.
    """
    c = CASES[case] if isinstance(case, str) else case
    return min(.8, c['spread_roundtrip'] + .0423 * c['depth_multiplier'] * math.sqrt(max(0.,notional)/25000))


def fee(qty, price, day, sell, charge_day=None):
    if qty <= 0: return 0.
    notional = qty * price
    # One hypothetical daily child. Intraday replay retains its own child buckets.
    commission = min(max(.005 * qty, 1.), .01 * notional)
    allowance = qty * .000003
    if not sell: return math.ceil((commission+allowance)*100-1e-10)/100
    sec = next((r for d,r in reversed(SEC_RATES) if d <= (charge_day or day)),22.1)
    if '2026-10-01' <= day <= '2026-12-31': taf,cap=0.,0.
    elif day >= '2026-01-01': taf,cap=.000195,9.79
    elif day >= '2024-01-01': taf,cap=.000166,8.30
    elif day >= '2023-01-01': taf,cap=.000145,7.27
    elif day >= '2022-01-01': taf,cap=.000130,6.49
    else: taf,cap=.000119,5.95
    return math.ceil((commission+allowance+notional*sec/1e6+min(qty*taf,cap))*100-1e-10)/100


class PriceStore:
    def __init__(self, root, events, *, first='2021-01-01', last='2026-10-13', overlay=None):
        import exchange_calendars as xcals
        source = Path(root)/f'_system/data/reverse_splits/local/expansion/expansion_v2/runs/{RUN}/prices.sqlite'
        self.source = source
        conn = sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True)
        conn.row_factory = sqlite3.Row
        cal = xcals.get_calendar('XNYS',start='2020-01-01',end='2027-03-01')
        self.days=[d.strftime('%Y-%m-%d') for d in cal.sessions if first <= d.strftime('%Y-%m-%d') <= last]
        self.future_days=[d.strftime('%Y-%m-%d') for d in cal.sessions if first <= d.strftime('%Y-%m-%d') <= '2027-02-01']
        self.index={d:i for i,d in enumerate(self.days)}
        self.opens={d:datetime.fromisoformat(d+'T09:30:00').replace(tzinfo=NY).timestamp() for d in self.days}
        symbols=sorted({e['ticker'] for e in events if e.get('ticker')})
        self.series=defaultdict(dict)
        self.actions=defaultdict(dict)
        self.ssr={}
        for start in range(0,len(symbols),400):
            batch=symbols[start:start+400]
            placeholders=','.join('?' for _ in batch)
            query=f'''SELECT p.ticker,p.date,p.open,p.high,p.low,p.close,p.volume,v.nominal,v.source,v.volume_basis
                FROM prices_daily p LEFT JOIN price_provenance v ON p.ticker=v.ticker AND p.date=v.date
                WHERE p.ticker IN ({placeholders}) AND p.date>=? AND p.date<=? ORDER BY p.ticker,p.date'''
            for r in conn.execute(query,(*batch,'2020-10-01',last)):
                vals=[r[k] for k in ('open','high','low','close')]
                if not all(x is not None and math.isfinite(x) and x>0 for x in vals): continue
                if not r['nominal']: continue
                if r['low']>min(r['open'],r['close']) or r['high']<max(r['open'],r['close']) or r['high']<r['low']:continue
                volume=r['volume']
                if volume is None or not math.isfinite(volume) or volume<0:continue
                self.series[r['ticker']][r['date']]={'o':r['open'],'h':r['high'],'l':r['low'],'c':r['close'],
                    'v':volume,'ref':sum(vals)/4,'source':r['source'],'volume_basis':r['volume_basis']}
            for r in conn.execute(f'SELECT ticker,date,restricted FROM ssr_states WHERE ticker IN ({placeholders})',batch):
                self.ssr[(r['ticker'],r['date'])]=bool(r['restricted'])
            for r in conn.execute(f'SELECT ticker,ex_date,split_from,split_to FROM reverse_splits WHERE ticker IN ({placeholders})',batch):
                if r['split_from'] and r['split_to'] and r['split_from']>0 and r['split_to']>0:
                    ratio=r['split_from']/r['split_to']
                    prev=self.actions[r['ticker']].get(r['ex_date'])
                    if r['ex_date'] in self.actions[r['ticker']] and (prev is None or abs(prev-ratio)>1e-6):
                        self.actions[r['ticker']][r['ex_date']]=None
                    else: self.actions[r['ticker']][r['ex_date']]=ratio
        conn.close()
        if overlay and Path(overlay).exists():
            extra=sqlite3.connect(Path(overlay).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
            extra.row_factory=sqlite3.Row
            for r in extra.execute('SELECT p.*,v.nominal,v.source,v.volume_basis FROM prices_daily p JOIN price_provenance v USING(ticker,date) WHERE p.date<=?',(last,)):
                vals=[r[k] for k in ('open','high','low','close')]
                if not r['nominal'] or not all(x is not None and math.isfinite(x) and x>0 for x in vals):continue
                if r['volume'] is None or not math.isfinite(r['volume']) or r['volume']<0:continue
                if r['low']>min(r['open'],r['close']) or r['high']<max(r['open'],r['close']):continue
                # Preserve the frozen historical input; add gaps and later sessions only.
                self.series[r['ticker']].setdefault(r['date'],{'o':r['open'],'h':r['high'],'l':r['low'],'c':r['close'],'v':r['volume'],'ref':sum(vals)/4,'source':r['source'],'volume_basis':r['volume_basis']})
            extra.close()
        # The old SQLite reverse_splits table is incomplete. Reconcile real
        # corporate actions before treating nominal price jumps as investment P&L.
        # Ratio conventions differ: catalogue ratio=new/old; provider ratio=old/new.
        from .ledger import load_jsonl
        catalogue=source.parent/'event_outcomes.jsonl'
        action_rows=[a for a in load_jsonl(catalogue) if a['ticker'] in self.series]
        from .profit_actions import primary_adjustments
        self.primary_action_repairs=primary_adjustments(root,source,self.series,action_rows)
        for action in self.primary_action_repairs:
            self.actions[action['ticker']][action['ex_date']]=action['price_factor']
        matched=reconcile_actions(self.actions,events,action_rows)
        self.action_provenance={'verified_catalogue_actions':matched,
            'explicit_vendor_actions':sum(a['verification']=='vendor_action_only' for a in action_rows),
            'automatically_corroborated_primary_repairs':len(self.primary_action_repairs),
            'catalogue_index_sha256':digest(catalogue.with_suffix('.parts.json')),
            'provider_action_rows':sum(e['family']=='split' for e in events),
            'priority':'Verified catalogue overrides provider action metadata and explicit vendor actions; primary-clause corroboration repairs missing parser ratios. Price jumps alone never establish actions. Automated repairs require review; coverage remains incomplete.'}
        self.history={s:sorted(v) for s,v in self.series.items()}

    def entry_index(self,event):
        if not event.get('known_at'): return None
        at=datetime.fromisoformat(event['known_at'])+timedelta(minutes=5)
        if event.get('family')=='split':
            # Provider catalogue contains completed actions. Do not condition a
            # pre-completion trade on the action's eventual completion.
            completed=datetime.fromisoformat(event['event_date']+'T00:00:00').replace(tzinfo=NY)+timedelta(days=1)
            at=max(at,completed)
        i=bisect.bisect_left(self.days,at.astimezone(NY).date().isoformat())
        while i<len(self.days) and self.opens[self.days[i]]<at.timestamp(): i+=1
        return i if i<len(self.days) else None

    def prior_liquidity(self,symbol,day):
        days=self.history.get(symbol,[])
        i=bisect.bisect_left(days,day)
        old=days[max(0,i-20):i]
        if len(old)<10:return None
        if (datetime.fromisoformat(day)-datetime.fromisoformat(old[-1])).days>7:return None
        if (datetime.fromisoformat(day)-datetime.fromisoformat(old[0])).days>45:return None
        points=[self.series[symbol][d] for d in old]
        return {'adv_shares':float(np.mean([p['v'] for p in points])),
                'adv_dollars':float(np.mean([p['v']*p['c'] for p in points])),
                'last_price':points[-1]['c'],'observations':len(old)}

    def point(self,symbol,day):return self.series.get(symbol,{}).get(day)

    def factor(self,symbol,first,last):
        ratios=[v for d,v in self.actions.get(symbol,{}).items() if first<d<=last]
        return None if any(v is None for v in ratios) else math.prod(ratios)

    def gross_label(self,event,horizon):
        i=self.entry_index(event)
        if i is None or i+horizon-1>=len(self.days):return None
        first,last=self.days[i],self.days[i+horizon-1]
        p0,p1=self.point(event['ticker'],first),self.point(event['ticker'],last)
        factor=self.factor(event['ticker'],first,last)
        if not p0 or not p1 or not factor:return None
        return {'gross_return':1-p1['ref']/factor/p0['ref'],'entry_day':first,'exit_day':last,
                'issuer':event['issuer'],'event_id':event['id']}


def prepare_opportunities(events,prices,work):
    from .profit_data import fingerprint
    opportunities=[]
    for e in events:
        i=prices.entry_index(e)
        liquidity=prices.prior_liquidity(e['ticker'],prices.days[i]) if i is not None else None
        point=prices.point(e['ticker'],prices.days[i]) if i is not None else None
        status='ready_for_conditional_daily_replay' if point and liquidity else 'missing_nominal_price_or_prior_liquidity'
        opportunities.append({'event':e,'entry_index':i,'liquidity':liquidity,'coverage_status':status})
    write(Path(work)/'price_coverage.local.json',{'counts':dict(__import__('collections').Counter(o['coverage_status'] for o in opportunities)),
        'event_coverage':[{ 'id':o['event']['id'],'status':o['coverage_status'],'entry_day':prices.days[o['entry_index']] if o['entry_index'] is not None else None} for o in opportunities],
        'price_source':prices.source.name,'corporate_actions':prices.action_provenance,
        'opportunities_sha256':fingerprint([e['id'] for e in events])})
    write(Path(work)/'corporate_action_repairs.json',prices.primary_action_repairs)
    return opportunities
