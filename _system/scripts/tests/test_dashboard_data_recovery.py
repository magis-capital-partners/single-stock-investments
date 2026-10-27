"""Regressions for the empty aggregates views and misleading feed completeness."""
import json
import subprocess
import sys
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '_system/scripts'))

from aggregates_extract import parse_tables
from aggregates_operating_metrics import operating_periods
from dashboard_data_coverage import surface_coverage


def test_amrize_reported_volume_table_is_extracted():
    html = '''<p>Aggregates sales volumes</p><table>
      <tr><td>Volumes</td><td colspan="3">For the years ended December 31,</td></tr>
      <tr><td>in millions</td><td>2025</td><td>2024</td><td>% Change</td></tr>
      <tr><td>Cement - tons sold</td><td>22.4</td><td>22.6</td><td>(0.9%)</td></tr>
      <tr><td>Aggregates - tons sold</td><td>118.9</td><td>119.8</td><td>(0.8%)</td></tr>
    </table>'''
    meta = dict(ticker='AMRZ', form='10-K', period_end='2025-12-31',
                source_url='https://www.sec.gov/Archives/example.htm',
                published_at='2026-02-18', retrieved_at='2026-10-26')
    rows = parse_tables(html, meta)
    assert [(r['metric'], r['value']) for r in rows] == [
        ('shipments_million_tons', 118.9), ('shipments_million_tons', 119.8)]


def test_ytd_operating_shipments_make_contiguous_quarters():
    def row(value, start, end, kind):
        return dict(ticker='KNF', metric='shipments_million_tons', value=value,
                    unit='million short tons', currency=None, period_start=start,
                    period_end=end, period_type=kind, business_segment='aggregates',
                    geography='consolidated', product='aggregates',
                    freight_basis='not_applicable', sales_scope='issuer_reported',
                    perimeter_basis='reported', status='reported',
                    source_url='https://www.sec.gov/Archives/example.htm',
                    locator='Volume table', published_at='2026-02-18', retrieved_at='2026-10-26')
    periods = operating_periods([
        row(10, '2025-01-01', '2025-03-31', 'Q'),
        row(30, '2025-01-01', '2025-06-30', 'YTD'),
        row(60, '2025-01-01', '2025-09-30', 'YTD'),
        row(100, '2025-01-01', '2025-12-31', 'FY')])
    quarters = [p['metrics']['shipments_million_tons']['value'] for p in periods if p['period_type']=='Q']
    assert quarters == [10, 20, 30, 40]
    assert next(p for p in periods if p['period_type']=='TTM')['metrics']['shipments_million_tons']['value'] == 100


def test_titan_america_external_volumes_and_reported_price_keep_their_scope():
    html='''<table><tr><td>Year ended December 31</td><td>2025</td><td>2024</td><td>Change</td></tr>
    <tr><td>Volumes (thousands)</td></tr>
    <tr><td>Total aggregates volumes</td><td>8,360</td><td>7,229</td></tr>
    <tr><td>External aggregates volumes</td><td>4,646</td><td>3,403</td><td>1,243</td></tr>
    <tr><td>Average external selling price</td></tr>
    <tr><td>Aggregates</td><td>$24.82</td><td>$24.15</td><td>$0.67</td></tr></table>'''
    meta=dict(ticker='TTAM',form='20-F',period_end='2025-12-31',source_url='https://www.sec.gov/test',published_at='2026-03-24',retrieved_at='2026-10-27')
    rows=parse_tables(html,meta)
    current={r['metric']:r for r in rows if r['period_end']=='2025-12-31'}
    assert current['shipments_million_tons']['value']==4.646
    assert current['price_per_ton']['value']==24.82
    assert current['price_per_ton']['freight_basis']=='issuer_not_freight_adjusted'
    assert current['shipments_million_tons']['sales_scope']=='external'


