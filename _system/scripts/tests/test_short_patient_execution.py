import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'_system/scripts'))
spec = importlib.util.spec_from_file_location('patient', ROOT/'_system/scripts/short_patient_execution.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def sample(restricted=True):
    opened = 1672756200
    ts = np.arange(opened+1, opened+23400)
    bid = np.linspace(10., 9., len(ts))
    a = dict(ts=ts, bid=bid, ask=bid+.02, valid=np.ones(len(ts), bool),
             restricted=np.full(len(ts), restricted), volume=np.full(len(ts), 100.),
             eligible=np.full(len(ts), 50.), price_volume=100*(bid+.01),
             listing_volume=np.full(len(ts), 50.), offer=s.above_bid(bid))
    row = dict(opened='2023-01-03T14:30:00+00:00', closed='2023-01-03T21:00:00+00:00',
               date='2023-01-03', issuer='issuer', key='event')
    return row, a


def test_ssr_partial_included_and_more_capture_more_shares():
    r, a = sample()
    low = s.replay_one(r, a, 50000, 30, s.CASES[0], 'flow')
    high = s.replay_one(r, a, 50000, 30, s.CASES[2], 'flow')
    assert 0 < low['filled'] < high['filled']
    assert low['ssr_shares'] == low['filled']
    assert high['notional'] <= 50000


def test_volume_and_cash_caps_with_fractional_carry():
    cap = np.array([.7, .7, .7, .7])
    fill = s.constrained_fill(cap, np.ones(4)*10, dollars=15)
    assert fill.sum() == 1
    assert np.all(np.cumsum(fill) <= np.cumsum(cap)+1e-8)


def test_no_volume_no_flow_fill_but_target_assumption_explicit():
    r, a = sample()
    a['volume'][:] = a['eligible'][:] = a['price_volume'][:] = 0
    assert s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')['filled'] == 0
    conditional = s.replay_one(r, a, 25000, 60, s.CASES[1], 'target')
    assert conditional['filled'] > 0
    assert conditional['residual'] == conditional['filled']
    assert conditional['gap100'] > 0
    assert conditional['entry_participation'] is None


def test_failed_cover_charged_and_marked_no_silent_drop():
    r, a = sample(False)
    a['bid'][:] = 10.
    a['ask'][:] = 10.02
    a['price_volume'][:] = 1001.
    baseline = s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')
    a['volume'][a['ts'] > a['ts'][0]+4*3600] = 0
    failed = s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')
    assert failed['filled'] == baseline['filled']
    assert failed['residual'] > baseline['residual']
    assert failed['net_pnl'] < baseline['net_pnl']


def test_future_cover_price_cannot_change_entry_shares():
    r, a = sample()
    x = s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')
    a['ask'][-5000:] *= 4
    y = s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')
    assert x['filled'] == y['filled']
    assert y['net_pnl'] < x['net_pnl']


def test_halt_and_missing_quotes_cannot_fill_or_poison_pnl():
    r, a = sample()
    a['valid'][:1000] = False
    a['bid'][:1000] = a['ask'][:1000] = np.nan
    a['offer'][:1000] = np.nan
    x = s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')
    assert np.isfinite(x['net_pnl'])
    a['valid'][:] = False
    assert s.replay_one(r, a, 25000, 60, s.CASES[1], 'target')['filled'] == 0


def test_penny_floor_and_fee_minimums():
    r, a = sample(False)
    for key in ('bid', 'ask', 'offer'):
        a[key][:] = .5
    a['price_volume'][:] = 50
    x = s.replay_one(r, a, 25000, 60, s.CASES[1], 'flow')
    assert x['peak_margin'] >= 4*x['notional']
    qty = np.array([1., 1.])
    assert s.child_fees(qty, np.array([1000., 1000.]), np.array([0, 300]), 0, False) == 2.02


def test_status_transition_and_offer_above_bid():
    h = {'is_short_sell_restricted': {'ts': [0, 50], 'value': ['N', 'Y']}}
    assert list(s.states(h, 'is_short_sell_restricted', np.array([10, 60]), 'U')) == ['N', 'Y']
    bids = np.array([.0521, .50, 1., 1.231])
    assert np.all(s.above_bid(bids) > bids)
    assert s.eligible_fraction(np.array([1.]), np.array([1.01]), np.array([1.01]))[0] == .5


def test_higher_participation_keeps_budget_and_partial_capacity():
    r, a = sample()
    low = s.replay_one(r, a, 500000, 30, s.CASES[1], 'flow', participation=.05)
    high = s.replay_one(r, a, 500000, 30, s.CASES[1], 'flow', participation=.20)
    assert high['filled'] >= low['filled']
    assert high['notional'] <= 500000
    assert high['filled'] <= .20*.5*a['eligible'][:1800].sum()


def test_chart_payload_preserves_daily_risk_metrics():
    d = {'start': '2024-01-01', 'models': [{'max_dd_dollars': 50., 'net_pnl': 20.,
         'series': [['2024-01-02', -50., -50.], ['2024-01-31', 20., 0.]]}]}
    compact = s.dashboard_doc(d)
    assert compact['models'][0]['max_dd_dollars'] == 50.
    assert compact['models'][0]['series'][-1][1] == 20.


def test_published_protocol_variants_and_no_raw_events():
    p = ROOT/'dashboard/data/short_patient_execution.json'
    if not p.exists():
        pytest.skip('not built yet')
    d = json.loads(p.read_text())
    assert d['aggregate_only'] and len(d['models']) == 96
    assert d['population'] == 551
    assert d['coverage']['download_cost'] == 0
    assert all(m['trades'] <= d['population'] and m['net_pnl'] is not None for m in d['models'])
    assert 'event/' not in p.read_text()
