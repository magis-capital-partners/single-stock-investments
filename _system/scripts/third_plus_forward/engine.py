"""Pre-entry decisions and forward diagnostics; never creates an execution."""
from __future__ import annotations

from datetime import timedelta
from statistics import median

from . import journal as J
from .policy import NY, closing, entry_clock, schedule, sessions, sha, stamp


def base_record(kind, snapshot, source, now, policy=None, **fields):
    record = {'kind': kind, 'event_id': snapshot['event_id'], 'issuer_id': snapshot['issuer_id'],
              'known_at': now.isoformat(), 'observed_at': now.isoformat(), 'source': source, **fields}
    if policy:
        record.update(policy_id=policy['policy']['id'], policy_sha256=policy['sha256'])
    record['evidence_id'] = sha(record)
    return record


def reservations(rows, policy_id, at):
    rows = [row for row in rows if stamp(row['record']['observed_at']) <= at and stamp(row['record']['known_at']) <= at and stamp(row['recorded_at']) <= at]
    open_issuers = set()
    gross = 0.
    for e in J.records(rows):
        if e['kind'] != 'enrollment' or e.get('policy_id') != policy_id or e['decision'] != 'observe':
            continue
        ps = J.position(rows, e['event_id'], policy_id)
        subset = [r for r in J.records(rows) if (r.get('event_id'), r.get('policy_id')) == (e['event_id'], policy_id)]
        closed = any(r['kind'] == 'closure' and r.get('environment') == 'paper' and stamp(r['observed_at']) < at for r in subset)
        if closed:
            continue
        if ps['entry_shares'] and ps['shares'] <= 1e-7:
            continue
        if ps['entry_shares'] == 0 and terminal_orders(subset, 'paper') and stamp(e['schedule']['entry_end']) <= at:
            continue
        # Missing execution evidence is unresolved, not a retroactively invented no-fill.
        references = [r for r in subset if r['kind'] == 'reference' and stamp(r['observed_at']) <= at]
        last = max(references, key=lambda r: r['observed_at']) if references else None
        value = ps['shares'] * last['price'] if ps['entry_shares'] and last else e['target_usd']
        if ps['entry_shares'] and ps['shares'] <= 1e-7:
            value = 0.
        open_issuers.add(e['issuer_id']); gross += value
    return open_issuers, gross


def terminal_orders(records, environment):
    latest = {}
    for r in sorted(records, key=lambda r: r['observed_at']):
        if r['kind'] == 'order' and r.get('environment') == environment and r['phase'] == 'entry':
            latest[r['order_id']] = r['status']
    return bool(latest) and all(status in {'expired', 'cancelled', 'rejected'} for status in latest.values())


def decide(snapshot, at, policy, rows, now):
    p = policy['policy']
    if any(snapshot['signals'].get(k) == 'fail' for k in p['requires']):
        return 'abstain', 0, 'Required signal failed'
    if any(snapshot['signals'].get(k) != 'pass' for k in p['requires']):
        return 'abstain', 0, 'Required signal remains unknown'
    if snapshot['documented_split_ordinal'] < 3:
        return 'abstain', 0, 'Fewer than three documented splits'
    issuers, gross = reservations(rows, p['id'], now)
    if snapshot['issuer_id'] in issuers:
        return 'capacity', 0, 'Issuer already reserved or open'
    if len(issuers) >= p['maximum_concurrent_issuers']:
        return 'capacity', 0, 'Three issuer slots occupied or unresolved'
    target = min(p['target_usd'], max(0, p['gross_budget_usd'] - gross),
                 max(0, p['squeeze_loss_budget_usd']/p['squeeze_up_fraction'] - gross))
    target = int(target/100)*100
    return ('observe', target, 'Frozen research plan; all names assumed tradable') if target >= 100 else ('capacity', 0, 'Gross or squeeze admission budget exhausted')


def register(path, snapshot, candidate, frozen, now):
    source = candidate['source']
    at = entry_clock(candidate['effective_day'], candidate['action_known_at'])
    if stamp(frozen['frozen_at']) >= at:
        return {'status': 'before_policy', 'entry_at': at.isoformat()}
    clock = schedule(at)
    rows = J.load(path)
    pending = []
    for policy in frozen['policies']:
        pid = policy['policy']['id']
        if J.enrollment(rows, snapshot['event_id'], pid) or any(r['record']['kind'] == 'missed' and (r['record']['event_id'], r['record']['policy_id']) == (snapshot['event_id'], pid) for r in rows):
            continue
        if now >= at:
            pending.append(base_record('missed', snapshot, source, now, policy, entry_at=at.isoformat(),
                                       reason='Entry passed before registration; excluded from prospective results'))
            continue
        if now < closing(candidate['effective_day']):
            continue
        unknown = any(snapshot['signals'].get(k) == 'unknown' for k in policy['policy']['requires'])
        if unknown and now < at - timedelta(minutes=5):
            continue
        decision, target, reason = decide(snapshot, at, policy, rows, now)
        pending.append(base_record('enrollment', snapshot, source, now, policy, input=snapshot,
                                   input_sha256=sha(snapshot), entry_at=at.isoformat(), schedule=clock,
                                   decision=decision, target_usd=target, reason=reason))
    if pending:
        J.append(path, pending, frozen, now)
    return {'status': 'registered' if pending else 'waiting_or_registered', 'entry_at': at.isoformat()}


