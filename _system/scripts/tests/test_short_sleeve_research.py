"""Financial-accounting and publication invariants for indicative sleeve research."""
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT/"_system/scripts/short_sleeve_research.py"
spec = importlib.util.spec_from_file_location("short_sleeve_research", MODULE)
sleeve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sleeve)


def fixture_evidence(closes=None, actions=None):
    days=[];d=date(2024,6,3)
    while len(days)<20:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    prices={day:{"open":10.,"close":10.} for day in days}
    for i,value in (closes or {}).items():prices[days[i]]["close"]=value
    r={"date":days[0],"ticker":"AAA","issuer":"issuer-a","adv":1_000_000,"open":10.,"calendar_i":0,"cohorts":["eligible"]}
    return {"days":days[:8],"calendar":days,"records":[r],"prices":{"AAA":prices},
            "actions":{"AAA":actions or {}},"settlements":{d:days[i+1] for i,d in enumerate(days[:-1])}}


def test_initial_loss_is_in_drawdown_and_zero_vol_ratios_are_missing():
    metrics,_,_=sleeve.summary(np.array([-10.,0.,0.]),100.,["2024-06-03","2024-06-04","2024-06-05"])
    assert metrics["max_drawdown"] == pytest.approx(-.1)
    flat,_,_=sleeve.summary(np.zeros(3),100.,["2024-06-03","2024-06-04","2024-06-05"])
    assert flat["cagr"]==0 and flat["calmar"] is None and flat["sharpe"] is None


def test_same_day_has_no_ordinary_borrow_charge():
    result=sleeve.replay(fixture_evidence(),10000,100,1,{"id":"test","execution_fraction":0.,"borrow_annual":3.})
    assert result["metrics"]["borrow_cost"]==0
    assert result["metrics"]["commission_cost"]==2
    assert result["metrics"]["net_pnl"]==-2


def test_borrow_uses_settlement_weekends_and_rounded_collateral():
    result=sleeve.replay(fixture_evidence(),10000,100,5,{"id":"test","execution_fraction":0.,"borrow_annual":.5})
    assert result["metrics"]["borrow_cost"]==pytest.approx(10*11*.5*6/360)


def test_split_changes_share_count_without_creating_profit():
    evidence=fixture_evidence({1:100.}, {"2024-06-04":.1})
    result=sleeve.replay(evidence,10000,100,2,{"id":"test","execution_fraction":0.,"borrow_annual":0.})
    assert result["metrics"]["net_pnl_before_proceeds_interest"]==pytest.approx(-2)
    assert result["metrics"]["closed"]==1


def test_missing_cover_waits_and_does_not_become_a_zero_price_profit():
    result=sleeve.replay(fixture_evidence({1:None}),10000,100,2,{"id":"test","execution_fraction":0.,"borrow_annual":0.})
    assert result["metrics"]["delayed_covers"]==1
    assert result["metrics"]["missing_mark_days"]==1
    assert result["metrics"]["net_pnl_before_proceeds_interest"]==pytest.approx(-2)


def test_end_of_sample_position_remains_an_open_liability():
    result=sleeve.replay(fixture_evidence(),10000,100,10,{"id":"test","execution_fraction":0.,"borrow_annual":0.})
    assert result["metrics"]["entered"]==1 and result["metrics"]["unresolved"]==1
    assert result["metrics"]["closed"]==0


def test_per_share_margin_floor_and_collateral_are_distinct():
    assert sleeve.margin(100,1.)==250.
    assert sleeve.margin(100,2.)==250.
    assert sleeve.margin(100,4.)==400.
    assert sleeve.margin(100,10.,house=2.)==2000.


def test_capacity_shrinks_targets_and_costs_are_monotonic():
    evidence=fixture_evidence();evidence['records'][0]['adv']=20000
    bull=sleeve.replay(evidence,1000000,25,5,{"id":"bull","execution_fraction":.01,"borrow_annual":.1})
    bear=sleeve.replay(evidence,1000000,25,5,{"id":"bear","execution_fraction":.05,"borrow_annual":1.})
    assert bull["metrics"]["mean_actual_weight"]==pytest.approx(200/1000000)
    assert bull["metrics"]["partial"]==1
    assert bear["metrics"]["net_pnl"]<bull["metrics"]["net_pnl"]


