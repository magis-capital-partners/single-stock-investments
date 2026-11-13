"""Economic response, units, source failure, availability and issuer reconciliation."""
import copy
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commodity_common import load, save
from commodity_company_bridge import (
    asset_cashflow,
    build_companies,
    sjt_case,
    stream_case,
)
from commodity_forecast_scores import score
from commodity_observations import (
    available,
    meaningful_diff,
    observation,
    pack,
    source_state,
    unpack,
    weighted_readiness,
)
from commodity_operating_cases import (
    data_center_load,
    gold_flow,
    propagate,
    refinery_products,
    weather_demand,
)
from commodity_physics import (
    concentrate_balance,
    cost_curve,
    hourly_dispatch,
    lng_feedgas,
    mine_output,
    pv_silver,
    regional_gas_step,
    warehouse,
)
from commodity_resolution import DATA
from fetch_commodity_resolution import refresh
from fetch_energy_assets import parse_lng_trains

ASOF = date(2026, 11, 13)
SOURCE = {'id': 'fixture', 'url': 'https://example.org/table', 'published_at': '2026-11-01',
          'retrieved_at': '2026-11-02', 'reviewed_at': '2026-11-03', 'sha256': 'a'*64, 'max_age_days': 35}


def obs(**kwargs):
    return observation(value=5, source=SOURCE, period='2026-10', metric='production',
                       commodity='gas', unit='bcf/day', frequency='monthly', **kwargs)


def test_identity_vintage_roundtrip_and_availability():
    row = obs()
    assert available([row], date(2026, 11, 2)) == []
    assert available([row], ASOF) == [row]
    assert unpack({'datasets': pack([row])}) == [row]
    other = obs(region='Permian')
    assert other['id'] != row['id']
    revised = {**row, 'value': 6, 'vintage': 'b'*64, 'known_at': '2026-11-10'}
    assert available([row, revised], ASOF) == [revised]
    assert meaningful_diff([row], [revised])[0]['change'] == 1


def test_freshness_release_failure_and_weighted_core_readiness():
    req = [{'match': {'metric': 'production'}, 'weight': 9, 'core': True, 'missing_reason': 'missing'},
           {'match': {'metric': 'cost'}, 'weight': 1, 'core': False, 'missing_reason': 'optional'}]
    result = weighted_readiness(req, [obs()], [SOURCE], ASOF)
    assert result['weighted_pct'] == 90 and result['core_ready']
    failed = {**SOURCE, 'error': 'TimeoutError'}
    assert source_state(failed, ASOF)['state'] == 'retained_after_failure'
    assert weighted_readiness(req, [obs()], [failed], ASOF)['weighted_pct'] == 0
    assert source_state({**SOURCE, 'next_release': '2026-11-10'}, ASOF)['state'] == 'overdue'
    assert source_state({**SOURCE, 'reviewed_sha256': 'b'*64}, ASOF)['state'] == 'review_due'


def test_solar_units_thrifting_mix_and_recovered_scrap():
    tech = [{'share': .8, 'mg_per_watt': 10}, {'share': .2, 'mg_per_watt': 20}]
    base = pv_silver(1000, tech)
    assert base['pv_moz'] == pytest.approx(12000/31.1034768)
    assert pv_silver(1000, tech, .8)['pv_moz'] == pytest.approx(base['pv_moz']/0.8)
    with pytest.raises(ValueError):
        pv_silver(1000, [{'share': .5, 'mg_per_watt': 10}])


def test_copper_split_ramp_ownership_life_and_missing_inputs():
    assert concentrate_balance(100, None, 0, 0, 90)['balance_kt'] is None
    assert concentrate_balance(100, 20, 10, 5, 90)['balance_kt'] == -5
    with pytest.raises(ValueError):
        concentrate_balance(100, 120, 0, 0, 90)
    project = {'start_period': '2027-01', 'end_period': '2028-12', 'ore_mt_per_year': 100,
               'copper_grade_pct': 1, 'recovery': .9, 'ownership': .5, 'availability': 1, 'ramp_months': 12}
    first = mine_output(project, '2027-01')
    assert first['gross_kt'] == pytest.approx(900*31/365/12)
    assert first['attributable_kt'] == first['gross_kt']*.5
    assert mine_output(project, '2026-12')['gross_kt'] == 0
    assert mine_output(project, '2029-01')['gross_kt'] == 0
    assert mine_output({**project, 'recovery': None}, '2027-01')['gross_kt'] is None


def test_stocks_do_not_turn_into_available_inventory():
    r = warehouse(100, 60, 80)
    assert r['outside_etfs'] == 40 and r['available'] is None
    with pytest.raises(ValueError):
        warehouse(100, 101)


