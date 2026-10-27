"""Conservative table extraction with explicit column dates and segment bounds.

Unknown layouts produce gaps; they do not infer corporate values per rock ton.
"""
from __future__ import annotations
import calendar
import re
from html import unescape
from datetime import date, timedelta
from html.parser import HTMLParser
from aggregates_operating_metrics import METRICS, validate

ALIASES={
 'shipments_million_tons':r'^(unit shipments.*tons|shipments \(tons\)|aggregates \(tons\)|aggregates (?:shipments|volumes?|[-–] tons sold|sales volume)(?: \(.*\))?)$',
 'price_per_ton':r'^(freight.adjusted sales price(?: per ton)?|average selling price per ton|aggregates \(per ton\)|aggregates average selling price(?: per ton)?)$',
 'cash_gp_per_ton':r'^(aggregates )?cash gross profit per ton$',
 'cash_cost_per_ton':r'^(freight.adjusted )?cash cost of sales per ton$',
 'gross_profit_per_ton':r'^(aggregates )?gross profit per ton$',
 'segment_ebitda_usd':r'^aggregates (?:adjusted )?ebitda$',
 'organic_volume_growth_pct':r'^(?:aggregates )?(?:organic|same.store) (?:shipments|volume) (?:growth|change)(?: %)?$',
 'organic_price_growth_pct':r'^(?:aggregates )?organic (?:mix.adjusted )?(?:price|pricing|asp) (?:growth|change)(?: %)?$',
 'reserve_life_years':r'^(?:aggregates )?(?:average )?reserve life(?: \(years\))?$',
 'backlog_usd':r'^(?:awarded |construction |contracting )?backlog$',
}


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.tables=[];self.depth=0;self.rows=[];self.row=[];self.cell=None;self.span=1;self.context='';self.before=''
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='table':
            if not self.depth:self.rows=[];self.before=self.context[-600:]
            self.depth+=1
        if self.depth and tag=='tr':self.row=[]
        if self.depth and tag in {'td','th'}:self.cell=[];self.span=min(50,int(a.get('colspan') or 1))
        if tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,data):
        self.context=(self.context+' '+data)[-1200:]
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in {'td','th'} and self.cell is not None:
            value=' '.join(''.join(self.cell).split());self.row.extend([value]+['']*(self.span-1));self.cell=None
        if tag=='tr' and self.depth and self.row:self.rows.append(self.row);self.row=[]
        if tag=='table':
            self.depth=max(0,self.depth-1)
            if not self.depth and self.rows:self.tables.append((self.before,self.rows))


def number(text):
    value=text.strip().replace(',','').replace('$','').replace('%','').replace('\u2212','-')
    if re.fullmatch(r'\(?-?\d+(?:\.\d+)?\)?',value):return -float(value[1:-1]) if value.startswith('(') else float(value)
    return None


