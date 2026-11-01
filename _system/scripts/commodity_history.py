"""Publisher-specific historical inputs, with units, vintages and explicit frequency."""
from __future__ import annotations

import calendar
import csv
from datetime import date, datetime
import io
import json
import math
import re
import zipfile

from commodity_common import digest, finite

WORLD_BANK_PAGE='https://www.worldbank.org/en/research/commodity-markets'
WORLD_BANK_BOOK='https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx'
STEO_BULK='https://api.eia.gov/bulk/STEO.zip'
CAPACITY_URL='https://www.eia.gov/petroleum/storagecapacity/crudeoilstorage.xlsx'
LBMA_PAGE='https://www.lbma.org.uk/prices-and-data/london-vault-data'
EIA_SERIES={
    'cushing_stocks':('W_EPC0_SAX_YCUOK_MBBL','w','thousand barrels'),
    'east_coast_distillate_stocks':('WDISTP11','w','thousand barrels'),
    'east_coast_distillate_use':('MDIUPP11','m','thousand barrels/day'),
}
FRED_SERIES={
    'wti_spot':('DCOILWTICO','USD/barrel'),
    'brent_spot':('DCOILBRENTEU','USD/barrel'),
    'real_yield':('DFII10','percent'),
    'broad_dollar':('DTWEXBGS','index, January 2006=100'),
}


def month_end(period):
    year,month=int(period[:4]),int(period[-2:])
    return date(year,month,calendar.monthrange(year,month)[1]).isoformat()


def clean(rows, as_of):
    found={}
    for row in rows:
        try:when=date.fromisoformat(row['date'])
        except (TypeError,ValueError):continue
        if when<=as_of and finite(row.get('value')):
            found[row['date']]=row
    return [found[d] for d in sorted(found)]


def fred_csv(raw, series_id, as_of):
    records=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if series_id not in (records.fieldnames or []):
        raise ValueError('FRED response has no requested series column')
    rows=[]
    for r in records:
        try:value=float(r[series_id])
        except (ValueError,TypeError):continue
        rows.append({'date':r.get('observation_date') or r.get('DATE') or '', 'value':value})
    rows=clean(rows,as_of)
    if not rows:raise ValueError('No historical observations')
    return rows


def eia_xls(raw, source_id, as_of):
    import xlrd
    book=xlrd.open_workbook(file_contents=raw)
    for sheet in book.sheets():
        if sheet.nrows<4:continue
        keys=[str(v) for v in sheet.row_values(1)]
        if source_id not in keys:continue
        column=keys.index(source_id);rows=[]
        for i in range(3,sheet.nrows):
            stamp,value=sheet.cell_value(i,0),sheet.cell_value(i,column)
            if not finite(stamp) or not finite(value):continue
            when=xlrd.xldate_as_datetime(stamp,book.datemode).date().isoformat()
            if source_id=='MDIUPP11':when=month_end(when[:7])
            rows.append({'date':when,'value':float(value)})
        result=clean(rows,as_of)
        if result:return result
    raise ValueError('EIA workbook does not contain '+source_id)


def world_bank(raw, as_of):
    import openpyxl
    book=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    sheet=book['Monthly Prices'];rows=iter(sheet.iter_rows(values_only=True));header=None
    for row in rows:
        if 'Gold' in row and 'Silver' in row and 'Copper' in row:
            header=list(row);break
    if header is None:raise ValueError('World Bank price columns missing')
    units=next(rows)
    columns={'gold_bullion':('Gold','troy oz'),'silver_bullion':('Silver','troy oz'),'copper_spot':('Copper','mt')}
    positions={k:header.index(label) for k,(label,_) in columns.items()}
    for key,(_,unit) in columns.items():
        if unit not in str(units[positions[key]]):raise ValueError('Unexpected World Bank unit: '+key)
    output={k:[] for k in columns}
    for row in rows:
        if not re.fullmatch(r'\d{4}M\d{2}',str(row[0] or '')):continue
        when=month_end(row[0].replace('M','-'))
        for key,col in positions.items():
            value=row[col]
            if finite(value) and value>0:output[key].append({'date':when,'value':float(value)})
    book.close()
    return {k:clean(v,as_of) for k,v in output.items()}