def observations(path, candidate, bars, source, borrow, frozen, now):
    rows = J.load(path)
    existing_ids = {r['record']['evidence_id'] for r in rows}
    output = []
    for policy in frozen['policies']:
        e = J.enrollment(rows, candidate['event_id'], policy['policy']['id'])
        if not e:
            continue
        for bar in bars:
            if bar['day'] < stamp(e['entry_at']).astimezone(NY).date().isoformat():
                continue
            if source:
                r = base_record('reference', candidate, source, now, policy, price=bar['close'],
                                day=bar['day'], observed_at=closing(bar['day']).isoformat(),
                                basis='vendor daily close; indicative reference, no fill or NBBO claim')
                # One immutable first-seen observation per day and policy; revisions do not rewrite it.
                r['evidence_id'] = sha([r['kind'], candidate['event_id'], policy['sha256'], bar['day']])
                if r['evidence_id'] not in existing_ids:
                    output.append(r)
        if borrow:
            r = base_record('borrow', candidate, borrow['source'], now, policy,
                            status='indication' if borrow.get('available_shares') else 'unavailable',
                            apr=borrow.get('fee_apr'), available_shares=borrow.get('available_shares'),
                            observed_at=borrow['as_of'], approval=False)
            r['evidence_id'] = sha(['borrow', candidate['event_id'], policy['sha256'], borrow['source']['sha256']])
            if r['evidence_id'] not in existing_ids and stamp(borrow['as_of']) <= now:
                output.append(r)
    if output:
        J.append(path, output, frozen, now)


def trade_diagnostics(rows, e, now, environment='paper'):
    pid, event = e['policy_id'], e['event_id']
    subset = [r for r in J.records(rows) if (r.get('event_id'), r.get('policy_id')) == (event, pid)]
    fills = [r for r in subset if r['kind'] == 'fill' and r.get('environment') == environment]
    ps = J.position(rows, event, pid, environment)
    quotes = [r for r in subset if r['kind'] == 'quote']
    shorts = [r for r in fills if r['phase'] == 'entry']
    covers = [r for r in fills if r['phase'] == 'cover']
    shortfalls = {'entry': [], 'cover': []}
    for fill in fills:
        available = [q for q in quotes if 0 <= (stamp(fill['observed_at'])-stamp(q['observed_at'])).total_seconds() <= 120
                     and stamp(q['known_at']) <= stamp(fill['observed_at'])]
        if available:
            q = max(available, key=lambda q: q['observed_at'])
            mid = (q['bid']+q['ask'])/2
            shortfalls[fill['phase']].append((mid-fill['price'])/mid*10000 if fill['phase'] == 'entry' else (fill['price']-mid)/mid*10000)
    references = sorted((r for r in subset if r['kind'] == 'reference'), key=lambda r: r['observed_at'])
    last = references[-1] if references else None
    closures = [r for r in subset if r['kind'] == 'closure' and r.get('environment') == environment]
    last_closure = max((stamp(r['observed_at']) for r in closures), default=None)
    changing = [stamp(r['observed_at']) for r in subset if r['kind'] in {'fill', 'cashflow', 'action', 'loan_return'} and r.get('environment') == environment]
    closed = last_closure is not None and (not changing or last_closure >= max(changing))
    cashflows = [r for r in subset if r['kind'] == 'cashflow' and r.get('environment') == environment]
    coverage = {category: any(r['category'] == category for r in cashflows) for category in ['borrow', 'locate']}
    mark_pnl = ps['cash_pnl'] - ps['shares']*last['price'] if last and shorts else ps['cash_pnl'] if shorts and ps['shares'] == 0 else None
    unresolved_actions = [r for r in subset if r['kind'] == 'exception' and r.get('issue') == 'corporate_action' and
                          not any(a['kind'] == 'action' and a.get('environment') == environment and a.get('day') == r['day'] for a in subset)]
    if unresolved_actions:
        mark_pnl = None
        closed = False
    after_cover = max(0, len(sessions(e['schedule']['cover_day'], stamp(covers[-1]['observed_at']).astimezone(NY).date().isoformat()))-1) if covers and stamp(covers[-1]['observed_at']).date().isoformat() >= e['schedule']['cover_day'] else 0
    terminal_empty = not shorts and terminal_orders(subset, environment)
    overdue = now >= stamp(e['schedule']['exception_after']) and e['decision'] == 'observe' and not closed and not terminal_empty
    return {'environment': environment, 'entered': bool(shorts), 'closed': closed,
            'entry_fill_fraction': ps['entry_proceeds']/e['target_usd'] if e['target_usd'] and (shorts or terminal_empty) else None,
            'entry_dollars': ps['entry_proceeds'], 'open_shares': ps['shares'],
            'loan_remaining': ps['loan_remaining'], 'net_marked_pnl': mark_pnl,
            'costs_reconciled': closed, 'borrow_recorded': coverage['borrow'], 'locate_recorded': coverage['locate'],
            'entry_shortfall_bps': median(shortfalls['entry']) if shortfalls['entry'] else None,
            'cover_shortfall_bps': median(shortfalls['cover']) if shortfalls['cover'] else None,
            'cover_delay_sessions': after_cover if covers else None,
            'overdue': overdue, 'no_fill_observed': terminal_empty, 'latest_mark_day': last['day'] if last else None,
            'unresolved_actions': len(unresolved_actions),
            'status': 'closed' if closed else 'open' if shorts and ps['shares'] else 'awaiting loan/cost reconciliation' if shorts else 'no fill observed' if terminal_empty else 'awaiting entry observations' if now >= stamp(e['entry_at']) else 'planned'}
