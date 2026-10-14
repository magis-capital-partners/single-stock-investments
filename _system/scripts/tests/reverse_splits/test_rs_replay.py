"""Account fixtures exercise real sequencing, liabilities and cost reconciliation."""
from copy import deepcopy

import pytest

from reverse_splits.replay import replay
from reverse_splits.rerun import eligible_score, metrics

DAYS=['2024-01-05','2024-01-08','2024-01-09','2024-01-10','2024-01-11','2024-01-12']


def inputs(horizon=2,fee=1):
    account=dict(max_names=5,position_fraction=.05,target_notional=1000,max_participation=.01,house_margin=1,buffer_fraction=.1)
    spec=dict(initial_equity=50000,account=account,conservative_account=deepcopy(account),
              execution={'base':dict(spread_floor=0,range_fraction=0,extra_slippage_bps_per_side=0)},
              commission=dict(minimum_per_side=0,per_share_per_side=0),borrow_collateral=dict(day_basis=360),borrow_max_age_hours=4)
    case=dict(horizon_sessions=horizon,execution='base',fee_annual=fee)
    return spec,case


def lead(ticker='AAA',entry=DAYS[0],prices=None,volumes=None):
    prices=prices or [10]*len(DAYS);volumes=volumes or [100000]*len(DAYS)
    return dict(id=ticker,ticker=ticker,cik=ticker,entry_date=entry,adv=100000,prior_row={'high':10,'low':10},
        fundamental={'score':70},rows={d:dict(open=p,high=p,low=p,close=p,volume=v,factor=1) for d,p,v in zip(DAYS,prices,volumes)})


def test_weekend_fee_and_horizon_includes_entry():
    spec,case=inputs()
    r=replay([lead()],DAYS,spec,case)
    p=r['positions'][0]
    assert p['last_cover_date']==DAYS[1]
    assert p['borrow']==pytest.approx(100*11*3/360)
    assert r['reconciliation_error']==pytest.approx(0,abs=1e-8)
    assert metrics(r,50000)['dollar_pnl']==pytest.approx(-p['borrow'])


def test_exit_capacity_partial_then_next_open_and_no_duplicate_volume():
    spec,case=inputs(fee=0)
    r=replay([lead(volumes=[100000,2000,3000,5000,100000,100000])],DAYS,spec,case)
    assert [c['shares'] for c in r['covers']]==[20,30,50]
    assert [c['at_open'] for c in r['covers']]==[False,True,True]
    assert r['positions'][0]['last_cover_date']==DAYS[3]
    assert r['positions'][0]['partial_covers']==2


def test_known_schedule_covers_before_action_and_unknown_fraction_is_liability():
    spec,case=inputs(horizon=5,fee=0)
    l=lead();l['announced_ex_date']=DAYS[2]
    assert replay([l],DAYS,spec,case)['positions'][0]['last_cover_date']==DAYS[1]
    l=lead(prices=[10,10,30,30,30,30])
    for d in DAYS[2:]:l['rows'][d]['factor']=1/3
    r=replay([l],DAYS,spec,case)
    p=r['positions'][0]
    assert p['fractional_obligation_seen'] and p['remaining']==pytest.approx(1/3)
    assert r['unresolved']==1 and metrics(r,50000)['sharpe_zero_rf'] is None
    assert p['net_pnl']==pytest.approx(0)


def test_close_does_not_admit_same_morning_entry_when_name_cap_full():
    spec,case=inputs(fee=0);spec['account']['max_names']=1
    r=replay([lead(),lead('BBB',entry=DAYS[1])],DAYS,spec,case)
    assert len(r['positions'])==1 and r['rejections'][0]['reason']=='max_names'


def test_rerate_charges_subsequent_intervals_after_third_session():
    spec,case=inputs(horizon=4);case['fee_after_holding_session_3']=3
    p=replay([lead()],DAYS,spec,case)['positions'][0]
    assert p['borrow']==pytest.approx(1100*(3+1+3)/360)


def test_missing_terminal_quote_keeps_liability_and_fee():
    spec,case=inputs();l=lead();l['rows']={DAYS[0]:l['rows'][DAYS[0]]}
    r=replay([l],DAYS,spec,case)
    assert r['unresolved']==1 and r['positions'][0]['remaining']==100
    assert r['positions'][0]['borrow']==pytest.approx(1100*7/360)
    m=metrics(r,50000);assert m['stale_mark_days']==5 and m['annualized_volatility'] is None


def test_gap_margin_liquidation_uses_gap_and_preserves_account_loss():
    spec,case=inputs(horizon=5,fee=0);spec['initial_equity']=2000;spec['account']['position_fraction']=1
    l=lead(prices=[10,40,40,40,40,40])
    r=replay([l],DAYS,spec,case)
    assert r['covers'][0]['reason']=='margin' and r['covers'][0]['fill']==40
    assert r['positions'][0]['net_pnl']==-3000
    assert r['equity'][1]['equity']==-1000


def test_strict_borrow_requires_fresh_pre_entry_timestamp():
    spec,case=inputs();case.update(borrow_policy='strict',fee_annual=None)
    permission={'approved':True,'reference':'FIXTURE-LOCATE'}
    r=replay([lead()],DAYS,spec,case,{'AAA':[('2024-01-05T08:00:00-05:00',30,.5,permission)]})
    assert r['positions'][0]['entry_shares']==30 and r['positions'][0]['rate']==.5
    r=replay([lead()],DAYS,spec,case,{'AAA':[('2024-01-05T04:00:00-05:00',30,.5,permission)]})
    assert not r['positions'] and r['rejections'][0]['reason']=='no_fresh_locate_and_fee'
    r=replay([lead()],DAYS,spec,case,{'AAA':[('2024-01-05T08:00:00-05:00',30,.5)]})
    assert not r['positions']  # Fresh availability without documented permission is insufficient.


def test_spread_slippage_commission_waterfall_reconciles():
    spec,case=inputs(fee=.5)
    spec['execution']['base'].update(spread_floor=.1,extra_slippage_bps_per_side=25)
    spec['commission'].update(minimum_per_side=1,per_share_per_side=.005)
    r=replay([lead(prices=[10,8,8,8,8,8])],DAYS,spec,case)
    m=metrics(r,50000);c=m['costs']
    assert m['dollar_pnl']==pytest.approx(c['raw_price_pnl']-c['spread_cost']-c['slippage_cost']-c['borrow']-c['commission'])


def test_filter_excludes_stale_fallback_and_non_operating():
    s=dict(as_of='2024-01-05',latest_period='2023-09-30',score=70,evidence_count=3,source='raw_companyfacts',historical_eligible=True,profile='operating')
    assert eligible_score(s,60)
    for patch in ({'latest_period':'2022-09-30'},{'source':'ssi_latest_revision'},{'profile':'financial'},{'evidence_count':2}):
        assert not eligible_score({**s,**patch},60)
