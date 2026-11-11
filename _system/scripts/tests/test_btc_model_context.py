"""Economic identities, evidence precision, no lookahead and refresh recovery."""
import csv
import io
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import btc_cost_of_production as cop
import btc_model_context as context
import btc_power_history as power
import build_hk_snowball_model as hk
import fetch_crypto_panel as fetch
from btc_mining_economics import fee_adjusted_breakeven, reward_economics
from validate_btc_model import validate


def test_cbeci_new_csv_uses_twh_not_gw():
    text = 'Average electricity cost assumption: 0.05 USD/kWh,,,,,,,\nTimestamp,Date and Time,"power MAX, GW","power MIN, GW","power GUESS, GW","annualised consumption MAX, TWh","annualised consumption MIN, TWh","annualised consumption GUESS, TWh"\n1,2026-11-10T00:00:00,30,10,20,262.8,87.6,175.2\n'
    row = cop.parse_cbeci_csv(text)[0]
    assert row['twh_guess'] == 175.2
    assert cop.fleet_jth_from_twh(row['twh_guess'], 1000) == pytest.approx(20)


def test_fee_identities_and_security_budget():
    zero = reward_economics(100000, 1.5625, 0, 200000)
    fees = reward_economics(100000, 1.5625, .25, 200000)
    assert zero['fee_adjusted_breakeven_usd'] == 100000
    assert fees['production_cost_usd'] == zero['production_cost_usd']
    assert fees['issued_btc_per_day'] == zero['issued_btc_per_day'] == 225
    assert fees['fee_adjusted_breakeven_usd'] == pytest.approx(100000 * 1.5625 / 1.8125, abs=.01)
    assert fees['security_revenue_daily_usd'] == fees['fee_revenue_daily_usd'] + fees['subsidy_revenue_daily_usd']
    assert fee_adjusted_breakeven(45000000,450,1000000) == pytest.approx(44000000/450)
    assert fee_adjusted_breakeven(1,1,2) == 0


@pytest.mark.parametrize('fee',[-1,math.nan,math.inf])
def test_invalid_fees_rejected(fee):
    with pytest.raises(ValueError):
        reward_economics(100000,3.125,fee,100000)


def test_projection_preserves_halving_jump_and_extends_all_scenarios():
    state=cop.CostState(date(2026,11,11),1000,16,.05,3.125)
    fan=cop.forward_scenarios(state)
    for name, scenario in fan.items():
        rows={p['date']:p for p in scenario['path']}
        assert scenario['path'][-1]['date']=='2033-12-31'
        for before,after in [('2028-04-14','2028-04-15'),('2032-04-19','2032-04-20')]:
            assert rows[after]['all_in_usd']/rows[before]['all_in_usd']==pytest.approx(2,rel=.001)
            assert rows[after]['subsidy_btc']==rows[before]['subsidy_btc']/2
        assert len(scenario['path'])>=85
    assert fan['naive_hk']['2033']['all_in_usd']==pytest.approx(state.all_in()*4,abs=.01)


def test_own_demand_is_not_forced_to_hk_target():
    series=[(date(2011,1,1)+timedelta(days=400+i*20),2 * ((400+i*20)/365.25)**3.77) for i in range(250)]
    constrained=hk.fit_power_law(series)
    free=hk.fit_power_law(series,constrain=False)
    assert constrained['k']==4 and constrained['k_constrained']
    assert free['k']==pytest.approx(3.77,abs=1e-5) and not free['k_constrained']
    assert hk.model_price(free,context.HORIZON) != 1000000
    assert context.hk_references()['vintages'][1]['references'][1]['date_precision']=='year'
    assert 'date' not in context.hk_references()['vintages'][1]['references'][1]


def test_diagnostics_never_fit_holdout_prices():
    series=[(date(2011,1,1)+timedelta(days=i*7),100+i) for i in range(800)]
    def fitted(rows,**kwargs):
        assert all(d<=date(2026,1,1) for d,_ in rows)
        return {'ok':True,'k':4,'A':1,'origin':'2011-01-01'}
    output=context.demand_diagnostics(series,date(2026,1,1),fitted,hk.model_price)
    for r in output['one_year_holdouts']:
        assert r['cutoff'] < r['target']
    assert output['hk_anchor_implied']['hk_published_exponent'] is False