def steo_history(raw,as_of):
    wanted={'STEO.COPS_OPEC.M':'opec_spare_capacity','STEO.PASC_OECD_T3.M':'oecd_commercial_stocks'}
    output={}
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        name=next(n for n in bundle.namelist() if n.lower().endswith('.txt'))
        for line in bundle.read(name).splitlines():
            row=json.loads(line);key=wanted.get(row.get('series_id'))
            if not key:continue
            expected='million barrels per day' if key=='opec_spare_capacity' else 'million barrels, end-of-period'
            if row.get('units')!=expected:raise ValueError('Unexpected STEO unit: '+key)
            observations=clean([{'date':month_end(period),'value':value,'basis':'published_estimate'} for period,value in row.get('data',[]) if re.fullmatch(r'\d{6}',period)],as_of)
            output[key]={'observations':observations,'unit':row['units'],'source_id':row['series_id'],'publisher_updated_at':row.get('updated'),
                         'basis':'Published estimates in the fetched STEO vintage; historical revisions are retained.'}
    if len(output)!=len(wanted):raise ValueError('STEO inventory or spare-capacity series missing')
    return output


def metadata(raw,url,rows,as_of,*,unit,frequency,source_id,basis='observed',max_age_days=None):
    if not rows:raise ValueError('No valid historical observations')
    age=(as_of-date.fromisoformat(rows[-1]['date'])).days
    tolerance=max_age_days or {'daily':14,'weekly':21,'monthly':75,'annual':550}.get(frequency,120)
    return {'source_url':url,'source_id':source_id,'sha256':digest(raw),'status':'fetched','fetched_at':as_of.isoformat(),
            'unit':unit,'frequency':frequency,'basis':basis,'first_observation':rows[0]['date'],'last_observation':rows[-1]['date'],
            'age_days':age,'max_age_days':tolerance,'stale':age>tolerance,'observations':rows}


def capacity_history(raw,as_of):
    import openpyxl
    book=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    rows=list(book['Cushing'].iter_rows(values_only=True));dates=rows[3]
    target=next(r for r in rows if r[0]=='Tank Working Storage Capacity')
    if 'thousand barrels' not in str(rows[1][0]):raise ValueError('Unexpected capacity unit')
    values=clean([{'date':d.date().isoformat(),'value':target[i]} for i,d in enumerate(dates) if isinstance(d,datetime) and finite(target[i])],as_of)
    book.close();return values


def lbma_history(raw,as_of):
    import openpyxl
    book=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    rows=list(book['London Vault Holdings Data'].iter_rows(values_only=True))
    if rows[1][1:3]!=('Gold','Silver') or not all('000s' in str(x) for x in rows[2][1:3]):
        raise ValueError('Unexpected London vault columns or units')
    result={}
    for col,key in [(1,'london_gold_stocks'),(2,'london_silver_stocks')]:
        result[key]=clean([{'date':month_end(str(r[0])),'value':r[col]/1000} for r in rows[3:] if re.fullmatch(r'\d{4}-\d{2}',str(r[0])) and finite(r[col])],as_of)
    book.close();return result


