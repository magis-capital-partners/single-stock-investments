#!/usr/bin/env python3
"""Reinterpret the published event feed using local evidence; preserve other catalogs.

No market-data access, downloads, valuation changes or trading connections.
Use --apply to publish and --report PATH to save the before/after audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import subprocess
from pathlib import Path

from atomic_io import write_json_if_changed
import build_insights as builder
from event_triage import triage_events
from filing_review import pct_change
from reconcile_insights_event_summary import reconciled_manifest
from security_profiles import security_profile
from xbrl_context import contextual_metrics

ROOT = Path(__file__).resolve().parents[2]


def refresh_filing(event: dict, root: Path, cache: dict) -> dict:
    event = deepcopy(event)
    v = event.get('verification') or {}
    ref = event.get('source_filing_ref') or v.get('source_filing_ref')
    if not ref or str(ref).startswith(('http:', 'https:')):
        return event
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.suffix.lower() not in {'.htm', '.html'}:
        return event
    if ref not in cache:
        identity = security_profile(event['ticker'], root)
        cache[ref] = contextual_metrics(path.read_text(encoding='utf-8', errors='ignore'),
            period_end=v.get('period_end'), expected_cik=identity.get('cik'))
    metric = cache[ref].get(event.get('metric_name'))
    if not metric:
        return event
    current, prior = metric['current'], metric['prior']
    change = pct_change(current, prior)
    profile = security_profile(event['ticker'], root)
    label = builder.METRIC_LABELS.get(event['metric_name'], event['metric_name'].replace('_', ' ').title())
    if event['metric_name'] == 'net_income' and profile['economic_profile'].endswith('_fund'):
        label = 'Net change in assets from operations'
    if prior is None:
        title = f'{label}: comparable prior period unavailable'
    elif current * prior < 0:
        title = f"{label} turned {'negative' if current < 0 else 'positive'}"
    elif change is None:
        title = f'{label}: prior value is zero'
    else:
        title = f"{label} {'up' if change > 0 else 'down'} {abs(change):.0f}%"
    event.update(title=title, prior_value=prior, current_value=current, change_pct=change,
        direction=builder.metric_direction(event['metric_name'], change) if change is not None else 'neutral',
        confidence='high' if metric['parser_confidence'] == 'high' else 'med',
        summary=f"{label}: {prior if prior is not None else 'unavailable'} to {current:,.1f} ({metric['unit']})." +
            (' Values crossed zero; the percentage change is not a useful comparison.' if prior is not None and current * prior < 0 else ''),
        verification={**v, **{key: metric.get(key) for key in (
            'unit', 'context_verified', 'current_period', 'prior_period', 'scope', 'parser_confidence', 'parser_flags', 'extract_snippet', 'all_values', 'comparison')},
            'current_value': current, 'prior_value': prior})
    return event


def audit(events: list[dict]) -> dict:
    signals = [e for e in events if e.get('tier') == 'signal' and e.get('feed_eligible')]
    financial = {'net_income', 'revenues', 'revenue', 'eps_basic', 'eps_diluted', 'operating_income', 'operating_cash_flow', 'cfo'}
    fund_errors = [e for e in signals if security_profile(e.get('ticker', ''))['economic_profile'].endswith('_fund') and e.get('metric_name') in financial]
    wrong_dates = [e for e in signals if e.get('source') == 'filing' and (e.get('verification') or {}).get('filing_date') and e.get('published_at') != e['verification']['filing_date']]
    unverified_ownership = [e for e in signals if e.get('source') == 'insider' and
        not (e.get('issuer_cik') if e.get('event_type') == 'form4_transaction' else e.get('constituent_identity_verified'))]
    return {'event_count': len(events), 'tiers': dict(Counter(e.get('tier') for e in events)),
        'fund_accounting_signals': len(fund_errors), 'publication_date_errors_in_signals': len(wrong_dates),
        'unverified_ownership_signals': len(unverified_ownership),
        'top_twenty': [{k: e.get(k) for k in ('id', 'ticker', 'title', 'tier', 'decision_priority', 'published_at')}
            for e in sorted(signals, key=lambda e: e.get('decision_priority', 0), reverse=True)[:20]]}


def refresh(events: list[dict], root: Path = ROOT) -> tuple[list[dict], dict]:
    cache = {}
    prepared = []
    for original in events:
        event = refresh_filing(original, root, cache) if original.get('source') == 'filing' else deepcopy(original)
        # Recompute grouping and decisions under the new interpretation; inherited
        # score floors and generic explanations are not independent evidence.
        for key in ('template_id', 'story_id', 'superseded_by', 'superseded_penalty', 'materiality_floor', 'raw_materiality', 'security_profile'):
            event.pop(key, None)
        if event.get('source') == 'insider' and event.get('event_type') == 'form4_transaction' and not event.get('issuer_cik'):
            event['title'] = 'Ownership activity: issuer verification required'
            event['direction'] = 'neutral'
        prepared.append(event)
    result, summary = triage_events(prepared)
    return result, {'before': audit(events), 'after': audit(result), 'triage_summary': summary,
                    'primary_filings_revalidated': len(cache)}


def evaluate_feedback(events: list[dict], feedback: dict) -> dict:
    by_id = {e.get('id'): e for e in events}
    labels = feedback.get('labels') or []
    matched = [label for label in labels if label.get('id') in by_id]
    violations = [label['id'] for label in matched if label.get('reason') in {'wrong_company', 'wrong_interpretation', 'already_known'} and by_id[label['id']].get('tier') == 'signal']
    return {'labels': len(labels), 'matched_labels': len(matched), 'remaining_signal_disagreements': violations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--feedback', type=Path, help='Exported browser flags; evaluate without treating them as verified facts.')
    parser.add_argument('--baseline-ref', help='Compare with this committed event shard rather than the current local feed.')
    args = parser.parse_args()
    folder = ROOT / 'dashboard/data/insights'
    shard = json.loads((folder / 'events.json').read_text(encoding='utf-8'))
    old_events = shard['events']
    # Rebuild the retained ownership stories from repaired local SEC rows.
    references = {e.get('evidence_ref') for e in old_events if e.get('event_type') == 'form4_transaction'}
    front, holdings = builder.portfolio_tickers(), builder.our_holdings_tickers()
    records = [r for r in builder.from_insider_transactions(front, holdings_tickers=holdings) if r.get('evidence_ref') in references]
    repaired = builder.events_from_records(records, front, holdings, builder.portfolio_company_hints(), builder.portfolio_identity_meta())
    repaired_refs = {e.get('evidence_ref') for e in repaired if e.get('issuer_cik')}
    staged = [e for e in old_events if not (e.get('event_type') == 'form4_transaction' and e.get('evidence_ref') in repaired_refs)]
    staged.extend(e for e in repaired if e.get('evidence_ref') in repaired_refs)
    events, report = refresh(staged)
    report['before'] = audit(old_events)
    report['ownership_stories_repaired'] = len(repaired_refs)
    if args.baseline_ref:
        baseline = subprocess.run(['git', 'show', f'{args.baseline_ref}:dashboard/data/insights/events.json'], cwd=ROOT,
                                  capture_output=True, text=True, encoding='utf-8', check=True)
        report['before'] = audit(json.loads(baseline.stdout)['events'])
        report['baseline_ref'] = args.baseline_ref
    if args.feedback:
        report['review_feedback'] = evaluate_feedback(events, json.loads(args.feedback.read_text(encoding='utf-8')))
    report['generated_at'] = datetime.now(timezone.utc).isoformat()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        write_json_if_changed(args.report, report)
    if args.apply:
        stamp = report['generated_at']
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        write_json_if_changed(folder / 'events.json', {**shard, 'events': events, 'events_by_ticker': builder.events_by_ticker(events), 'generated_at': stamp}, indent=None)
        manifest = reconciled_manifest(manifest, events)
        manifest['provenance']['event_relevance_version'] = 1
        manifest['provenance']['event_relevance_refreshed_at'] = stamp
        write_json_if_changed(folder / 'manifest.json', manifest, indent=None)
        # Some local/full builders retain the monolith; update only the event slice.
        monolith = ROOT / 'dashboard/data/insights.json'
        if monolith.exists():
            doc = json.loads(monolith.read_text(encoding='utf-8'))
            doc.update(events=events, events_by_ticker=builder.events_by_ticker(events))
            doc = reconciled_manifest(doc, events)
            write_json_if_changed(monolith, doc, indent=None)
    print(json.dumps({key: value for key, value in report.items() if key not in {'before', 'after'}}, indent=2))
    print('Before:', {k:v for k,v in report['before'].items() if k != 'top_twenty'})
    print('After: ', {k:v for k,v in report['after'].items() if k != 'top_twenty'})


if __name__ == '__main__':
    main()