def test_regional_gas_pipeline_and_storage_conserve_without_duplicate_demand():
    base = {'storage': 500, 'capacity': 1000, 'minimum': 100, 'max_withdrawal': 10, 'max_injection': 10}
    nodes = [{**base, 'id': 'A', 'production': 30, 'demand': 10},
             {**base, 'id': 'B', 'production': 0, 'demand': 20}]
    edges = [{'from': 'A', 'to': 'B', 'capacity': 20, 'scheduled_flow': 20, 'outage_fraction': .5}]
    result = regional_gas_step(nodes, edges, 30)
    assert result['national_balance_bcf_day'] == 0
    assert result['pipelines'][0]['flow'] == 10
    assert all(abs(r['conservation_error_bcf']) < 1e-6 for r in result['regions'])
    assert not result['included_in_national_balance']
    low = [{**nodes[1], 'storage': 110}]
    assert regional_gas_step(low, [], 30)['regions'][0]['withdrawal_limit_bcf_day'] < 2


def test_lng_ramp_fuel_and_missing_date():
    train = {'start_period': '2027-01', 'baseload_bcf_day': 1}
    assert lng_feedgas(train, '2026-12', 1)['feedgas_bcf_day'] == 0
    assert lng_feedgas(train, '2027-01', .9, ramp_months=6, fuel_fraction=.1)['feedgas_bcf_day'] == pytest.approx(1/6)


def test_dispatch_outage_scarcity_contract_and_load_identity():
    hours = [{'load_mw': 100, 'renewable_mw': 30, 'weight_hours': 24, 'scarcity_price': 1000}]
    fleet = [{'id': 'gas', 'capacity_mw': 100, 'availability': .5, 'heat_rate': 7, 'variable_cost': 2}]
    r = hourly_dispatch(hours, fleet, 3, contract={'fixed_fraction': .8, 'fixed_usd_mwh': 50})
    assert r['rows'][0]['residual_mw'] == 0
    assert r['unserved_mwh'] == 20*24
    assert r['weighted_delivered_usd_mwh'] == pytest.approx(240)
    assert r['gas_mmbtu'] == 50*7*24
    assert hourly_dispatch([], fleet, 3)['status'] == 'hourly_load_unavailable'


def test_cost_sample_weights_and_distinct_currency_basis():
    base = {'unit': 'USD/oz', 'currency': 'USD', 'period': '2026-Q3', 'byproduct_basis': 'credits'}
    assets = [{**base, 'id': 'A', 'production': 9, 'cash': -10, 'sustaining': 100},
              {**base, 'id': 'B', 'production': 1, 'cash': 100, 'sustaining': 200}]
    result = cost_curve(assets)
    assert result[0]['weighted_average'] == 1
    assert result[0]['sample_quantiles']['p50'] == -10
    assert all(not r['global_percentiles'] and r['coverage_pct'] is None for r in result)


def test_issuer_bridges_reconcile_and_cannot_become_base_returns():
    config = load(DATA/'company_bridges.json')
    result = build_companies(config, ASOF)
    assert len(result) == 2
    assert all(c['revenue_sensitivity_coverage_pct'] >= 90 for c in result)
    assert all(not c['in_base_irr'] and c['valuation_authority'] == 'none' for c in result)
    sjt, wpm = config['companies']
    assert sjt_case(sjt)['gross_deficit_usd'] == sjt['gross_deficit_usd']
    assert sjt_case(sjt, 2)['royalty_cash_before_trust_hurdles_usd'] == 0
    assert sjt_case(sjt, .5)['gross_deficit_usd'] > sjt['gross_deficit_usd']
    base = stream_case(wpm)
    assert base['revenue_usd'] == wpm['reported_revenue_usd']
    assert stream_case(wpm, {'gold': 1.1})['revenue_usd']-base['revenue_usd'] == pytest.approx(39297000)
    assert base['components'][1]['sold_oz'] != base['components'][1]['produced_oz']


def test_contract_hedge_ownership_stream_cap_and_missing_cost():
    asset = {'kind': 'stream', 'volume': 100, 'volume_basis': 'gross', 'ownership': .5,
             'period': '2026-Q3', 'currency': 'CAD', 'volume_unit': 'oz', 'benchmark_unit': 'CAD/oz',
             'variable_cost': 1, 'fixed_cost': 10, 'sustaining_capex': 5, 'working_capital': 3,
             'tax_rate': .2, 'hedge': {'fraction': .5, 'price': 80},
             'payment': {'fixed_per_unit': 10, 'price_fraction': .5, 'cap_per_unit': 30}}
    r = asset_cashflow(asset, 100, fx=2)
    assert r['volume'] == 50 and r['price_realized'] == 90
    assert r['revenue'] == 6000
    assert asset_cashflow({**asset, 'fixed_cost': None}, 100)['cashflow'] is None