def parse_tables(html, meta):
    parser=Tables();parser.feed(html);out=[]
    end=date.fromisoformat(meta['period_end']);published=meta['published_at']
    prose=re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',html))) if meta['ticker'] in {'GVA','KNF'} else ''
    knf_freight=meta['ticker']=='KNF' and 'average selling price includes freight and delivery' in prose.lower()
    for before,rows in parser.tables:
        context=before.lower();segment='aggregates' if 'aggregates' in context[-250:] else None
        year_columns=[];column_kind={};scale_millions='millions' in (' '.join(' '.join(r) for r in rows[:8])+' '+before).lower()
        scale_thousands='thousands' in ' '.join(' '.join(r) for r in rows[:8]).lower()
        for index,row in enumerate(rows):
            text=' '.join(row).lower()
            # A new segment heading stops the aggregates scope immediately.
            heading=[c.lower().strip(': ') for c in row if c.strip()]
            if len(heading)<=2 and any('aggregates' in c for c in heading):segment='aggregates'
            elif len(heading)<=2 and any(re.search(r'\b(asphalt|concrete|cement|specialties) (segment|product line)\b',c) for c in heading):segment=None
            for col,cell in enumerate(row):
                lower=cell.lower()
                if re.search(r'(?:year|twelve months) ended',lower):column_kind[col]='FY'
                elif re.search(r'(?:three months|quarter) ended',lower):column_kind[col]='Q'
                elif re.search(r'(?:six|nine) months ended',lower):column_kind[col]='YTD'
            years=[(col,int(cell)) for col,cell in enumerate(row) if re.fullmatch(r'20\d\d',cell.strip())]
            if years:year_columns=years;continue
            if not year_columns:continue
            label=next((c for c in row if re.search('[a-zA-Z]',c)), '')
            clean=re.sub(r'[¹²³⁴⁵⁶*]|\s*\d+$|\s*\(\d+\)$','',label.lower()).strip()
            # Explicit product rows establish their own scope, even when the
            # preceding row belongs to cement or concrete in a shared table.
            if re.match(r'^aggregates\b',clean):segment='aggregates'
            if not segment:continue
            metric=next((key for key,pattern in ALIASES.items() if re.fullmatch(pattern,clean)),None)
            organic_pct=None
            if meta['ticker']=='MLM' and clean in {'organic shipments (tons)','organic average selling price per ton'}:
                percentages=[number(c) for c in row if '%' in c and number(c) is not None]
                if len(percentages)==1:
                    organic_pct=percentages[0]
                    metric='organic_volume_growth_pct' if clean=='organic shipments (tons)' else 'organic_price_growth_pct'
            if not metric:continue
            # Currency per-ton and volume require a known issuer table basis.
            freight='freight_adjusted' if meta['ticker']=='VMC' else 'issuer_asp_ex_freight' if meta['ticker']=='MLM' else 'issuer_including_freight_delivery' if knf_freight else meta.get('freight_basis','reported_unresolved')
            if metric=='price_per_ton' and freight=='reported_unresolved':continue
            for position,(col,year) in enumerate(year_columns[:1] if organic_pct is not None else year_columns):
                if col>=len(row):continue
                stop=year_columns[position+1][0] if position+1<len(year_columns) else len(row)
                values=[number(c) for c in row[col:stop] if '%' not in c and number(c) is not None]
                value=organic_pct if organic_pct is not None else values[0] if len(values)==1 else None
                if value is None:continue
                kind='FY' if meta['form'].startswith('10-K') else 'Q'
                starts=[c for c in column_kind if c<=col]
                if starts:kind=column_kind[max(starts)]
                month=end.month
                day=calendar.monthrange(year,month)[1]
                finish=date(year,month,day)
                fiscal_start=int(meta.get('fiscal_start_month',4 if meta['ticker']=='EXP' else 10 if meta['ticker']=='ROAD' else 1))
                if kind in {'FY','YTD'}:
                    start=date(year if fiscal_start<=month else year-1,fiscal_start,1).isoformat()
                else:
                    start=(date(year,month-2,1) if month>=3 else date(year-1,month+10,1)).isoformat()
                period_end=finish.isoformat()
                unit=METRICS[metric][0]
                if unit=='USD' and scale_millions:value*=1e6
                if unit=='million short tons':
                    if scale_thousands:value/=1000
                    elif not scale_millions:continue
                record={**meta,'metric':metric,'value':value,'unit':unit,'currency':'USD' if unit.startswith('USD') else None,'period_start':start,'period_end':period_end,'period_type':kind,
                    'business_segment':'aggregates','geography':'consolidated','product':'aggregates','freight_basis':freight if unit.startswith('USD/') else 'not_applicable',
                    'sales_scope':meta.get('sales_scope','issuer_reported'),'perimeter_basis':'reported','status':'reported','confidence':'high',
                    'locator':f"table {parser.tables.index((before,rows))+1}, row {index+1}: {label}",'extraction_version':'aggregates-table-v1'}
                validate(record);out.append(record)
    from aggregates_issuer_tables import extract
    out.extend(extract(parser.tables,meta,prose))
    return out
