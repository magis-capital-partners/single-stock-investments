"""Reproduce the adaptive backtest's instantaneous entry-depth statistic offline.

Reads frozen local caches through the existing hash-verifying loader. No network,
broker access or strategy changes. Full event rows stay in ignored local storage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import statistics


def capacity(midpoint, bid_levels, limit_fraction=.03):
    """Capacity in midpoint-valued shares, distinct from cash at bid prices."""
    if not math.isfinite(midpoint) or midpoint <= 0:
        raise ValueError('A finite, positive midpoint is required')
    if not 0 <= limit_fraction < 1:
        raise ValueError('Invalid price limit fraction')
    floor = midpoint * (1 - limit_fraction)
    levels = [(p, q) for p, q in bid_levels if p >= floor]
    shares = sum(q for _, q in levels)
    return {'midpoint': midpoint, 'price_floor': floor,
            'shares_within_limit': shares, 'capacity_at_midpoint': midpoint * shares,
            'cash_if_swept': sum(p * q for p, q in levels)}


def summarize(rows):
    ordered = sorted(rows, key=lambda r: (r['capacity_at_midpoint'], r['date'], r['ticker']))
    if not ordered:
        raise ValueError('No capacity observations')
    n = len(ordered)
    middle = [ordered[(n-1)//2]] if n % 2 else ordered[n//2-1:n//2+1]
    return {'events': n, 'first_date': min(r['date'] for r in rows),
            'last_date': max(r['date'] for r in rows),
            'median_capacity_at_midpoint': statistics.median(r['capacity_at_midpoint'] for r in rows),
            'median_cash_if_swept': statistics.median(r['cash_if_swept'] for r in rows),
            'middle_observations': middle,
            'snapshot_capacity_at_least': {str(t): sum(r['capacity_at_midpoint'] >= t for r in rows)
                                           for t in (25_000, 50_000, 100_000)}}


def build(source_root):
    spec = importlib.util.spec_from_file_location('short_adaptive_sizing', Path(__file__).with_name('short_adaptive_sizing.py'))
    sizing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sizing)
    rows, _, source = sizing.load_rows(source_root)
    targets = sizing.audit.read(source_root / f'_system/data/reverse_splits/local/execution_research/{sizing.audit.RUN}__quotes_v1/targets.local.json')
    names = {r['key']: r['ticker'] for r in targets}
    observations = [dict(ticker=names[r['key']], date=r['date'],
                         **capacity(r['mid'], r['decision']['bid_levels'], sizing.PROTOCOL['entry_limit_fraction']))
                    for r in rows if sizing.dstart(r['date'])]
    observations.sort(key=lambda r: (r['capacity_at_midpoint'], r['date'], r['ticker']))
    summary = summarize(observations)
    summary['middle_capacity_values'] = [r['capacity_at_midpoint'] for r in summary.pop('middle_observations')]
    doc = {'schema_version': 'short_entry_capacity_audit.v1', 'research_only': True, 'authority': 'none', 'aggregate_only': True,
           'source_run_id': sizing.audit.RUN, 'limit_fraction': sizing.PROTOCOL['entry_limit_fraction'],
           'decision_time': 'scheduled session open + 1 second',
           'formula': 'midpoint * sum(bid shares with bid price >= 0.97 * midpoint)',
           'interpretation': 'Instantaneous cached visible depth, valued at midpoint; not daily capacity, actual proceeds or measured own-order impact.',
           'test_calendar_start': sizing.PROTOCOL['test_start'], 'test_calendar_end': sizing.PROTOCOL['test_end'],
           'summary': summary,
           'sources': {name: sizing.audit.sha(source/name) for name in ('books.local.json', 'paths.local.json', 'manifest.json')}}
    return doc, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--local-out', type=Path, required=True)
    args = parser.parse_args()
    # Per-event licensed-derived evidence must stay in the ignored workbench.
    local_root = (args.source_root/'_system/data/reverse_splits/local').resolve()
    if not args.local_out.resolve().is_relative_to(local_root):
        parser.error('--local-out must be inside the source root research local directory')
    doc, rows = build(args.source_root)
    for path, data in ((args.out, doc), (args.local_out, rows)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(doc['summary'], indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
