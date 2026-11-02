"""Adapters for reviewed SEC property and product tables.

Select tables by their headings and product labels, never a filing's table
number. Each published number retains the exact table and row locator.
"""
from __future__ import annotations
import re
from datetime import date, timedelta
from aggregates_operating_metrics import METRICS, validate


def compact(row):
    return [re.sub(r'\s+', ' ', x.replace('\u200b', '')).strip() for x in row if x.replace('\u200b','').strip()]


def numbers(row):
    out=[]
    for cell in row:
        if '%' in cell:continue
        cell=cell.replace(',','').replace('$','').strip()
        if re.fullmatch(r'\(?-?\d+(?:\.\d+)?\)?',cell):
            out.append(-float(cell[1:-1]) if cell.startswith('(') else float(cell))
    return out


def extract(tables, meta, text=''):
    ticker=meta['ticker'];out=[]
    if meta['form'] not in {'10-K','10-K/A','20-F','20-F/A'}:return out
    end=date.fromisoformat(meta['period_end'])
    def emit(metric,value,table,row,*,year=None,product='aggregates',scope='mining_properties',freight='not_applicable',status='reported'):
        finish=end.replace(year=year or end.year)
        start=date(finish.year-1,finish.month,finish.day)+timedelta(days=1)
        unit=METRICS[metric][0]
        record={**meta,'metric':metric,'value':round(value,6),'unit':unit,
            'currency':'USD' if unit.startswith('USD') else None,
            'period_start':start.isoformat(),'period_end':finish.isoformat(),'period_type':'FY',
            'business_segment':'aggregates' if product=='aggregates' else product,
            'geography':'consolidated','product':product,'freight_basis':freight,
            'sales_scope':scope,'perimeter_basis':'reported','status':status,'confidence':'high',
            'locator':f'table {table}, row {row}: reviewed issuer property/product table',
            'extraction_version':'issuer-tables-v1'}
        validate(record);out.append(record)
    if ticker=='GVA':
        match=re.search(r'Annual production of aggregates for all mining properties was ([\d,.]+) million tons, ([\d,.]+) million tons, and ([\d,.]+) million tons during the years ended December 31, (20\d\d), (20\d\d) and (20\d\d)',text,re.I)
        if match:
            for amount,year in zip(match.groups()[:3],match.groups()[3:]):
                emit('production_million_tons',float(amount.replace(',','')),'Item 2','Annual production of aggregates for all mining properties',year=int(year))
    for table,(before,raw) in enumerate(tables,1):
        rows=[compact(row) for row in raw];text=' '.join(' '.join(row) for row in rows)
        context=(before+' '+text).lower()
        years=[]
        for row in rows:
            found=[int(cell) for cell in row if re.fullmatch(r'20\d\d',cell)]
            if found and len(found)==len(row):years=found;break
        if ticker=='TTAM' and 'external aggregates volumes' in text.lower() and 'average external selling price' in text.lower():
            # Item 5 explicitly defines tons as short tons. The external
            # volume excludes internal transfers; ASP has no freight adjustment.
            table_years=next(([int(c) for c in row if re.fullmatch(r'20\d\d',c)] for row in rows
                              if sum(bool(re.fullmatch(r'20\d\d',c)) for c in row)>=2),[])
            for index,row in enumerate(rows,1):
                if not row:continue
                label=row[0].lower()
                metric='shipments_million_tons' if label=='external aggregates volumes' else 'price_per_ton' if label=='aggregates' else None
                if not metric:continue
                for year,value in zip(table_years,numbers(row[1:])):
                    emit(metric,value/1000 if metric=='shipments_million_tons' else value,table,index,
                         year=year,scope='external',freight='issuer_not_freight_adjusted' if metric=='price_per_ton' else 'not_applicable')
                    out[-1]['notes']='Item 5 short-ton convention; external sales only, excluding internal transfers and by-products. ASP is not freight-adjusted.'
        if ticker=='VMC' and 'aggregates reserves' in text.lower() and 'production' in text.lower() and 'millions of tons' in text.lower():
            for index,row in enumerate(rows,1):
                values=numbers(row)
                if row and row[0]=='Total' and len(values)==8:
                    emit('reserves_million_tons',values[-2],table,index)
                    emit('production_million_tons',values[-1],table,index)
        if ticker=='KNF':
            if 'total annual aggregate production' in text.lower() and 'thousands' in text.lower():
                for index,row in enumerate(rows,1):
                    if row and row[0]=='Total' and len(numbers(row))==2:emit('production_million_tons',sum(numbers(row))/1000,table,index)
            if 'proven mineral reserves' in text.lower() and 'aggregate sites' in text.lower() and 'thousands' in text.lower():
                for index,row in enumerate(rows,1):
                    values=numbers(row)
                    if row and row[0]=='Total' and len(values)==8:
                        emit('reserves_million_tons',values[-1]/1000,table,index)
                        emit('quarries',values[0],table,index)
            if years and 'sales (thousands)' in text.lower():
                for index,row in enumerate(rows,1):
                    label=row[0].lower().rstrip('*') if row else ''
                    values=numbers(row[1:])
                    if label not in {'aggregates (tons)','aggregates (per ton)'} or len(values)!=len(years):continue
                    for year,value in zip(years,values):
                        is_price='per ton' in label
                        emit('price_per_ton' if is_price else 'shipments_million_tons',value if is_price else value/1000,table,index,year=year,scope='issuer_reported',freight='issuer_including_freight_delivery' if is_price else 'not_applicable')
        if ticker=='ACA':
            if 'annual production (million tons)' in text.lower() and years:
                for index,row in enumerate(rows,1):
                    if row and row[0].lower()=='natural aggregates' and len(numbers(row[1:]))==len(years):
                        for year,value in zip(years,numbers(row[1:])):emit('production_million_tons',value,table,index,year=year,product='natural_aggregates')
            if 'estimated mineral reserves (million tons)' in text.lower():
                natural=False
                for index,row in enumerate(rows,1):
                    if row and row[0].lower()=='natural aggregates:':natural=True;continue
                    if row and 'specialty materials' in row[0].lower():natural=False
                    values=numbers(row)
                    if natural and row and re.fullmatch(r'[\d,.]+',row[0]) and len(values)>=3:
                        emit('reserves_million_tons',values[2],table,index,product='natural_aggregates');natural=False
        if ticker=='MLM' and 'summary mineral reserves at end of fiscal year' in text.lower() and 'in thousands' in text.lower():
            totals=[]
            for index,row in enumerate(rows,1):
                if row and re.fullmatch(r'total (?:crushed stone|sand & gravel)',row[0],re.I) and len(numbers(row))==3:totals.append((index,numbers(row)[-1]))
            if len(totals)==2:emit('reserves_million_tons',sum(x[1] for x in totals)/1000,table,','.join(str(x[0]) for x in totals),status='derived')
        if ticker=='CRH':
            aggregates=False
            for index,row in enumerate(rows,1):
                if row==['Aggregates']:aggregates=True;continue
                if row and row[0] in {'Cement','Lime'}:aggregates=False
                if not aggregates or not row or row[0]!='Subtotal':continue
                values=numbers(row)
                if 'total reserves' in text.lower() and 'proven' in text.lower() and len(values)==3:
                    emit('reserves_million_tons',values[-1],table,index)
                if 'annualized extraction' in text.lower() and len(values)>=6:
                    emit('quarries',values[0],table,index)
                    for year,value in zip([end.year-2,end.year-1,end.year],values[3:6]):emit('production_million_tons',value,table,index,year=year)
        if ticker=='AMRZ' and 'reserves' in text.lower() and 'in millions of tons' in text.lower() and 'resources' not in text.lower():
            aggregates=False
            for index,row in enumerate(rows,1):
                if row and row[0].lower()=='aggregates':aggregates=True;continue
                if row and row[0].lower() in {'cement','limestone'}:aggregates=False
                values=numbers(row)
                if aggregates and row and row[0]=='Subtotal' and len(values)==3:emit('reserves_million_tons',values[-1],table,index)
        if ticker=='GVA' and 'proven mineral reserves' in text.lower() and 'tons in millions' in before.lower():
            for index,row in enumerate(rows,1):
                values=numbers(row)
                if row and row[0]=='Grand Total' and len(values)==3:emit('reserves_million_tons',values[-1],table,index)
        if ticker=='EXP' and 'aggregates reserves' in text.lower() and 'proven' in text.lower():
            for index,row in enumerate(rows,1):
                if len(row)==3 and len(numbers(row))==3:
                    values=numbers(row)
                    if abs(values[0]+values[1]-values[2])<1:emit('reserves_million_tons',values[-1]/1000,table,index)
        if ticker=='USLM' and 'summary of total limestone mineral reserves as of' in text.lower() and 'in thousands of tons' in text.lower():
            match=re.search(r'as of December 31, (20\d\d)',text)
            for index,row in enumerate(rows,1):
                values=numbers(row)
                if len(values)==3 and len(row)>3 and abs(values[0]+values[1]-values[2])<1:
                    emit('reserves_million_tons',values[-1]/1000,table,index,year=int(match[1]) if match else None,product='limestone')
    return out
