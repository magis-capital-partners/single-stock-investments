"""Foreign disclosure event dates cannot establish financial reporting epochs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autonomous_compounders as ac
from test_autonomous_compounders import inputs
from test_underwriting_pipeline import packet
from test_valuation_market_sync import fixture, save
from underwriting_evidence import evidence_readiness, prepare_packet


def submissions():
    return {'filings': {'recent': {
        'form': ['6-K', '6-K', '6-K', '40-F'],
        'filingDate': ['2026-11-03', '2026-08-06', '2026-05-06', '2026-02-01'],
        'reportDate': ['2026-11-03', '2026-08-06', '2026-05-06', '2025-12-31'],
        'accessionNumber': ['0000000123-26-000004', '0000000123-26-000003',
                            '0000000123-26-000002', '0000000123-26-000001'],
        'primaryDocument': ['dividend.htm', 'older.htm', 'oldest.htm', 'annual.htm'],
        'items': ['', '', '', '']}}}


def test_unverified_6k_event_metadata_is_not_a_financial_reporting_period():
    reports = ac.submission_reports(submissions(), '123', '2026-11-08')
    assert [r['form'] for r in reports] == ['40-F']
    assert reports[0]['period'] == '2025-12-31'


def test_a_cached_6k_event_epoch_cannot_survive_a_fresh_normal_collection(tmp_path, monkeypatch):
    prior = {'period': '2026-11-03', 'filed': '2026-11-03', 'form': '6-K',
             'accession': '0000000123-26-000004', 'source_url': 'https://www.sec.gov/old'}
    save(tmp_path, ac.INPUTS/'TEST.json', {'latest_report': prior})
    class Client:
        def get_json(self, url, **kwargs):
            return submissions() if '/submissions/' in url else {'facts': {}}
    monkeypatch.setattr(ac, '_PRIMARY_SEC_CLIENT', Client())
    monkeypatch.setattr(ac, 'quote', lambda *args: inputs()['quote'])
    monkeypatch.setattr(ac, 'provider_facts', lambda *args: inputs()['facts'])
    result = ac.collect('TEST', {'download': {'cik': '123'}}, '2026-11-08', tmp_path)
    assert result['latest_report']['period'] == '2025-12-31'
    assert result['unverified_prior_report'] == prior
    assert result['latest_disclosure']['form'] == '6-K'
    assert result['latest_disclosure']['reported_event_date'] == '2026-11-03'
    assert 'period' not in result['latest_disclosure']
    assert result['report_discovery']['status'] == 'earnings_unresolved'
    p = packet()
    p.update(latest_report=result['latest_report'], source_discovery=result['report_discovery'])
    assert 'report_discovery_failed' in {g['code'] for g in evidence_readiness(p, require_documents=True)['gaps']}


def test_failed_discovery_preserves_unverified_foreign_metadata_without_advertising_it_as_financial(tmp_path, monkeypatch):
    prior = {'period': '2026-11-03', 'filed': '2026-11-03', 'form': '6-K'}
    save(tmp_path, ac.INPUTS/'TEST.json', {'latest_report': prior})
    class Client:
        def get_json(self, url, **kwargs):
            if '/submissions/' in url:
                raise OSError('Preserved source failure')
            return {'facts': {}}
    monkeypatch.setattr(ac, '_PRIMARY_SEC_CLIENT', Client())
    monkeypatch.setattr(ac, 'quote', lambda *args: inputs()['quote'])
    monkeypatch.setattr(ac, 'provider_facts', lambda *args: inputs()['facts'])
    result = ac.collect('TEST', {'download': {'cik': '123'}}, '2026-11-08', tmp_path)
    assert not result.get('latest_report')
    assert result['unverified_prior_report'] == prior
    assert result['report_discovery']['status'] == 'failed'


def test_shared_refresh_does_not_restore_a_rejected_foreign_event_epoch(tmp_path, monkeypatch):
    from refresh_shared_forecasts import FUNDAMENTALS, refresh_missing_model_inputs
    data = fixture(tmp_path, ratio=1)
    prior = {'period': '2026-11-03', 'filed': '2026-11-03', 'form': '6-K'}
    data['latest_report'] = prior
    save(tmp_path, FUNDAMENTALS/'BKNG.json', data)
    monkeypatch.setattr(ac, 'collect', lambda *args, **kwargs: {
        'facts': data['facts'], 'quote': data['quote'], 'report_discovery': {'status': 'failed'},
        'unverified_prior_report': prior})
    refresh_missing_model_inputs('BKNG', {}, tmp_path, '2026-11-08', {})
    saved = json.loads((tmp_path/FUNDAMENTALS/'BKNG.json').read_bytes())
    assert not saved.get('latest_report')
    assert saved['unverified_prior_report'] == prior


class SourceClient:
    def __init__(self, financial=False, explicit_period=True):
        self.financial, self.explicit_period, self.requests = financial, explicit_period, []

    def get_json(self, url, **kwargs):
        return submissions() if '/submissions/' in url else {'facts': {}}

    def get_bytes(self, url, **kwargs):
        self.requests.append(url)
        if url.endswith('dividend.htm') and not self.financial:
            return b'<html><p>Quarterly dividend declared November 3, 2026.</p></html>'
        period = '<p>Three months ended September 30, 2026.</p>' if self.explicit_period else ''
        return ('<html>'+period+'<table>Consolidated balance sheet and income statements: '
                'total assets 2, cash 1, debt 1, net income 1, revenue 2 and common shares 1.</table></html>').encode()


def root(tmp_path):
    fixture(tmp_path, ratio=1)
    save(tmp_path, '_system/portfolio/registry.json', {'holdings': {'BKNG': {'download': {'cik': '123'}}}})
    # An independently supplied listing proof isolates period integrity from
    # listing reconciliation, which has its own strict primary-source tests.
    save(tmp_path, '_system/reference/valuation_listing_ratios.json', {'listings': {'BKNG': {
        'ordinary_shares_per_listing_share': 1, 'source_url': 'https://issuer.test/verified-unit',
        'source_as_of': '2026-02-01', 'locator': 'preverified fixture listing claim'}}})


def test_packet_collection_never_substitutes_older_6k_covers_after_current_failure(tmp_path):
    root(tmp_path)
    client = SourceClient()
    result = prepare_packet(tmp_path, 'BKNG', '2026-11-08', collect=False, client=client)
    assert len(client.requests) == 2
    assert not any('/older.htm' in url or '/oldest.htm' in url for url in client.requests)
    assert not any(d.get('period') == '2026-11-03' for d in result['documents'])
    assert result['collection_errors']
    assert 'foreign_primary_financial_period_unresolved' in {g['code'] for g in result['readiness']['gaps']}


def test_a_financial_6k_uses_its_completed_source_period_and_retains_the_event_date(tmp_path):
    root(tmp_path)
    result = prepare_packet(tmp_path, 'BKNG', '2026-11-08', collect=False, client=SourceClient(financial=True))
    doc = next(d for d in result['documents'] if d.get('form') == '6-K')
    assert doc['period'] == '2026-09-30'
    assert doc['reported_event_date'] == '2026-11-03'
    assert result['latest_report']['period'] != '2026-11-03'


def test_financial_tables_without_an_explicit_completed_period_cannot_inherit_a_6k_event_date(tmp_path):
    root(tmp_path)
    result = prepare_packet(tmp_path, 'BKNG', '2026-11-08', collect=False,
                            client=SourceClient(financial=True, explicit_period=False))
    assert not any(d.get('form') == '6-K' for d in result['documents'])
    assert result['collection_errors']


def test_a_registration_cover_with_a_fiscal_year_label_is_not_a_financial_statement(tmp_path):
    root(tmp_path)
    class Client(SourceClient):
        def get_bytes(self, url, **kwargs):
            if not url.endswith('dividend.htm'):
                return super().get_bytes(url, **kwargs)
            self.requests.append(url)
            return (b'<html><p>For the fiscal year ended December 31, 2025.</p>'
                    b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="issuer">123</ix:nonNumeric>'
                    b'<table><ix:nonNumeric name="dei:Security12bTitle" contextRef="listing">Common Shares</ix:nonNumeric>'
                    b'<ix:nonNumeric name="dei:TradingSymbol" contextRef="listing">BKNG</ix:nonNumeric>'
                    b'<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="listing">New York Stock Exchange</ix:nonNumeric>'
                    b'</table></html>')
    result = prepare_packet(tmp_path, 'BKNG', '2026-11-08', collect=False, client=Client())
    assert not any(d.get('form') == '6-K' for d in result['documents'])
    assert 'foreign_primary_financial_period_unresolved' in {g['code'] for g in result['readiness']['gaps']}


def test_acquisition_target_6k_period_is_also_bound_to_the_primary_financial_text(tmp_path):
    from underwriting_related_evidence import collect_target
    class Client(SourceClient):
        def get_json(self, url, **kwargs):
            if '/submissions/' in url:
                return submissions()
            return {'entityName': 'Distinct Acquisition Target Inc.', 'facts': {'us-gaap': {
                'CashAndCashEquivalentsAtCarryingValue': {'units': {'USD': [{
                    'val': 1, 'form': '40-F', 'filed': '2026-02-01', 'end': '2025-12-31',
                    'accn': '0000000123-26-000001'}]}}}}}
    result = collect_target(tmp_path, 'TARGET', '123', '2026-11-08', 'USD', client=Client(financial=True))
    doc = next(d for d in result['documents'] if d.get('form') == '6-K')
    assert doc['period'] == '2026-09-30'
    assert doc['reported_event_date'] == '2026-11-03'
    assert result['latest_report']['period'] == '2026-09-30'


@pytest.mark.parametrize('field,value', [('primaryDocument', '../escape.htm'),
                                        ('accessionNumber', 'untrusted'), ('filingDate', '2026-00-01')])
def test_unverifiable_current_foreign_disclosure_metadata_cannot_clear_discovery(field, value):
    from valuation_earnings import latest_foreign_disclosure
    source = submissions()
    source['filings']['recent'][field][0] = value
    with pytest.raises(ValueError):
        latest_foreign_disclosure(source, '123', '2026-11-08', {'filed': '2026-02-01'})


def test_foreign_amendments_are_retained_as_disclosures_and_future_filings_are_ignored():
    from valuation_earnings import latest_foreign_disclosure
    source = submissions()
    source['filings']['recent']['form'][0] = '6-K/A'
    result = latest_foreign_disclosure(source, '123', '2026-11-08', {'filed': '2026-02-01'})
    assert result['form'] == '6-K/A' and 'period' not in result
    assert latest_foreign_disclosure(source, '123', '2026-11-08', {'filed': '2026-11-03'}) is None
    assert latest_foreign_disclosure(source, '123', '2026-02-01', {'filed': '2026-02-01'}) is None
