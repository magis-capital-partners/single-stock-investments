"""Regressions at the forecast -> PV/return -> served decision seam."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from universal_valuation_contract import build_universal_valuation_contract
from valuation_forecast import build_forecast, _irr, _npv, attach_forecast


def model():
    """A small owner-cash proof with scenario rates and excess cash."""
    return {
        'ticker': 'TEST', 'as_of': '2026-10-26',
        'inputs': {'price': 100, 'price_as_of': '2026-10-26', 'price_source': 'https://issuer.test/quote'},
        'valuation_methodology': {'horizon_years': 2},
        'component_valuation_results': {'all_material_components_identified': True,
            'additive_components': [{'id': 'business', 'method': 'owner_earnings_reinvestment_dcf',
                'treatment': 'additive', 'category': 'operating_business',
                'calculation_proof': {
                    'schema_version': '1.0', 'method_id': 'owner_earnings_reinvestment_dcf',
                    'method_version': '1.0', 'output_unit': 'USD per share',
                    'inputs': [{'id': 'cash', 'value': 10, 'unit': 'USD per share', 'kind': 'fact', 'locked': True,
                        'source': {'ref': 'https://issuer.test/filing', 'locator': 'excess cash', 'as_of': '2026-10-26'}}],
                    'assumptions': [
                        {'id': 'owner_cash', 'kind': 'judgment', 'value': 10, 'unit': 'USD per share', 'rationale': 'Distributable cash', 'allowed_range': {'min': 0, 'max': 20}},
                        {'id': 'terminal', 'kind': 'judgment', 'value': 120, 'unit': 'USD per share', 'rationale': 'Equity sale proceeds', 'allowed_range': {'min': 0, 'max': 200}},
                        {'id': 'discount_rate', 'kind': 'judgment', 'values': {'low': .12, 'base': .1, 'high': .08}, 'unit': 'ratio', 'rationale': 'Scenario hurdles', 'allowed_range': {'min': .01, 'max': .2}},
                    ],
                    'calculations': [
                        {'id': 'cash_pv', 'op': 'present_value', 'args': ['owner_cash', 1, 'owner_cash', 2, 'discount_rate'], 'unit': 'USD per share'},
                        {'id': 'terminal_pv', 'op': 'discount', 'args': ['terminal', 'discount_rate', 2], 'unit': 'USD per share'},
                        {'id': 'operating', 'op': 'add', 'args': ['cash_pv', 'terminal_pv'], 'unit': 'USD per share'},
                        {'id': 'value_per_share', 'op': 'add', 'args': ['operating', 'cash'], 'unit': 'USD per share'},
                    ],
                    'outputs': {c: 'value_per_share' for c in ('low', 'base', 'high')},
                }}]},
    }


def test_contract_has_one_shared_forecast_for_pv_and_irr():
    result = build_universal_valuation_contract(model())
    forecast = result.get('shared_forecast') or {}
    assert forecast.get('status') == 'available', forecast
    assert forecast['present_value_today_per_share']['base'] == pytest.approx(126.5289, abs=.0001)
    assert forecast['forward_irr_pct']['base'] is not None
    assert forecast['reconciliation']['passed']


def test_scenario_discount_rates_are_preserved():
    forecast = build_universal_valuation_contract(model()).get('shared_forecast') or {}
    assert forecast.get('required_return_pct') == {'low': 12, 'base': 10, 'high': 8}


def test_price_change_cannot_change_the_model_forecast_or_pv():
    before = build_universal_valuation_contract(model()).get('shared_forecast') or {}
    changed = copy.deepcopy(model())
    changed['inputs']['price'] = 110
    after = build_universal_valuation_contract(changed).get('shared_forecast') or {}
    assert before.get('status') == 'available'
    assert before['forecast_hash'] == after['forecast_hash']
    assert before['present_value_today_per_share'] == after['present_value_today_per_share']
    assert after['forward_irr_pct']['base'] < before['forward_irr_pct']['base']


def test_pv_and_every_hurdle_reprice_to_their_required_return():
    forecast = build_forecast(model())
    for case, rate in [('low', 12), ('base', 10), ('high', 8)]:
        rows = forecast['forward_cashflow_schedule'][case]
        assert _irr(forecast['present_value_today_per_share'][case], rows) == pytest.approx(rate, abs=.01)
        for zone in forecast['buy_prices']:
            assert _irr(zone['prices'][case], rows) == pytest.approx(zone['hurdle_pct'], abs=.01)


def test_later_quote_rolls_remaining_forecast_without_moving_cash_dates():
    original = build_forecast(model())
    later = build_forecast(model(), quote={'value': 100, 'as_of': '2027-10-27', 'source_url': 'https://provider.test'}, as_of='2027-10-27')
    assert later['status'] == 'available'
    assert later['forecast_hash'] == original['forecast_hash']
    assert later['model_present_value_per_share'] == original['model_present_value_per_share']
    flows = later['forward_cashflow_schedule']['base']
    assert all(p['year'] >= 0 for p in flows)
    assert len([p for p in flows if p['year'] > 0]) == 2
    assert later['present_value_today_per_share']['base'] == pytest.approx(_npv(flows), abs=.0001)


def test_nav_without_realization_timing_does_not_become_a_book_value_return():
    value = model()
    proof = value['component_valuation_results']['additive_components'][0]['calculation_proof']
    proof['calculations'] = []
    proof['outputs'] = {c: 'terminal' for c in ('low', 'base', 'high')}
    value['ticker'] = 'AMZN'
    result = build_forecast(value)
    assert result['status'] == 'model_gap'
    assert 'realization_timing_missing' in result['gaps'][0]['code']
    assert result['forward_irr_pct']['base'] is None


def test_explicit_milestone_payoff_uses_its_date_and_scenario_discount_rate():
    value = model()
    c = value['component_valuation_results']['additive_components'][0]
    proof = c['calculation_proof']
    proof['calculations'] = []
    proof['outputs'] = {case: 'terminal' for case in ('low', 'base', 'high')}
    proof['output_basis'] = 'future_payoff'
    c['probability_and_timing'] = {'horizon_years': 2}
    f = build_forecast(value)
    assert f['status'] == 'available'
    assert f['present_value_today_per_share']['base'] == pytest.approx(120/1.1**2, abs=.0001)
    assert f['forward_irr_pct']['base'] == pytest.approx(((120/100)**.5-1)*100, abs=.01)


def test_multiple_component_rates_are_not_flattened_to_one_base_rate():
    value = model()
    second = copy.deepcopy(value['component_valuation_results']['additive_components'][0])
    second['id'] = 'second_business'
    second['calculation_proof']['assumptions'][-1]['values'] = {'low': .15, 'base': .13, 'high': .11}
    value['component_valuation_results']['additive_components'].append(second)
    f = build_forecast(value)
    assert f['status'] == 'available'
    assert f['required_return_pct']['base'] is None
    assert f['present_value_today_per_share']['base'] == pytest.approx(126.52892562 + 10 + 10/1.13 + 130/1.13**2, abs=.0002)


@pytest.mark.parametrize('change,reason', [('stale_quote', 'fresh_sourced_quote_missing'), ('future_source', 'future_dated_source'), ('currency', 'dated_reporting_to_listing_fx_missing'), ('coverage', 'material_component_coverage_incomplete')])
def test_invalid_inputs_withhold_research_returns_automatically(change, reason):
    value = model()
    quote = {'value': 100, 'as_of': '2026-10-26', 'currency': 'USD', 'source_url': 'https://issuer.test/quote'}
    if change == 'stale_quote': quote['as_of'] = '2026-09-01'
    if change == 'future_source': value['component_valuation_results']['additive_components'][0]['calculation_proof']['inputs'][0]['source']['as_of'] = '2027-01-01'
    if change == 'currency': quote['currency'] = 'EUR'
    if change == 'coverage': value['component_valuation_results']['all_material_components_identified'] = False
    f = build_forecast(value, quote=quote, as_of='2026-10-26')
    assert f['status'] != 'available'
    assert any(g['code'] == reason for g in f['gaps'])
    assert f['requires_human_review'] is False


def test_research_publication_is_independent_of_committee_status():
    f = build_forecast(model())
    row = attach_forecast({'valuation_decision': {'return_publishable': False, 'model_level': 'screening_grade'}}, f)
    assert row['valuation_decision']['research_return_available']
    assert row['valuation_decision']['return_publishable'] is False
    assert row['valuation_decision']['value_per_share'] == f['present_value_today_per_share']


def test_full_universe_publication_replays_and_rejects_served_tampering(tmp_path):
    import json
    import refresh_shared_forecasts as refresh
    def save(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding='utf-8')
    save(tmp_path/'dashboard/data/core.json', {'tickers': [{'ticker': 'TEST'}, {'ticker': 'MISSING'}]})
    save(tmp_path/'TEST/research/valuation.json', model())
    report = refresh.run(tmp_path, '2026-10-26')
    assert report['summary']['companies'] == 2
    assert report['summary']['available'] == 1
    assert refresh.check(tmp_path)['companies'] == 2
    core = json.loads((tmp_path/'dashboard/data/core.json').read_text(encoding='utf-8'))
    core['tickers'][0]['valuation_decision']['forward_return_at_price_pct']['base'] = 99
    save(tmp_path/'dashboard/data/core.json', core)
    with pytest.raises(ValueError, match='served forward_return'):
        refresh.check(tmp_path)


def test_legacy_full_model_keeps_issuer_growth_multiple_and_distributions():
    from legacy_forecast_model import build
    from marvin_valuation import cashflows_full
    value = {'ticker': 'TEST', 'method': 'full', 'as_of': '2026-10-26',
        'inputs': {'price': 100, 'price_as_of': '2026-10-26', 'price_source': 'https://provider.test', 'fcf_per_share': 4, 'fcf_source': 'Issuer normalized owner cash'},
        'scenarios': {name: {'growth_y1_5': .07, 'growth_y6_10': .04, 'exit_pfcf_y10': 22} for name in ('bear', 'base', 'bull')}}
    adapted = build(value, currency='USD')
    f = build_forecast(adapted)
    expected = cashflows_full(100, 4, .07, .04, 22, years=7)
    assert f['status'] == 'available'
    assert f['forward_cashflow_schedule']['base'][-1]['amount_per_share'] == pytest.approx(expected[-1]-expected[-1]/23)  # Terminal is a separate flow.
    assert sum(p['amount_per_share'] for p in f['forward_cashflow_schedule']['base']) == pytest.approx(sum(expected[1:]))


def test_automatic_model_uses_one_proof_and_source_bound_listing_ratio():
    from automatic_forecast_model import build
    from test_autonomous_compounders import inputs
    facts = inputs()
    facts['model_anchor'] = '2026-10-26'
    ordinary = build('TEST', facts, {}, '2026-10-26')
    ratio = {'ordinary_shares_per_listing_share': 5, 'source_url': 'https://issuer.test/adr', 'locator': '5 ordinary shares per ADS', 'source_as_of': '2026-01-01'}
    adr = build('TEST', facts, {}, '2026-10-26', share_basis=ratio)
    q = {'value': 100, 'as_of': '2026-10-26', 'currency': 'USD', 'source_url': 'https://provider.test'}
    f1, f5 = build_forecast(ordinary, quote=q), build_forecast(adr, quote=q)
    assert f1['status'] == f5['status'] == 'available'
    assert f5['present_value_today_per_share']['base'] == pytest.approx(f1['present_value_today_per_share']['base']*5, abs=.001)


def test_quote_without_close_array_requires_a_dated_regular_price(monkeypatch):
    import autonomous_compounders as ac
    from datetime import datetime, timezone
    timestamp = int(datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp())
    data = {'chart': {'result': [{'meta': {'symbol': 'TEST', 'currency': 'USD', 'regularMarketTime': timestamp, 'regularMarketPrice': 100}, 'indicators': {'quote': [{}]}}]}}
    monkeypatch.setattr(ac, 'get_json', lambda url: data)
    assert ac.quote('TEST', '2026-10-26')['value'] == 100
    data['chart']['result'][0]['meta'].pop('regularMarketTime')
    with pytest.raises(ValueError, match='positive dated quote'):
        ac.quote('TEST', '2026-10-26')


def test_wrong_issuer_quote_is_rejected_without_a_manual_gate():
    from refresh_shared_forecasts import quote_identity
    identity = quote_identity('EVR', {'company': 'Evolve Royalties Ltd'}, {'company_name': 'Evercore Inc.', 'symbol': 'EVR'}, {})
    assert identity['status'] == 'mismatch'
    f = build_forecast(model(), quote={'value': None, 'identity_status': 'mismatch', 'currency': 'USD', 'as_of': '2026-10-26', 'source_url': 'https://provider.test'})
    assert f['status'] == 'identity_gap'
    row = attach_forecast({'valuation_decision': {'price_per_share': 123, 'margin_of_safety_pct': {'base': 99}}}, f)
    assert row['valuation_decision']['price_per_share'] is None
    assert row['valuation_decision']['margin_of_safety_pct']['base'] is None
    assert not row['valuation_decision']['research_return_available']


def test_primary_cik_handles_a_verified_issuer_rename(monkeypatch):
    from refresh_shared_forecasts import quote_identity
    monkeypatch.setattr('sec_client.SecClient.get_json', lambda self, url, **kwargs: {'name': 'Meta Platforms Inc.', 'tickers': ['META']})
    result = quote_identity('META', {'company': 'Facebook'}, {'company_name': 'Meta Platforms Inc.', 'symbol': 'META'}, {'META': {'download': {'cik': 1326801}}})
    assert result['status'] == 'primary_cik_match'
    assert result['source_url'].endswith('CIK0001326801.json')


def test_issuer_alias_requires_a_bound_source_and_matching_expected_company():
    from refresh_shared_forecasts import quote_identity
    aliases = {'WAB': {'expected_company': 'Wabtec', 'provider_name': 'Westinghouse Air Brake Technologies Corporation', 'source_url': 'https://issuer.test/10k'}}
    quote = {'company_name': 'Westinghouse Air Brake Technologies Corporation', 'symbol': 'WAB'}
    assert quote_identity('WAB', {'company': 'Wabtec'}, quote, {}, aliases)['status'] == 'matched_name_alias'
    assert quote_identity('WAB', {'company': 'Another Issuer'}, quote, {}, aliases)['status'] == 'mismatch'


def test_missing_model_reports_the_actual_missing_financial_input():
    from automatic_forecast_model import missing_inputs
    from test_autonomous_compounders import inputs
    data = inputs()
    data['facts'] = [p for p in data['facts'] if p['field'] != 'capex']
    assert missing_inputs('TEST', data, {}, '2026-10-26') == ['annual_capex_missing']


def test_replay_reads_served_content_even_when_its_timestamp_is_reused(tmp_path):
    import json
    import os
    import refresh_shared_forecasts as refresh
    core = tmp_path/'dashboard/data/core.json'
    core.parent.mkdir(parents=True)
    core.write_text(json.dumps({'tickers': [{'ticker': 'TEST'}]}), encoding='utf-8')
    source = tmp_path/'TEST/research/valuation.json'
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(model()), encoding='utf-8')
    refresh.run(tmp_path, '2026-10-26')
    refresh.universe(tmp_path)
    before = core.stat()
    text = core.read_text(encoding='utf-8')
    core.write_text(text.replace('"calculation_status":"available"', '"calculation_status":"model_gap"').replace('"calculation_status": "available"', '"calculation_status": "model_gap"'), encoding='utf-8')
    os.utime(core, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ValueError, match='served calculation_status'):
        refresh.check(tmp_path)
