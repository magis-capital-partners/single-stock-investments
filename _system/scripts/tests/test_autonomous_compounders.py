"""Exercise publication at the source -> schedule -> dashboard seam."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autonomous_compounders as ac


def inputs():
    facts = []
    for year, cash in ((2023, 100), (2024, 110), (2025, 120)):
        for field, value in {'ocf': cash, 'capex': 20, 'shares': 10, 'ordinary_shares': 10,
                             'revenue': 200, 'equity': 300, 'net_income': 30, 'da': 10}.items():
            facts.append({'field': field, 'value': value, 'period': f'{year}-12-31',
                          'currency': None if 'shares' in field else 'USD',
                          'source_url': 'https://issuer.test/annual', 'locator': field,
                          'source_kind': 'primary', 'filed': f'{year+1}-02-01'})
    return {'quote': {'value': 100, 'currency': 'USD', 'as_of': '2026-10-23',
                      'source_url': 'https://provider.test/quote'}, 'facts': facts}


def test_missing_optional_acquisition_and_sbc_observations_use_explicit_funded_scenarios():
    row = ac.estimate('MA', inputs(), '2026-10-26')
    assert row['status'] == 'available'
    assert row['requires_human_review'] is False
    assert row['capital_actionable'] is False
    assert row['assumptions']['unobserved_sbc_dilution_pct'] > 0
    assert row['assumptions']['retention_ratio']['base'] > 0
    assert row['forward_irr_pct']['low'] <= row['forward_irr_pct']['base'] <= row['forward_irr_pct']['high']
    assert all(p['date'] > row['quote']['as_of'] for p in row['forward_cashflow_schedule']['base'])


def test_holding_company_uses_parent_book_not_consolidated_operating_cash():
    data = inputs()
    row = ac.estimate('MKL', data, '2026-10-26')
    assert row['status'] == 'available'
    assert row['model_route'] == 'parent_book_value'
    assert row['assumptions']['exit_price_book_multiple']['base'] == 1
    for p in data['facts']:
        if p['field'] == 'ocf':
            p['value'] *= 1000
    assert ac.estimate('MKL', data, '2026-10-26')['forward_irr_pct'] == row['forward_irr_pct']


@pytest.mark.parametrize('change', ['stale_quote', 'future_quote', 'negative_quote', 'missing_source', 'stale_facts', 'future_facts'])
def test_invalid_inputs_withhold_automatically(change):
    data = inputs()
    if change == 'stale_quote': data['quote']['as_of'] = '2026-09-01'
    if change == 'future_quote': data['quote']['as_of'] = '2026-10-27'
    if change == 'negative_quote': data['quote']['value'] = -1
    if change == 'missing_source': data['quote']['source_url'] = ''
    if change in {'stale_facts', 'future_facts'}:
        for p in data['facts']: p['period'] = '2020-12-31' if change == 'stale_facts' else '2027-12-31'
    row = ac.estimate('MA', data, '2026-10-26')
    assert row['status'] != 'available'
    assert row['forward_irr_pct'] is None
    assert row['next_action'] == 'automatic_retry'
    assert row['requires_human_review'] is False


def test_fx_cannot_be_silently_assumed():
    data = inputs()
    data['quote']['currency'] = 'CAD'
    assert ac.estimate('CSU', data, '2026-10-26')['status'] != 'available'
    data['fx'] = {'from_currency': 'USD', 'to_currency': 'CAD', 'value': 1.4,
                  'as_of': '2026-10-23', 'source_url': 'https://provider.test/fx'}
    assert ac.estimate('CSU', data, '2026-10-26')['status'] == 'available'


def test_primary_parser_rejects_quarters_and_not_yet_filed_reports():
    rows = [{'start': '2025-01-01', 'end': '2025-12-31', 'filed': '2026-02-01', 'val': 100},
            {'start': '2026-01-01', 'end': '2026-03-31', 'filed': '2026-05-01', 'val': 90},
            {'start': '2025-01-01', 'end': '2025-12-31', 'filed': '2026-12-01', 'val': 999}]
    payload = {'facts': {'us-gaap': {'NetCashProvidedByUsedInOperatingActivities': {'units': {'USD': rows}}}}}
    facts = ac.primary_facts(payload, 'https://data.sec.gov/test', '2026-10-26')
    assert len(facts) == 1 and facts[0]['value'] == 100


def test_partial_refresh_preserves_other_companies_and_withdraws_old_estimate(tmp_path):
    def write(p, d):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d))
    write(tmp_path / '_system/reference/core_compounders.json', {'tickers': ['MA', 'V']})
    write(tmp_path / ac.INPUTS / 'MA.json', inputs())
    write(tmp_path / ac.STATE, {'companies': {'V': {'status': 'available', 'forward_irr_pct': {'base': 7}}}})
    write(tmp_path / 'dashboard/data/core.json', {'tickers': [{'ticker': 'MA'}, {'ticker': 'V'}]})
    write(tmp_path / 'dashboard/data/tickers/MA.json', {'ticker': 'MA'})
    result = ac.run(tmp_path, '2026-10-26', tickers=['MA'])
    assert result['companies']['V']['forward_irr_pct']['base'] == 7
    assert result['companies']['MA']['status'] == 'available'
    result = ac.run(tmp_path, '2026-11-26', tickers=['MA'])
    assert result['companies']['MA']['forward_irr_pct'] is None
    assert ac.read(tmp_path / 'dashboard/data/core.json')['tickers'][0]['autonomous_irr']['status'] != 'available'


def test_retry_retains_source_cache_without_fabrication(tmp_path):
    path = tmp_path / ac.INPUTS / 'MA.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(inputs()))
    with patch.object(ac, 'quote', side_effect=OSError('offline')), patch.object(ac, 'provider_facts', side_effect=OSError('offline')):
        result = ac.collect('MA', {}, '2026-10-26', tmp_path)
    assert result['facts'] == inputs()['facts']
    assert result['quote'] == inputs()['quote']
    assert len(result['errors']) == 2
    assert all(x['retry'] == 'next_scheduled_run' for x in result['errors'])


def test_ferrari_and_hermes_do_not_require_membership_fees():
    config = ac.read(Path(__file__).resolve().parents[2] / 'reference/core_compounders.json')
    for ticker in ('RACE', 'RMS.PA'):
        assert 'membership_fee_income_m' not in config['issuers'][ticker]['kpi_ids']


def test_owner_cash_proof_bridge_reads_flows_not_present_value():
    from tci_return_bridge import build_bridge
    fact = lambda key, value: {'id': key, 'value': value, 'kind': 'fact', 'unit': 'USD millions',
                              'source': {'ref': 'https://issuer.test/report', 'as_of': '2025-12-31', 'locator': key}, 'locked': True}
    proof = {'schema_version': '1.0', 'method_id': 'owner_earnings_reinvestment_dcf', 'method_version': '1.0',
             'output_unit': 'USD per share', 'inputs': [fact('shares_m', 10), fact('terminal_value', 1000),
             *[fact(f'owner_cash_y{y}', 100) for y in range(1, 8)]],
             'calculations': [{'id': 'pv', 'op': 'divide', 'args': ['terminal_value', 'shares_m'], 'unit': 'USD per share'}],
             'outputs': {c: 'pv' for c in ('low', 'base', 'high')}}
    model = {'ticker': 'CPRT', 'method': 'owner_earnings_reinvestment_dcf', 'inputs': {'price': 100},
             'component_valuation_results': {'additive_components': [{'calculation_proof': proof}]}}
    bridge = build_bridge(model)
    assert len(bridge['scenarios']) == 3
    assert bridge['scenarios']['base']['exact_irr_pct'] > 0
    assert bridge['forward_cashflow_schedule']['base'][-1]['amount_per_share'] == 110
    proof['calculations'][0]['args'] = [1, 10]  # Alter PV only, leave undiscounted economics intact.
    assert build_bridge(model)['scenarios'] == bridge['scenarios']


def test_later_dashboard_build_expires_stale_returns(tmp_path):
    row = ac.estimate('MA', inputs(), '2026-10-26')
    p = tmp_path / ac.STATE
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'companies': {'MA': row}}))
    assert ac.load_estimate('MA', tmp_path, '2026-10-26')['status'] == 'available'
    expired = ac.load_estimate('MA', tmp_path, '2026-11-26')
    assert expired['forward_irr_pct'] is None
    assert expired['next_action'] == 'automatic_retry'


def test_frmo_parser_scales_parent_equity_and_diluted_shares_not_par_value():
    texts = ["Consolidated Balance Sheets\n(in thousands, except par value amounts)\n2026 2025\nStockholders' equity attributable to the Company 330,977 327,899",
             'Consolidated Statements of Operations\n(in thousands, except per share data)\nNet income (loss) attributable to the Company $ 2,936 $ 100,454\nWeighted average shares outstanding\nBasic 44,023 44,023\nDiluted 44,027 44,030']
    facts = ac.parse_frmo_report(texts, 'https://issuer.test/report.pdf', 2026, '2026-10-26', 'hash')
    current = {p['field']: p['value'] for p in facts if p['period'] == '2026-05-31'}
    assert current == {'equity': 330977000, 'net_income': 2936000, 'shares': 44027000}
    with pytest.raises(ValueError):
        ac.parse_frmo_report([t.replace('(in thousands', '(in units') for t in texts], 'https://issuer.test/report.pdf', 2026, '2026-10-26', 'hash')


def test_core_rows_keep_returns_but_not_large_cashflow_histories():
    from build_dashboard_shards import slim_ticker_row
    full = ac.estimate('MA', inputs(), '2026-10-26')
    row = slim_ticker_row({'ticker': 'MA', 'autonomous_irr': full})
    assert row['autonomous_irr']['forward_irr_pct'] == full['forward_irr_pct']
    assert 'financial_observations' not in row['autonomous_irr']
    assert 'forward_cashflow_schedule' not in row['autonomous_irr']


def test_multiple_twelve_month_ends_do_not_create_revisions_on_every_replay(tmp_path):
    data = inputs()
    extra = [dict(p, period='2025-06-30', value=p['value'] * 2) for p in data['facts'] if p['period']=='2025-12-31']
    data['facts'] += extra
    points = ac.operating_points('MA', data)
    assert len(points) == len({(p['kpi'],p['period']) for p in points})
    assert all(p['fiscal_period_end']=='2025-12-31' for p in points if p['period']=='2025')
    from operating_kpis import model
    with patch.object(model, 'STORE_DIR', tmp_path):
        path = model.write_ticker_store('MA', points, sources=[], fetched_at='2026-10-26')
        original = path.read_bytes()
        model.write_ticker_store('MA', points, sources=[], fetched_at='2026-10-26')
        assert path.read_bytes() == original
