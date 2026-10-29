"""Economic identities and publication safeguards, without network access."""
import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SCRIPTS))
from build_commodity_models import build
from build_compounder_roster import build as roster
from commodity_common import CONFIG_DIR, LB_PER_TONNE, load
from commodity_engines import crude, copper, gold, silver, gold_residual
from validate_commodity_models import validate
from buy_zones import load_config

AS_OF=date(2026,10,28)


@pytest.fixture
def models(tmp_path):
    return build(AS_OF,panel_path=tmp_path/'absent.json')


def test_complete_context_contract(models):
    assert validate(models)==[]
    assert all(m['in_base_irr'] is False and m['sources'] and m['falsifiers'] for m in models['models'])
    for m in models['models']:
        assert all(s['rows'][-1]['period'].startswith('2032') for s in m['scenarios'])
        assert all(s['transcription_sha256'] for s in m['sources'])


def test_oil_published_prices_and_oecd_stocks_match_source(models):
    m=models['models'][0]
    published={r['period']:r for r in m['reference']['quarterly']}
    rows=m['scenarios'][0]['rows']
    for r in rows:
        assert abs(r['balance_residual'])<1e-7
        if r['period']<='2027-Q4':
            assert r['price']==published[r['period']]['brent']
            assert r['wti']==published[r['period']]['wti']
            assert r['oecd_stock_mb']==published[r['period']]['oecd_stock_mb']
            assert r['price_status']=='published_forecast'
        else:assert r['basis']=='analyst_extension'
    # A global surplus cannot be presented as OECD inventory growth.
    assert rows[1]['world_stock_change_mb'] != rows[1]['oecd_stock_change_mb']


def test_oil_disruption_and_lag_are_real_sensitivities(models):
    paths=models['models'][0]['scenarios']
    base,disrupted,_,shale=paths
    assert disrupted['rows'][0]['oecd_stock_mb']<base['rows'][0]['oecd_stock_mb']
    assert disrupted['rows'][0]['price']>base['rows'][0]['price']
    assert all(r['shale_response_mbd']==0 for r in shale['rows'][:4])
    assert shale['rows'][4]['shale_response_mbd']>0


def test_copper_two_balances_and_units(models):
    m=models['models'][1]
    assert m['concentrate']['balance_kt'] is None
    assert m['exchange_stocks']['COMEX']['stock_t'] is None
    for s in m['scenarios']:
        for r in s['rows']:
            assert abs(r['price']/LB_PER_TONNE-r['usd_lb'])<.0001
            assert abs(r['refined_kt']-r['use_kt']-r['balance_kt'])<.002
            assert r['price_status']=='analyst_assumption'
            assert r['concentrate_balance_kt'] is None
    assert m['validation'][-1]['passed'] is None
    assert m['scenarios'][1]['rows'][0]['balance_kt']<m['scenarios'][0]['rows'][0]['balance_kt']


def test_recycling_does_not_create_gold_stock():
    c=load(CONFIG_DIR/'gold.json')
    first=gold(c,{},AS_OF)
    c['scenarios'][0]['recycling_price_elasticity']=100
    other=gold(c,{},AS_OF)
    assert [r['above_ground_t'] for r in first['scenarios'][0]['rows']]==[r['above_ground_t'] for r in other['scenarios'][0]['rows']]
    assert first['scenarios'][1]['rows'][0]['price']<first['scenarios'][0]['rows'][0]['price']


def test_copper_concentrate_inputs_enable_separate_balance():
    c=load(CONFIG_DIR/'copper.json')
    c['reference'].update(concentrate_supply_kt=19000,smelter_intake_kt=19200)
    m=copper(c,{},AS_OF)
    assert m['concentrate']['balance_kt']==-200
    assert m['scenarios'][1]['rows'][0]['concentrate_balance_kt']==-600
    assert m['scenarios'][0]['rows'][0]['balance_kt']>0


