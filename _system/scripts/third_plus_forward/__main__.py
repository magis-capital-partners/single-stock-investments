"""Freeze, monitor, publish and import evidence for the prospective comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import journal as J
from .engine import base_record, observations, register, trade_diagnostics
from .policy import ROOT, STATE, canonical, code_receipts, entry_clock, freeze, sha, stamp, utcnow, write
from .publish import aggregate, export_csv, publish
from .sources import PublicSources, discover, input_snapshot


def borrow_rows(root):
    file = Path(root)/'_system/data/reverse_splits/borrow_monitor/latest.json'
    if not file.exists():
        return {}, None
    doc = json.loads(file.read_text(encoding='utf-8'))
    source = doc.get('source') or {}
    if source.get('checksum_verified') != 1 or not source.get('source_sha256'):
        return {}, None
    result = {}
    for r in doc.get('rows', []):
        ticker = r.get('symbol') or r.get('ticker')
        if not ticker:
            continue
        result[ticker] = dict(r, as_of=r.get('as_of') or source['as_of'],
                              source={'url': source['source_url'], 'sha256': source['source_sha256'],
                                      'locator': 'symbol='+ticker, 'retrieved_at': source['captured_at']})
    return result, source['as_of']


def monitor(root=ROOT, directory=STATE, work=None, maximum=30, network=True, now=None, provider=None, publication_root=ROOT):
    now = now or utcnow()
    root, directory = Path(root), Path(directory)
    work = Path(work or ROOT/'_system/data/reverse_splits/local/third_plus_forward')
    frozen = freeze(directory, now)
    candidates, leads, input_receipt = discover(root, now, frozen['frozen_at'])
    path = directory/'journal.jsonl'
    client = provider or PublicSources(work, now, maximum, network)
    borrowing, borrow_at = borrow_rows(root)
    errors = []
    # Continue observing all previously enrolled companies after their events leave discovery's date window.
    existing = J.records(J.load(path))
    known = {c['event_id']: c for c in candidates}
    for r in existing:
        if r['kind'] == 'candidate' and r['event_id'] not in known:
            s = r['input']
            if any(e['kind'] == 'enrollment' and e['event_id'] == r['event_id'] for e in existing):
                known[r['event_id']] = dict(s, cik=s['issuer_id'].split('/')[-1],
                                            action_known_at=r.get('action_known_at', s['known_at']), source=r['source'])
    for candidate in sorted(known.values(), key=lambda c: c['event_id']):
        try:
            rows = J.load(path)
            if any(r['record']['kind'] == 'candidate' and r['record']['event_id'] == candidate['event_id'] and r['record'].get('status') == 'before_policy' for r in rows):
                continue
            done = []
            for p in frozen['policies']:
                e = J.enrollment(rows, candidate['event_id'], p['policy']['id'])
                missed = any(r['record']['kind'] == 'missed' and r['record']['event_id'] == candidate['event_id'] and r['record']['policy_id'] == p['policy']['id'] for r in rows)
                progress = trade_diagnostics(rows, e, now) if e and e['decision'] == 'observe' else None
                done.append(missed or bool(e and (e['decision'] != 'observe' or progress and (progress['closed'] or progress['no_fill_observed']))))
            if all(done):
                continue
            enrolled = all(J.enrollment(rows, candidate['event_id'], p['policy']['id']) for p in frozen['policies'])
            bars, price_source, actions = client.prices(candidate['ticker'])
            if not enrolled:
                financial, financial_source = client.financials(candidate['cik'])
                snapshot = input_snapshot(candidate, financial, bars, now)
                snapshot['source_receipts'] = [s for s in [candidate['source'], financial_source, price_source] if s]
                at = entry_clock(candidate['effective_day'], candidate['action_known_at'])
                record = base_record('candidate', snapshot, candidate['source'], now, input=snapshot,
                                     input_sha256=sha(snapshot), entry_at=at.isoformat(),
                                     action_known_at=candidate['action_known_at'],
                                     status='waiting', detail='Awaiting complete inputs after the effective session')
                if at <= stamp(frozen['frozen_at']):
                    record['status'] = 'before_policy'
                    record['detail'] = 'Entry predates policy freeze; excluded from prospective results'
                J.append(path, [record], frozen, now)
                register(path, snapshot, candidate, frozen, now)
            observations(path, candidate, bars, price_source, borrowing.get(candidate['ticker']), frozen, now)
            for action in actions:
                for policy in frozen['policies']:
                    e = J.enrollment(J.load(path), candidate['event_id'], policy['policy']['id'])
                    if e and action['day'] >= stamp(e['entry_at']).date().isoformat():
                        notice = base_record('exception', candidate, price_source, now, policy,
                                             issue='corporate_action', day=action['day'],
                                             detail='Subsequent split: import a sourced quantity adjustment before using marked P&L')
                        notice['evidence_id'] = sha(['action_notice', candidate['event_id'], policy['sha256'], action['day']])
                        if notice['evidence_id'] not in {r['record']['evidence_id'] for r in J.load(path)}:
                            J.append(path, [notice], frozen, now)
        except (ValueError, KeyError, OSError) as exc:
            errors.append({'event_id': candidate['event_id'], 'status': 'review', 'detail': str(exc)})
    status = {'as_of': now.isoformat(), 'mode': 'research_observation_only', 'production_authority': 'none',
              'leads': leads, 'discovered_candidates': len(candidates), 'input_receipt': input_receipt,
              'borrow_as_of': borrow_at, 'requests': client.client.requests if hasattr(client, 'client') else 0,
              'network_enabled': network, 'errors': errors + client.errors,
              'coverage_complete': False,
              'coverage_note': 'Uses the existing bounded disclosure discovery pipeline; uncovered issuers and late discoveries remain possible.',
              'prospective_outcomes_note': 'New observations need future sessions. No historical trade has been relabeled prospective.',
              'source_code': code_receipts(), 'source_code_hash_basis': 'UTF-8 source bytes with LF line endings'}
    write(directory/'status.json', status)
    doc = publish(directory, publication_root, now)
    return {'candidates': len(candidates), 'leads': len(leads), 'enrollments': doc['ledger']['enrollments'],
            'requests': status['requests'], 'errors': len(status['errors']), 'production_authority': 'none'}


def private_path(value):
    path = Path(value).resolve()
    allowed = ROOT/'_system/data/reverse_splits/local'
    if path.is_relative_to(ROOT) and not path.is_relative_to(allowed):
        raise ValueError('Private broker evidence must be outside the repository or under ignored reverse_splits/local')
    return path


def import_evidence(file, directory, source_documents, private_work=None, now=None):
    now = now or utcnow()
    frozen = freeze(directory, now)
    incoming = json.loads(Path(file).read_text(encoding='utf-8'))
    if not isinstance(incoming, list):
        raise ValueError('Evidence import must be an array')
    if any(r.get('kind') in {'candidate', 'enrollment', 'missed'} for r in incoming):
        raise ValueError('Decision records are created only by prospective registration')
    permitted = {hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in source_documents}
    if not permitted or any(r.get('source', {}).get('sha256') not in permitted for r in incoming):
        raise ValueError('Every imported record must bind to provided source-document bytes')
    context = J.load(Path(directory)/'journal.jsonl')
    if private_work:
        target = private_path(private_work)/'broker_observations.jsonl'
        return J.append(target, incoming, frozen, now, private=True, context_rows=context)
    if any(r.get('environment') == 'broker' or r.get('status') == 'approval' for r in incoming):
        raise ValueError('Use --private-work for broker evidence')
    return J.append(Path(directory)/'journal.jsonl', incoming, frozen, now)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['freeze', 'monitor', 'publish', 'check', 'import', 'private-report', 'csv'])
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--state', type=Path, default=STATE)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--max-requests', type=int, default=30)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--file', type=Path)
    parser.add_argument('--source-document', action='append', default=[], type=Path)
    parser.add_argument('--private-work', type=Path)
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 100:
        parser.error('--max-requests must be between 1 and 100')
    now = utcnow()
    if args.command == 'freeze':
        result = freeze(args.state, now)
    elif args.command == 'monitor':
        result = monitor(args.source_root, args.state, args.work, args.max_requests, not args.offline, now)
    elif args.command == 'import':
        if not args.file or not args.source_document:
            parser.error('import requires --file and --source-document')
        result = import_evidence(args.file, args.state, args.source_document, args.private_work, now)
    elif args.command == 'private-report':
        if not args.private_work:
            parser.error('private-report requires --private-work')
        frozen = freeze(args.state, now)
        rows = J.load(args.state/'journal.jsonl') + J.load(private_path(args.private_work)/'broker_observations.jsonl')
        result = {'as_of': now.isoformat(), 'environment': 'broker', 'production_authority': 'none',
                  'policies': [dict(id=p['policy']['id'], results=aggregate(rows,
                              [r['record'] for r in rows if r['record']['kind'] == 'enrollment' and r['record']['policy_id'] == p['policy']['id']],
                              p['policy'], now, 'broker')) for p in frozen['policies']]}
        write(private_path(args.private_work)/'report.json', result)
    else:
        result = publish(args.state, ROOT, now, args.command in {'check', 'csv'})
        if args.command == 'csv':
            print(export_csv(result), end='')
            return
        result = {'verified': True, 'data_version': result['data_version'], 'enrollments': result['ledger']['enrollments']}
    print(canonical(result))


if __name__ == '__main__':
    main()