def test_interim_columns_with_separate_currency_cells_and_reported_organic_change():
    html='''<table><tr><td></td><td>Three Months Ended June 30,</td></tr>
    <tr><td>(in millions)</td><td>2026</td><td></td><td>2025</td><td></td><td>% Change</td></tr>
    <tr><td>Aggregates product line</td></tr>
    <tr><td>Shipments (tons)</td><td></td><td>61.6</td><td></td><td>52.7</td><td>17.0%</td></tr>
    <tr><td>Average selling price per ton</td><td>$</td><td>22.74</td><td>$</td><td>23.21</td><td>(2.0)%</td></tr>
    <tr><td>Organic shipments (tons)</td><td></td><td>53.8</td><td></td><td>52.7</td><td>2.3%</td></tr></table>'''
    meta=dict(ticker='MLM',form='10-Q',period_end='2026-06-30',source_url='https://www.sec.gov/test',published_at='2026-08-04',retrieved_at='2026-10-27')
    rows=parse_tables(html,meta)
    current={r['metric']:r for r in rows if r['period_end']=='2026-06-30'}
    assert current['shipments_million_tons']['value']==61.6
    assert current['price_per_ton']['value']==22.74
    assert current['organic_volume_growth_pct']['value']==2.3
    assert not any(r['metric']=='organic_volume_growth_pct' and r['period_end']=='2025-06-30' for r in rows)


def test_knife_river_interim_thousands_and_freight_definition():
    html='''<table><tr><td>Three Months Ended</td></tr>
    <tr><td></td><td>2026</td><td>2025</td></tr><tr><td>Sales (thousands):</td></tr>
    <tr><td>Aggregates (tons)</td><td>10,031</td><td>8,826</td></tr>
    <tr><td>Average selling price:</td></tr>
    <tr><td>Aggregates (per ton)</td><td>19.41</td><td>18.80</td></tr></table>
    <p>The average selling price includes freight and delivery and other revenues.</p>'''
    meta=dict(ticker='KNF',form='10-Q',period_end='2026-06-30',source_url='https://www.sec.gov/test',published_at='2026-08-04',retrieved_at='2026-10-27')
    current={r['metric']:r for r in parse_tables(html,meta) if r['period_end']=='2026-06-30'}
    assert current['shipments_million_tons']['value']==10.031
    assert current['price_per_ton']['value']==19.41
    assert current['price_per_ton']['freight_basis']=='issuer_including_freight_delivery'


def test_operating_period_selector_does_not_hide_explicit_fy_valuations():
    program = '''const fs=require('fs'),vm=require('vm');const c={window:{}};
      vm.runInNewContext(fs.readFileSync('dashboard/aggregates-viz.js','utf8'),c);
      const a=c.window.AggregatesViz,r={financial_status:'verified',ev_ebitda:12,
        fcf_yield_pct:5,financial_as_of:'2025-12-31'};
      for(const p of ['FY','Q','TTM']) if(a.value(r,'ev',p)!==12)process.exit(1);'''
    subprocess.run(['node', '-e', program], cwd=ROOT, check=True)


def test_recent_build_does_not_mean_complete_aggregates():
    doc={'generated_at':'2026-10-26T20:00:00Z','rows':[
        {'ticker':'VMC','ev_ebitda':12,'fcf_yield_pct':3,
         'operating_coverage':{'required_missing':['reserve_life_years']}}]}
    result=surface_coverage('rock',doc)
    assert result['incomplete_rows']==1
    assert result['missing_by_field']['reserve_life_years']==1


def test_zero_bank_deposit_cost_is_present_and_not_missing():
    result=surface_coverage('banks',{'rows':[dict(deposits_total_usd=100,
        dda_share_pct=0,cost_of_deposits_pct=0,p_tbv=1)]})
    assert result['complete_rows']==1


