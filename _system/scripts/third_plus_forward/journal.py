"""Validated append-only evidence, with separate private broker imports."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from .policy import canonical, sha, stamp, utcnow

KINDS = {'candidate', 'enrollment', 'missed', 'borrow', 'quote', 'reference',
         'order', 'fill', 'cashflow', 'loan_return', 'action', 'closure', 'exception'}
OUTCOMES = {'future_return', 'realized_return', 'h20_return', 'eventual_failure', 'outcomes'}


def number(value, minimum=0):
    return type(value) in (int, float) and math.isfinite(value) and value >= minimum


def no_outcomes(value):
    if isinstance(value, dict):
        if OUTCOMES.intersection(value):
            raise ValueError('Outcome information cannot enter a frozen decision')
        for item in value.values():
            no_outcomes(item)
    elif isinstance(value, list):
        for item in value:
            no_outcomes(item)


def load(path):
    path = Path(path)
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines() if path.exists() else []:
        row = json.loads(line)
        body = {k: v for k, v in row.items() if k != 'sha256'}
        if body.get('previous_sha256') != (rows[-1]['sha256'] if rows else None) or sha(body) != row.get('sha256'):
            raise ValueError('Forward evidence chain is damaged')
        if rows and stamp(row['recorded_at']) < stamp(rows[-1]['recorded_at']):
            raise ValueError('Forward journal recording clock moved backwards')
        rows.append(row)
    return rows


def records(rows):
    return [r['record'] for r in rows]


def enrollment(rows, event_id, policy_id):
    return next((r for r in records(rows) if r['kind'] == 'enrollment' and
                 (r['event_id'], r['policy_id']) == (event_id, policy_id)), None)


def position(rows, event_id, policy_id, environment='paper'):
    subset = [r for r in records(rows) if (r.get('event_id'), r.get('policy_id')) == (event_id, policy_id)
              and r.get('environment') == environment]
    qty = proceeds = covers = fees = cash = 0.
    returned = 0.
    entry_qty = 0.
    for r in sorted(subset, key=lambda r: (r['observed_at'], {'action': 0}.get(r['kind'], 1), r.get('evidence_id', ''))):
        if r['kind'] == 'action':
            qty *= r['new_shares_per_old']
            entry_qty *= r['new_shares_per_old']
            returned *= r['new_shares_per_old']
        elif r['kind'] == 'fill':
            if r['phase'] == 'entry':
                qty += r['shares']; entry_qty += r['shares']; proceeds += r['shares'] * r['price']
            else:
                qty -= r['shares']; covers += r['shares'] * r['price']
                if qty < -1e-7:
                    raise ValueError('Cover exceeds the open short; import corporate actions or reconcile first')
            fees += r['commission_usd']
        elif r['kind'] == 'cashflow':
            cash += r['amount_usd']
        elif r['kind'] == 'loan_return':
            returned += r['shares']
            if returned > entry_qty + 1e-7:
                raise ValueError('Returned loan shares exceed sourced entries')
    return {'shares': max(0., qty), 'entry_shares': entry_qty, 'entry_proceeds': proceeds,
            'cover_cash': covers, 'fees': fees, 'cashflows': cash,
            'loan_remaining': max(0., entry_qty - returned), 'cash_pnl': proceeds - covers - fees + cash}


def validate(record, rows, frozen, now, private=False):
    canonical(record)
    if record.get('kind') not in KINDS or not record.get('event_id') or not record.get('issuer_id'):
        raise ValueError('Missing evidence kind or event/issuer identity')
    if stamp(record['known_at']) > now or stamp(record['observed_at']) > stamp(record['known_at']):
        raise ValueError('Evidence is not yet available')
    if stamp(record['known_at']) < stamp(frozen['frozen_at']):
        # Older source observations may inform a new candidate; their receipt is captured now.
        if record['kind'] not in {'candidate'}:
            raise ValueError('Prospective journal evidence predates the policy freeze')
    if not record.get('evidence_id') or not record.get('source'):
        raise ValueError('Sourced evidence ID is required')
    source = record['source']
    if not source.get('url', '').startswith(('https://', 'ftp://ftp2.interactivebrokers.com/', 'broker-export://', 'paper-export://', 'repo://')):
        raise ValueError('Unsupported source reference')
    if len(source.get('sha256', '')) != 64 or any(c not in '0123456789abcdef' for c in source['sha256']) or not source.get('locator'):
        raise ValueError('Source bytes hash and locator are required')
    if any(r['record'].get('evidence_id') == record['evidence_id'] for r in rows):
        raise ValueError('Conflicting evidence ID')
    kind = record['kind']
    if kind in {'candidate', 'enrollment', 'missed'}:
        no_outcomes(record.get('input', {}))
    if kind == 'candidate':
        if sha(record['input']) != record['input_sha256']:
            raise ValueError('Candidate snapshot hash mismatch')
        if stamp(record['input']['known_at']) > now:
            raise ValueError('Candidate inputs are from the future')
        return
    policy = next((p for p in frozen['policies'] if p['policy']['id'] == record.get('policy_id')), None)
    if not policy or record.get('policy_sha256') != policy['sha256']:
        raise ValueError('Evidence must bind to the unchanged policy')
    existing = enrollment(rows, record['event_id'], record['policy_id'])
    if kind == 'enrollment':
        if existing or stamp(record['entry_at']) <= now or stamp(record['observed_at']) != now:
            raise ValueError('Enrollment must be unique and recorded before entry')
        if sha(record['input']) != record['input_sha256'] or stamp(record['input']['known_at']) > now:
            raise ValueError('Frozen inputs are unavailable or changed')
        if record['decision'] not in {'observe', 'abstain', 'capacity'}:
            raise ValueError('Invalid frozen decision')
        if record.get('target_usd', 0) > policy['policy']['target_usd'] or not number(record.get('target_usd')):
            raise ValueError('Target exceeds frozen size')
        from .engine import decide
        from .policy import entry_clock, schedule
        expected_at = entry_clock(record['input']['effective_day'], record['input']['action_known_at'])
        if stamp(record['entry_at']) != expected_at or record['schedule'] != schedule(expected_at) or now < closing_time(record['input']['effective_day']):
            raise ValueError('Enrollment violates the exchange-session timing rule')
        if (record['event_id'], record['issuer_id']) != (record['input']['event_id'], record['input']['issuer_id']):
            raise ValueError('Frozen identity differs from enrollment')
        expected = decide(record['input'], expected_at, policy, rows, now)
        if (record['decision'], record['target_usd'], record['reason']) != expected:
            raise ValueError('Frozen decision differs from signals or reserved capacity')
        return
    if kind == 'missed':
        if stamp(record['entry_at']) > now:
            raise ValueError('An upcoming entry cannot be called missed')
        return
    if not existing or record['issuer_id'] != existing['issuer_id']:
        raise ValueError('Observation needs matching prospective enrollment')
    if kind in {'borrow', 'quote', 'reference', 'exception'}:
        if kind == 'borrow' and (record.get('status') not in {'indication', 'approval', 'unavailable'} or
                                 (record.get('apr') is not None and not number(record['apr']))):
            raise ValueError('Invalid borrowing indication')
        if kind == 'borrow' and record['status'] == 'approval' and not private:
            raise ValueError('Broker approvals stay in the private evidence store')
        if kind == 'quote' and (not number(record.get('bid'), .000001) or not number(record.get('ask'), record['bid'])):
            raise ValueError('Crossed or invalid quote')
        if kind == 'reference' and not number(record.get('price'), .000001):
            raise ValueError('Invalid reference price')
        return
    if record.get('environment') not in {'paper', 'broker'}:
        raise ValueError('Separate paper and broker environments are required')
    if record['environment'] == 'broker' and not private:
        raise ValueError('Broker observations require a private journal')
    if existing['decision'] != 'observe':
        raise ValueError('An abstained or capacity-excluded decision cannot become a trade')
    if stamp(record['observed_at']) < stamp(existing['entry_at']):
        raise ValueError('Trading observation precedes planned entry')
    if kind == 'order':
        if record.get('phase') not in {'entry', 'cover'} or record.get('status') not in {'submitted', 'rejected', 'cancelled', 'expired', 'uncertain'}:
            raise ValueError('Invalid observed order state')
        if not record.get('order_id') or not number(record.get('requested_shares'), .000001):
            raise ValueError('Observed order needs quantity and unique identity')
        if not number(record.get('limit_price'), .000001):
            raise ValueError('Observed order needs its working limit')
    if kind == 'fill':
        if record.get('phase') not in {'entry', 'cover'} or not number(record.get('shares'), .000001) or not number(record.get('price'), .000001) or not number(record.get('commission_usd')):
            raise ValueError('Invalid sourced fill')
        if not record.get('execution_id') or not record.get('order_id') or record.get('observed') is not True:
            raise ValueError('Execution must be explicitly observed and uniquely identified')
        if any(r['record'].get('execution_id') == record['execution_id'] and r['record'].get('environment') == record['environment'] for r in rows):
            raise ValueError('Duplicate execution ID')
        orders = [r for r in records(rows) if r.get('kind') == 'order' and r.get('order_id') == record['order_id'] and r.get('phase') == record['phase'] and r.get('environment') == record['environment']
                  and r.get('event_id') == record['event_id'] and r.get('policy_id') == record['policy_id'] and stamp(r['observed_at']) <= stamp(record['observed_at'])]
        if not orders:
            raise ValueError('Fill requires its observed order attempt')
        order = orders[-1]
        used = sum(r['shares'] for r in records(rows) if r['kind'] == 'fill' and r.get('order_id') == record['order_id'] and r.get('environment') == record['environment'] and r.get('event_id') == record['event_id'] and r.get('policy_id') == record['policy_id'])
        if record['shares'] + used > order['requested_shares'] + 1e-7:
            raise ValueError('Execution exceeds observed order quantity')
        if record['environment'] == 'paper' and ((record['phase'] == 'entry' and record['price'] < order['limit_price']) or (record['phase'] == 'cover' and record['price'] > order['limit_price'])):
            raise ValueError('Paper fill violates its working limit')
        if record['environment'] == 'paper' and record['phase'] == 'entry' and stamp(record['observed_at']) >= stamp(existing['schedule']['entry_end']):
            raise ValueError('Entry fill falls outside the frozen window')
        before = position(rows, record['event_id'], record['policy_id'], record['environment'])
        if record['environment'] == 'paper' and record['phase'] == 'entry' and before['entry_proceeds'] + record['shares'] * record['price'] > existing['target_usd'] + .01:
            raise ValueError('Entry exceeds frozen requested dollars')
        if record['phase'] == 'cover' and stamp(record['observed_at']) < stamp(existing['schedule']['cover_start']):
            if record['environment'] == 'paper' and not record.get('exception_reason'):
                raise ValueError('Early paper cover requires a sourced exception reason')
    if kind == 'cashflow' and (not number(abs(record.get('amount_usd', float('nan')))) or record.get('category') not in {'borrow', 'dividend', 'locate', 'commission', 'credit', 'other'}):
        raise ValueError('Invalid signed cash flow')
    if kind in {'loan_return', 'action'} and not number(record.get('shares' if kind == 'loan_return' else 'new_shares_per_old'), .000001):
        raise ValueError('Invalid loan return or split factor')
    if kind == 'closure':
        p = position(rows, record['event_id'], record['policy_id'], record['environment'])
        if p['entry_shares'] <= 0 or p['shares'] > 1e-7 or p['loan_remaining'] > 1e-7 or not all(record.get(k) is True for k in ['positions_zero', 'loans_zero', 'costs_reconciled']):
            raise ValueError('Closure requires covered shares, returned loan and reconciled costs')
        categories = {r.get('category') for r in records(rows) if r['kind'] == 'cashflow' and r.get('environment') == record['environment'] and r['event_id'] == record['event_id'] and r['policy_id'] == record['policy_id']}
        if not {'borrow', 'locate'} <= categories:
            raise ValueError('Closure needs explicit borrow and locate costs, including sourced zero costs')


def closing_time(day):
    from .policy import closing
    return closing(day)


def append(path, incoming, frozen, now=None, private=False, context_rows=None):
    now = now or utcnow()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        stored = load(path)
        rows = list(context_rows or []) + stored
        if rows and stamp(rows[-1]['recorded_at']) > now:
            raise ValueError('Journal clock moved backwards')
        seen = {sha(r['record']) for r in rows}
        added = []
        for record in incoming:
            if sha(record) in seen:
                continue
            validate(record, rows, frozen, now, private)
            body = {'record': record, 'recorded_at': now.isoformat(), 'previous_sha256': (added or stored)[-1]['sha256'] if (added or stored) else None}
            row = dict(body, sha256=sha(body))
            rows.append(row); added.append(row); seen.add(sha(record))
            if record['kind'] in {'fill', 'action', 'loan_return'}:
                position(rows, record['event_id'], record['policy_id'], record['environment'])
        # A bad batch writes nothing. One exclusive writer and atomic replacement prevent torn tails.
        if added:
            temporary = path.with_suffix('.pending')
            temporary.write_text(''.join(canonical(r) + '\n' for r in stored + added), encoding='utf-8', newline='\n')
            temporary.replace(path)
        return {'appended': len(added), 'total': len(rows), 'head': rows[-1]['sha256'] if rows else None}
    finally:
        os.close(fd)
        lock.unlink()
