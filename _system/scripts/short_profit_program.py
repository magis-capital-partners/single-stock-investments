"""Build the SSI short-alpha strategy lab from cached/public source evidence.

Offline by default. Raw prices, broker evidence and full filings stay local.
The published dataset contains public filing facts and aggregate research only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from _system.scripts.reverse_splits.profit_data import (  # noqa: E402
    VERSION, attach_financials, audit_queue, cached_financings, digest, fingerprint,
    import_studies, publish_events, read, write,
)

PROTOCOL = {
    'version': 'short_profit_program.v1', 'hypotheses': ['H23', 'H24', 'H25', 'H26'],
    'research_only': True, 'authority': 'none', 'nav': 10_000_000,
    'targets': [25_000, 50_000], 'horizons': [2, 5, 10, 20],
    'sizing': ['fixed', 'net_edge'], 'cases': ['bear', 'base', 'bull'],
    'H23': 'Compare financing disclosures, plus dated cash pressure, plus reconciled saleable supply, plus both. Extracted financing contexts remain unverified; no future financing or eventual failure selects entry.',
    'H24': 'Compare first provider-defined deficiency episodes, equity/market-value deficiencies, and those plus cash pressure. Repeated notices remain in the source denominator, never independent overlapping positions.',
    'H25': 'Compare fixed targets with shrunk prior-other-issuer gross forecasts and size-dependent costs. Forecast labels must finish before the event clock with a 20-session embargo. At least 30 prior other issuers; no fallback future return.',
    'H26': 'Retain unsupported patient covers as short liabilities; replay future daily cover opportunities with volume limits, carry, margin and explicit stale marks. Compare time exits, a 20% stop/target comparator and progressive covers.',
    'entry': 'First cached exchange session opening after known_at plus five minutes. No private notice-date entry or pre-publication gap profit. Daily OHLC4 reference and capacity are conditional execution proxies, not broker fills.',
    'liquidity': 'Entry budget uses prior 20-session volume; actual entry/cover quantity also capped at 5% of that session recorded volume. Restricted/unknown SSR entry uses case capture. Incomplete venue coverage is not multiplied by guessed off-exchange flow.',
    'exit': 'Time exit after 2/5/10/20 sessions including entry. Residual cover shares remain open across later sessions, accrue obligations and remain in marked NAV until actually modeled covered. No zero-price terminal cover.',
    'costs': 'Three joint execution+borrow cases. Size-dependent static-book-anchored cost sensitivity, per-share child commissions, dated regulatory fee schedule, ACT/360 rounded collateral, marginal tiered short credit; measured rates override assumptions only with timely evidence.',
    'risk': 'One open position per issuer. +200% price-shock loss reserve capped at 2% of initial hypothetical NAV; 20% NAV margin headroom reserve; 100% house margin sensitivity plus low-price floors. This does not change live account rules.',
    'statistics': 'Complete calendar marked equity including unresolved liabilities. Monthly and daily net dollars, CAGR on declared $10m, drawdown, Calmar, Sharpe, Sortino, expected shortfall, worst issuer/day, fees, carry, credit, cover completion and collateral/margin.',
    'monte_carlo': 'Seeded three-month calendar-block bootstrap of daily portfolio cash/mark paths, retaining within-block issuer/overlap/cost dependence. Five years, 1000 trials. Parameter/recall/illiquidity stress is reported separately. No future-tail probability claim.',
    'validation': 'Previously inspected and provider-prepared histories are exploratory development. Chronological and issuer-separated diagnostics; no untouched backtest claim. Designated execution holdout remains unread. Forward registry freezes estimates before entry and imports outcomes separately.',
    'budget': {'new_paid_downloads_usd': 0, 'broker_connections': False, 'orders': False, 'theta_access': False},
}


def declare(work):
    path = Path(work) / 'protocol.json'
    spec = {'protocol': PROTOCOL, 'sha256': fingerprint(PROTOCOL)}
    if path.exists():
        existing = read(path)
        if existing['sha256'] != spec['sha256']: raise ValueError('Frozen protocol changed: create a new version')
        return existing
    spec['declared_at'] = datetime.now(timezone.utc).isoformat()
    write(path, spec)
    return spec


def ingest(args):
    frozen = declare(args.work)
    events, aggregates, sources = import_studies(args.study_source)
    filings, coverage, text_hash = cached_financings(args.source_root, max_files=args.max_filings)
    events += filings
    print(f'Loaded {len(events)} event records; SEC financing contexts {len(filings)}', flush=True)
    financials = attach_financials(events, args.source_root, args.work)
    events.sort(key=lambda e: (e.get('known_at') or '9999', e['id']))
    write(args.work / 'events.local.json', events)
    write(args.work / 'study_aggregates.json', aggregates)
    manifest = {'schema_version': VERSION, 'protocol_sha256': frozen['sha256'], 'source_inputs': sources,
        'cached_text_manifest_sha256': text_hash, 'source_coverage': coverage, 'financial_coverage': financials,
        'event_counts': dict(Counter(e['family'] for e in events)), 'events_sha256': digest(args.work / 'events.local.json'),
        'new_paid_downloads_usd': 0, 'raw_market_data_published': False}
    write(args.work / 'source_manifest.json', manifest)
    write(args.work / 'review_queue.json', audit_queue(events))
    print('Financial coverage:', financials, flush=True)
    return events, aggregates, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['ingest', 'build', 'publish', 'declare','import','evidence','collect','repair-patient'])
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--study-source', type=Path)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / '_system/data/reverse_splits/profit_program')
    parser.add_argument('--dashboard', type=Path, default=ROOT / 'dashboard/data/short_profit_program')
    parser.add_argument('--max-filings', type=int, default=25000)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--max-requests',type=int,default=200)
    parser.add_argument('--since',default='2026-10-14')
    args = parser.parse_args(argv)
    args.work = args.work or args.source_root / '_system/data/reverse_splits/local/profit_program/20261022_v1'
    args.study_source = args.study_source or args.source_root / '_system/data/reverse_splits/local/literature_audit_2026-10-21/sources/practitioner_pack/practitioner/microcapledger'
    if args.command == 'declare':
        print(declare(args.work)['sha256']); return
    if args.command in ('import','evidence','collect'):
        from _system.scripts.reverse_splits.profit_evidence import import_file,status,collect_public
        if args.command=='import':
            if not args.input:parser.error('--input required')
            print(import_file(args.input,args.work));return
        if args.command=='evidence':print(status(args.work));return
        from _system.scripts.reverse_splits.config import load_config
        events=read(args.work/'events.local.json')
        ciks=sorted({e['cik'] for e in events},key=lambda c:fingerprint(c))[:100]
        cfg=load_config()
        result=collect_public(args.work,ciks=ciks,user_agent=cfg.section('edgar')['user_agent'],maximum=args.max_requests,since=args.since)
        print({'records':len(result['records']),'failures':len(result['failures']),'requests':result['requests']});return
    if args.command == 'ingest': ingest(args); return
    if args.command == 'repair-patient':
        from _system.scripts.reverse_splits.profit_patient import build_patient
        build_patient(args);return
    if args.command == 'build':
        if not (args.work / 'events.local.json').exists(): ingest(args)
        from _system.scripts.reverse_splits.profit_replay import build
        build(args)
        from _system.scripts.reverse_splits.profit_patient import build_patient
        build_patient(args)
    if args.command in ('build', 'publish'):
        from _system.scripts.reverse_splits.profit_publish import publish
        publish(args)


if __name__ == '__main__': main()