def test_gold_diagnostic_has_no_future_leakage_or_proxy_fallback():
    assert gold_residual({},AS_OF)['status']=='unavailable'
    series={k:{'observations':[]} for k in ['gold_bullion','real_yield','broad_dollar']}
    import math
    for year in range(2010,2027):
        for month in range(1,13):
            i=(year-2010)*12+month
            rate=1+math.sin(i/4)
            dollar=90+i/30+math.cos(i/8)
            for key,value in [('gold_bullion',math.exp(10-.15*rate-math.log(dollar))),('real_yield',rate),('broad_dollar',dollar)]:
                series[key]['observations'].append({'date':f'{year}-{month:02d}-01','value':value})
    result=gold_residual({'series':series},AS_OF)
    assert result['training_months']==144
    assert all(r['period']<='2026-10' for r in result['rows'])
    assert abs(result['coefficients'][1]+.15)<1e-6


def test_silver_counts_etp_once_and_inherits_gold(models):
    g,s=models['models'][2:]
    for scenario in s['scenarios']:
        gold_path=next(x['rows'] for x in g['scenarios'] if x['id']==scenario['gold_scenario'])
        for row,gold_row in zip(scenario['rows'],gold_path):
            assert abs(row['price']-gold_row['price']/scenario['gold_silver_ratio'])<.011
            assert abs(row['balance_less_etp_moz']-(row['balance_moz']-row['etp_moz']))<.011
    assert s['byproduct_bridge']['included_in_balance'] is False


def test_future_sources_and_forbidden_valuation_use_fail(models):
    with pytest.raises(ValueError,match='Future source'):
        crude(load(CONFIG_DIR/'crude.json'),{},date(2025,1,1))
    doc=copy.deepcopy(models);doc['models'][0]['in_base_irr']=True
    assert validate(doc)
    doc=copy.deepcopy(models);doc['models'][3]['scenarios'][0]['rows'][0]['balance_less_etp_moz']+=50
    assert any('ETP' in e for e in validate(doc))
    doc=copy.deepcopy(models);doc['models'][0]['scenarios'][0]['rows'][-1]['basis']='published_forecast'
    assert any('source horizon' in e for e in validate(doc))
    doc=copy.deepcopy(models);doc['models'][1]['scenarios'][0]['rows'][0]['concentrate_balance_kt']=100
    assert any('without measured inputs' in e for e in validate(doc))


def test_source_staleness_is_visible():
    c=load(CONFIG_DIR/'copper.json')
    result=copper(c,{},date(2027,1,1))
    assert result['status']=='source_review_due'
    assert result['sources'][0]['stale']


def test_compounder_roster_matches_owner_and_single_source():
    expected='MA V AXP MCO SPGI MSCI CME ICE CBOE LSEG DB1.DE MIAX B3SA3.SA 8697.T CSU TOI.V LMN LIFCO.ST TEQ.ST HEI BRK.B BN MKL FRMO FNV WPM RGLD TPL PSK.TO DRR.AX TFPM OR CP FER AENA.MC WCN GOOGL AMZN META ASML RMS.PA RACE COST CPRT'.split()
    doc=roster();cfg=load_config()
    assert [r['ticker'] for r in doc['companies']]==expected==cfg['tickers']
    assert len(expected)==44
    assert doc==load(SCRIPTS.parents[1]/'dashboard/data/compounders.json')
    assert all('driver_to_fcf' in cfg['issuers'][t] for t in expected)


def test_gold_theme_uses_new_history_and_correct_units():
    text=(SCRIPTS/'theme_panel_config.json').read_text(encoding='utf-8')
    doc=json.loads(text)
    def walk(v):
        if isinstance(v,dict):
            yield v
            for item in v.values():yield from walk(item)
        elif isinstance(v,list):
            for item in v:yield from walk(item)
    gold_spec=next(x for x in walk(doc) if x.get('id')=='gold_futures_usd_oz')
    assert gold_spec['yahoo_symbol']=='GC=F'
    assert gold_spec['unit']=='USD/troy oz'
    assert 'fallback' not in gold_spec
    assert not any(x.get('id')=='gold_spot_usd' for x in walk(doc))
    from scaffold_industry_kpi_ledgers import GOLD
    assert GOLD['kpi_id']=='gold_futures_usd_oz'
    assert GOLD['unit']=='usd_oz'
    assert GOLD['expected']['value']==0  # Quote validity, never the old 200 GLD-share threshold.
