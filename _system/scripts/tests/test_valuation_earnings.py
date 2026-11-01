"""Actual earnings releases must precede paid judgment and current valuations."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import autonomous_compounders as ac
from test_autonomous_compounders import inputs
from test_underwriting_pipeline import packet
from test_underwriting_refresh import save
from valuation_earnings import collect_earnings, latest_disclosure, reporting_period


def submissions():
    return {'filings': {'recent': {
        'form': ['8-K', '8-K', '10-Q'],
        'filingDate': ['2026-10-20', '2026-10-14', '2026-07-31'],
        'reportDate': ['2026-10-20', '2026-10-14', '2026-06-30'],
        'items': ['5.02,9.01', '2.02, 7.01,9.01', ''],
        'accessionNumber': ['0000070858-26-000490', '0000070858-26-000481', '0000070858-26-000394'],
        'primaryDocument': ['director.htm', 'bac-20261014.htm', 'bac-20260630.htm']}}}


class Client:
    def __init__(self, period=True):
        self.period, self.requests = period, []

    def get_json(self, url, **kwargs):
        self.requests.append(url)
        if '/submissions/' in url:
            return submissions()
        if url.endswith('index.json'):
            return {'directory': {'item': [{'name': 'ex991.htm'}, {'name': '../../escape.htm'}]}}
        return {'facts': {}}

    def get_bytes(self, url, **kwargs):
        self.requests.append(url)
        period = 'Three months ended September 30, 2026.' if self.period else 'Results published October 14, 2026.'
        return ('<html><p>'+period+'</p><table>Consolidated capital assets cash debt and shares. '
                'Total assets 9000, debt 1000, cash 2000 and common equity 7000. '
                'Regulatory capital CET1 ratio 12.0 percent.</table></html>').encode()


def test_earnings_event_date_is_not_the_reporting_period_and_unrelated_events_are_ignored():
    client = Client()
    disclosure, docs = collect_earnings(submissions(), '70858', '2026-10-29', {'filed': '2026-07-31'}, client)
    assert disclosure['filed'] == '2026-10-14'
    assert docs[0]['period'] == '2026-09-30'
    assert '000007085826000481/ex991.htm' in docs[0]['source_url']
    assert len(client.requests) == 2 and len(docs) == 1
    assert 'Regulatory capital' in docs[0]['contexts'][0]
    assert collect_earnings(submissions(), '70858', '2026-10-29', {'filed': '2026-07-31'}, client, docs)[1] == docs
    assert len(client.requests) == 2
    assert latest_disclosure(submissions(), '70858', '2026-10-13', {'filed': '2026-07-31'}) is None
    assert latest_disclosure(submissions(), '70858', '2026-10-29', {'filed': '2026-10-14'}) is None


@pytest.mark.parametrize('text, expected', [
    ('Published October 14, 2026. Quarter ending December 31, 2026.', None),
    ('Quarter ended Sept. 30, 2026; year ended December 31, 2025.', '2026-09-30'),
    ('Three months ended September 30, 2026', '2026-09-30'),
    ('Quarter ended December 31, 2026', None),
])
def test_reporting_period_requires_an_explicit_completed_financial_period(text, expected):
    assert reporting_period(text, '2026-10-29') == expected


@pytest.mark.parametrize('resolved', [True, False])
def test_collector_preserves_new_release_and_readiness_blocks_unresolved_period(tmp_path, monkeypatch, resolved):
    from underwriting_evidence import evidence_readiness
    monkeypatch.setattr(ac, '_PRIMARY_SEC_CLIENT', Client(resolved))
    monkeypatch.setattr(ac, 'quote', lambda *args: inputs()['quote'])
    monkeypatch.setattr(ac, 'provider_facts', lambda *args: inputs()['facts'])
    result = ac.collect('BAC', {'download': {'cik': '70858'}}, '2026-10-29', tmp_path)
    assert result['latest_disclosure']['filed'] == '2026-10-14'
    p = packet()
    p.update(latest_report=result['latest_report'], source_discovery=result['report_discovery'])
    p['documents'] = [{'form': '10-K', 'period': '2025-12-31'}, *result['primary_documents']]
    if resolved:
        assert p['latest_report']['period'] == '2026-09-30'
        assert evidence_readiness(p, require_documents=True)['status'] == 'ready'
    else:
        assert result['report_discovery']['status'] == 'earnings_unresolved'
        assert evidence_readiness(p, require_documents=True)['status'] == 'evidence_gap'


def test_unresolved_release_withdraws_the_entire_forecast_at_the_shared_gate():
    from test_shared_valuation_forecast import model, sourced_market
    from valuation_forecast import build_forecast
    result = build_forecast(model(), market=sourced_market(source_discovery={'status': 'earnings_unresolved'}))
    assert result['status'] == 'sync_gap'
    assert 'new_earnings_disclosure_unresolved' in {g['code'] for g in result['gaps']}
    assert not result['reconciliation']['passed'] and not result['buy_prices']
    assert all(value is None for value in result['forward_irr_pct'].values())
    assert all(value is None for value in result['present_value_today_per_share'].values())


def test_revised_old_facts_invalidate_the_receipt_but_quote_and_clock_changes_do_not(tmp_path, monkeypatch):
    import underwriting_pipeline
    from refresh_shared_forecasts import calculate
    from test_shared_valuation_forecast import model, sourced_market, sourced_quote
    from underwriting_evidence import source_fingerprint
    current = model()
    # This test isolates freshness of archived v1 economics. Production requires
    # v2, whose complete publication path is exercised below.
    save(tmp_path, underwriting_pipeline.POLICY, {'required_contract_schema': 'underwriting-contract/1'})
    current['underwriting'] = {'contract_hash': 'bound', 'review_due': '2027-01-24'}
    save(tmp_path, 'TEST/research/valuation.json', current)
    save(tmp_path, '_system/reference/market-data/valuation_quotes/TEST.json',
         {'quote': sourced_quote(), 'corporate_actions': sourced_market()})
    source = {'facts': [{'field': 'cash', 'value': 10, 'filed': '2026-02-01'}]}
    path = '_system/reference/market-data/valuation_fundamentals/TEST.json'
    save(tmp_path, path, source)
    receipt = {'contract_hash': 'bound', 'input_fingerprint': source_fingerprint(tmp_path, 'TEST')}
    monkeypatch.setattr(underwriting_pipeline, 'validate_saved', lambda *args: receipt)
    assert calculate('TEST', tmp_path, '2026-10-26')['status'] == 'available'
    source.update(quote={'value': 200}, retrieved_at='new clock', latest_disclosure=None)
    save(tmp_path, path, source)
    assert source_fingerprint(tmp_path, 'TEST') == receipt['input_fingerprint']
    assert calculate('TEST', tmp_path, '2026-10-26')['status'] == 'available'
    source['facts'][0]['value'] = 20
    save(tmp_path, path, source)
    result = calculate('TEST', tmp_path, '2026-10-26')
    assert result['status'] == 'sync_gap'
    assert 'new_economic_evidence_after_underwriting' in {g['code'] for g in result['gaps']}
    assert all(value is None for value in result['forward_irr_pct'].values())


def test_new_earnings_accession_changes_the_economic_fingerprint(tmp_path):
    from underwriting_evidence import source_fingerprint
    path = '_system/reference/market-data/valuation_fundamentals/TEST.json'
    source = {'facts': [], 'latest_report': {'period': '2026-06-30'}}
    save(tmp_path, path, source)
    before = source_fingerprint(tmp_path, 'TEST')
    source['latest_disclosure'] = latest_disclosure(submissions(), '70858', '2026-10-29', {'filed': '2026-07-31'})
    save(tmp_path, path, source)
    assert source_fingerprint(tmp_path, 'TEST') != before


def test_release_supplements_cannot_crowd_the_annual_report_out_of_the_packet(tmp_path):
    from test_valuation_market_sync import fixture
    from underwriting_evidence import prepare_packet
    data = fixture(tmp_path, ratio=1)
    client = Client()
    _, documents = collect_earnings(submissions(), '70858', '2026-10-29', {'filed': '2026-07-31'}, client)
    data['primary_documents'] = documents*3
    data['latest_report'] = {'period': '2026-09-30', 'filed': '2026-10-14'}
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    save(tmp_path, '_system/portfolio/registry.json', {'holdings': {'BKNG': {'download': {'cik': '70858'}}}})
    original = client.get_json
    def get_json(url, **kwargs):
        result = original(url, **kwargs)
        if '/submissions/' in url:
            recent = result['filings']['recent']
            for key, value in {'form': '10-K', 'filingDate': '2026-02-01', 'reportDate': '2025-12-31',
                               'items': '', 'accessionNumber': '0000070858-26-000100', 'primaryDocument': 'annual.htm'}.items():
                recent[key].append(value)
        return result
    client.get_json = get_json
    result = prepare_packet(tmp_path, 'BKNG', '2026-10-29', collect=False, client=client)
    assert {'10-K', '10-Q', '8-K'} <= {d['form'] for d in result['documents']}
    assert result['latest_report']['period'] == '2026-09-30'


def test_scheduled_refresh_declares_every_input_needed_to_validate_a_real_approved_model(tmp_path, monkeypatch):
    import shutil
    import yaml
    import underwriting_pipeline as pipeline
    import refresh_shared_forecasts as refresh
    import vault_paths
    from test_underwriting_pipeline import company_root
    from test_underwriting_economics import economic_contract, economic_review
    from underwriting_contract import compile_contract
    source, checkout, vault = tmp_path/'source', tmp_path/'checkout', tmp_path/'vault'
    company_root(source)
    pipeline.write(source/pipeline.POLICY, {'required_contract_schema': 'underwriting-contract/2'})
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *args, **kwargs: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *args: None)
    monkeypatch.setattr(vault_paths, 'research_vault_root', lambda: vault)
    c = economic_contract()
    def execute(stage, payload, output, receipt_path):
        pipeline.write(output,c if stage == 'author' else economic_review(c,compile_contract(packet(),c)))
        pipeline.write(receipt_path, {'agent_id':stage+'-v2','run_id':stage+'-v2','status':'finished'})
    result = pipeline.run_batch(source, launch=True, work=tmp_path/'work', vault=vault,
                                prepare=lambda *args: packet(), execute=execute)
    assert result['completed'] == ['TEST']
    pipeline.write(source/'_system/data/underwriting_queue.json', {'companies': [
        {'ticker': 'TEST', 'status': 'automatic_retry_pending', 'last_attempt': '2026-10-25T10:00:00+00:00',
         'underwriting_gaps': [{'code': 'ContractError', 'detail': 'An older draft failed review'}]}]})
    workflow = Path(__file__).resolve().parents[3]/'.github/workflows/autonomous-compounders.yml'
    steps = yaml.safe_load(workflow.read_text(encoding='utf-8'))['jobs']['refresh']['steps']
    patterns = steps[0]['with']['sparse-checkout'].split()
    for item in source.rglob('*'):
        relative = item.relative_to(source).as_posix()
        if item.is_file() and any(relative == p.lstrip('/') or relative.startswith(p.strip('/')+'/')
                                  or item.relative_to(source).match(p.lstrip('/')) for p in patterns):
            target = checkout/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
    assert pipeline.read(checkout/'_system/data/underwriting_queue.json')['companies'][0]['underwriting_gaps']
    forecast = refresh.calculate('TEST', checkout, '2026-10-26')
    assert forecast['status'] == 'available', forecast['gaps']
    assert forecast['model_basis'] == 'independent_underwriting'
    assert forecast['economic_review_status'] == 'passed'
