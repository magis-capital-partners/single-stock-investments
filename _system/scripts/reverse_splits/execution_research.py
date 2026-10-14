"""Measure execution costs from licensed quotes, separately from daily ranges.

Raw books, individual observations and security joins remain in local/. Public
output contains aggregates only. This study never changes a frozen book, uses
a broker gateway, or treats a displayed book as a guaranteed broker fill.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time

from .config import load_config
from .databento_bars import client_from_env, fetch, is_complete
from .expansion import digest
from .execute import session_open
from .ledger import read_json, write_json


def distribution(values):
    values = sorted(float(v) for v in values if v is not None and math.isfinite(v))
    if not values:
        return {"n": 0, "mean": None, "median": None, "p90": None}
    def percentile(p):
        at = (len(values) - 1) * p
        lo = math.floor(at)
        return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (at - lo)
    return {"n": len(values), "mean": sum(values) / len(values),
            "median": percentile(.5), "p90": percentile(.9)}


def targets(source):
    """Use the published sample, historical auction symbol and venue exactly."""
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS", start="2018-01-01", end="2027-01-01")
    paths = read_json(source / "one_day_paths.local.json", {})
    cohort = {name: {r["event_id"] for r in rows} for name, rows in paths.items()}
    events = {}
    for part in read_json(source / "event_outcomes.parts.json", {})["files"]:
        path = source / part["path"]
        if digest(path) != part["sha256"]:
            raise ValueError("Source event outcomes changed")
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                e = json.loads(line)
                if e["event_id"] in cohort["primary"]:
                    events[e["event_id"]] = e
    case = read_json(source / "post_split_fundamental_60_h1_current_mean.json", {})
    conn = sqlite3.connect((source / "prices.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    auctions = {}
    def auction(ticker, day, point):
        key = ticker, day, point
        if key not in auctions:
            found = conn.execute('SELECT * FROM official_auction_prices WHERE ticker=? AND date=? AND point=?', key).fetchone()
            auctions[key] = dict(found) if found else None
        return auctions[key]
    rows = {}
    def add(key, ticker, day, event_id, issuer):
        op = auction(ticker, day, "open")
        cl = auction(ticker, day, "close")
        if not op or not cl:
            raise ValueError("Published observed path lacks historical auction identity")
        if op["symbol"] != cl["symbol"] or op["dataset"] != cl["dataset"]:
            raise ValueError("Auction identity differs within a session")
        opened = session_open(day).astimezone(timezone.utc)
        closed = cal.session_close(day).to_pydatetime()
        rows[key] = {"key": key, "ticker": ticker, "symbol": op["symbol"],
                     "dataset": op["dataset"], "date": day, "event_id": event_id,
                     "issuer": issuer, "open": op["price"], "close": cl["price"],
                     "opened": opened.isoformat(), "closed": closed.isoformat(),
                     "cohorts": [name for name, ids in cohort.items() if event_id in ids]}
    for eid, e in events.items():
        outcome = next(o for o in e["outcomes"] if o["cohort"] == "ex_plus_1_h1")
        add(eid, e.get("database_ticker", e["ticker"]), outcome["entry_date"], eid, e["issuer"])
    for p in case["positions"]:
        key = p["id"]
        if key not in rows or rows[key]["date"] != p["entry_date"]:
            key += "/account/" + p["entry_date"]
            add(key, p["ticker"], p["entry_date"], p["id"], str(p["cik"]))
        rows[key]["account"] = {k: p[k] for k in ("entry_shares", "raw_price_pnl", "spread_cost", "slippage_cost", "borrow", "commission", "net_pnl", "last_cover_date", "partial_covers", "rate")}
    conn.close()
    return list(rows.values()), case


def requests_for(rows):
    groups = defaultdict(set)
    for row in rows:
        for schema in ("bbo-1s", "mbp-10") if "account" in row else ("bbo-1s",):
            for point in ("open", "close"):
                boundary = datetime.fromisoformat(row["opened" if point == "open" else "closed"])
                start, end = ((boundary - timedelta(seconds=5), boundary + timedelta(seconds=35))
                              if point == "open" else (boundary - timedelta(seconds=35), boundary + timedelta(seconds=2)))
                groups[(row["dataset"], schema, point, start.isoformat(), end.isoformat())].add(row["symbol"])
    requests = []
    for (dataset, schema, point, start, end), symbols in sorted(groups.items()):
        req = dict(dataset=dataset, schema=schema, symbols=sorted(symbols), start=start, end=end)
        rid = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:24]
        requests.append({"id": rid, "point": point, "request": req})
    # Retrieve the account books first; they directly explain the prior result.
    return sorted(requests, key=lambda r: (r["request"]["schema"] != "mbp-10", r["id"]))


def collect(root, requests, *, budget, workers):
    budget_lock = threading.Lock()
    reserved = 0.0
    state = threading.local()
    stop = threading.Event()
    metadata_lock = threading.Lock()
    next_metadata_at = 0.0
    results = []
    def get(item):
        nonlocal reserved, next_metadata_at
        req = item["request"]
        path = root / "raw" / req["dataset"] / req["schema"] / (item["id"] + ".dbn.zst")
        if is_complete(path):
            ok = read_json(path.with_name(path.name.replace(".dbn.zst", ".ok.json")), {})
            if ok["request"] != {k: str(v) for k, v in req.items()}:
                raise ValueError("Cached request identity differs")
            return {**ok, **item, "status": "cached", "file": str(path.relative_to(root)), "sha256": digest(path)}
        if stop.is_set():
            return {**item, "status": "stopped"}
        if not hasattr(state, "client"):
            state.client = client_from_env()
        try:
            # Stay below the provider's 20 metadata requests/second/IP limit.
            with metadata_lock:
                time.sleep(max(0, next_metadata_at - time.monotonic()))
                next_metadata_at = time.monotonic() + 1 / 6
            quote = float(state.client.metadata.get_cost(**req))
            if not math.isfinite(quote) or quote < 0:
                raise ValueError('Invalid provider cost quote')
            # Reserve the quote plus a small rounding allowance before download.
            allowance = max(quote * 1.25, .0001)
            with budget_lock:
                if reserved + allowance > budget or quote > .05:
                    return {**item, "status": "cost_refused", "quoted_usd": quote}
                reserved += allowance
            ok = fetch(state.client, path, max_cost=allowance, quoted_cost=quote, **req)
            return {**ok, **item, "status": "downloaded", "file": str(path.relative_to(root)), "sha256": digest(path)}
        except Exception as exc:
            # Authentication/permission failures end the pull; do not switch keys.
            message = str(exc)
            if any(s in message for s in ("401", "403", "license", "permission", "429")):
                stop.set()
            return {**item, "status": "error", "error": type(exc).__name__ + ": " + message[:350]}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(get, item) for item in requests]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if len(results) % 50 == 0 or len(results) == len(requests):
                print(f"Quote collection: {len(results)}/{len(requests)} windows; "
                      f"{dict(Counter(r['status'] for r in results))}", flush=True)
                write_json(root / "collection.json", results)
    write_json(root / "collection.json", results)
    return results


def snapshot(frame, target, *, sampled):
    """A record available by the decision time; never look forward to a good quote."""
    import pandas as pd
    moment = pd.Timestamp(target)
    prior = frame.loc[frame.index <= moment]
    if not sampled:
        # A complete event's book is usable only after its F_LAST record.
        prior = prior.loc[(prior['flags'].astype(int) & 128) != 0]
    if prior.empty:
        return None, "no_predecision_record"
    row = prior.iloc[-1]
    if int(row['flags']) & (8 | 4):
        return None, 'provider_bad_timestamp_or_book_gap'
    age = (moment - prior.index[-1]).total_seconds()
    if age > 30:
        return None, "record_older_than_30_seconds"
    bid, ask = float(row["bid_px_00"]), float(row["ask_px_00"])
    if not all(math.isfinite(p) and p > 0 for p in (bid, ask)) or ask < bid:
        return None, "invalid_or_crossed_book"
    if int(row["bid_sz_00"]) <= 0 or int(row["ask_sz_00"]) <= 0:
        return None, "empty_book_side"
    book = {"bid": bid, "ask": ask, "mid": (bid + ask) / 2,
            "age_seconds": age, "timestamp": prior.index[-1].isoformat(),
            "bid_size": int(row["bid_sz_00"]), "ask_size": int(row["ask_sz_00"]),
            "sampled": sampled}
    for side in ("bid", "ask"):
        levels = []
        for depth in range(10):
            price = row.get(f"{side}_px_{depth:02d}")
            size = row.get(f"{side}_sz_{depth:02d}", 0)
            if price is not None and math.isfinite(float(price)) and float(price) > 0 and int(size) > 0:
                levels.append((float(price), int(size)))
        if any((a[0] < b[0] if side == "bid" else a[0] > b[0]) for a, b in zip(levels, levels[1:])):
            return None, "nonmonotone_book"
        book[side + "_levels"] = levels
    return book, None


def sweep(book, side, quantity):
    remaining, value = quantity, 0.0
    for price, size in book[side + "_levels"]:
        take = min(remaining, size)
        value += take * price
        remaining -= take
        if remaining <= 0:
            return value / quantity
    return None


def trading_states(cfg, root, rows):
    """Read cached national status evidence; make no network request."""
    import databento as db
    import numpy as np
    import pandas as pd
    binding = hashlib.sha256(json.dumps([(r['key'], r['symbol'], r['date'], r['opened'], r['closed']) for r in rows]).encode()).hexdigest()
    cache = root / 'trading_status.local.json'
    saved = read_json(cache, {})
    if saved.get('binding') == binding and all(digest(Path(s['path'])) == s['sha256'] for s in saved['sources']):
        return saved['states']
    groups = defaultdict(list)
    for row in rows:
        year, month, _ = map(int, row['date'].split('-'))
        groups[f'{year}Q{(month-1)//3+1}'].append(row)
    states, sources = {}, []
    for period, active in sorted(groups.items()):
        p = cfg.databento_dir / 'XNAS.ITCH' / 'status' / (period + '.dbn.zst')
        mapping = p.with_name(period + '.symbology.json')
        if not is_complete(p) or not mapping.exists():
            continue
        symbols = {r['symbol'] for r in active}
        spans = {int(i): [s for s in iv if s['s'] in symbols]
                 for i, iv in read_json(mapping, {}).items() if any(s['s'] in symbols for s in iv)}
        a = db.DBNStore.from_file(str(p)).to_ndarray()
        a = a[np.isin(a['instrument_id'], list(spans))]
        sources.extend({'path': str(f.resolve()), 'sha256': digest(f)} for f in (p, mapping))
        for row in active:
            ids = [i for i, iv in spans.items() if any(s['s'] == row['symbol'] and s['d0'] <= row['date'] < s['d1'] for s in iv)]
            data = a[np.isin(a['instrument_id'], ids)]
            data = np.sort(data, order='ts_recv')
            states[row['key']] = {}
            for point, offsets in [('open', (1, 30)), ('close', (-1,))]:
                boundary = datetime.fromisoformat(row['opened' if point == 'open' else 'closed'])
                for offset in offsets:
                    before = data[data['ts_recv'] <= pd.Timestamp(boundary + timedelta(seconds=offset)).value]
                    result = {}
                    for field in ('is_trading', 'is_short_sell_restricted'):
                        explicit = before[np.isin(before[field], [b'Y', b'N'])]
                        result[field] = explicit[-1][field].decode() if len(explicit) else None
                    states[row['key']][f'{point}/{offset}'] = result
        print('Cached trading-status evidence:', period, len(active), 'paths', flush=True)
    write_json(cache, {'binding': binding, 'sources': sources, 'states': states})
    return states


def observations(root, rows, collection):
    import databento as db
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["dataset"], row["date"])].append(row)
    measured = defaultdict(dict)
    for item in collection:
        if item["status"] not in {"cached", "downloaded"}:
            continue
        path = root / item["file"]
        if digest(path) != item["sha256"]:
            raise ValueError("Quote source changed")
        df = db.DBNStore.from_file(str(path)).to_df()
        if df.empty:
            continue
        req, point = item["request"], item["point"]
        day = datetime.fromisoformat(req["start"]).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat()
        for row in grouped[(req["dataset"], day)]:
            if row["symbol"] not in req["symbols"]:
                continue
            frame = df.loc[df["symbol"] == row["symbol"]].sort_index(kind="stable")
            if frame.empty:
                continue
            boundary = datetime.fromisoformat(row["opened" if point == "open" else "closed"])
            offsets = (1, 30) if point == "open" else (-1,)
            if req['schema'] == 'mbp-10':
                offsets = (1, 1.01, 1.1, 1.5, 30, 30.01, 30.1, 30.5) if point == 'open' else (-1, -.99, -.9, -.5)
            for offset in offsets:
                label = f"{req['schema']}/{point}/{offset}"
                book, reason = snapshot(frame, boundary + timedelta(seconds=offset), sampled=req["schema"] == "bbo-1s")
                measured[row["key"]][label] = {"book": book, "reason": reason}
    write_json(root / "observations.local.json", dict(measured))
    return measured


def combine_routes(rows, measured, routed):
    """Merge displayed depth on explicitly named venues; never call it NBBO."""
    for row in rows:
        if 'account' not in row:
            continue
        for point, offsets in [('open', (1, 1.01, 1.1, 1.5, 30, 30.01, 30.1, 30.5)), ('close', (-1, -.99, -.9, -.5))]:
            for offset in offsets:
                label = f'mbp-10/{point}/{offset}'
                books = [measured.get(row['key'], {}).get(label, {}).get('book')]
                books += [routed.get(row['key'] + '/' + venue, {}).get(label, {}).get('book')
                          for venue in ('ARCX.PILLAR', 'EDGX.PITCH') if venue != row['dataset']]
                books = [book for book in books if book]
                out_label = f'routed-mbp-10/{point}/{offset}'
                if not books:
                    measured[row['key']][out_label] = {'book': None, 'reason': 'no_valid_venue_book'}
                    continue
                book = {'sampled': False, 'venues': len(books), 'age_seconds': max(b['age_seconds'] for b in books)}
                for side in ('bid', 'ask'):
                    levels = defaultdict(int)
                    for source in books:
                        for price, size in source[side + '_levels']:
                            levels[price] += size
                    book[side + '_levels'] = sorted(levels.items(), reverse=side == 'bid')
                    book[side], book[side + '_size'] = book[side + '_levels'][0]
                if book['ask'] < book['bid']:
                    measured[row['key']][out_label] = {'book': None, 'reason': 'crossed_combined_snapshot'}
                    continue
                book['mid'] = (book['bid'] + book['ask']) / 2
                measured[row['key']][out_label] = {'book': book, 'reason': None}
    return measured


def latency_study(rows, measured, states):
    from .capital_risk import margin
    result = []
    for mode in ('mbp-10', 'routed-mbp-10'):
        for offset in (1, 30):
            for milliseconds in (10, 100, 500):
                moves, exclusions = [], Counter()
                for row in rows:
                    if 'account' not in row:
                        continue
                    status = states.get(row['key'], {})
                    if (status.get(f'open/{offset}', {}).get('is_trading') != 'Y'
                        or status.get('close/-1', {}).get('is_trading') != 'Y'
                        or status.get(f'open/{offset}', {}).get('is_short_sell_restricted') != 'N'):
                        exclusions['baseline_trading_or_SSR_not_confirmed'] += 1
                        continue
                    obs = measured.get(row['key'], {})
                    delta = milliseconds / 1000
                    labels = [f'{mode}/open/{offset}', f'{mode}/close/-1',
                              f'{mode}/open/{offset+delta}', f'{mode}/close/{-1+delta}']
                    books = [obs.get(label, {}).get('book') for label in labels]
                    if not all(books):
                        exclusions['missing_baseline_or_delayed_book'] += 1
                        continue
                    q = row['account']['entry_shares']
                    fills = [sweep(b, side, q) for b, side in zip(books, ('bid', 'ask', 'bid', 'ask'))]
                    if any(fill is None for fill in fills):
                        exclusions['insufficient_baseline_or_delayed_depth'] += 1
                        continue
                    entry, exit_, later_entry, later_exit = fills
                    change = entry-later_entry+later_exit-exit_
                    moves.append({'fraction': change/books[0]['mid'], 'margin_fraction':q*change/margin(q,books[0]['mid']),
                                  'dollars': q*change})
                if moves:
                    result.append({'execution_mode': mode, 'entry_seconds_after_open': offset,
                                   'delay_milliseconds': milliseconds, 'pairs': len(moves),
                                   'additional_round_trip_cost': distribution(r['fraction'] for r in moves),
                                   'additional_round_trip_cost_on_margin': distribution(r['margin_fraction'] for r in moves),
                                   'aggregate_additional_usd': sum(r['dollars'] for r in moves),
                                   'adverse_share': sum(r['fraction'] > 0 for r in moves) / len(moves),
                                   'exclusions': dict(exclusions)})
    return result


def analyze(root, rows, measured, case, collection, states=None):
    states = states or {}
    populations = []
    account_cases = []
    details = []
    schemas = ['bbo-1s', 'mbp-10']
    if any(any(k.startswith('routed-mbp-10/') for k in o) for o in measured.values()):
        schemas.append('routed-mbp-10')
    for schema in schemas:
        for offset in (1, 30):
            available = []
            missing = Counter()
            target_rows = rows if schema == "bbo-1s" else [r for r in rows if "account" in r]
            for row in target_rows:
                obs = measured.get(row["key"], {})
                entry = obs.get(f"{schema}/open/{offset}", {})
                exit_ = obs.get(f"{schema}/close/-1", {})
                if not entry.get("book") or not exit_.get("book"):
                    missing[entry.get("reason") or exit_.get("reason") or "missing_source_window"] += 1
                    continue
                e, x = entry["book"], exit_["book"]
                available.append({"row": row, "entry": e, "exit": x,
                                  "entry_spread_fraction": (e["ask"] - e["bid"]) / e["mid"],
                                  "exit_spread_fraction": (x["ask"] - x["bid"]) / x["mid"],
                                  "round_trip_spread_fraction": ((e["mid"] - e["bid"]) + (x["ask"] - x["mid"])) / e["mid"],
                                  "quote_return": 1 - x["ask"] / e["bid"]})
            for cohort in ("primary", "eligible", "fundamental") if schema == "bbo-1s" else ("account",):
                wanted = [r for r in target_rows if cohort in r['cohorts'] or cohort == "account" and "account" in r]
                usable = [o for o in available if o["row"] in wanted]
                capacity = []
                for dollars in (125, 500, 1250):
                    counts = Counter()
                    for o in usable:
                        q = math.floor(dollars / o["entry"]["bid"])
                        if q <= 0:
                            counts["less_than_one_share"] += 1
                        elif sweep(o['entry'], 'bid', q) is None:
                            counts["insufficient_entry_depth"] += 1
                        elif sweep(o['exit'], 'ask', q) is None:
                            counts["insufficient_exit_depth"] += 1
                        else:
                            counts["both_sides_fit"] += 1
                    capacity.append({"notional_usd": dollars, **dict(counts)})
                populations.append({"schema": schema, "entry_seconds_after_open": offset, "cohort": cohort,
                                    "target_events": len(wanted), "paired_quotes": len(usable),
                                    "missing_pairs": len(wanted) - len(usable),
                                    "issuers": len({o["row"]["issuer"] for o in usable}),
                                    "entry_full_spread": distribution(o['entry_spread_fraction'] for o in usable),
                                    "exit_full_spread": distribution(o['exit_spread_fraction'] for o in usable),
                                    "round_trip_half_spreads": distribution(o['round_trip_spread_fraction'] for o in usable),
                                    "multiple_venues_at_both_times": sum(o['entry'].get('venues', 1) >= 2 and o['exit'].get('venues', 1) >= 2 for o in usable),
                                    "quote_price_return_before_borrow_commission_impact": distribution(o['quote_return'] for o in usable),
                                    "capacity": capacity})
            if schema in {"mbp-10", "routed-mbp-10"}:
                for extra_bps in (0, 5, 10, 25):
                    taken, failed, total = [], Counter(), Counter()
                    for o in available:
                        row, e, x = o['row'], o['entry'], o['exit']
                        a = row['account']
                        entry_state = states.get(row['key'], {}).get(f'open/{offset}', {})
                        exit_state = states.get(row['key'], {}).get('close/-1', {})
                        if entry_state.get('is_trading') != 'Y' or exit_state.get('is_trading') != 'Y':
                            failed['trading_not_confirmed_at_both_times'] += 1
                            continue
                        if entry_state.get('is_short_sell_restricted') != 'N':
                            failed['SSR_restricted_or_unknown_for_marketable_short'] += 1
                            continue
                        q = a['entry_shares']
                        entry = sweep(e, 'bid', q)
                        exit_ = sweep(x, 'ask', q)
                        if entry is None or exit_ is None:
                            failed['insufficient_entry_depth' if entry is None else 'insufficient_exit_depth'] += 1
                            continue
                        quote_spread = q * ((e['mid'] - e['bid']) + (x['ask'] - x['mid']))
                        depth = q * ((e['bid'] - entry) + (exit_ - x['ask']))
                        timing = q * ((row['open'] - e['mid']) + (x['mid'] - row['close']))
                        additional = q * (entry + exit_) * extra_bps / 10000
                        actual_price_pnl = q * (entry - exit_)
                        new_commission = sum(min(max(1, q * .005), q * fill * .01) for fill in (entry, exit_))
                        net = actual_price_pnl - additional - a['borrow'] - new_commission
                        raw_same_day = q * (row['open'] - row['close'])
                        total.update({"raw_auction_pnl": raw_same_day, "quoted_half_spread_cost": quote_spread,
                                      "displayed_depth_cost": depth, "timing_difference": timing,
                                      "additional_slippage": additional, "borrow": a['borrow'],
                                      "commission": new_commission, "net": net,
                                      "previous_spread_cost": a['spread_cost'], "previous_slippage_cost": a['slippage_cost'],
                                      "previous_net_same_entries": a['net_pnl'], "previous_exit_path_pnl_difference": a['raw_price_pnl']-raw_same_day,
                                      "entry_auction_notional": q * row['open']})
                        assert abs(raw_same_day - quote_spread - depth - timing - actual_price_pnl) < 1e-5
                        taken.append(row['key'])
                        if extra_bps == 0:
                            details.append({"key": row['key'], "entry_offset": offset, "shares": q,
                                            "quoted_half_spread_cost": quote_spread, "displayed_depth_cost": depth,
                                            "timing_difference": timing, "entry_vwap": entry, "exit_vwap": exit_, "net": net})
                    account_cases.append({"execution_mode": schema, "entry_seconds_after_open": offset, "additional_bps_per_side": extra_bps,
                                          "observed_spread_depth_fraction": (total['quoted_half_spread_cost'] + total['displayed_depth_cost']) / total['entry_auction_notional'] if total['entry_auction_notional'] else None,
                                          "target_positions": sum('account' in r for r in rows),
                                          "paired_books": len(available), "both_sides_fit": len(taken),
                                          "missing_or_invalid_books": sum('account' in r for r in rows) - len(available),
                                          "unfilled_depth": dict(failed), "totals": dict(total),
                                          "status": "fixed_positions_partial_coverage_conditional" if len(taken) < sum('account' in r for r in rows) else "fixed_positions_conditional"})
    write_json(root / "fixed_positions.local.json", details)
    old = case['metrics']['costs']
    summary = {"schema_version": "execution_evidence.v1", "built_at": datetime.now(timezone.utc).isoformat(),
               "source_run_id": root.name.split('__')[0], "provider": "Databento",
               "datasets": sorted({r['dataset'] for r in rows} | {i['request']['dataset'] for i in collection}),
               "sample": {"primary_events": sum('primary' in r['cohorts'] for r in rows), "account_positions": len(case['positions'])},
               "collection": {"requests": len(collection), "statuses": dict(Counter(r['status'] for r in collection)),
                              "quoted_usd": sum(r.get('quoted_usd', 0) for r in collection),
                              "bytes": sum(r.get('bytes', 0) for r in collection)},
               "populations": populations, "fixed_position_scenarios": account_cases,
               "latency_quote_changes": latency_study(rows, measured, states),
               "status_evidence": {'provider': 'Cached Nasdaq national trading and SSR status',
                                   'paths': len(states), 'account_requires_trading_Y_and_SSR_N': True},
               "previous_account": {"positions": len(case['positions']), "gross_price_pnl": old['raw_price_pnl'],
                                    "spread_cost": old['spread_cost'], "additional_slippage": old['slippage_cost'], "net": case['metrics']['net']},
               "method": "Historical listing-venue quotes at 1 and 30 seconds after the open; cover quotes one second before the scheduled close, including early closes. Use records available by each decision time, at most 30 seconds old. Require completed MBP events and reject provider bad-timestamp/book-gap flags. Bid for selling, ask for covering. Depth study sweeps up to ten displayed levels for the original position sizes. No daily-range proxy or tick-floor substitute.",
               "limits": ["Listing-venue quotes are not consolidated NBBO and may show wider spreads than a smart router can access.",
                          "The multi-venue sensitivity combines available books among the listing venue, NYSE Arca and Cboe EDGX; it can fall back to a single valid venue. Counts of pairs with multiple venues at both times are reported. This is a subset of venues, not full NBBO, and assumes access to their displayed liquidity.",
                          "Displayed quotes and depth estimate instantaneous execution costs; they do not establish broker fills, queue outcomes, latency or dynamic market impact. Account comparisons also require affirmative cached Nasdaq trading status at both times and unrestricted SSR at entry. Venue-specific order and auction eligibility still require review.",
                          "Sampled BBO is rounded to one-second boundaries. Event-level MBP-10 is used for the account study.",
                          "Continuous trading near the auctions uses different prices and times from actual auction participation. Timing differences are reported separately from spread and book depth.",
                          "Comparisons preserve the old entry selection and share sizes, use a full same-session cover where displayed depth fits, and retain assumed borrowing. The previous volume-cap model delayed part of six covers; its different exit-path P&L is recorded separately. This study does not replay margin or prove an approved locate.",
                          "Missing exit books and insufficient exit depth remain disclosed. Complete-pair subsets are not a full-account net-profit estimate.",
                          "Additional 5/10/25bp slippage per side is an uncalibrated latency/impact sensitivity; zero-extra-cost estimates only the displayed static book."]}
    summary['limits'].append('Latency diagnostics compare displayed execution-price changes after 10/100/500ms, using the same quantities on both legs. They measure market movement without our orders and do not estimate our causal market impact, broker latency distribution or guaranteed delayed fills.')
    write_json(root / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--max-cost', type=float, default=0)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--routing', action='store_true', help='Also collect listing + Arca + EDGX depth for original entries')
    parser.add_argument('--intraday', action='store_true', help='Also collect regular-session minute bars for tail diagnostics')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args(argv)
    cfg = load_config()
    source = args.source_run.resolve()
    root = cfg.local_dir / 'execution_research' / (source.name + '__quotes_v1')
    root.mkdir(parents=True, exist_ok=True)
    rows, case = targets(source)
    requests = requests_for(rows)
    write_json(root / 'targets.local.json', rows)
    write_json(root / 'requests.json', requests)
    print(f"Research targets: {len(rows)} events/account paths, {len(requests)} windows", flush=True)
    if args.offline:
        collection = read_json(root / 'collection.json', [])
    else:
        collection = collect(root, requests, budget=args.max_cost, workers=args.workers)
    expected = {item['id']: item['request'] for item in requests}
    for item in collection:
        req = expected[item['id']]
        if item['request'] not in (req, {k: str(v) for k, v in req.items()}):
            raise ValueError('Collection request differs from the declared request')
        item['request'] = req
    write_json(root / 'collection.json', collection)
    measured = observations(root, rows, collection)
    routing_root = root / 'routing'
    if args.routing and not args.offline:
        route_rows = [{**row, 'key': row['key'] + '/' + venue, 'dataset': venue}
                      for row in rows if 'account' in row
                      for venue in ('ARCX.PILLAR', 'EDGX.PITCH') if venue != row['dataset']]
        route_requests = [r for r in requests_for(route_rows) if r['request']['schema'] == 'mbp-10']
        routing_root.mkdir(exist_ok=True)
        write_json(routing_root / 'targets.local.json', route_rows)
        write_json(routing_root / 'requests.json', route_requests)
        collect(routing_root, route_requests, budget=args.max_cost, workers=args.workers)
    route_collection = read_json(routing_root / 'collection.json', [])
    if route_collection:
        route_rows = read_json(routing_root / 'targets.local.json', [])
        route_measured = observations(routing_root, route_rows, route_collection)
        measured = combine_routes(rows, measured, route_measured)
        collection += [{**i, 'file': 'routing/' + i['file']} if i.get('file') else i for i in route_collection]
    states = trading_states(cfg, root, rows)
    summary = analyze(root, rows, measured, case, collection, states)
    from .capital_risk import build_capital_risk, intraday_requests
    intraday_root = root / 'intraday'
    if args.intraday and not args.offline:
        intraday_root.mkdir(exist_ok=True)
        bar_requests = intraday_requests(rows)
        write_json(intraday_root / 'requests.json', bar_requests)
        collect(intraday_root, bar_requests, budget=args.max_cost, workers=args.workers)
    summary['capital_risk'] = build_capital_risk(cfg, root, rows, measured, states, summary)
    write_json(root / 'summary.json', summary)
    manifest = {"source_run": source.name, "source_manifest_sha256": digest(source / 'manifest.json'),
               "account_source_sha256": digest(source / 'post_split_fundamental_60_h1_current_mean.json'),
               "source_code_sha256": digest(Path(__file__)), "targets_sha256": digest(root / 'targets.local.json'),
               "collection_sha256": digest(root / 'collection.json'), "summary_sha256": digest(root / 'summary.json')}
    manifest['source_code'] = [{'path': p.name, 'sha256': digest(p)} for p in (Path(__file__), Path(__file__).with_name('databento_bars.py'), Path(__file__).with_name('capital_risk.py'), Path(__file__).with_name('realism.py'))]
    if route_collection:
        manifest['routing_collection_sha256'] = digest(routing_root / 'collection.json')
        manifest['routing_targets_sha256'] = digest(routing_root / 'targets.local.json')
    manifest['trading_status_sha256'] = digest(root / 'trading_status.local.json')
    if (intraday_root / 'collection.json').exists():
        manifest['intraday_collection_sha256'] = digest(intraday_root / 'collection.json')
    write_json(root / 'manifest.json', manifest)
    if args.publish:
        write_json(cfg.ledger_dir / 'execution_research.json', summary)
        write_json(cfg.ledger_dir / 'execution_research_manifest.json', {**manifest, 'public_contains_raw_market_data': False})
    print(json.dumps({'collection': summary['collection'],
                      'quote_samples': [{'sample': r['cohort'], 'schema': r['schema'], 'entry_seconds': r['entry_seconds_after_open'], 'pairs': r['paired_quotes'], 'mean_spread': r['round_trip_half_spreads']['mean']} for r in summary['populations']],
                      'account': [{'mode': r['execution_mode'], 'entry_seconds': r['entry_seconds_after_open'], 'positions': r['both_sides_fit'], 'extra_bps': r['additional_bps_per_side'], 'net': r['totals'].get('net')} for r in summary['fixed_position_scenarios']]}, indent=1), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
