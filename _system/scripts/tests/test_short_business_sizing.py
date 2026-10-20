"""Dollars, fee floors and information-preserving sizing comparisons."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('business_sizing', Path(__file__).resolve().parents[1]/'short_business_sizing.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_regulatory_components_round_and_taf_caps_without_buy_side_sec():
    assert m.regulatory(0, 10.) == 0.
    assert m.regulatory(1000, 10.) == pytest.approx(.43)
    assert m.regulatory(100000, 10.) == pytest.approx(30.99)


def test_fixed_size_filter_keeps_opportunities_and_does_not_mutate_forecasts():
    original = {'2023-01-03': ([{'row': {'key': 'a'}, 'adaptive': [{'ticket': 500}, {'ticket': 25000}]},
                                {'row': {'key': 'b'}, 'adaptive': [{'ticket': 25000}]}], 56)}
    before = deepcopy(original)
    filtered = m.fixed_edge_predictions(original, 500)
    assert len(filtered['2023-01-03'][0]) == 2
    assert filtered['2023-01-03'][0][1]['adaptive'] == []
    assert filtered['2023-01-03'][1] == 56
    assert original == before


def test_business_profit_uses_dollars_and_elapsed_calendar_not_cagr():
    days = ['2023-01-03', '2023-06-01', '2024-01-03']
    model = {'series': [[0, .01, 0, 0], [1, -.02, 0, 0], [2, .005, 0, 0]],
             'metrics': {'mean_notional': 500, 'modeled_cover_trades': 1, 'modeled_cover_share_fraction': .01,
                         'commission_cost': 6, 'execution_cost': 12, 'borrow_cost': 0, 'proceeds_interest': 0,
                         'peak_margin': .002, 'stress_reserve_200': .016,
                         'fully_observed_cover_pnl_diagnostic': -4, 'gate_counts': {}}}
    decisions = [{'result': {'filled': 1, 'net_pnl': p}} for p in (10, -20, 5)]
    result = m.dollar_metrics(model, decisions, days, 1000.)
    assert result['net_trading_pnl'] == -5
    assert result['annualized_trading_pnl'] == pytest.approx(-5*365.2425/365)
    assert result['closing_equity_max_drawdown_dollars'] == 20
    assert result['losing_trades'] == 1
    assert result['trade_win_fraction'] == pytest.approx(2/3)
    assert result['annual_pnl'] == {'2023': -10., '2024': 5.}
    assert result['peak_margin_dollars'] == 2


def test_grid_declared_all_variants_and_no_larger_than_user_cap():
    assert m.TICKETS == (250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000)
    assert (len(m.TICKETS)*2+1)*3 == m.PROTOCOL['variants']


def test_published_sensitivity_retains_all_cases_and_matches_dollar_accounting():
    root = Path(__file__).resolve().parents[3]
    doc = json.loads((root/'_system/data/reverse_splits/business_sizing_2026-10-20.json').read_text())
    assert doc['aggregate_only'] and doc['research_only'] and doc['authority'] == 'none'
    assert len(doc['results']) == 57
    assert len({(r['case'], r['policy'], r['target']) for r in doc['results']}) == 57
    for r in doc['results']:
        assert r['net_trading_pnl'] == pytest.approx(sum(r['annual_pnl'].values()))
        assert r['annualized_trading_pnl']*doc['years'] == pytest.approx(r['net_trading_pnl'])
        assert r['closing_equity_max_drawdown_dollars'] >= 0
        assert r['borrow_cost'] == r['proceeds_interest'] == 0