def collect(download, prior, as_of, capture):
    """Return last-good observations plus per-source failures, never an empty success."""
    output={};failures=[]
    def failed(key,url,exc):
        previous=prior.get(key,{})
        # Preserve the provenance of retained values. A failed attempt has its
        # own URL, not a replacement source label for the old observations.
        output[key]={**previous,'status':'fetch_failed','last_attempt':as_of.isoformat(),'attempted_url':url,
                     'error':type(exc).__name__,'http_status':getattr(exc,'code',None),'observations':previous.get('observations',[])}
        failures.append(key)
    for key,(sid,unit) in FRED_SERIES.items():
        url='https://fred.stlouisfed.org/graph/fredgraph.csv?id='+sid
        try:
            raw=download(url);capture(raw)
            output[key]=metadata(raw,url,fred_csv(raw,sid,as_of),as_of,unit=unit,frequency='daily',source_id=sid)
        except Exception as exc:failed(key,url,exc)
    for key,(sid,freq,unit) in EIA_SERIES.items():
        url=f'https://www.eia.gov/dnav/pet/hist_xls/{sid}{freq}.xls'
        try:
            raw=download(url);capture(raw)
            output[key]=metadata(raw,url,eia_xls(raw,sid,as_of),as_of,unit=unit,frequency='weekly' if freq=='w' else 'monthly',source_id=sid,max_age_days=120 if sid=='MDIUPP11' else None)
        except Exception as exc:failed(key,url,exc)
    try:
        # Resolve the current publisher link so a yearly document-id change
        # cannot silently strand the history on an old workbook.
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        landing=download(WORLD_BANK_PAGE)
        soup=BeautifulSoup(landing,'html.parser')
        link=next((a.get('href') for a in soup.select('a[href]') if 'CMO-Historical-Data-Monthly' in a.get('href','')),None)
        url=urljoin(WORLD_BANK_PAGE,link) if link else WORLD_BANK_BOOK
        raw=download(url);capture(raw)
        for key,rows in world_bank(raw,as_of).items():
            output[key]=metadata(raw,url,rows,as_of,unit='USD/tonne' if key=='copper_spot' else 'USD/troy oz',frequency='monthly',source_id='World Bank Pink Sheet: '+key,
                                 basis='Published monthly average bullion price' if key!='copper_spot' else 'Published monthly average copper price')
    except Exception as exc:
        for key in ('gold_bullion','silver_bullion','copper_spot'):failed(key,WORLD_BANK_BOOK,exc)
    try:
        raw=download(STEO_BULK);capture(raw)
        for key,values in steo_history(raw,as_of).items():
            output[key]={**metadata(raw,STEO_BULK,values['observations'],as_of,unit=values['unit'],frequency='monthly',source_id=values['source_id'],basis=values['basis']),
                         'publisher_updated_at':values['publisher_updated_at']}
    except Exception as exc:
        for key in ('oecd_commercial_stocks','opec_spare_capacity'):failed(key,STEO_BULK,exc)
    try:
        raw=download(CAPACITY_URL);capture(raw)
        output['cushing_working_capacity']=metadata(raw,CAPACITY_URL,capacity_history(raw,as_of),as_of,unit='thousand barrels',frequency='annual',source_id='EIA Cushing tank working storage capacity')
        output['cushing_working_capacity']['discontinued']=True
        output['cushing_working_capacity']['note']='EIA discontinued this survey after March 2024; retained as a dated historical capacity reference.'
    except Exception as exc:failed('cushing_working_capacity',CAPACITY_URL,exc)
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        landing=download(LBMA_PAGE)
        soup=BeautifulSoup(landing,'html.parser')
        link=next((a['href'] for a in soup.select('a[href]') if 'Vault-Holdings' in a['href'] and a['href'].endswith('.xlsx')),None)
        if not link:raise ValueError('London vault workbook link missing')
        url=urljoin(LBMA_PAGE,link);raw=download(url);capture(raw)
        for key,rows in lbma_history(raw,as_of).items():
            output[key]=metadata(raw,url,rows,as_of,unit='million troy oz',frequency='monthly',source_id='LBMA London Vault Holdings: '+key,basis='Physical location inventory; includes ETF-owned metal. Not freely available supply.')
    except Exception as exc:
        for key in ('london_gold_stocks','london_silver_stocks'):failed(key,LBMA_PAGE,exc)
    return output,failures
