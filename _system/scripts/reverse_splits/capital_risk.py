"""Capital denominators, observed loss tails and explicit squeeze scenarios.

No normal-distribution assumption or probability is attached to the stresses.
Minute highs bound intraday adverse movement; they are not executable covers.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
import sqlite3
from pathlib import Path

from .analysis import cluster_interval
from .expansion import digest
from .ledger import read_json, write_json
from .realism import maintenance, rounded_collateral

HOUSES = (.5, 1., 2.)


def margin(q, price, house=1.):
    return max(.5 * q * price, maintenance(q, price, house))


def stats(values):
    import numpy as np
    a = np.array(list(values), dtype=float)
    return {"n": len(a), "mean": float(a.mean()) if len(a) else None,
            "median": float(np.median(a)) if len(a) else None,
            "p90": float(np.quantile(a, .9)) if len(a) else None}


def tail(records, field):
    import numpy as np
    a = np.array([r[field] for r in records], dtype=float)
    result = {"n": len(a), "worst_return": float(a.min()) if len(a) else None}
    for alpha in (.95, .99):
        label = str(int(alpha * 100))
        minimum = 20 if alpha == .95 else 100
        n = max(1, math.ceil((100-int(alpha*100))*len(a)/100))
        result['loss_var_' + label] = max(0., float(np.quantile(-a, alpha))) if len(a) >= minimum else None
        result['loss_es_' + label] = max(0., float(-np.sort(a)[:n].mean())) if len(a) >= minimum else None
        result['tail_observations_' + label] = n if len(a) >= minimum else 0
    result['loss_frequency'] = float((a < 0).mean()) if len(a) else None
    return result


def intraday_requests(rows):
    grouped = defaultdict(set)
    for r in rows:
        grouped[r['dataset'], r['opened'], r['closed']].add(r['symbol'])
    requests = []
    for (dataset, start, end), symbols in sorted(grouped.items()):
        req = {'dataset': dataset, 'schema': 'ohlcv-1m', 'symbols': sorted(symbols), 'start': start, 'end': end}
        rid = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:24]
        requests.append({'id': rid, 'point': 'session', 'request': req})
    return requests


def minute_paths(root, rows):
    import databento as db
    paths = {}
    grouped = defaultdict(list)
    for r in rows:
        grouped[r['dataset'], r['opened']].append(r)
    collection = read_json(root / 'intraday' / 'collection.json', [])
    for item in collection:
        if item['status'] not in {'downloaded', 'cached'}:
            continue
        path = root / 'intraday' / item['file']
        if digest(path) != item['sha256']:
            raise ValueError('Intraday source changed')
        df = db.DBNStore.from_file(str(path)).to_df()
        if df.empty:
            continue
        req = item['request']
        for row in grouped[req['dataset'], req['start']]:
            frame = df.loc[df['symbol'] == row['symbol']].sort_index()
            opened, closed = datetime.fromisoformat(row['opened']), datetime.fromisoformat(row['closed'])
            frame = frame.loc[(frame.index >= opened) & (frame.index < closed)]
            frame = frame.loc[(frame['high'] >= frame['low']) & (frame['low'] > 0) & (frame['volume'] > 0)]
            if len(frame):
                paths[row['key']] = {'times': [t.isoformat() for t in frame.index],
                                     'high': [float(v) for v in frame['high']],
                                     'close': [float(v) for v in frame['close']],
                                     'bars': len(frame)}
    write_json(root / 'minute_paths.local.json', paths)
    return paths, collection


def vwap(book, side, q):
    rest, value = q, 0.
    for price, size in book[side+'_levels']:
        part = min(rest, size)
        rest -= part
        value += part * price
        if rest <= 0:
            return value / q
    return None


def capital_positions(rows, measured, states, mode, offset, extra):
    positions = []
    for r in rows:
        if 'account' not in r:
            continue
        st = states.get(r['key'], {})
        if (st.get(f'open/{offset}', {}).get('is_trading') != 'Y'
            or st.get('close/-1', {}).get('is_trading') != 'Y'
            or st.get(f'open/{offset}', {}).get('is_short_sell_restricted') != 'N'):
            continue
        o = measured.get(r['key'], {})
        e, x = o.get(f'{mode}/open/{offset}', {}).get('book'), o.get(f'{mode}/close/-1', {}).get('book')
        if not e or not x:
            continue
        q = r['account']['entry_shares']
        entry, exit_ = vwap(e, 'bid', q), vwap(x, 'ask', q)
        if entry is None or exit_ is None:
            continue
        comm = sum(min(max(1, q*.005), q*fill*.01) for fill in (entry, exit_))
        cost = q*(entry+exit_)*extra/10000
        net = q*(entry-exit_) - cost - comm - r['account']['borrow']
        gross = q*e['mid']
        positions.append({'key': r['key'], 'issuer': r['issuer'], 'date': r['date'], 'shares': q,
                          'opened': r['opened'], 'closed': r['closed'],
                          'entry_price': e['mid'], 'entry_fill': entry, 'gross': gross,
                          'margin': margin(q, e['mid']), 'net': net, 'gross_return': net/gross,
                          'margin_return': net/margin(q, e['mid']), 'rate': r['account']['rate']})
    return positions


def path_risk(positions, paths, offset):
    bounds, missing = [], 0
    for p in positions:
        path = paths.get(p['key'])
        if not path:
            missing += 1
            continue
        # Whole bars strictly within the position exclude ambiguous boundary minutes.
        entry_at = datetime.fromisoformat(p['opened']) + timedelta(seconds=offset)
        exit_at = datetime.fromisoformat(p['closed']) - timedelta(seconds=1)
        overlap = [high for t,high in zip(path['times'],path['high'])
                   if datetime.fromisoformat(t) + timedelta(minutes=1) > entry_at and datetime.fromisoformat(t) <= exit_at]
        all_high = max(overlap)
        middle = [high for t,high in zip(path['times'],path['high'])
                  if datetime.fromisoformat(t) >= entry_at and datetime.fromisoformat(t)+timedelta(minutes=1) <= exit_at]
        interior_high = max(middle) if middle else None
        maximum = max(0., all_high / p['entry_fill'] - 1)
        bounds.append({'full_minute_adverse_bound': maximum,
                       'interior_minute_adverse': max(0., interior_high / p['entry_fill'] - 1) if interior_high else None,
                       'margin_loss_bound': p['shares'] * max(0, all_high-p['entry_fill']) / p['margin'],
                       'peak_margin_multiple': margin(p['shares'], all_high, p.get('house',1)) / p['margin']})
    return {'paths': len(bounds), 'missing': missing,
            'adverse_price_bound': stats(b['full_minute_adverse_bound'] for b in bounds),
            'worst_adverse_price_bound': max((b['full_minute_adverse_bound'] for b in bounds), default=None),
            'loss_on_margin_bound': stats(b['margin_loss_bound'] for b in bounds),
            'worst_loss_on_margin_bound': max((b['margin_loss_bound'] for b in bounds), default=None),
            'peak_margin_multiple': max((b['peak_margin_multiple'] for b in bounds), default=None),
            'interior_minute_adverse': stats(b['interior_minute_adverse'] for b in bounds if b['interior_minute_adverse'] is not None)}


def stress(positions, *, squeeze, house, days, rate_multiplier, cover_cost):
    pnl, required, gross, starting_margin = 0., 0., 0., 0.
    for p in positions:
        q, ref = p['shares'], p['entry_price']
        price = ref * (1+squeeze)
        cover = price * (1+cover_cost)
        borrow = rounded_collateral(q, price)*p['rate']*rate_multiplier*days/360
        commission = sum(min(max(1, q*.005), q*fill*.01) for fill in (p['entry_fill'], cover))
        pnl += q*(p['entry_fill']-cover)-borrow-commission
        required += margin(q, price, house)
        gross += p['gross']
        starting_margin += p['margin']
    loss = max(0, -pnl)
    return {'price_rise': squeeze, 'house_fraction_after_squeeze': house, 'calendar_borrow_days': days,
            'fee_multiple': rate_multiplier, 'cover_cost_fraction': cover_cost, 'names': len(positions),
            'gross_exposure': gross, 'starting_margin': starting_margin, 'pnl': pnl,
            'return_on_gross': pnl/gross if gross else None,
            'return_on_margin': pnl/starting_margin if starting_margin else None,
            'stressed_margin_requirement': required, 'loss_plus_margin_budget': loss+required,
            'additional_cash_budget': max(0, loss+required-starting_margin),
            'loss_on_50k_equity': loss/50000,
            'notional_for_250_loss_budget': 250/(loss/gross) if gross and loss else None}


def build_capital_risk(cfg, root, rows, measured, states, summary):
    paths, collection = minute_paths(root, rows)
    price_cohorts = []
    source = cfg.local_dir / 'expansion' / 'expansion_v2' / 'runs' / summary['source_run_id']
    primary_year = {r['event_id']:r['year'] for r in read_json(source/'one_day_paths.local.json',{})['primary']}
    current = {r['ticker']:r for r in (json.loads(line) for line in (source/'current_borrow.jsonl').read_text().splitlines())}
    for name in ('primary', 'eligible', 'fundamental', 'cost_capacity', 'current_cap50'):
        selected = [r for r in rows if name in r['cohorts']]
        if name == 'current_cap50':
            selected = [r for r in rows if 'primary' in r['cohorts'] and current.get(r['ticker'],{}).get('available_shares',0)>0 and current[r['ticker']].get('fee_annual_fraction') is not None and current[r['ticker']]['fee_annual_fraction']<=.5]
        for house in HOUSES:
            events = [{'issuer': r['issuer'], 'gross_return': 1-r['close']/r['open'],
                       'margin_return': (r['open']-r['close'])/margin(1, r['open'], house)} for r in selected]
            by_year = []
            for year in sorted({primary_year.get(r['event_id'],r['date'][:4]) for r in selected}):
                annual = [r for r in selected if primary_year.get(r['event_id'],r['date'][:4]) == year]
                by_year.append({'year':year, 'gross_returns':stats(1-r['close']/r['open'] for r in annual),
                                'margin_returns':stats((r['open']-r['close'])/margin(1,r['open'],house) for r in annual)})
            price_cohorts.append({'cohort': name, 'house_fraction': house, 'by_year':by_year,
                                  'gross_returns': stats(r['gross_return'] for r in events),
                                  'margin_returns': stats(r['margin_return'] for r in events),
                                  'margin_mean_interval': cluster_interval(events, 'margin_return', cluster='issuer'),
                                  'gross_tail': tail(events, 'gross_return'), 'margin_tail': tail(events, 'margin_return'),
                                  'intraday': path_risk([{'key':r['key'],'shares':1,'entry_fill':r['open'], 'opened':r['opened'],'closed':r['closed'],
                                                         'margin':margin(1,r['open'],house),'house':house} for r in selected], paths, 0)})
    scenario_positions = {}
    for case in summary['fixed_position_scenarios']:
        mode, offset, extra = case['execution_mode'], case['entry_seconds_after_open'], case['additional_bps_per_side']
        positions = capital_positions(rows, measured, states, mode, offset, extra)
        if len(positions) != case['both_sides_fit'] or abs(sum(p['net'] for p in positions)-case['totals'].get('net', 0)) > 1e-6:
            raise ValueError('Capital analysis does not reconcile with execution study')
        gross = sum(p['gross'] for p in positions)
        marg = sum(p['margin'] for p in positions)
        case['capital'] = {'gross_entry_exposure': gross, 'summed_entry_margin': marg,
                           'equal_weighted_net_return_on_gross': stats(p['gross_return'] for p in positions)['mean'],
                           'equal_weighted_net_return_on_margin': stats(p['margin_return'] for p in positions)['mean'],
                           'net_return_on_gross': case['totals'].get('net',0)/gross if gross else None,
                           'net_return_on_margin': case['totals'].get('net',0)/marg if marg else None,
                           'components': {k: {'dollars': v, 'on_gross': v/gross if gross else None, 'on_margin': v/marg if marg else None}
                                          for k,v in case['totals'].items() if k in {'raw_auction_pnl','quoted_half_spread_cost','displayed_depth_cost','timing_difference','additional_slippage','borrow','commission','net'}}}
        case['margin_sensitivities'] = [{'house_fraction': h, 'summed_margin': sum(margin(p['shares'], p['entry_price'], h) for p in positions),
                                        'net_return_on_margin': sum(p['net'] for p in positions)/sum(margin(p['shares'], p['entry_price'], h) for p in positions) if positions else None} for h in HOUSES]
        case['tail'] = {'gross': tail(positions, 'gross_return'), 'margin': tail(positions, 'margin_return'),
                        'mean_return_interval': cluster_interval(positions, 'gross_return', cluster='issuer'),
                        'intraday': path_risk(positions, paths, offset)}
        daily = defaultdict(lambda: {'pnl': 0., 'gross': 0., 'margin': 0.})
        for p in positions:
            d = daily[p['date']]
            d['pnl'] += p['net']; d['gross'] += p['gross']; d['margin'] += p['margin']
        balance = peak = 50000.
        drawdown = 0.
        for d in sorted(daily):
            balance += daily[d]['pnl']; peak = max(peak,balance); drawdown=min(drawdown,balance/peak-1)
        case['capital']['maximum_same_day_gross'] = max((d['gross'] for d in daily.values()), default=None)
        case['capital']['maximum_same_day_entry_margin'] = max((d['margin'] for d in daily.values()), default=None)
        case['capital']['net_return_on_50k_equity'] = case['totals'].get('net',0)/50000
        case['capital']['cumulative_net_over_peak_entry_margin'] = case['totals'].get('net',0)/case['capital']['maximum_same_day_entry_margin'] if case['capital']['maximum_same_day_entry_margin'] else None
        for sensitivity in case['margin_sensitivities']:
            grouped_margin = defaultdict(float)
            for p in positions:
                grouped_margin[p['date']] += margin(p['shares'],p['entry_price'],sensitivity['house_fraction'])
            sensitivity['maximum_same_day_entry_margin'] = max(grouped_margin.values(),default=None)
        case['tail']['close_of_day_drawdown_on_50k'] = drawdown
        case['tail']['worst_same_day_return_on_50k'] = min((d['pnl']/50000 for d in daily.values()), default=None)
        scenario_positions[mode, offset, extra] = positions
    base = scenario_positions.get(('routed-mbp-10', 1, 0), [])
    biggest = sorted(base, key=lambda p:p['gross'], reverse=True)
    shocks = []
    for basket, positions in [('largest_observed_position',[biggest[0]] if biggest else []), ('three_largest_hypothetically_together',biggest[:3])]:
        if not positions:
            continue
        for squeeze in (.25,.5,1.,2.,5.):
            shocks.append({'basket':basket, **stress(positions,squeeze=squeeze,house=1,days=1,rate_multiplier=1,cover_cost=.01)})
        for squeeze in (1.,2.,5.):
            shocks.append({'basket':basket, **stress(positions,squeeze=squeeze,house=2,days=7,rate_multiplier=3,cover_cost=.05)})
    # Quote spreads already use entry-midpoint exposure. Add their margin view.
    for pop in summary['populations']:
        values=[]
        for row in rows:
            if pop['cohort']=='account' and 'account' not in row or pop['cohort']!='account' and pop['cohort'] not in row['cohorts']:
                continue
            o=measured.get(row['key'],{}); offset=pop['entry_seconds_after_open']; mode=pop['schema']
            e=o.get(f'{mode}/open/{offset}',{}).get('book'); x=o.get(f'{mode}/close/-1',{}).get('book')
            if e and x: values.append(((e['mid']-e['bid'])+(x['ask']-x['mid']))/margin(1,e['mid']))
        pop['round_trip_half_spreads_on_margin'] = stats(values)
    legacy = []
    frozen_summary = read_json(source/'summary.json',{})
    for old in frozen_summary.get('accounts',[]):
        case = old['case']; book = read_json(source/(case['id']+'.json'),{})
        ps = book.get('positions',[])
        gross = sum(p['entry_shares']*p['entry_price'] for p in ps)
        marg = sum(margin(p['entry_shares'],p['entry_price']) for p in ps)
        costs = old['metrics'].get('costs',{})
        legacy.append({'case_id':case['id'],'gross_entry_exposure':gross,'summed_entry_margin':marg,
                       'net_return_on_gross':old['metrics']['net']/gross if gross else None,
                       'net_return_on_margin':old['metrics']['net']/marg if marg else None,
                       'gross_price_return_on_gross':costs.get('raw_price_pnl',0)/gross if gross else None,
                       'gross_price_return_on_margin':costs.get('raw_price_pnl',0)/marg if marg else None,
                       'cost_return_on_gross':sum(costs.get(k,0) for k in ('spread_cost','slippage_cost','borrow','commission'))/gross if gross else None,
                       'cost_return_on_margin':sum(costs.get(k,0) for k in ('spread_cost','slippage_cost','borrow','commission'))/marg if marg else None})
    grouped_prices = defaultdict(list)
    prices = sqlite3.connect((source/'prices.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    cache = {}
    for part in read_json(source/'event_outcomes.parts.json',{})['files']:
        with (source/part['path']).open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                if event['verification'] not in {'primary_schedule_matched','structured_corporate_action'}:
                    continue
                ticker = event.get('database_ticker',event['ticker'])
                for o in event['outcomes']:
                    if o['status'] != 'observed_price_path':
                        continue
                    key = ticker,o['entry_date'],o['entry_point']
                    if key not in cache:
                        found = prices.execute('SELECT price FROM official_auction_prices WHERE ticker=? AND date=? AND point=?',key).fetchone()
                        cache[key] = found[0] if found else None
                    price = cache[key]
                    if price and price > 0:
                        grouped_prices[o['cohort']].append(o['gross_short_return']*price/margin(1,price))
    control_document = read_json(source/'control_matches.local.json',{})
    controls_margin = []
    row_by_id = {r['event_id']:r for r in rows}
    for matched,outcome in zip(control_document.get('matches',[]),control_document.get('outcomes',[])):
        row = row_by_id.get(matched['event_id'])
        control_prices=[]
        for ticker in matched['controls']:
            found = prices.execute("SELECT price FROM official_auction_prices WHERE ticker=? AND date=? AND point='open'",(ticker,matched['date'])).fetchone()
            if found and found[0]>0: control_prices.append(found[0])
        if row and len(control_prices)==len(matched['controls']) and control_prices:
            subject_return = outcome['subject']/(margin(1,row['open'])/row['open'])
            control_return = outcome['control']/(sum(margin(1,p)/p for p in control_prices)/len(control_prices))
            controls_margin.append({'issuer':outcome['issuer'],'subject':subject_return,'control':control_return,'excess':subject_return-control_return})
    prices.close()
    expanded_cohorts = [{'cohort':name,'margin_returns':stats(values)} for name,values in grouped_prices.items()]
    return {'schema_version':'capital_tail.v1', 'house_margin_fraction':1., 'margin_sensitivity_fractions':list(HOUSES),
            'definitions': {'gross':'Shares × entry midpoint for quote scenarios; opening auction price for descriptive price cohorts. Gross exposure counts one side, not entry-plus-exit turnover.',
                            'margin':'Equity required, excluding encumbered short-sale proceeds. Greater of 50% of market exposure, FINRA per-share maintenance floors and the selected house fraction. Historical broker-specific requirements are not supplied.',
                            'aggregation':'Account scenario returns divide summed P&L by summed entry exposure or margin. Capital is reused across dates: this is not a portfolio annual return or P&L divided by peak capital. Peak simultaneous entry capital is shown separately.',
                            'costs':'Cost fractions are positive amounts consumed. Subtract spread, depth, timing changes, borrow and commissions from gross price P&L; timing can be negative.',
                            'tail':'Historical VaR is a sample loss percentile; expected shortfall is the average of the worst ceil(5% × n) observations. 99% estimates require at least 100 observations. Stress scenarios have no assigned probability.',
                            'intraday':'Listing-venue regular-session minute highs. Full entry/exit minute extremes are conservative bounds and can fall just outside the actual position window. Interior-minute results omit those boundary minutes. Prices are marks, not observed size-adjusted cover fills.'},
            'price_cohorts':price_cohorts, 'expanded_price_cohorts':expanded_cohorts, 'legacy_accounts':legacy, 'squeeze_stresses':shocks,
            'matched_controls_on_margin':{'events':len(controls_margin),'subject':stats(r['subject'] for r in controls_margin),
                                          'control':stats(r['control'] for r in controls_margin),'excess':stats(r['excess'] for r in controls_margin),
                                          'excess_interval':cluster_interval(controls_margin,'excess',cluster='issuer'),
                                          'basis':'Same paired observations; equal gross notional within each matched control basket; return divided by its modeled entry margin. Missing margin price bases are excluded and counted.'},
            'intraday_collection':{'requests':len(collection),'statuses':dict(Counter(i['status'] for i in collection)),
                                  'quoted_usd':sum(i.get('quoted_usd',0) for i in collection),'observed_paths':len(paths)},
            'limits':['Observed tails are conditional on available data and repeated issuers. Small execution samples do not establish rare-event probabilities.',
                      'A planned one-day hold does not bound losses if liquidity vanishes, a recall forces a buy-in or the broker raises requirements.',
                      'Short losses have no finite upper bound. The largest +500% scenario is an illustration, not a worst possible outcome.',
                      'Stress cash budget adds potential cover loss, costs and stressed margin as a conservative reserve; those obligations do not all settle at the same instant.',
                      'The three-largest-position stress is a hypothetical correlated basket; it does not claim those positions historically overlapped.',
                      'The fixed-position daily path assumes same-day covers and no resizing, cash interest or new admissions after costs change. It is not the full production account replay.']}