def test_power_parser_industrial_only_and_release_lag():
    text='MSN,YYYYMM,Value\nESRCUUS,202406,20\nESICUUS,202406,8\nESICUUS,202413,9\nESICUUS,202607,10\nESICUUS,202612,12\n'
    rows=power.parse_eia(text,retrieved_on=date(2026,11,11))
    assert len(rows)==2
    assert rows[0]['usd_kwh']==.08
    assert power.proxy_on(date(2024,7,31),rows) is None
    assert power.proxy_on(date(2024,8,1),rows)==.045
    assert power.proxy_on(date(2026,11,11),rows)==pytest.approx(.045*10/8)


def test_power_failed_refresh_keeps_cache_and_dates(tmp_path):
    path=tmp_path/'btc_power_eia_industrial.csv'
    raw='date,available_on,usd_kwh,retrieved_on\n2024-06-30,2024-08-01,.08,2026-01-01\n'
    path.write_text(raw)
    with patch.object(power.urllib.request,'urlopen',side_effect=OSError('unavailable')):
        status=power.refresh(directory=tmp_path,as_of=date(2026,11,11))
    assert path.read_text()==raw
    assert status['refresh_status']=='cached_after_failure'
    assert status['through']=='2024-06-30'
    assert status['observed_global_series'] is False


def test_latest_rig_price_never_backdated():
    catalog={'models':[{'release':'2020-01-01','j_th':10,'usd_per_th':30,
                        'price_observations':[{'date':'2026-11-11','usd_per_th':15}]}]}
    assert cop.sota_usd_per_th(date(2026,11,10),catalog)==30
    assert cop.sota_usd_per_th(date(2026,11,11),catalog)==15


def test_rig_explicit_cost_has_no_depreciation_double_count():
    catalog={'pue':1,'models':[{'id':'test','name':'test','release':'2020-01-01','j_th':10,
                              'th_s':100,'watts':1000,'usd_per_th':20,'cooling':'air','spec_source_url':'https://example.com'}]}
    rig=context.rig_comparison(catalog,1000,date(2026,11,11),3.125)['rigs'][0]
    assert rig['plus_25pct_return_usd']==pytest.approx(sum(rig[k] for k in
        ('electricity_usd','ancillary_opex_usd','depreciation_usd','required_profit_usd')),abs=.02)
    assert rig['sensitivities']['power_004_usd']<rig['plus_25pct_return_usd']<rig['sensitivities']['power_006_usd']


def test_mined_fees_use_dated_prices_and_allow_real_zero():
    timestamp=1794355200
    with patch.object(fetch,'_get_json',return_value=[{'timestamp':timestamp,'avgFees':5000000,'USD':80000}]):
        rows,error=fetch.fetch_mempool_fees_usd(999999)
    assert not error and rows[0][1]==4000
    with patch.object(fetch,'_get_json',return_value=[{'timestamp':timestamp,'avgFees':0,'USD':80000}]):
        rows,error=fetch.fetch_mempool_fees_usd(999999)
    assert not error and rows[0][1]==0


def test_failed_mined_fees_do_not_invent_current_observation(tmp_path):
    p=tmp_path/'btc_avg_fee_per_block_usd.csv';p.write_text('date,value\n2020-01-01,100\n')
    with patch.object(fetch,'CRYPTO_DIR',tmp_path),patch.object(fetch,'_get_json',return_value=None):
        result=fetch.process_series({'id':'btc_avg_fee_per_block_usd','source':'mempool_fees'}, {},False)
    assert result['as_of']=='2020-01-01'
    assert result['stale'] and result['error']


def test_fee_conversion_uses_fee_date_not_current_spot(tmp_path):
    p=tmp_path/'fees.csv';p.write_text('date,value\n2026-01-01,1000\n')
    result=context.fee_context(p,date(2026,11,11),[(date(2026,1,1),50000),(date(2026,11,11),100000)],60000,{},lambda _:1)
    assert result['fee_btc_per_block']==.02
    assert result['conversion_price_date']=='2026-01-01'


def test_missing_fees_are_not_observed_zero(tmp_path):
    result=context.fee_context(tmp_path/'missing.csv',date(2026,11,11),[],60000,{},lambda _:1)
    assert not result['available']
    assert result['fee_btc_per_block'] is None and result['current_breakeven_usd'] is None


def test_published_snapshot_contract():
    path=hk.OUT_DASHBOARD
    if not path.exists():pytest.skip('Snapshot not in sparse checkout')
    doc=json.loads(path.read_text(encoding='utf-8'))
    assert validate(doc)==[]
    assert hk.OUT_REF.read_bytes()==path.read_bytes()