def test_squeeze_reserve_covers_entry_exposure_even_when_price_falls_by_close():
    result=sleeve.replay(fixture_evidence({0:1.}),10000,100,1,
                         {"id":"test","execution_fraction":0.,"borrow_annual":0.})
    # Entry notional $100, a +200% price loss $200 and post-shock margin $600.
    assert result["metrics"]["stress_reserve_200"]==pytest.approx(800/10000)
    assert result["metrics"]["stress_margin_200"]==pytest.approx(600/10000)


def test_short_credit_uses_collateral_tiers_and_not_total_portfolio_nav():
    assert sleeve.annual_short_credit(0,10_000_000)==0
    assert sleeve.annual_short_credit(100_000,10_000_000)==0
    assert sleeve.annual_short_credit(200_000,10_000_000)==pytest.approx(100_000*.0263)
    assert sleeve.annual_short_credit(1_000_001,10_000_000)==pytest.approx(900_000*.0263+.0338)
    # The external account balance is excluded from the sleeve's credit.
    assert sleeve.annual_short_credit(1_100_000,10_000_000)-sleeve.annual_short_credit(100_000,10_000_000)==pytest.approx(900_000*.0263+100_000*.0338)


def test_short_credit_is_zero_for_same_day_settled_flat_positions():
    result=sleeve.replay(fixture_evidence(),10_000_000,100,1,
                         {"id":"test","execution_fraction":0.,"borrow_annual":.5},capacity=False)
    assert result['metrics']['proceeds_interest']==0


def test_credit_combines_names_before_tiers_and_survives_weekend_cover_settlement():
    evidence=fixture_evidence()
    evidence['records'].append({**evidence['records'][0],'ticker':'BBB','issuer':'issuer-b'})
    evidence['prices']['BBB']=evidence['prices']['AAA'].copy()
    evidence['actions']['BBB']={}
    result=sleeve.replay(evidence,10_000_000,100,5,
                         {"id":"test","execution_fraction":0.,"borrow_annual":.5},capacity=False)
    # Two $100k positions at $10 have $220k rounded collateral. The zero-rate band
    # is already used externally; six settled days include the weekend.
    assert result['metrics']['proceeds_interest']==pytest.approx(220_000*.0263*6/360)
    monday=next(r for r in result['series'] if r[0]==5)
    assert monday[1]>0 and monday[2:]==[0.,0.]
    assert result['metrics']['net_pnl']-result['metrics']['net_pnl_before_proceeds_interest']==pytest.approx(result['metrics']['proceeds_interest'])


def test_committed_publication_is_aggregate_finite_and_has_exactly_three_cases():
    path=ROOT/"dashboard/data/short_sleeve.json"
    doc=json.loads(path.read_text())
    assert [c['id'] for c in doc['cases']]==['bear','base','bull']
    assert path.stat().st_size<20*1024*1024
    assert len(doc['models'])==90
    assert doc['navs']==[10_000_000] and doc['weights']==[25,50,100]
    assert doc['defaults']['nav']==10_000_000 and doc['defaults']['capacity'] is False
    assert doc['financing']['external_short_collateral']==100_000
    assert all('ticker' not in m and 'event_id' not in m for m in doc['models'])
    assert next(g for g in doc['groups'] if g['id']=='primary' and g['horizon']==5)['n']==665
    assert next(g for g in doc['groups'] if g['id']=='primary' and g['horizon']==20)['n']==608
    assert len({(m['nav'],m['bps'],m['horizon'],m['scenario'],m['capacity']) for m in doc['models']})==90
    assert all(r['matched'] for r in doc['reconciliation']['price_checks'])
    assert [p['file'] for p in doc['reconciliation']['other_policies']]==['net_edge_research.json','net_edge_research_v3.json']
    assert doc['reconciliation']['same_tickets_on_10m']['net_pnl']==pytest.approx(doc['reconciliation']['legacy']['net_pnl'])
    base=next(c for c in doc['cases'] if c['id']=='base')
    assert base['execution_fraction']==pytest.approx(base['spread_fraction']+base['depth_fraction'])