def test_activist_checkpoint_survives_a_transient_windows_lock(tmp_path):
    import scan_activist_sources as scan
    path=tmp_path/'state.json'
    path.write_text('{"old":true}')
    replace=scan.os.replace
    attempts=[]
    def locked_once(source,target):
        attempts.append(source)
        if len(attempts)==1:raise PermissionError('temporary sharing violation')
        return replace(source,target)
    with mock.patch.object(scan.os,'replace',side_effect=locked_once),mock.patch.object(scan.time,'sleep'):
        scan.save_state({'new':True},path)
    assert json.loads(path.read_text())['new'] is True
    assert len(attempts)==2
    assert not list(tmp_path.glob('*.tmp'))


def test_parallel_scan_checkpoints_success_and_failure_on_owner_thread():
    import threading
    import scan_activist_sources as scan
    state={}; owner=threading.get_ident(); checkpoints=[]
    def work(key):
        assert threading.get_ident()!=owner
        if key=='B':raise ValueError('bad source')
        return [{'ticker':key}]
    def checkpoint():
        assert threading.get_ident()==owner
        checkpoints.append(True)
    hits=scan._run_rotation('sec',['A','B','C','D'],state,scan.Budget(None),work,
                            workers=3,checkpoint=checkpoint)
    assert [h['ticker'] for h in hits]==['A','C','D']
    assert state['sec']['last_run']['scanned']==3
    assert state['sec']['last_run']['failed']==1
    assert 'B' not in state['sec']['last_scanned']
    assert len(checkpoints)==5


def test_index_fetch_retains_dated_usd_market_cap_and_withholds_foreign_values():
    import fetch_float_adv as fetch
    def chart(currency):
        return {'chart':{'result':[{'meta':{'currency':currency,'marketCap':1000,
                'regularMarketTime':1793044800,'regularMarketPrice':10},
                'indicators':{'quote':[{'volume':[100,200],'close':[9,10]}]}}]}}
    for currency,expected in [('USD',1000),('EUR',None)]:
        with mock.patch.object(fetch,'_get_json',side_effect=[chart(currency),None]):
            row=fetch.fetch_yahoo_float_adv('EXAMPLE')
        assert row['issuer_market_cap']==expected
        assert row['market_cap_as_of']
        if currency=='EUR':assert row['adv_dollar'] is None
    with mock.patch.object(fetch,'_get_json',return_value=None):
        assert fetch.fetch_yahoo_float_adv('EXAMPLE')['issuer_market_cap'] is None


def test_risk_refresh_does_not_replace_a_newer_source_with_an_older_checkout():
    import build_market_risk_components as risk
    old=dict(component='flow',scope='market',symbol='US_EQUITY',model_version=risk.MODEL_VERSION,
             as_of='2026-10-26T20:00:00+00:00',quality_state='ready',cadence='daily',value=42)
    new=dict(old,as_of='2026-09-28T20:00:00+00:00',value=1)
    with mock.patch.object(risk,'quality',return_value='delayed'):
        result=risk.retain_newer_observations({'components':[new]},{'components':[old]})
    assert result['components'][0]['value']==42
    assert result['components'][0]['as_of']==old['as_of']
    assert result['components'][0]['quality_state']=='delayed'
    assert result['coverage']['delayed']==1


def test_road_share_total_requires_both_reviewed_classes_on_the_same_date():
    from aggregates_pipeline import reviewed_share_totals
    a=dict(tag='dei:EntityCommonStockSharesOutstanding',scope='us-gaap:CommonClassAMember',end='2026-08-05',value=48206437)
    b=dict(a,scope='us-gaap:CommonClassBMember',value=8549118)
    total=reviewed_share_totals([a,b],'ROAD')[0]
    assert total['value']==56755555
    assert len(total['inputs'])==2
    assert not reviewed_share_totals([a,dict(b,end='2026-07-01')],'ROAD')
    assert not reviewed_share_totals([a,b],'OTHER')


