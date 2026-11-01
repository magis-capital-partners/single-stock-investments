"""Retrospective patient-entry scenarios. Research only; no broker authority.

Only the collect command uses Databento, with a hard zero-dollar download gate.
Raw licensed data and individual decisions remain in the ignored local directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

RUN = '20261013T224003582762Z'
FEEDS = ('XNAS.ITCH', 'ARCX.PILLAR', 'EDGX.PITCH')
CASES = (
    {'id': 'bear', 'ssr_capture': .25, 'impact': .0025, 'residual_cover': .05},
    {'id': 'base', 'ssr_capture': .50, 'impact': .0010, 'residual_cover': .02},
    {'id': 'bull', 'ssr_capture': .75, 'impact': .0005, 'residual_cover': .01},
)
PROTOCOL = {
    'version': 'short_patient_execution.v1', 'hypothesis_id': 'H21',
    'targets': [25000, 50000], 'windows_minutes': [30, 60, 120, 240],
    'modes': ['flow', 'target'], 'cases': CASES, 'variants': 48,
    'population': 'All 551 already examined primary ex+1 events in 2023-01-03..2026-10-13, including 325 SSR-active at the open. No forecast-profit filter, full-opening-depth admission, 3% opening anchor or three-name cap.',
    'flow': 'At most 5% of observed one-second volume across distinct XNAS/ARCX/EDGX and listing feeds. Exclude the first 60 seconds, including opening auction prints. Partial entries are kept; unfilled quantities canceled at the window end. Not consolidated US volume.',
    'ssr': 'Dynamic cached status; unknown restriction treated as restricted, known nontrading states excluded. Peg offer one tick above the latest sampled best bid at the start of the bar. Uniform bar-price distribution approximates volume at/above that offer; capture 25/50/75% of the 5% eligible-volume allocation. Quotes are sampled direct feeds, not verified live NBBO; queue position and compliant broker execution unverified.',
    'target': 'Conditional target-fill sensitivity: equal-dollar one-minute slices through the entry window; restricted slices fill 25/50/75%, unrestricted slices 100%, if a valid quote exists. Assumes sufficient flow; required entry participation reported. No evidence that these targets actually fill.',
    'prices': 'Entry uses contemporaneous sampled bid (unrestricted) or bid-plus-tick (restricted), with adverse bar-range midpoint adjustment for unrestricted flow. Extra impact 25/10/5 bps per side. Entry amount capped at target in dollars before fees. No legacy 3.11% proxy or duplicated spread/depth addition.',
    'cover': 'From 90 minutes before close to 15 minutes before close, buy at sampled ask, taking at most 5% of observed volume. Residual assumes completion at the final observed ask plus 5/2/1% surcharge. All residual completions flagged and retained in P&L, with +20%/+100% gap loss sensitivity. This is conditional same-day completion, not proof of flatness.',
    'fees': 'IBKR Pro Fixed 0.005/share, $1 minimum, 1% notional cap per occupied five-minute child bucket per side; current SEC 20.60/million sold, normal TAF .000195/share capped9.79 per sell child, CAT .000003/share both sides, cents rounded up. Cover residual is a separate child. Replacements within a five-minute child assumed not to restart its minimum.',
    'financing': 'Conditional same-day flat: zero borrow/proceeds credit. A failed cover instead retains a short liability, adds gap/borrow exposure, and invalidates the same-day business-income estimate. Borrow approval and locate fees unverified.',
    'risk': 'Daily closing-equity dollar drawdown; not intraday maximum loss. Full-session quote marks estimate peak exposure/margin at 100% house, Reg-T low-price floors and 102%-rounded borrow collateral. $10m hypothetical NAV only for ratios. No account-level cap enforced; aggregate concurrency and +200% squeeze loss shown.',
    'validation': 'Retrospective assumption sensitivity, all 48 variants retained, no new untouched holdout claim. Designated execution holdout file remains unread. No production strategy change, broker orders or paid downloads.',
}
PARTICIPATION_PROTOCOL = {
    'version': 'short_patient_participation.v1', 'hypothesis_id': 'H22',
    'rates': [.10, .20], 'reference_rate': .05, 'additional_variants': 48,
    'rule': 'Reuse H21 flow replay, all two targets/four windows/three combined cases. Both entry and cover participation increase to the specified rate of recorded venue flow. SSR capture unchanged. Extra impact per side equals H21 case impact times sqrt(rate/0.05); this scaling is an uncalibrated sensitivity, not an empirical impact estimate. No other admission or exit change.',
    'validation': 'Declared after seeing all H21 results and before any H22 replay. Retrospective capacity/cost sensitivity, all 48 extra variants retained. No winning rate promoted and no additional data or trading authority.',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(root):
    local = root/'_system/data/reverse_splits/local'
    targets = read(local/f'execution_research/{RUN}__quotes_v1/targets.local.json')
    return local, [r for r in targets if 'primary' in r['cohorts'] and '2023-01-03' <= r['date'] <= '2026-10-13']


def requests(rows):
    groups = defaultdict(set)
    for row in rows:
        for feed in sorted(set(FEEDS+(row['dataset'],))):
            groups[feed, row['opened'], row['closed']].add(row['symbol'])
    out = []
    for (feed, start, end), symbols in sorted(groups.items()):
        req = dict(dataset=feed, schema='ohlcv-1s', symbols=sorted(symbols), start=start, end=end)
        ident = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:24]
        out.append({'id': ident, 'request': req})
    return out


def collect(root, work, monthly=False, retry_daily=False):
    from reverse_splits.execution_realism import _client
    from reverse_splits.databento_bars import fetch, is_complete
    local, rows = inputs(root)
    client = _client()
    pending = []
    saved = {}
    ledger = work/'collection.local.json'
    if ledger.exists():
        saved = {r['id']: r for r in read(ledger)['requests'] if r['status'] in ('have', 'refused')}
    jobs = requests(rows)
    if retry_daily:
        previous = read(ledger)['requests']
        errors = [r['request'] for r in previous if r['status'] == 'error']
        added = [j for j in jobs if any(e['dataset'] == j['request']['dataset'] and e['start'] <= j['request']['start'] < e['end'] for e in errors)]
        jobs = [r for r in previous if r['status'] != 'error']+added
        jobs = list({r['id']: r for r in jobs}.values())
    if monthly:
        cached, groups = [], defaultdict(list)
        for item in jobs:
            req = item['request']
            path = local/'raw/databento'/req['dataset']/req['schema']/'sessions'/f"{item['id']}.dbn.zst"
            if is_complete(path):
                cached.append(item)
            else:
                groups[req['dataset'], req['start'][:7]].append(req)
        jobs = cached
        for (feed, _), reqs in sorted(groups.items()):
            req = dict(dataset=feed, schema='ohlcv-1s', symbols=sorted({s for r in reqs for s in r['symbols']}),
                       start=min(r['start'] for r in reqs), end=max(r['end'] for r in reqs))
            ident = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:24]
            jobs.append({'id': ident, 'request': req})
        # Keep only this exact collection plan; do not count overlapping daily files
        # alongside a monthly file for the same symbol and event.
        saved = {k: v for k, v in saved.items() if k in {j['id'] for j in jobs}}
    for item in jobs:
        req = item['request']
        path = local/'raw/databento'/req['dataset']/req['schema']/'sessions'/f"{item['id']}.dbn.zst"
        item['file'] = str(path)
        if is_complete(path):
            receipt = read(path.with_name(path.name.replace('.dbn.zst', '.ok.json')))
            if receipt['request'] == {k: str(v) for k, v in req.items()}:
                saved[item['id']] = {**item, 'status': 'have', 'quoted_usd': receipt['quoted_usd'], 'bytes': receipt['bytes']}
                continue
        if item['id'] not in saved:
            pending.append(item)
    print(f'{len(jobs)} requests; {len(saved)} cached or previously refused; {len(pending)} to price', flush=True)
    def one(item):
        try:
            quote = float(client.metadata.get_cost(**item['request']))
            if not math.isfinite(quote) or quote != 0.:
                return {**item, 'status': 'refused', 'quoted_usd': quote if math.isfinite(quote) else None}
            result = fetch(client, Path(item['file']), max_cost=0., quoted_cost=quote, **item['request'])
            return {**item, 'status': 'have', 'quoted_usd': quote, 'bytes': result['bytes']}
        except Exception as exc:
            # Do not serialize HTTP exception strings, which might contain credentials.
            return {**item, 'status': 'error', 'error_type': type(exc).__name__}
    # Well below Databento's 100-connection / 20-metadata-per-second limits.
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = []
        for item in pending:
            futures.append(pool.submit(one, item))
            time.sleep(.18)  # metadata requests limited below six per second
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            saved[result['id']] = result
            if i % 50 == 0:
                print('completed', len(saved), dict(Counter(r['status'] for r in saved.values())), flush=True)
                write(ledger, {'requests': list(saved.values()), 'free_only': True})
    doc = {'built_at': datetime.now(timezone.utc).isoformat(), 'free_only': True,
           'requests': [saved[j['id']] for j in jobs],
           'summary': dict(Counter(r['status'] for r in saved.values()))}
    write(ledger, doc)
    print(doc['summary'], flush=True)


def quality(root, work):
    """Free metadata; preserve provider day flags without selecting returns."""
    from reverse_splits.execution_realism import _client
    _, rows = inputs(root)
    client = _client()
    result = {}
    for feed in sorted(set(FEEDS+tuple(r['dataset'] for r in rows))):
        values = client.metadata.get_dataset_condition(dataset=feed, start_date='2023-01-03', end_date='2026-10-13')
        result[feed] = [r for r in values if r.get('condition') not in (None, 'available')]
    write(work/'quality.local.json', result)
    print('flagged provider days', {k: len(v) for k, v in result.items()}, flush=True)


def states(history, field, ts, default):
    value = history.get(field, {})
    times = np.asarray(value.get('ts', []))
    result = np.full(len(ts), default, dtype='<U1')
    if len(times):
        indices = np.searchsorted(times, ts, side='right')-1
        valid = indices >= 0
        result[valid] = np.asarray(value['value'])[indices[valid]]
    return result


def eligible_fraction(low, high, price):
    """Explicit uniform-price proxy, not signed trades or a queue simulation."""
    tick = np.where(price >= 1., .01, .0001)
    total = np.rint((high-low)/tick)+1
    above = np.rint((high-price)/tick)+1
    return np.where(high < price-tick*1e-6, 0., np.clip(above/np.maximum(total, 1), 0, 1))


def above_bid(bid):
    tick = np.where(bid >= 1., .01, .0001)
    return (np.floor(bid/tick+1e-8)+1)*tick


def prepare(root, work):
    import databento as db
    local, rows = inputs(root)
    source = local/f'portfolio_research/{RUN}__portfolio_v1'
    manifest = read(source/'manifest.json')
    for name in ('paths.local.json', 'status_history.local.json'):
        if sha(source/name) != manifest['inputs'][name]:
            raise ValueError('Frozen portfolio input changed: '+name)
    paths = read(source/'paths.local.json')
    histories = read(source/'status_history.local.json')['histories']
    grouped = defaultdict(list)
    arrays, evidence = {}, []
    for row in rows:
        item = paths.get(row['key'])
        if not item:
            continue
        path = source/item['file']
        if sha(path) != item['sha256']:
            raise ValueError('Quote path changed')
        with np.load(path) as saved:
            a = {k: saved[k].copy() for k in ('ts', 'bid', 'ask')}
        a['restricted'] = states(histories.get(row['key'], {}), 'is_short_sell_restricted', a['ts'], 'U') != 'N'
        trading = states(histories.get(row['key'], {}), 'is_trading', a['ts'], 'U')
        a['valid'] = np.isfinite(a['bid']) & np.isfinite(a['ask']) & (a['bid'] > 0) & (a['ask'] >= a['bid']) & (trading != 'N')
        a['volume'] = np.zeros(len(a['ts']))
        a['eligible'] = np.zeros(len(a['ts']))
        a['price_volume'] = np.zeros(len(a['ts']))
        a['listing_volume'] = np.zeros(len(a['ts']))
        a['offer'] = above_bid(a['bid'])
        arrays[row['key']] = a
        grouped[row['symbol']].append(row)
    coverage = Counter()
    used = set()
    for item in read(work/'collection.local.json')['requests']:
        if item['status'] != 'have':
            continue
        path = Path(item['file'])
        frame = db.DBNStore.from_file(str(path)).to_df(pretty_ts=False)
        evidence.append({'file': str(path.relative_to(local)), 'sha256': sha(path), 'quoted_usd': item['quoted_usd']})
        if frame.empty or 'symbol' not in frame:
            continue
        for symbol, f in frame.groupby('symbol'):
            ts = f.index.to_numpy(dtype=np.int64)//10**9
            low = f['low'].to_numpy(float)
            high = f['high'].to_numpy(float)
            vol = f['volume'].to_numpy(float)
            for row in grouped.get(symbol, []):
                if not item['request']['start'] <= row['opened'] < item['request']['end']:
                    continue
                identity = row['key'], item['request']['dataset']
                if identity in used:
                    continue
                used.add(identity)
                a = arrays[row['key']]
                idx = np.searchsorted(a['ts'], ts)
                good = (idx < len(a['ts'])) & (ts >= int(datetime.fromisoformat(row['opened']).timestamp())+60)
                idx, lo, hi, v = idx[good], low[good], high[good], vol[good]
                exact = a['ts'][idx] == ts[good]
                idx, lo, hi, v = idx[exact], lo[exact], hi[exact], v[exact]
                # Each source is a distinct venue; no consolidated volume added on top.
                np.add.at(a['volume'], idx, v)
                np.add.at(a['eligible'], idx, v*eligible_fraction(lo, hi, a['offer'][idx]))
                np.add.at(a['price_volume'], idx, v*(lo+hi)/2)
                if item['request']['dataset'] == row['dataset']:
                    np.add.at(a['listing_volume'], idx, v)
                coverage[item['request']['dataset']] += int(bool(v.sum()))
    write(work/'source_manifest.local.json', {'files': evidence, 'portfolio_manifest_sha256': sha(source/'manifest.json')})
    for row in rows:
        a = arrays.get(row['key'])
        if a is not None:
            file = work/'prepared'/f"{hashlib.sha256(row['key'].encode()).hexdigest()[:24]}.npz"
            file.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(file, **a)
            row['prepared'] = str(file)
    write(work/'prepared.local.json', {'rows': rows, 'venue_event_coverage': dict(coverage)})
    print('prepared', len(arrays), dict(coverage), flush=True)


def constrained_fill(capacity, prices, dollars=None, shares=None):
    """Whole shares, bounded by cumulative capacity, and by budget or position."""
    capacity = np.maximum(0., np.nan_to_num(capacity))
    whole = np.diff(np.r_[0., np.floor(np.cumsum(capacity)+1e-8)])
    # Accrued fractional participation may carry to a later print, never backwards.
    weights = whole*prices if dollars is not None else whole
    remaining = dollars if dollars is not None else shares
    cumulative = np.cumsum(weights)
    result = whole.copy()
    if len(result) and cumulative[-1] > remaining:
        k = int(np.searchsorted(cumulative, remaining, side='right'))
        before = cumulative[k-1] if k else 0.
        result[k] = min(result[k], math.floor((remaining-before)/prices[k]+1e-8) if dollars is not None else remaining-before)
        result[k+1:] = 0.
    return result


def child_fees(qty, prices, ts, opened, sell):
    active = qty > 0
    if not active.any():
        return 0.
    buckets = np.floor((ts[active]-opened)/300).astype(int)
    q = np.bincount(buckets, weights=qty[active])
    cash = np.bincount(buckets, weights=qty[active]*prices[active])
    present = q > 0
    q, cash = q[present], cash[present]
    cents = lambda v: np.ceil(np.maximum(v, 0)*100-1e-10)/100
    cost = cents(np.minimum(np.maximum(1., q*.005), cash*.01))+cents(q*.000003)
    if sell:
        cost += cents(cash*.0000206)+cents(np.minimum(9.79, q*.000195))
    return float(cost.sum())


def replay_one(row, a, target, minutes, case, mode, participation=.05):
    opened = int(datetime.fromisoformat(row['opened']).timestamp())
    closed = int(datetime.fromisoformat(row['closed']).timestamp())
    ts, valid = a['ts'], a['valid']
    entry = valid & (ts >= opened+60) & (ts < min(opened+minutes*60, closed-90*60))
    restricted = a['restricted']
    raw_sell = np.where(restricted, a['offer'], a['bid'])
    if mode == 'flow':
        # Causal quotes at second start; range/volume determine simulated execution,
        # never which events are admitted. Downward moves worsen marketable fills.
        bar_price = np.divide(a['price_volume'], a['volume'], out=a['bid'].copy(), where=a['volume'] > 0)
        raw_sell = np.where(restricted, a['offer'], np.minimum(a['bid'], bar_price))
        capacity = participation*np.where(restricted, a['eligible']*case['ssr_capture'], a['volume'])
        capacity = np.where(entry, capacity, 0.)
    else:
        # One minute TWAP; failed restricted slices are canceled, not catch-up fills.
        scheduled = entry & ((ts-opened) % 60 == 0)
        count = max(1, min(minutes, (closed-opened)//60-90)-1)
        capacity = np.where(scheduled, target/count/np.maximum(raw_sell, 1e-10)*np.where(restricted, case['ssr_capture'], 1.), 0.)
    # Invalid quote values must never enter sums even with zero quantity.
    sell = np.where(valid, raw_sell, 1.)
    take = constrained_fill(capacity, sell, dollars=target)
    q = int(take.sum())
    empty = {'date': row['date'], 'issuer': row['issuer'], 'key': row['key'], 'target': target,
             'ssr_open': bool(restricted[0]), 'filled': q, 'valid_seconds': int(entry.sum())}
    if not q:
        return {**empty, 'net_pnl': 0., 'notional': 0., 'fees': 0., 'residual': 0, 'unresolved': False}
    cover = valid & (ts >= closed-90*60) & (ts < closed-15*60)
    bar_price = np.divide(a['price_volume'], a['volume'], out=a['ask'].copy(), where=a['volume'] > 0)
    buy = np.where(valid, np.maximum(a['ask'], bar_price), 1.)
    covered = constrained_fill(np.where(cover, participation*a['volume'], 0.), buy, shares=q)
    residual = q-int(covered.sum())
    available = np.flatnonzero(valid & (ts >= closed-15*60))
    final = int(available[-1]) if len(available) else int(np.flatnonzero(valid)[-1])
    # Liabilities remain priced even when no fresh closing quote exists.
    cover_cash = float(np.dot(covered, buy))
    residual_price = a['ask'][final]*(1+case['residual_cover'])
    cover_cash += residual*residual_price
    cash = float(np.dot(take, sell))
    impact_cost = case['impact']*(cash+cover_cash)
    fees = child_fees(take, sell, ts, opened, True)+child_fees(covered, buy, ts, opened, False)
    if residual:
        fees += child_fees(np.array([residual]), np.array([residual_price]), np.array([closed]), opened, False)
    inventory = np.cumsum(take-covered)
    mark = np.where(valid, a['ask'], np.nan)
    # Forward fill marks through halts for capital accounting, never infer a fill.
    last = np.maximum.accumulate(np.where(np.isfinite(mark), np.arange(len(mark)), 0))
    mark = mark[last]
    mark = np.nan_to_num(mark, nan=cash/q)
    notional_path = inventory*mark
    floor = np.where(mark < 5, np.maximum(2.5, mark), np.maximum(5., .30*mark))
    margin = inventory*np.maximum(floor, mark)  # 100% house sensitivity plus floors
    collateral = np.ceil(1.02*mark)*inventory
    participation = q/float(a['volume'][entry].sum()) if a['volume'][entry].sum() else None
    initial = int(np.flatnonzero(valid)[0])
    entry_timing_cost = q*(a['bid'][initial]+a['ask'][initial])/2-cash
    return {**empty, 'net_pnl': cash-cover_cash-fees-impact_cost, 'notional': cash, 'fees': fees,
            'sell_vwap': cash/q, 'buy_vwap': cover_cash/q,
            'entry_timing_cost': float(entry_timing_cost), 'impact_cost': float(impact_cost),
            'residual': residual, 'unresolved': not bool(len(available)),
            'entry_participation': participation, 'entry_shares': q,
            'volume_ratio': float(a['volume'][entry].sum()/a['listing_volume'][entry].sum()) if a['listing_volume'][entry].sum() else None,
            'full': cash >= target*.95, 'peak_exposure': float(max(notional_path)),
            'peak_margin': float(max(margin)), 'peak_collateral': float(max(collateral)),
            'gap20': residual*residual_price*.20, 'gap100': residual*residual_price,
            'modeled_cost_vs_window_mid': float(impact_cost + np.dot(take, np.where(valid, (a['bid']+a['ask'])/2, 0)-sell) + np.dot(covered, buy-np.where(valid, (a['bid']+a['ask'])/2, 0)) + residual*(residual_price-(a['bid'][final]+a['ask'][final])/2)),
            'ssr_shares': int(take[restricted].sum())}


def metrics(rows, days):
    trades = [r for r in rows if r['filled']]
    daily = defaultdict(float)
    margin, collateral, exposure = defaultdict(float), defaultdict(float), defaultdict(float)
    count = Counter()
    for r in trades:
        daily[r['date']] += r['net_pnl']
        count[r['date']] += 1
        margin[r['date']] += r['peak_margin']
        collateral[r['date']] += r['peak_collateral']
        exposure[r['date']] += r['peak_exposure']
    pnl = np.array([daily[d] for d in days])
    curve = np.cumsum(pnl)
    drawdown = np.maximum.accumulate(np.r_[0., curve])[1:]-curve
    years = (date.fromisoformat(days[-1])-date.fromisoformat(days[0])).days/365.2425
    equity = 1e7+np.r_[0., curve]
    ret = np.diff(equity)/equity[:-1]
    mdd = float(-(equity/np.maximum.accumulate(equity)-1).min())
    cagr = (equity[-1]/equity[0])**(1/years)-1 if equity.min() > 0 else None
    downside = float(np.sqrt(np.mean(np.minimum(ret, 0.)**2)))
    quantile = lambda v, q: float(np.quantile(v, q)) if len(v) else None
    positions = [r['notional'] for r in trades]
    profits = [r['net_pnl'] for r in trades]
    part = [r['entry_participation'] for r in trades if r['entry_participation'] is not None]
    ratios = [r['volume_ratio'] for r in trades if r['volume_ratio'] is not None]
    return {'trades': len(trades), 'trades_per_year': len(trades)/years,
            'trades_over_1k': sum(r['notional'] >= 1000 for r in trades),
            'trades_over_10k': sum(r['notional'] >= 10000 for r in trades),
            'net_pnl': float(pnl.sum()), 'annual_pnl': float(pnl.sum()/years),
            'annual_pnl_ex_best_trade': float((pnl.sum()-max(profits))/years) if profits else 0.,
            'best_trade': max(profits) if profits else None,
            'profit_factor': sum(p for p in profits if p > 0)/-sum(p for p in profits if p < 0) if any(p < 0 for p in profits) else None,
            'mean_position': float(np.mean(positions)) if positions else 0.,
            'median_position': quantile(positions, .5), 'full_targets': sum(r['full'] for r in trades),
            'win_rate': float(np.mean(np.array(profits) > 0)) if profits else None,
            'max_dd_dollars': float(max(drawdown)), 'worst_trade': min(profits) if profits else None,
            'worst_day': float(min(pnl)), 'cagr': cagr, 'max_dd': mdd,
            'calmar': cagr/mdd if cagr is not None and mdd else None,
            'sharpe': float(ret.mean()/ret.std(ddof=1)*np.sqrt(252)) if ret.std() else None,
            'sortino': float(ret.mean()/downside*np.sqrt(252)) if downside else None,
            'annual_volatility': float(ret.std(ddof=1)*np.sqrt(252)),
            'ssr_open_trades': sum(r['ssr_open'] for r in trades),
            'ssr_open_net_pnl': sum(r['net_pnl'] for r in trades if r['ssr_open']),
            'unrestricted_open_net_pnl': sum(r['net_pnl'] for r in trades if not r['ssr_open']),
            'ssr_shares': sum(r['ssr_shares'] for r in trades),
            'cover_residual_trades': sum(r['residual'] > 0 for r in trades),
            'cover_residual_fraction': sum(r['residual'] for r in trades)/sum(r['filled'] for r in trades) if trades else 0.,
            'missing_fresh_close': sum(r['unresolved'] for r in trades),
            'entry_participation_p50': quantile(part, .5), 'entry_participation_p90': quantile(part, .9),
            'entry_over_10pct': sum(r['entry_participation'] is None or r['entry_participation'] > .1 for r in trades),
            'fees': sum(r['fees'] for r in trades),
            'volume_ratio_p50': quantile(ratios, .5), 'volume_ratio_p90': quantile(ratios, .9),
            'entry_timing_fraction': sum(r['entry_timing_cost'] for r in trades)/sum(positions) if positions else None,
            'impact_cost': sum(r['impact_cost'] for r in trades),
            'execution_fraction': sum(r['modeled_cost_vs_window_mid'] for r in trades)/sum(positions) if positions else None,
            'peak_margin': max(margin.values(), default=0.), 'peak_collateral': max(collateral.values(), default=0.),
            'peak_exposure': max(exposure.values(), default=0.), 'squeeze_200': 2*max(exposure.values(), default=0.),
            'peak_names': max(count.values(), default=0),
            'residual_gap20': sum(r['gap20'] for r in trades), 'residual_gap100': sum(r['gap100'] for r in trades),
            'yearly': {y: float(sum(p for d, p in zip(days, pnl) if d.startswith(y))) for y in sorted({d[:4] for d in days})},
            'series': [[d, float(c), float(-dd)] for d, c, dd in zip(days, curve, drawdown)]}


def build(root, work, out):
    from reverse_splits.universe_study import trading_calendar
    declared = read(work/'protocol.json')
    if json.dumps(declared['protocol'], sort_keys=True) != json.dumps(PROTOCOL, sort_keys=True):
        raise ValueError('Protocol differs from the saved pre-run declaration')
    prepared = read(work/'prepared.local.json')
    rows = prepared['rows']
    days = [str(d)[:10] for d in trading_calendar('2023-01-03', '2026-10-13')]
    variants = [(case, size, mins, mode) for case in CASES for size in PROTOCOL['targets'] for mins in PROTOCOL['windows_minutes'] for mode in PROTOCOL['modes']]
    results = [[] for _ in variants]
    for index, row in enumerate(rows):
        if 'prepared' not in row:
            continue
        with np.load(row['prepared']) as archive:
            a = {k: archive[k] for k in archive.files}
        for i, (case, size, mins, mode) in enumerate(variants):
            results[i].append(replay_one(row, a, size, mins, case, mode))
        if index % 100 == 0:
            print('replayed', index, flush=True)
    aggregates = []
    for (case, size, mins, mode), decisions in zip(variants, results):
        name = f"{case['id']}_{size}_{mins}_{mode}"
        write(work/f'{name}.decisions.local.json', decisions)
        m = metrics(decisions, days)
        aggregates.append({'id': name, 'case': case['id'], 'target': size, 'minutes': mins, 'mode': mode, **m})
        print(name, m['trades'], round(m['mean_position']), round(m['annual_pnl']), flush=True)
    ledger = read(work/'collection.local.json')
    quality_flags = read(work/'quality.local.json') if (work/'quality.local.json').exists() else {}
    flagged = {(feed, r.get('date')) for feed, flags in quality_flags.items() for r in flags}
    affected = sum(any((feed, r['date']) in flagged for feed in set(FEEDS+(r['dataset'],))) for r in rows)
    doc = {'schema_version': PROTOCOL['version'], 'built_at': datetime.now(timezone.utc).isoformat(),
           'aggregate_only': True, 'hypothesis_ids': ['H21'], 'research_only': True, 'authority': 'none',
           'protocol': PROTOCOL, 'declared_at': declared['declared_at'], 'start': days[0], 'end': days[-1],
           'population': len(rows), 'prepared_events': sum('prepared' in r for r in rows),
           'ssr_open_events': sum('eligible' not in r['cohorts'] for r in rows),
           'coverage': {'venues': prepared['venue_event_coverage'], 'requests': ledger['summary'],
                        'quality_audited': bool(quality_flags), 'provider_flagged_events': affected,
                        'download_cost': sum(r.get('quoted_usd') or 0 for r in ledger['requests'] if r['status'] == 'have'),
                        'source_manifest_sha256': sha(work/'source_manifest.local.json')},
           'models': aggregates}
    write(out, doc)
    return doc


def supplement(root, work, out):
    """Separately declared H22 rates; preserve every original H21 result."""
    declaration = read(work/'participation_protocol.json')
    if declaration['protocol'] != PARTICIPATION_PROTOCOL:
        raise ValueError('Participation protocol differs from declaration')
    doc = read(out)
    if 'H22' in doc['hypothesis_ids']:
        raise ValueError('Supplement already built')
    rows = read(work/'prepared.local.json')['rows']
    days = [r[0] for r in doc['models'][0]['series']]
    variants = [(case, size, mins, rate) for rate in PARTICIPATION_PROTOCOL['rates'] for case in CASES for size in PROTOCOL['targets'] for mins in PROTOCOL['windows_minutes']]
    results = [[] for _ in variants]
    for index, row in enumerate(rows):
        if 'prepared' not in row:
            continue
        with np.load(row['prepared']) as saved:
            a = {k: saved[k] for k in saved.files}
        for i, (case, size, mins, rate) in enumerate(variants):
            c = {**case, 'impact': case['impact']*math.sqrt(rate/.05)}
            results[i].append(replay_one(row, a, size, mins, c, 'flow', participation=rate))
        if index % 100 == 0:
            print('participation replay', index, flush=True)
    for model in doc['models']:
        model['participation'] = .05
    for (case, size, mins, rate), decisions in zip(variants, results):
        ident = f"{case['id']}_{size}_{mins}_flow_{round(rate*100)}pct"
        write(work/f'{ident}.decisions.local.json', decisions)
        m = metrics(decisions, days)
        doc['models'].append({'id': ident, 'case': case['id'], 'target': size, 'minutes': mins,
                              'mode': 'flow', 'participation': rate, **m})
        print(ident, m['trades'], round(m['mean_position']), round(m['annual_pnl']), flush=True)
    doc['hypothesis_ids'].append('H22')
    doc['participation_protocol'] = PARTICIPATION_PROTOCOL
    doc['participation_declared_at'] = declaration['declared_at']
    doc['built_at'] = datetime.now(timezone.utc).isoformat()
    doc['legacy_excluded_events'] = doc['ssr_open_events']
    # The original eligibility labels and the dynamic status reconstruction differ.
    # Preserve the declared population while reporting the status used by this replay.
    original = read(work/'base_25000_60_target.decisions.local.json')
    doc['ssr_assumed_restricted_open_events'] = sum(r['ssr_open'] for r in original)
    write(out, doc)
    return doc


def report(doc):
    money = lambda v: ('-' if v < 0 else '')+f'${abs(v):,.0f}' if v is not None else 'Unavailable'
    lines = ['# Patient short entry at $25k and $50k targets', '',
             f"Retrospective sensitivity, {doc['start']} through {doc['end']}. All {len(doc['models'])} declared variants retained. {doc['population']} primary events; {doc['ssr_open_events']} outside the old unrestricted cohort. No broker orders or paid data. H21 was declared before its replay, after extensive prior examination of the underlying event sample. H22 was declared after H21 results but before its additional participation replays.", '',
             'Dollar trading profit below deducts sampled-price execution costs, case impact buffers, child-order commissions and current regulatory-rate sensitivities. Annualized profit divides total by elapsed calendar years; it is not a forecast of annual business revenue. Borrow approvals, locate fees, overhead, capital opportunity cost and tax are unverified or excluded. Same-day flatness is conditional on completing every cover.', '',
             'Timing reconciliation: the legacy cohort has 325 restricted events at the instant of the open. Cached status shows nine more restrictions triggered within the first second, giving 334 by open+1 second. The new replay uses the status at each execution interval, including later intraday triggers; earlier published cohort labels are preserved for reproducibility.', '',
             '## What changed and why', '',
             '| Old assumption | Audit | New sensitivity |', '|---|---|---|',
             '| Exclude SSR-active names | A short-sale price restriction is not a blanket short-sale ban. | Include them with offers above the sampled bid and 25/50/75% assumed capture. Live Rule 201 compliance still requires current NBBO. |',
             '| Entire target must fit one opening book | A snapshot cannot establish capacity available over several hours. | Keep partial fills and work orders over 30/60/120/240 minutes. |',
             '| Never enter more than 3% below the opening midpoint | This is an absolute price anchor, not a measure of our own impact; it can reject a profitable trade after an unrelated market move. | Price against contemporaneous quotes, with a declared impact buffer. Delayed entry naturally loses any decline that occurred before the fill. |',
             '| Listing venue volume represents opportunity flow | Understates recorded capacity when other exchanges also trade the stock. | Sum distinct Nasdaq/Arca/EDGX and listing feeds where available, without double-counting overlapping daily/monthly files. Other venues and off-exchange prints remain missing. |',
             '| Forecast net return must exceed 0.5% | The cutoff and the small-sample forecast are not independently validated. | Remove the forecast filter for this experiment; losing names remain. |',
             '| Old $500 depth proxy and fixed opening/closing half-spread charge | Not calibrated to patient $25k-$50k orders. | Use quotes along the execution path, no duplicate legacy spread/depth charge. Impact buffers are assumptions, not measured market impact. |',
             '| Three-name cap | A portfolio policy, rather than per-stock execution capacity. | Show all opportunities, aggregate exposure and margin; do not change live risk policy. |',
             '| Same-day cover completion beyond observed depth | Potentially optimistic rather than conservative. | Count unsupported covers, charge an explicit surcharge, and show failed-cover gap exposure. No closed-position profitability claim without validating those exits. |', '',
             '## Flow-based estimates', '',
             'Use 5% of observed one-second trading volume, starting one minute after the open. For restricted intervals, estimate the portion trading at or above a bid-plus-tick offer by spreading each one-second bar over its tick prices, then apply the case capture rate to that 5% allocation. This is a bar proxy, not observed signed flow, queue priority or executed short orders. The target is a dollar ceiling; partial fills reduce actual position size.', '',
             '| Target | Entry window | Flow rate | Case | Trades | SSR/prudent restricted trades | Mean position | Annual profit | Closing DD | Covers requiring assumed completion |',
             '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in doc['models']:
        if r['mode'] == 'flow':
            lines.append(f"| {money(r['target'])} | {r['minutes']} min | {r.get('participation', .05):.0%} | {r['case']} | {r['trades']} | {r['ssr_open_trades']} | {money(r['mean_position'])} | {money(r['annual_pnl'])} | {money(r['max_dd_dollars'])} | {r['cover_residual_trades']} |")
    lines += ['', '## Conditional target-fill scenarios', '',
              'A separate what-if assumes equal-dollar minute slices fill throughout the chosen entry window: 100% of unrestricted slices and 25/50/75% of restricted slices in bear/base/bull. Unfilled restricted slices are canceled. Missing valid quotes also cancel their slices. This assumes liquidity; the required percentage of recorded volume is a diagnostic, not proof. These rates are fractions of proposed shares, not probabilities that an entire parent order fills.', '',
              '| Target | Entry window | Case | Trades | Mean position | Annual profit | Closing DD | Entries requiring >10% of flow or missing flow |',
              '|---|---|---|---:|---:|---:|---:|---:|']
    for r in doc['models']:
        if r['mode'] == 'target':
            lines.append(f"| {money(r['target'])} | {r['minutes']} min | {r['case']} | {r['trades']} | {money(r['mean_position'])} | {money(r['annual_pnl'])} | {money(r['max_dd_dollars'])} | {r['entry_over_10pct']} |")
    lines += ['', '## Cases, costs and cover risk', '',
              '| Case | Assumed SSR capture | Extra impact per side | Assumed residual-cover surcharge |', '|---|---:|---:|---:|']
    for c in CASES:
        lines.append(f"| {c['id']} | {c['ssr_capture']:.0%} | {10000*c['impact']:.0f} bps | {c['residual_cover']:.0%} |")
    lines += ['',
              'H22 adds 10% and 20% participation on recorded flow, for entry and cover, with impact buffers multiplied by sqrt(rate/5%). These are additional assumptions declared after observing H21, not independently calibrated rates. Missing venues mean participation in the full market can be lower than participation in the recorded subset. Higher participation can also move prices more than the assumed buffer. All 48 extra flow variants are retained alongside H21\'s original 48 results.', '',
              'The impact buffer is deducted as a separate dollar cost, so it does not turn a modeled SSR offer into an illegal below-bid execution price. It is not calibrated from our own fills. Fees use one persistent child per occupied five-minute interval: actual broker treatment of replacements can add minimums. The first minute is excluded to avoid counting opening auction shares as continuous liquidity.', '',
              'The cover schedule uses at most 5% of recorded volume from 90 to 15 minutes before the close. Every residual assumes completion at the last valid sampled ask plus the case surcharge and a separate child commission. P&L retains those costs and liabilities rather than dropping difficult trades. A missing valid final-15-minute quote is counted. No assumed closing completion is evidence of a completed cover.', '',
              'If a cover fails, the marked short remains open. The published aggregate includes additional +20% and +100% residual-price stresses across all affected historical trades; these are total-period dollar sensitivities, not simultaneous portfolio losses or assigned probabilities. Overnight borrow, proceeds credit and gap paths must then be modeled explicitly; zero same-day financing would no longer apply.', '',
              '## Risk, source quality and interpretation', '',
              'CAGR/Sharpe/Sortino/Calmar use a hypothetical flat-core $10m NAV and daily closing conditional P&L. They are denominator-dependent; dollar profit and drawdown are the business metrics. Daily closing drawdown omits intraday adverse paths and unseen squeezes. No stop, profit take, forecast filter or hindsight selection is added. Holding longer to enter changes the price captured, so the opening gross return is not preserved for delayed fills.', '',
              'Capital estimates sum individual intraday peaks by date, which can overstate coincident peaks. Margin uses a 100% house assumption plus low-price short floors; borrow collateral is shares times the dollar-rounded 102% quote mark. Collateral is restricted proceeds, not a second trading expense. Actual account margin and broker concentration requirements can differ. Historical borrow is assumed available: additional names may still be unavailable to short.', '',
              f"Coverage: {doc['coverage']}. The source manifest is private and hash-bound. Provider day-quality flags are counted against event sessions and retained rather than selecting events by data quality after seeing results. Data is partial multi-venue coverage, not consolidated US volume or verified NBBO. A zero-quote gate preceded every new download. Monthly files only batch transport; replay selects each event's exact session and never combines overlapping copies from the same venue.", '',
              'Rule 201 basis: [SEC staff FAQ](https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions-7). Fees: [IBKR US stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php), [SEC 2026 rate advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2). Normal TAF is retained as a forward sensitivity rather than extrapolating the temporary 2026Q4 holiday.', '',
              'The original execution-study designated holdout file remains unread. This newer sample overlaps previously examined adaptive/portfolio research and cannot be presented as an untouched holdout. New event families, validated fills, account borrows and incremental live impact remain the steps that can establish production profitability.', '']
    return '\n'.join(lines)


def dashboard_doc(doc):
    """Small chart payload; every headline statistic still uses daily P&L."""
    models = []
    for model in doc['models']:
        months = {}
        for point in model['series']:
            months[point[0][:7]] = point
        models.append({**model, 'series': [[doc['start'], 0., 0.]]+list(months.values())})
    return {**doc, 'models': models, 'chart_frequency': 'month-end; risk metrics use every session'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['collect', 'collect-monthly', 'retry-daily', 'quality', 'prepare', 'build', 'supplement', 'summarize', 'declare'])
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--dashboard', type=Path)
    args = parser.parse_args()
    local = args.source_root/'_system/data/reverse_splits/local'
    if not args.work.resolve().is_relative_to(local.resolve()):
        parser.error('Private research must stay in the ignored local workbench')
    if args.command == 'declare':
        if (args.work/'protocol.json').exists():
            raise SystemExit('Protocol already declared; do not overwrite')
        write(args.work/'protocol.json', {'declared_at': datetime.now(timezone.utc).isoformat(), 'protocol': PROTOCOL})
    elif args.command in ('collect', 'collect-monthly', 'retry-daily'):
        collect(args.source_root, args.work, monthly=args.command == 'collect-monthly', retry_daily=args.command == 'retry-daily')
    elif args.command == 'prepare':
        prepare(args.source_root, args.work)
    elif args.command == 'quality':
        quality(args.source_root, args.work)
    else:
        if not args.out:
            parser.error('--out required')
        if args.command == 'summarize':
            doc = read(args.out)
            days = [r[0] for r in doc['models'][0]['series']]
            doc['models'] = [{**m, **metrics(read(args.work/f"{m['id']}.decisions.local.json"), days)} for m in doc['models']]
            write(args.out, doc)
        else:
            doc = supplement(args.source_root, args.work, args.out) if args.command == 'supplement' else build(args.source_root, args.work, args.out)
        if args.report:
            args.report.write_text(report(doc), encoding='utf-8')
        if args.dashboard:
            write(args.dashboard, dashboard_doc(doc))


if __name__ == '__main__':
    main()
