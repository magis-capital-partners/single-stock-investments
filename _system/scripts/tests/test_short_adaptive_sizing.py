"""Information timing, censored-cover accounting and risk-budget invariants."""
from copy import deepcopy
from datetime import date,timedelta
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('adaptive',ROOT/'_system/scripts/short_adaptive_sizing.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def book(bid=9.99,ask=10.01,quantity=20000):
    return {'bid':bid,'ask':ask,'mid':(bid+ask)/2,
            'bid_levels':[(bid,quantity)],'ask_levels':[(ask,quantity)]}


def row(day='2023-01-03',issuer='issuer-a'):
    return {'date':day,'issuer':issuer,'key':issuer+'/'+day,'mid':10.,'exit_mid':9.7,
            'adv_dollars':1e7,'features':m.feature(10.,1e7,.002,.1),
            'decision':book(),'entry':book(),'cover':book(9.69,9.71),
            'peak_mid':10.1,'gross':.03,'label_observable':True}


def history():
    return [row((date(2020,1,1)+timedelta(days=i)).isoformat(),'past-'+str(i)) for i in range(40)]


def test_same_day_and_future_labels_and_current_exit_cannot_change_admission():
    current=row();same_day=row(issuer='same-day');future=row('2024-01-03','future')
    rows=history()+[current,same_day,future]
    before,count=m.predict(rows,current['date'],m.CASES[1])
    changed=deepcopy(rows)
    for r in changed:
        if r['date']>=current['date']:
            r.update(gross=-100.,exit_mid=1000.,cover=book(999.,1001.,1),peak_mid=2000.)
    after,changed_count=m.predict(changed,current['date'],m.CASES[1])
    assert count==changed_count==40
    assert [p['adaptive'] for p in before]==[p['adaptive'] for p in after]
    assert [(r['key'],c['ticket']) for r,c in m.select(before,m.POLICIES[-1])]==[(r['key'],c['ticket']) for r,c in m.select(after,m.POLICIES[-1])]


def test_no_model_or_trades_before_declared_training_minimum():
    current=row()
    predictions,n=m.predict(history()[:39]+[current],current['date'],m.CASES[1])
    assert predictions==[] and n==39


def test_ioc_uses_decision_limit_and_reports_partial_or_no_fill():
    r=row();c=m.candidate(r,25000,.1,history(),m.CASES[1]);assert c
    r['entry']=book(quantity=100)
    result=m.execute(r,c,m.CASES[1])
    assert result['filled']==100 and result['entry_residual']==c['quantity']-100
    r['entry']=book(9.,9.01)
    assert m.execute(r,c,m.CASES[1])['filled']==0


def test_missing_cover_depth_keeps_original_share_liability_and_is_not_dropped():
    r=row();r['cover']=book(19.99,20.,5);r['exit_mid']=20.
    price,observed,modeled=m.cover_price(r,10,m.CASES[1])
    assert observed==modeled==5
    assert price==pytest.approx((5*20+5*21)/10)
    c={'quantity':10,'limit':9.9}
    result=m.execute(r,c,m.CASES[1])
    assert result['filled']==10 and result['modeled_cover']==5 and result['net_pnl']<0
    expected=10*(result['sell_vwap']-result['cover_vwap'])-result['commissions']-result['extra_impact_cost']
    assert result['net_pnl']==pytest.approx(expected)


def test_risk_allocation_checks_entry_reserve_and_reconsiders_smaller_alternatives():
    rows=history()+[row(issuer='one'),row(issuer='two')]
    predictions,_=m.predict(rows,'2023-01-03',m.CASES[1])
    chosen=m.select(predictions,m.POLICIES[-1])
    assert chosen and sum(c['reserve'] for _,c in chosen)<=m.NAV*.10
    assert len({r['issuer'] for r,c in chosen})==len(chosen)<=3
    assert all(c['ticket']<=100000 for r,c in chosen)


def test_more_adverse_cost_case_cannot_improve_the_same_execution():
    r=row();r['cover']=book(9.69,9.71,5)
    c={'quantity':100,'limit':9.9}
    values=[m.execute(r,c,case)['net_pnl'] for case in m.CASES]
    assert values==sorted(values,reverse=True)


def test_publication_is_aggregate_and_every_test_event_remains_in_gate_counts():
    path=ROOT/'dashboard/data/short_adaptive_sizing.json';raw=path.read_text();doc=json.loads(raw)
    assert doc['aggregate_only'] is True and doc['authority']=='none'
    assert doc['protocol']==json.loads(json.dumps(m.PROTOCOL))
    assert doc['population']=={'eligible_events':282,'training_events':56,'test_events':226}
    assert len(doc['models'])==15 and len(doc['monte_carlo'])==15
    assert doc['days'][0]=='2023-01-03' and doc['days'][-1]=='2026-10-13'
    for model in doc['models']:
        assert sum(model['metrics']['gate_counts'].values())==226
        assert 0<=model['metrics']['modeled_cover_share_fraction']<=1
    assert all(x not in raw for x in ('"ticker":','"event_id":','"issuer":','"bid_levels":'))