def test_separate_short_term_borrowings_are_added_once_to_long_term_debt():
    from aggregates_facts import balance_at
    rows=[dict(metric=metric,value=value,locator=tag,period_type='instant',period_end='2026-06-30')
          for metric,value,tag in [('noncurrent_debt_usd',4235,'us-gaap:LongTermDebtNoncurrent'),
          ('current_debt_usd',1034,'us-gaap:LongTermDebtCurrent'),('short_term_borrowings_usd',735,'us-gaap:ShortTermBorrowings')]]
    assert balance_at(rows,'2026-06-30')['total_debt_usd']==6004
    rows[1]['locator']='us-gaap:DebtCurrent';rows[1]['value']=1769
    assert balance_at(rows,'2026-06-30')['total_debt_usd']==6004


def test_sec_incremental_refresh_overlaps_last_successful_scan():
    import scan_activist_sources as scan
    state={'sec':{'last_scanned':{'A':'2026-10-21T12:00:00Z'}}}
    with mock.patch.object(scan,'scan_ticker_sec',return_value=[]) as fetch:
        scan.run_sec_phase(['A'],state,scan.Budget(None))
    assert fetch.call_args.kwargs['min_date']=='2026-10-20'


def test_nol_market_cap_fallback_requires_a_current_usd_observation():
    from datetime import datetime,timezone
    from build_nol_screener import cached_market_cap
    today=datetime(2026,10,27,tzinfo=timezone.utc)
    row=dict(currency='USD',market_cap_as_of='2026-10-26T20:00:00Z',issuer_market_cap=1000)
    assert cached_market_cap(row,today)==1000
    assert cached_market_cap(dict(row,currency='EUR'),today) is None
    assert cached_market_cap(dict(row,market_cap_as_of='2026-09-30T20:00:00Z'),today) is None


def test_index_eligibility_prefers_current_market_observation_over_saved_model_price():
    import index_market_inputs as market
    saved=dict(inputs={'price':1,'shares_millions':1},equity_market_cap_m=1)
    cache=dict(currency='USD',issuer_market_cap=20_000_000,shares_outstanding=2_000_000,
               price=10,source='provider',market_cap_as_of='2026-10-26T20:00:00Z')
    with mock.patch.object(market,'_load_json',return_value=saved),mock.patch.object(market,'current_usd_snapshot',return_value=True):
        row=market.market_inputs_for_ticker('EXAMPLE',fundamentals_cache={'EXAMPLE':cache})
    assert row['market_cap_usd']==20_000_000
    assert row['price']==10
    assert row['mcap_source']=='provider'


def test_podcast_regression_guard_keeps_history_and_admits_new_summaries():
    from dashboard_catalog_recovery import merge_podcast_catalogs
    prior=[dict(episode_id='a',published='2026-09-01',summary_status='ready',summary_headline='Verified summary'),
           dict(episode_id='b',published='2026-09-02')]
    new=[dict(episode_id='a',published='2026-09-01',summary_status='pending_model',summary_headline='Fallback'),
         dict(episode_id='c',published='2026-10-20',summary_status='ready',summary_headline='New summary')]
    rows=merge_podcast_catalogs(prior,new);by={r['episode_id']:r for r in rows}
    assert set(by)=={'a','b','c'}
    assert by['a']['summary_headline']=='Verified summary'
    assert by['c']['summary_headline']=='New summary'


def test_published_financial_history_is_bounded_without_mutating_source_facts():
    from aggregates_pipeline import bounded_facts
    rows=[{'end':'2019-12-31','val':1},{'end':'2020-12-31','val':2},{'end':'2025-12-31','val':3}]
    raw={'facts':{'us-gaap':{'Revenues':{'units':{'USD':rows}}}}}
    limited=bounded_facts(raw,2020)
    assert [r['val'] for r in limited['facts']['us-gaap']['Revenues']['units']['USD']]==[2,3]
    assert len(raw['facts']['us-gaap']['Revenues']['units']['USD'])==3
