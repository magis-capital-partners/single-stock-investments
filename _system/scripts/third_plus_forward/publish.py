"""Allowlisted dashboard projection; private orders and identifiers never travel."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from statistics import median
from pathlib import Path

from . import journal as J
from .engine import trade_diagnostics
from .policy import ROOT, canonical, sha, stamp, write


def quantile(values, q):
    values = sorted(values)
    return values[max(0, min(len(values)-1, math.ceil(len(values)*q)-1))] if values else None


def aggregate(rows, enrollments, policy, now, environment):
    trades = [dict(trade_diagnostics(rows, e, now, environment), issuer_id=e['issuer_id']) for e in enrollments if e['decision'] == 'observe']
    closed = [t for t in trades if t['closed']]
    profit = sum(t['net_marked_pnl'] or 0 for t in closed)
    issuer_pnls = defaultdict(float)
    for t in closed:
        issuer_pnls[t['issuer_id']] += t['net_marked_pnl'] or 0
    best5 = sum(sorted((v for v in issuer_pnls.values() if v > 0), reverse=True)[:5])
    concentration = best5/profit if profit > 0 else None
    metric = lambda key: [t[key] for t in trades if t[key] is not None]
    entry_slip = median(metric('entry_shortfall_bps')) if metric('entry_shortfall_bps') else None
    cover_slip = median(metric('cover_shortfall_bps')) if metric('cover_shortfall_bps') else None
    delay = quantile(metric('cover_delay_sessions'), .9)
    aprs = [r['record']['apr'] for r in rows if r['record']['kind'] == 'borrow' and r['record'].get('policy_id') == policy['id'] and r['record'].get('apr') is not None]
    limits = policy['review']
    checks = {
        'closed_positions': len(closed) >= limits['minimum_closed_positions'],
        'closed_issuers': len(issuer_pnls) >= limits['minimum_closed_issuers'],
        'entry_shortfall': entry_slip is not None and entry_slip <= limits['maximum_median_entry_shortfall_bps'],
        'cover_shortfall': cover_slip is not None and cover_slip <= limits['maximum_median_cover_shortfall_bps'],
        'cover_delay': delay is not None and delay <= limits['maximum_p90_cover_delay_sessions'],
        'unresolved': sum(t['overdue'] for t in trades) <= limits['maximum_unresolved_positions'],
        'borrow_cost': bool(aprs) and max(aprs) <= limits['maximum_borrow_apr'],
        'net_after_costs': bool(closed) and profit > limits['minimum_net_after_costs'],
        'concentration': concentration is not None and concentration <= limits['maximum_best_five_profit_fraction'],
        'cost_evidence': bool(closed) and all(t['borrow_recorded'] and t['locate_recorded'] for t in closed),
    }
    return {'environment': environment, 'entered': sum(t['entered'] for t in trades), 'closed': len(closed),
            'closed_issuers': len(issuer_pnls), 'no_fills_observed': sum(t['no_fill_observed'] for t in trades),
            'unresolved': sum(t['overdue'] for t in trades),
            'net_closed_pnl': profit if closed else None,
            'median_fill_fraction': median(metric('entry_fill_fraction')) if metric('entry_fill_fraction') else None,
            'median_borrow_apr': median(aprs) if aprs else None,
            'borrow_apr_difference_from_base': median(aprs)-policy['base_costs']['borrow_apr'] if aprs else None,
            'median_entry_shortfall_bps': entry_slip, 'median_cover_shortfall_bps': cover_slip,
            'p90_cover_delay_sessions': delay, 'best_five_profit_fraction': concentration,
            'review_checks': checks, 'review_ready': all(checks.values()),
            'production_authority': 'none'}


def project(frozen, rows, status, now, historical=None):
    records = J.records(rows)
    if any(r.get('environment') == 'broker' or r['kind'] == 'borrow' and r.get('status') == 'approval' for r in records):
        raise ValueError('Private broker evidence cannot enter a public dashboard projection')
    candidates = {}
    for r in records:
        if r['kind'] == 'candidate':
            candidates[r['event_id']] = r
    decisions = [r for r in records if r['kind'] == 'enrollment']
    policies = []
    views = []
    for item in frozen['policies']:
        p = item['policy']
        enrolled = [e for e in decisions if e['policy_id'] == p['id']]
        agg = aggregate(rows, enrolled, p, now, 'paper')
        policies.append({'id': p['id'], 'label': p['label'], 'sha256': item['sha256'],
                         'requires': p['requires'], 'target_usd': p['target_usd'],
                         'slots': p['maximum_concurrent_issuers'], 'hold_sessions': p['hold_sessions_including_entry'],
                         'gross_budget_usd': p['gross_budget_usd'], 'squeeze_budget_usd': p['squeeze_loss_budget_usd'],
                         'review_limits': p['review'], 'results': agg})
        if historical:
            identifier = 'gate_S5' if p['id'] == 'burn_weak_h20' else 'burn_100'
            model = next(m for m in historical['models'] if m['policy'] == identifier and m['scenario'] == 'base' and m['capacity'] == 'three' and m['budget'] == 'matched')
            s = model['summary']
            policies[-1]['historical_reference'] = {
                'data_version': historical['data_version'], 'market_through': historical['market_through'],
                'net_pnl': s['net_pnl'], 'closing_drawdown': s['max_drawdown_dollars'],
                'entries': s['entered'], 'mean_entry_dollars': s['mean_position'],
                'costs': s['costs'], 'interpretation': 'Retrospective assumed executions; a comparison reference, not forward evidence'}
        for event_id, candidate in candidates.items():
            snapshot = candidate['input']
            e = next((e for e in enrolled if e['event_id'] == event_id), None)
            missed = next((r for r in records if r['kind'] == 'missed' and r.get('policy_id') == p['id'] and r['event_id'] == event_id), None)
            diagnostics = trade_diagnostics(rows, e, now) if e else None
            borrows = [r for r in records if r['kind'] == 'borrow' and r.get('policy_id') == p['id'] and r['event_id'] == event_id]
            last_borrow = max(borrows, key=lambda r: r['observed_at']) if borrows else None
            # Only explicitly enumerated fields leave the journal. No source account or order IDs.
            views.append({'event_id': event_id, 'issuer_id': snapshot['issuer_id'], 'ticker': snapshot['ticker'],
                          'company': snapshot['company'], 'policy_id': p['id'],
                          'effective_day': snapshot['effective_day'], 'ordinal': snapshot['documented_split_ordinal'],
                          'signals': (e['input'] if e else snapshot)['signals'],
                          'input_sha256': e['input_sha256'] if e else candidate['input_sha256'],
                          'decision_recorded_at': e['observed_at'] if e else None,
                          'entry_at': e['entry_at'] if e else missed['entry_at'] if missed else candidate.get('entry_at'),
                          'cover_day': e['schedule']['cover_day'] if e else None,
                          'decision': e['decision'] if e else 'missed' if missed else candidate.get('status', 'waiting'),
                          'reason': e['reason'] if e else missed['reason'] if missed else candidate.get('detail', 'Waiting for complete pre-entry inputs'),
                          'target_usd': e['target_usd'] if e else 0,
                          'borrow_apr': last_borrow.get('apr') if last_borrow else None,
                          'borrow_as_of': last_borrow['observed_at'] if last_borrow else None,
                          'borrow_is_approval': False,
                          'identity_status': snapshot['identity_status'],
                          'progress': diagnostics})
    doc = {'schema': 'third_plus_forward_dashboard.v1', 'as_of': now.isoformat(),
           'frozen_at': frozen['frozen_at'], 'production_authority': 'none',
           'all_names_assumed_tradable': True, 'policies': policies,
           'candidates': sorted(views, key=lambda r: (r['entry_at'] or '', r['event_id'], r['policy_id']), reverse=True),
           'leads': status.get('leads', []), 'source_status': status,
           'ledger': {'records': len(rows), 'head': rows[-1]['sha256'] if rows else None,
                      'enrollments': len(decisions), 'missed': sum(r['kind'] == 'missed' for r in records)},
           'observation_boundary': 'Public prices and borrow indications are references. Only imported, sourced paper fills produce paper P&L. Broker observations stay private.',
           'links': {'runbook': 'https://github.com/magis-capital-partners/single-stock-investments/blob/main/docs/THIRD_PLUS_FORWARD.md',
                     'executor_plan': 'https://github.com/magis-capital-partners/single-stock-investments/blob/main/docs/THIRD_PLUS_LIVE_EXECUTOR_PLAN.md'}}
    doc['data_version'] = sha(doc)
    return doc


def publish(directory, root=ROOT, now=None, check=False):
    from .policy import code_receipts, freeze, utcnow
    now = now or utcnow()
    directory = Path(directory)
    frozen = freeze(directory, now)
    rows = J.load(directory/'journal.jsonl')
    status = json.loads((directory/'status.json').read_text(encoding='utf-8'))
    if status.get('mode') == 'research_observation_only' and status.get('source_code') != code_receipts():
        raise ValueError('Forward code changed since the observation snapshot; rerun monitor')
    # The publication clock belongs to its input snapshot, not the check invocation.
    history_file = ROOT/'dashboard/data/third_plus_allocation.json'
    historical = json.loads(history_file.read_text(encoding='utf-8')) if history_file.exists() else None
    if historical and historical['data_version'] != frozen['policies'][0]['policy']['backtest_publication']:
        raise ValueError('Historical comparison changed; retain the frozen backtest publication')
    publication_at = max(stamp(status['as_of']), stamp(rows[-1]['recorded_at']) if rows else stamp(status['as_of']))
    doc = project(frozen, rows, status, publication_at, historical)
    target = Path(root)/'dashboard/data/third_plus_forward.json'
    body = canonical(doc) + '\n'
    manifest = {'schema': 'third_plus_forward_manifest.v1', 'payload': target.name,
                'data_version': doc['data_version'], 'sha256': hashlib.sha256(body.encode()).hexdigest()}
    manifest_path = target.with_name('third_plus_forward_manifest.json')
    if check:
        if target.read_bytes() != body.encode('utf-8') or json.loads(manifest_path.read_text()) != manifest:
            raise ValueError('Forward dashboard publication is stale or mismatched')
    else:
        write(target, doc); write(manifest_path, manifest)
    return doc


def export_csv(doc):
    out = io.StringIO()
    columns = ['policy_id', 'ticker', 'effective_day', 'decision', 'entry_at', 'cover_day', 'target_usd', 'borrow_apr', 'reason']
    writer = csv.DictWriter(out, columns, extrasaction='ignore'); writer.writeheader()
    for candidate in doc['candidates']:
        writer.writerow({k: "'"+str(v) if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in candidate.items() if k in columns})
    return out.getvalue()
