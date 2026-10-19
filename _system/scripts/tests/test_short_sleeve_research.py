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
    assert result["metrics"]["net_pnl"]==-2
    assert result["metrics"]["closed"]==1


def test_missing_cover_waits_and_does_not_become_a_zero_price_profit():
    result=sleeve.replay(fixture_evidence({1:None}),10000,100,2,{"id":"test","execution_fraction":0.,"borrow_annual":0.})
    assert result["metrics"]["delayed_covers"]==1
    assert result["metrics"]["missing_mark_days"]==1
    assert result["metrics"]["net_pnl"]==-2


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


def test_committed_publication_is_aggregate_finite_and_has_exactly_three_cases():
    path=ROOT/"dashboard/data/short_sleeve.json"
    doc=json.loads(path.read_text())
    assert [c['id'] for c in doc['cases']]==['bear','base','bull']
    assert path.stat().st_size<20*1024*1024
    assert len(doc['models'])==360
    assert all('ticker' not in m and 'event_id' not in m for m in doc['models'])
    assert next(g for g in doc['groups'] if g['id']=='primary' and g['horizon']==5)['n']==665
    assert next(g for g in doc['groups'] if g['id']=='primary' and g['horizon']==20)['n']==608
    assert len({(m['nav'],m['bps'],m['horizon'],m['scenario'],m['capacity']) for m in doc['models']})==360