def test_backtest_never_uses_economic_date_as_historical_availability():
    row = obs()
    history = [{**row, 'period': f'2025-{m:02d}', 'known_at': '2026-11-02'} for m in range(1, 13)]
    assert score(history)['status'] == 'awaiting_archived_origins'
    history = [{**row, 'period': f'2025-{m:02d}', 'known_at': f'2025-{m:02d}-02', 'value': m} for m in range(1, 13)]
    result = score(history)
    assert result['status'] == 'scored'
    assert {r['model'] for r in result['summary']} == {'no_change'}


def test_fetch_failures_preserve_dated_ledger_not_freshness(tmp_path):
    path = tmp_path/'inputs.json'
    row = {**obs(), 'source_id': 'steo_monthly'}
    save(path, {'observations': [row], 'sources': [{**SOURCE, 'id': 'steo_monthly'}]})
    def fail(_url):
        raise TimeoutError('offline fixture')
    result = refresh(path, ASOF, fail)
    assert len(result['errors']) == 3
    assert result['observations'] == [row]
    assert result['sources'][0]['published_at'] == SOURCE['published_at']
    assert not source_state(result['sources'][0], ASOF)['usable']


def test_lng_named_headers_survive_inserted_column_and_reject_wrong_units():
    headers = ['Project name', 'Train', 'Baseload nameplate capacity per Train', 'Inserted',
               'Peak nameplate capacity per Train', 'Project status', 'In-service date',
               'Date of the start of commercial service', 'Location (U.S. state)', 'Operator']
    class Sheet:
        values = [[], headers, [None, None, 'Bcf/d'],  # noqa: RUF012 -- isolated worksheet fixture
                  ['Plant', 'Train 1', 1, 'irrelevant', 1.2, 'Under construction', '2027 Q1', '2027 Q2', 'LA', 'Operator Inc']]
    r = parse_lng_trains(Sheet())[0]
    assert r['state'] == 'LA' and r['operator'] == 'Operator Inc' and r['start_period'] == '2027-03'
    bad = copy.deepcopy(Sheet.values)
    bad[2][2] = 'Mtpa'
    with pytest.raises(ValueError, match='unit'):
        parse_lng_trains(type('BadSheet', (), {'values': bad})())


def test_joint_shocks_count_copper_and_coproduct_losses_once():
    base = {'copper_refined_kt': 1000, 'silver_byproduct_moz': 20}
    shock = {'driver': 'copper_mine_disruption', 'loss_kt': 100, 'silver_byproduct_moz_per_kt': .01}
    result = propagate(base, [shock])
    assert result['result'] == {'copper_refined_kt': 900, 'silver_byproduct_moz': 19}
    assert result['probability'] is None
    with pytest.raises(ValueError, match='Duplicate'):
        propagate(base, [shock, shock])


def test_refinery_volumetric_gain_weather_and_data_center_milestones():
    case = {'region': 'PADD1', 'throughput_mbd': 1, 'days': 30, 'processing_gain_fraction': .05,
            'products': [{'product': 'distillate', 'yield_fraction': 1.05, 'imports_mbd': 0,
                          'exports_mbd': .1, 'use_mbd': 1, 'opening_inventory_mb': 1}]}
    r = refinery_products(case)[0]
    assert r['inventory_mb'] == 0 and r['unmet_product_demand_mb'] == pytest.approx(.5)
    case['products'][0]['yield_fraction'] = .9
    with pytest.raises(ValueError):
        refinery_products(case)
    weather = {'coefficients': {'basis': 'named_assumption', 'bcf_day_per_hdd': .1, 'bcf_day_per_cdd': .2},
               'rows': [{'hdd': 100, 'cdd': 0, 'normal_hdd': 50, 'normal_cdd': 0, 'observed_demand_bcf_day': 20}]}
    assert weather_demand(weather)[0]['normalized_demand_bcf_day'] == 15
    projects = [{'stage': 'proposed', 'mw': 100, 'known_at': '2026-11-01'},
                {'stage': 'operating', 'operating_from': '2026-10-01', 'mw': 20, 'known_at': '2026-11-01'}]
    assert [r['eligible_operating_mw'] for r in data_center_load(projects, ASOF)] == [0, 20]
    assert all(r['incremental_national_demand_mw'] is None for r in data_center_load(projects, ASOF))


def test_gold_recycling_and_etf_flows_are_transfers_not_new_stock():
    case = {'mine_t': 100, 'hedging_t': 0, 'recycling_t': 30, 'jewellery_t': 30,
            'technology_t': 10, 'bar_coin_t': 20, 'etf_t': 40, 'central_bank_t': 10}
    r = gold_flow(case)
    assert r['otc_and_unidentified_residual_t'] == 20
    assert r['above_ground_stock_addition_t'] == 100
