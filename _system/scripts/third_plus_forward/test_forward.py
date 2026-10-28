"""Offline prospective-registration and complete position-lifecycle tests."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from _system.scripts.third_plus_forward import journal as J
from _system.scripts.third_plus_forward import policy as P
from _system.scripts.third_plus_forward.engine import base_record, register, reservations, trade_diagnostics
from _system.scripts.third_plus_forward.sources import input_snapshot, public_url
from _system.scripts.third_plus_forward.publish import project, publish
from _system.scripts.third_plus_forward.__main__ import import_evidence, private_path, monitor


class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.now = P.stamp('2026-10-27T21:10:00Z')
        self.frozen = P.freeze(self.directory, P.stamp('2026-10-26T21:00:00Z'))
        self.path = self.directory/'journal.jsonl'
        self.source = {'url': 'paper-export://fixture', 'sha256': 'a'*64, 'locator': 'fixture row 1'}
        self.policy = self.frozen['policies'][0]
        self.candidate = self.cand()
        self.snapshot = self.snap(self.candidate)

    def tearDown(self):
        self.tmp.cleanup()

    def cand(self, name='A'):
        return {'event_id': 'event/'+name, 'issuer_id': 'cik/'+name, 'cik': '1', 'ticker': name,
                'company': name+' Corp', 'effective_day': '2026-10-27', 'documented_split_ordinal': 3,
                'action_known_at': '2026-10-26T20:00:00Z', 'identity_status': 'test source identity', 'source': self.source}

    def snap(self, c):
        return {k: c[k] for k in ['event_id', 'issuer_id', 'ticker', 'company', 'effective_day', 'documented_split_ordinal', 'identity_status', 'action_known_at']} | {
            'known_at': self.now.isoformat(), 'signals': {'S7': 'pass', 'burn': 'pass', 'S5': 'pass'}}

    def enroll(self, c=None, s=None, at=None):
        c = c or self.candidate
        s = s or self.snap(c)
        at = at or self.now
        record = base_record('candidate', s, self.source, at, input=s, input_sha256=P.sha(s))
        J.append(self.path, [record], self.frozen, at)
        register(self.path, s, c, self.frozen, at)
        return J.enrollment(J.load(self.path), c['event_id'], self.policy['policy']['id'])

    def observation(self, kind, at='2026-10-28T13:31:02Z', **kwargs):
        return base_record(kind, self.snapshot, self.source, P.stamp(at), self.policy, **kwargs)

    def add(self, *records):
        latest = max(P.stamp(r['known_at']) for r in records)
        return J.append(self.path, records, self.frozen, latest)

    def entry(self, shares=100, environment='paper'):
        order = self.observation('order', at='2026-10-28T13:31:00Z', environment=environment,
                                 phase='entry', order_id='entry1', requested_shares=shares, limit_price=10, status='submitted')
        fill = self.observation('fill', environment=environment, phase='entry', order_id='entry1', execution_id='exec1',
                                shares=shares, price=10, commission_usd=1, observed=True)
        if environment == 'paper':
            self.add(order, fill)
        return order, fill

    def test_policy_freeze_is_idempotent_and_rejects_rule_drift(self):
        self.assertEqual(self.frozen, P.freeze(self.directory, self.now))
        doc = copy.deepcopy(self.frozen); doc['policies'][0]['policy']['target_usd'] = 200000
        P.write(self.directory/'policies.json', doc)
        with self.assertRaisesRegex(ValueError, 'Frozen policy changed'):
            P.freeze(self.directory, self.now)

    def test_twenty_sessions_holidays_early_close_and_dst(self):
        entry = P.entry_clock('2026-10-27', '2026-10-26T20:00:00Z')
        self.assertEqual(entry.isoformat(), '2026-10-28T13:31:00+00:00')
        self.assertEqual(P.schedule(entry.isoformat())['cover_day'], '2026-11-24')
        # A Friday split enters after a Monday holiday, in standard time.
        self.assertEqual(P.entry_clock('2026-12-24', '2026-12-23T19:00:00Z').isoformat(), '2026-12-28T14:31:00+00:00')
        early = P.schedule('2026-10-30T13:31:00Z')
        self.assertEqual(early['cover_day'], '2026-11-27')
        self.assertEqual(early['cover_start'], '2026-11-27T16:30:00+00:00')
        self.assertEqual(early['cover_end'], '2026-11-27T17:45:00+00:00')

    def test_late_publication_waits_for_a_subsequent_regular_open(self):
        self.assertEqual(P.entry_clock('2026-10-27', '2026-10-28T13:28:00Z').isoformat(), '2026-10-29T13:31:00+00:00')
        with self.assertRaises(ValueError):
            P.entry_clock('2026-10-25', '2026-10-23T10:00:00Z')
        with self.assertRaises(ValueError):
            P.stamp('2026-10-27T12:00:00')

    def test_waits_for_effective_close_then_registers_both_books(self):
        before = P.stamp('2026-10-27T19:00:00Z')
        s = self.snap(self.candidate); s['known_at'] = before.isoformat()
        register(self.path, s, self.candidate, self.frozen, before)
        self.assertFalse(J.load(self.path))
        self.enroll()
        decisions = [r for r in J.records(J.load(self.path)) if r['kind'] == 'enrollment']
        self.assertEqual(len(decisions), 2)
        self.assertTrue(all(r['decision'] == 'observe' and r['target_usd'] == 100000 for r in decisions))

    def test_late_discovery_is_missed_not_backdated(self):
        late = P.stamp('2026-10-28T13:32:00Z')
        s = self.snap(self.candidate); s['known_at'] = late.isoformat()
        register(self.path, s, self.candidate, self.frozen, late)
        records = J.records(J.load(self.path))
        self.assertEqual([r['kind'] for r in records], ['missed', 'missed'])
        register(self.path, s, self.candidate, self.frozen, late)
        self.assertEqual(len(J.load(self.path)), 2)

    def test_unknowns_wait_then_explicitly_abstain_without_rejecting_borrow(self):
        s = self.snap(self.candidate); s['signals']['burn'] = 'unknown'
        register(self.path, s, self.candidate, self.frozen, self.now)
        self.assertFalse(J.load(self.path))
        final = P.stamp('2026-10-28T13:27:00Z'); s['known_at'] = final.isoformat()
        register(self.path, s, self.candidate, self.frozen, final)
        self.assertTrue(all(r['record']['decision'] == 'abstain' for r in J.load(self.path)))
        self.assertTrue(self.policy['policy']['all_names_assumed_tradable'])

    def test_weak_close_gate_only_changes_treatment_book(self):
        s = self.snap(self.candidate); s['signals']['S5'] = 'fail'
        self.enroll(s=s)
        records = [r for r in J.records(J.load(self.path)) if r['kind'] == 'enrollment']
        self.assertEqual([r['decision'] for r in records], ['abstain', 'observe'])

    def test_enrollment_cannot_be_rewritten_or_contain_outcomes(self):
        e = self.enroll()
        changed = copy.deepcopy(e); changed['target_usd'] = 50000; changed['evidence_id'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.add(changed)
        fresh = self.snap(self.cand('B')); fresh['nested'] = {'future_return': -1}
        record = base_record('candidate', fresh, self.source, self.now, input=fresh, input_sha256=P.sha(fresh))
        with self.assertRaisesRegex(ValueError, 'Outcome'):
            self.add(record)

    def test_three_tiny_or_unobserved_positions_use_three_slots(self):
        for name in 'ABC':
            self.enroll(self.cand(name))
        # Before entry, requested parents already reserve both independent policy books.
        e = self.enroll(self.cand('D'))
        self.assertEqual(e['decision'], 'capacity')
        self.assertEqual(reservations(J.load(self.path), self.policy['policy']['id'], self.now)[1], 300000)
        self.entry(shares=1)
        at = P.stamp('2026-10-29T12:00:00Z')
        self.assertEqual(len(reservations(J.load(self.path), self.policy['policy']['id'], at)[0]), 3)

    def test_no_fill_does_not_retroactively_release_morning_capacity(self):
        self.enroll()
        terminal = self.observation('order', at='2026-10-28T14:31:00Z', environment='paper', phase='entry',
                                    order_id='expired', requested_shares=100, limit_price=10, status='expired')
        self.add(terminal)
        self.assertEqual(len(reservations(J.load(self.path), self.policy['policy']['id'], P.stamp('2026-10-28T13:32:00Z'))[0]), 1)
        self.assertEqual(len(reservations(J.load(self.path), self.policy['policy']['id'], P.stamp('2026-10-28T14:32:00Z'))[0]), 0)

    def test_atomic_batches_idempotency_duplicate_and_tamper_detection(self):
        self.enroll()
        order, fill = self.entry()
        self.assertEqual(self.add(fill)['appended'], 0)
        before = self.path.read_bytes()
        duplicate = dict(fill, evidence_id='other')
        with self.assertRaisesRegex(ValueError, 'Duplicate execution'):
            self.add(duplicate)
        self.assertEqual(self.path.read_bytes(), before)
        broken = self.path.read_text().replace('100000', '100001', 1)
        self.path.write_text(broken)
        with self.assertRaisesRegex(ValueError, 'damaged'):
            J.load(self.path)

    def test_quotes_are_references_and_future_quotes_fail(self):
        e = self.enroll()
        q = self.observation('quote', bid=9.9, ask=10.1)
        self.add(q)
        self.assertIsNone(trade_diagnostics(J.load(self.path), e, P.stamp('2026-11-25T20:00:00Z'))['net_marked_pnl'])
        self.assertTrue(trade_diagnostics(J.load(self.path), e, P.stamp('2026-11-28T20:00:00Z'))['overdue'])
        q['observed_at'] = '2027-01-01T00:00:00Z'; q['evidence_id'] = 'future'
        with self.assertRaisesRegex(ValueError, 'available'):
            self.add(q)

    def test_fill_requires_order_and_cannot_overcover(self):
        self.enroll()
        _, fill = self.entry()
        fill2 = dict(fill, order_id='unknown', evidence_id='new', execution_id='new')
        with self.assertRaisesRegex(ValueError, 'order attempt'):
            self.add(fill2)
        order = self.observation('order', at='2026-11-24T20:00:00Z', environment='paper', phase='cover',
                                 order_id='cover1', requested_shares=101, limit_price=7, status='submitted')
        cover = self.observation('fill', at='2026-11-24T20:00:01Z', environment='paper', phase='cover', order_id='cover1',
                                 execution_id='coverexec', shares=101, price=7, commission_usd=1, observed=True)
        with self.assertRaisesRegex(ValueError, 'exceeds the open short'):
            self.add(order, cover)

    def test_full_twenty_session_lifecycle_costs_loan_and_closure(self):
        e = self.enroll(); self.entry()
        order = self.observation('order', at='2026-11-24T20:00:00Z', environment='paper', phase='cover',
                                 order_id='cover1', requested_shares=100, limit_price=7, status='submitted')
        cover = self.observation('fill', at='2026-11-24T20:00:01Z', environment='paper', phase='cover', order_id='cover1',
                                 execution_id='coverexec', shares=100, price=7, commission_usd=1, observed=True)
        borrow = self.observation('cashflow', at='2026-11-25T20:00:00Z', environment='paper', category='borrow', amount_usd=-10)
        locate = self.observation('cashflow', at='2026-11-25T20:00:00Z', environment='paper', category='locate', amount_usd=-5)
        returned = self.observation('loan_return', at='2026-11-25T20:00:00Z', environment='paper', shares=100)
        closure = self.observation('closure', at='2026-11-25T20:00:01Z', environment='paper', positions_zero=True, loans_zero=True, costs_reconciled=True)
        self.add(order, cover, borrow, locate, returned, closure)
        d = trade_diagnostics(J.load(self.path), e, P.stamp('2026-11-26T20:00:00Z'))
        self.assertTrue(d['closed']); self.assertEqual(d['net_marked_pnl'], 283)
        self.assertEqual(d['open_shares'], 0); self.assertEqual(d['loan_remaining'], 0)
        late_fee = self.observation('cashflow', at='2026-11-27T20:00:00Z', environment='paper', category='other', amount_usd=-3)
        self.add(late_fee)
        self.assertFalse(trade_diagnostics(J.load(self.path), e, P.stamp('2026-11-28T20:00:00Z'))['closed'])

    def test_unreturned_loan_prevents_completed_profit(self):
        self.enroll(); self.entry()
        closure = self.observation('closure', at='2026-11-25T20:00:00Z', environment='paper', positions_zero=True, loans_zero=True, costs_reconciled=True)
        with self.assertRaisesRegex(ValueError, 'Closure requires'):
            self.add(closure)

    def test_reverse_split_changes_quantity_without_erasing_cash(self):
        self.enroll(); self.entry()
        action = self.observation('action', at='2026-11-02T14:30:00Z', environment='paper', day='2026-11-02', new_shares_per_old=.1)
        self.add(action)
        p = J.position(J.load(self.path), self.candidate['event_id'], self.policy['policy']['id'])
        self.assertEqual(p['shares'], 10); self.assertEqual(p['entry_proceeds'], 1000)

    def test_missing_action_blocks_marked_profit(self):
        e = self.enroll(); self.entry()
        reference = self.observation('reference', at='2026-11-02T21:00:00Z', day='2026-11-02', price=80)
        notice = self.observation('exception', at='2026-11-02T21:00:00Z', issue='corporate_action', day='2026-11-02')
        self.add(reference, notice)
        d = trade_diagnostics(J.load(self.path), e, P.stamp('2026-11-03T21:00:00Z'))
        self.assertIsNone(d['net_marked_pnl']); self.assertEqual(d['unresolved_actions'], 1)

    def test_private_broker_evidence_stays_out_of_public_projection(self):
        self.enroll()
        order, fill = self.entry(environment='broker')
        with self.assertRaisesRegex(ValueError, 'private'):
            self.add(order, fill)
        private = self.directory/'private.jsonl'
        context = J.load(self.path)
        J.append(private, [order, fill], self.frozen, P.stamp('2026-10-28T15:00:00Z'), private=True, context_rows=context)
        self.assertEqual(len(J.load(private)), 2)
        combined = context + J.load(private)
        with self.assertRaisesRegex(ValueError, 'Private broker'):
            project(self.frozen, combined, self.status(), self.now)

    def status(self):
        return {'as_of': self.now.isoformat(), 'leads': [], 'requests': 0, 'errors': [], 'coverage_note': 'fixture', 'borrow_as_of': None}

    def test_projection_has_no_invented_profit_and_verifies_exact_bytes(self):
        self.enroll()
        P.write(self.directory/'status.json', self.status())
        doc = publish(self.directory, self.directory, self.now)
        self.assertIsNone(doc['policies'][0]['results']['net_closed_pnl'])
        self.assertFalse(doc['policies'][0]['results']['review_ready'])
        self.assertNotIn('order_id', P.canonical(doc))
        self.assertEqual(publish(self.directory, self.directory, check=True)['data_version'], doc['data_version'])
        file = self.directory/'dashboard/data/third_plus_forward.json'; file.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'stale'):
            publish(self.directory, self.directory, check=True)

    def test_import_checks_original_source_bytes_and_blocks_decision_import(self):
        self.enroll()
        raw = self.directory/'source.txt'; raw.write_bytes(b'paper observation export')
        doc = self.directory/'import.json'
        quote = self.observation('quote', bid=9.9, ask=10.1)
        P.write(doc, [quote])
        with self.assertRaisesRegex(ValueError, 'source-document'):
            import_evidence(doc, self.directory, [raw], now=P.stamp('2026-10-28T15:00:00Z'))
        quote['source']['sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest()
        P.write(doc, [quote])
        self.assertEqual(import_evidence(doc, self.directory, [raw], now=P.stamp('2026-10-28T15:00:00Z'))['appended'], 1)
        with self.assertRaises(ValueError):
            private_path(P.ROOT/'dashboard/private-broker-evidence')

    def test_price_filters_require_all_completed_sessions_and_exact_weak_close(self):
        days = P.sessions('2026-10-20', '2026-10-27')
        bars = [{'day': day, 'open': 10, 'high': 12, 'low': 8, 'close': 8.5, 'volume': 1000} for day in days]
        s = input_snapshot(self.candidate, {'cfo': -1, 'status': 'source_bound'}, bars, self.now)
        self.assertEqual(s['signals'], {'S7': 'pass', 'burn': 'pass', 'S5': 'pass'})
        s = input_snapshot(self.candidate, {'cfo': -1}, bars[1:], self.now)
        self.assertEqual(s['signals']['S7'], 'unknown')
        bars[2]['close'] = 13
        self.assertEqual(input_snapshot(self.candidate, {'cfo': -1}, bars, self.now)['signals']['S7'], 'fail')
        bars[-1].update(open=8, close=8, high=8, low=8)
        self.assertEqual(input_snapshot(self.candidate, None, bars, self.now)['signals']['S5'], 'unknown')

    def test_public_endpoint_allowlist_rejects_local_broker_and_paid_hosts(self):
        public_url('https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json')
        public_url('https://query1.finance.yahoo.com/v8/finance/chart/ABC?range=3mo&interval=1d')
        for url in ['http://127.0.0.1:7496', 'https://data.sec.gov/private', 'https://user:password@data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json', 'https://hist.databento.com/v0/timeseries.get_range', 'https://query1.finance.yahoo.com/redirect']:
            with self.assertRaises(ValueError):
                public_url(url)

    def test_monitor_registers_before_entry_and_observes_without_manufacturing_fills(self):
        root = self.directory/'inputs'
        data = root/'_system/data/reverse_splits'; data.mkdir(parents=True)
        raw = {'ticker': 'TEST', 'cik': '1', 'company': 'Test Company', 'ex_date': '2026-10-27',
               'split_from': 10, 'split_to': 1, 'prior_rs_count': 2, 'accept_time': '2026-10-26T20:00:00Z'}
        (data/'events.jsonl').write_text(json.dumps(raw)+'\n')
        source = self.source
        class Provider:
            errors = []
            def financials(self, cik):
                return {'cfo': -100, 'period': '2026-06-30', 'status': 'source_bound'}, source
            def prices(self, ticker):
                days = P.sessions('2026-10-20', '2026-10-27')
                return [{'day': day, 'open': 10, 'high': 12, 'low': 8, 'close': 8.5, 'volume': 1000} for day in days], source, []
        result = monitor(root, self.directory, now=self.now, provider=Provider(), publication_root=root)
        self.assertEqual(result['enrollments'], 2)
        self.assertEqual(result['errors'], 0)
        result = monitor(root, self.directory, now=self.now+timedelta(days=1), provider=Provider(), publication_root=root)
        self.assertEqual(result['enrollments'], 2)
        rows = J.load(self.path)
        self.assertFalse(any(r['record']['kind'] == 'fill' for r in rows))
        publication = json.loads((root/'dashboard/data/third_plus_forward.json').read_text())
        self.assertTrue(all(p['results']['entered'] == 0 and p['results']['net_closed_pnl'] is None for p in publication['policies']))

    def test_quote_shortfall_requires_a_preceding_available_fresh_quote(self):
        e = self.enroll()
        q = self.observation('quote', at='2026-10-28T13:30:59Z', bid=10, ask=10.2)
        self.add(q); self.entry()
        d = trade_diagnostics(J.load(self.path), e, P.stamp('2026-10-29T20:00:00Z'))
        self.assertAlmostEqual(d['entry_shortfall_bps'], (10.1-10)/10.1*10000)

    def test_registration_rejects_a_forged_signal_decision(self):
        e = self.enroll()
        e = copy.deepcopy(e); e['event_id'] = 'event/NEW'; e['issuer_id'] = 'cik/NEW'
        e['input'].update(event_id=e['event_id'], issuer_id=e['issuer_id'])
        e['input']['signals']['burn'] = 'fail'
        e['input_sha256'] = P.sha(e['input']); e['evidence_id'] = 'forged'
        with self.assertRaisesRegex(ValueError, 'differs from signals'):
            self.add(e)


if __name__ == '__main__':
    unittest.main()
