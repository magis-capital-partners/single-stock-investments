import io
import json
from datetime import date
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from commodity_history import fred_csv,world_bank,steo_history,lbma_history,metadata,collect
from commodity_inputs import crude_inputs,readiness,ratio_history

AS_OF=date(2026,10,28)


def test_fred_rejects_wrong_series_and_future_nonfinite():
    raw=b'observation_date,DFII10\n2026-10-01,-0.5\n2026-10-29,2\n2026-10-02,NaN\n2026-10-03,.\n'
    assert fred_csv(raw,'DFII10',AS_OF)==[{'date':'2026-10-01','value':-.5}]
    with pytest.raises(ValueError):fred_csv(raw,'DCOILWTICO',AS_OF)


def workbook(sheet,rows):
    import openpyxl
    b=openpyxl.Workbook();s=b.active;s.title=sheet
    for row in rows:s.append(row)
    f=io.BytesIO();b.save(f);return f.getvalue()


def test_world_bank_bullion_units_and_month_end():
    raw=workbook('Monthly Prices',[['Monthly prices'],[None,'Gold','Silver','Copper'],[None,'$/troy oz','$/troy oz','$/mt'],['2026M09',4000,50,10000],['2026M11',5000,60,11000]])
    p=world_bank(raw,AS_OF)
    assert p['gold_bullion']==[{'date':'2026-09-30','value':4000.0}]
    assert p['copper_spot'][0]['value']==10000


def test_steo_drops_forecast_from_historical_inputs():
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        z.writestr('STEO.txt','\n'.join(json.dumps({'series_id':sid,'units':'million barrels per day' if 'COPS' in sid else 'million barrels, end-of-period','data':[['202609',10],['202612',20]]}) for sid in ['STEO.COPS_OPEC.M','STEO.PASC_OECD_T3.M']))
    p=steo_history(b.getvalue(),AS_OF)
    assert all(len(v['observations'])==1 for v in p.values())
    assert all(v['observations'][0]['basis']=='published_estimate' for v in p.values())


def test_london_units_no_etf_double_count():
    raw=workbook('London Vault Holdings Data',[['Title'],['Month End','Gold','Silver'],[None,"Troy Ounces ('000s)","Troy Ounces ('000s)"],['2026-09',300000,900000]])
    assert lbma_history(raw,AS_OF)['london_silver_stocks'][0]['value']==900


def test_seasonal_normal_and_regional_days_use_aligned_periods():
    p={'series':{'oecd_commercial_stocks':{'observations':[{'date':f'{y}-{m:02}-28','value':y} for y in range(2021,2026) for m in [3,6,9,12]]},
                 'east_coast_distillate_use':{'observations':[{'date':'2026-07-31','value':1000}]},
                 'east_coast_distillate_stocks':{'observations':[{'date':'2026-07-24','value':30000},{'date':'2026-10-23','value':60000}]}}}
    d=crude_inputs(p,AS_OF)
    assert d['seasonal_oecd_stock_mb']==[2023]*4
    assert d['east_coast_distillate_days']==30
    assert d['distillate_basis']['stock_date']=='2026-07-24'
    assert not readiness('gold',p,AS_OF)['required_ready']


def test_failed_refresh_preserves_last_good_provenance():
    old={'gold_bullion':{'source_url':'https://original.example/data','observations':[{'date':'2026-09-30','value':4000}]}}
    def failed(url):raise OSError('offline')
    values,errors=collect(failed,old,AS_OF,lambda _:None)
    assert values['gold_bullion']['source_url']=='https://original.example/data'
    assert values['gold_bullion']['observations']==old['gold_bullion']['observations']
    assert values['gold_bullion']['status']=='fetch_failed' and 'gold_bullion' in errors
