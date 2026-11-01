"""Offline regressions for subject attribution, fund economics and publication dates."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_insights as builder
from insider_signal_common import parse_form4_xml, issuer_symbol_for_security, build_insider_signal
from event_triage import triage_event, load_rules
from security_profiles import resolve_economic_profile, canonical_symbol
from event_relevance import assess_relevance

FORM4 = '''<ownershipDocument><issuer><issuerCik>920760</issuerCik>
<issuerName>LENNAR CORP</issuerName><issuerTradingSymbol>LEN</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>1067983</rptOwnerCik>
<rptOwnerName>BERKSHIRE HATHAWAY INC</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isTenPercentOwner>1</isTenPercentOwner></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Class A Common Stock</value></securityTitle>
<transactionDate><value>2026-09-18</value></transactionDate>
<transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>2743529</value></transactionShares>
<transactionPricePerShare><value>77.41675</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>'''


class AttributionTests(unittest.TestCase):
    def test_real_lennar_multi_symbol_header_resolves_share_class(self):
        self.assertEqual(issuer_symbol_for_security('LEN, LEN.B', 'Class A Common Stock'), 'LEN')
        self.assertEqual(issuer_symbol_for_security('LEN, LEN.B', 'Class B Common Stock'), 'LEN.B')
        self.assertIsNone(issuer_symbol_for_security('LEN, LEN.B', 'Common Stock'))

    def test_berkshire_trade_does_not_inflate_berkshire_conviction(self):
        row = parse_form4_xml(FORM4, {})[0]
        self.assertIsNone(build_insider_signal('BRK.B', [row]))

    def test_parser_keeps_actor_and_issuer_separate(self):
        row = parse_form4_xml(FORM4, {"filing_date": "2026-09-21"})[0]
        self.assertEqual(row.get("issuer_ticker"), "LEN")
        self.assertEqual(row.get("issuer_cik"), "920760")
        self.assertEqual(row.get("owner_cik"), "1067983")
        self.assertEqual(row.get("security_title"), "Class A Common Stock")

    def test_missing_code_is_not_invented_from_acquisition_flag(self):
        row = parse_form4_xml(FORM4.replace('<transactionCode>P</transactionCode>', ''), {})[0]
        self.assertEqual(row["transaction_code"], "")

    def test_builder_routes_berkshire_purchase_to_lennar(self):
        row = parse_form4_xml(FORM4, {"filing_date": "2026-09-21", "accession": "fixture"})[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'transactions.csv'
            with path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'tickers': {'BRK.B': {'csv': str(path)}}}))
            with patch.object(builder, 'INSIDER_MANIFEST', manifest):
                rows = builder.from_insider_transactions({'BRK.B', 'LEN'}, holdings_tickers={'BRK.B', 'LEN'})
        direct = [r for r in rows if r['ref'] == 'LEN']
        self.assertEqual(len(direct), 1)
        self.assertIn('LEN', direct[0]['title'])
        self.assertEqual(direct[0]['actor_name'], 'BERKSHIRE HATHAWAY INC')
        related = [r for r in rows if r['ref'] == 'BRK.B']
        self.assertTrue(related)
        self.assertTrue(all(r['relationship'] == 'indirect' for r in related))
        self.assertTrue(all(r['direction'] == 'neutral' for r in related))


class RelevanceTests(unittest.TestCase):
    def event(self, ticker='ETHA', **extra):
        return dict(ticker=ticker, source='filing', event_type='filing_metric',
                    impact_axis='fundamentals', metric_name='net_income', change_pct=-99,
                    prior_value=200000, current_value=2000, confidence='high',
                    in_our_book=True, freshness_days=0, direction='bearish',
                    evidence_ref='fixture://primary-evidence',
                    verification={'parser_confidence': 'high', 'context_verified': True, 'unit': 'USD'},
                    **extra)

    def triage(self, event):
        return triage_event(event, rules=load_rules(), activist_tickers=set())

    def test_fund_net_income_cannot_be_auto_promoted(self):
        result = self.triage(self.event())
        self.assertEqual(result['tier'], 'context')
        self.assertEqual(result['direction'], 'neutral')
        self.assertEqual(result['economic_channel'], 'accounting_context')

    def test_insider_score_preservation_cannot_bypass_subject_gate(self):
        event = dict(ticker='BRK.B', source='insider', event_type='form4_transaction',
                     issuer_ticker='LEN', entity_verified=False, direction='bullish',
                     materiality=99, tier='signal', materiality_components={'size': 1.1})
        self.assertNotEqual(self.triage(event)['tier'], 'signal')

    def test_cik_mismatch_cannot_be_overridden_by_matching_symbol(self):
        event = dict(ticker='LEN', source='insider', event_type='form4_transaction',
                     issuer_ticker='LEN', issuer_cik='999', entity_verified=False,
                     materiality=99, tier='signal', materiality_components={'size': 1.1})
        self.assertNotEqual(self.triage(event)['tier'], 'signal')

    def test_unverified_aggregate_does_not_become_a_conviction_signal(self):
        event = dict(ticker='LEN', source='insider', event_type='insider_signal',
                     title='Insider conviction: exceptional', materiality=99, tier='signal',
                     materiality_components={'ics': 1.1})
        result = self.triage(event)
        self.assertNotEqual(result['tier'], 'signal')
        self.assertIn('verification required', result['title'])
        self.assertIsNone(result['published_at'])

    def test_source_confidence_cannot_replace_linked_evidence(self):
        event = self.event('ICE')
        event.pop('evidence_ref')
        self.assertNotEqual(self.triage(event)['tier'], 'signal')

    def test_unsourced_governance_watch_does_not_reappear_as_todays_news(self):
        result = self.triage({'ticker':'ICE','source':'kpi_trend','event_type':'leadership_risk',
            'impact_axis':'governance','direction':'bearish','confidence':'high',
            'observed_at':'2026-10-20','published_at':'2026-10-20','in_our_book':True})
        self.assertNotEqual(result['tier'], 'signal')
        self.assertIsNone(result['published_at'])
        self.assertEqual(result['processed_at'], '2026-10-20')

    def test_invalid_numeric_data_becomes_noise_without_crashing(self):
        event = self.event()
        event['prior_value'] = 'bad parse'
        self.assertEqual(self.triage(event)['tier'], 'noise')

    def test_bank_funding_cash_change_is_not_generic_bullish_evidence(self):
        event = self.event('JPM')
        event['metric_name'] = 'cash'
        result = self.triage(event)
        self.assertNotEqual(result['tier'], 'signal')
        self.assertEqual(result['direction'], 'neutral')

    def test_unknown_instrument_cannot_receive_generic_earnings_signal(self):
        self.assertNotEqual(self.triage(self.event('ZZUNKNOWN'))['tier'], 'signal')

    def test_important_custody_event_survives_fund_filter(self):
        e = self.event()
        e.update(event_type='custody_loss', metric_name='custody_loss', impact_axis='risk',
                 title='Custody shortfall confirmed', economic_channel='wrapper_risk')
        self.assertEqual(self.triage(e)['tier'], 'signal')

    def test_filing_rebuild_keeps_original_publication_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'research/evidence'
            evidence.mkdir(parents=True)
            (evidence / 'filing_facts_2026-10-20.json').write_text(json.dumps({
                'as_of': '2026-10-20', 'filing_meta': {'filing_date': '2026-02-27', 'period_end': '2025-12-31'},
                'metrics': {'net_income': {'current': 100, 'prior': 200, 'tag': 'NetIncomeLoss',
                    'parser_confidence': 'high', 'parser_flags': [], 'context_verified': True, 'unit': 'USD'}}
            }))
            rows = builder.from_filing_facts(root, 'ETHA')
        self.assertEqual(rows[0]['as_of'], '2026-02-27')
        self.assertEqual(rows[0]['processed_at'], '2026-10-20')


class ProfileTests(unittest.TestCase):
    def test_profiles_cover_distinct_structures(self):
        for name, expected in [('Example ETF', 'asset_fund'), ('Example Futures ETF', 'futures_fund'),
                               ('Example 2x ETF', 'leveraged_fund'), ('Example REIT', 'reit'),
                               ('Example Bank', 'bank'), ('Example Insurance', 'insurer')]:
            result = resolve_economic_profile('EX', entry={'company': name})
            self.assertEqual(result['economic_profile'], expected)

    def test_aliases_keep_different_classes_distinct(self):
        self.assertEqual(canonical_symbol('BRK-B'), canonical_symbol('BKRB'))
        self.assertNotEqual(canonical_symbol('LEN'), canonical_symbol('LEN.B'))

    def test_unresolved_identity_does_not_inherit_a_valuation_route(self):
        from automate_valuation_readiness import resolve_identity
        identity = resolve_identity('UNKNOWN', {'company': 'UNKNOWN'}, {}, '2026-10-20',
            {'status':'routed','score':16,'profile_id':'quality_reinvestment','primary_methods':['owner_earnings_reinvestment_dcf']})
        self.assertEqual(identity['classification_status'], 'unresolved')
        self.assertIsNone(identity['primary_method'])

    def test_documented_metric_adjustments_only_demote(self):
        profile = resolve_economic_profile('EX', entry={'company':'Example Corp'}, override={
            'metric_importance': {'net_income': {'importance':'context', 'reason':'Fair value gains obscure operations.', 'evidence':'fixture://annual-report'}}})
        result = assess_relevance({'ticker':'EX','source':'earnings','metric_name':'net_income','security_profile':profile})
        self.assertEqual(result['eligibility_cap'], 'context')
        self.assertIn('Fair value gains', result['why_it_matters'])


if __name__ == '__main__':
    unittest.main()
