"""Bounded primary-filing extraction. No financial value is inferred from absence.

Stdlib HTML/iXBRL extraction; optional PyMuPDF/Tesseract for PDF evidence.
OCR candidates require owner review. No model, broker or credential dependency.
"""
from __future__ import annotations
import base64
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser

VERSION = 'primary_financial_extraction.v1'
FLOW = {'revenues', 'net_income', 'operating_income', 'cfo'}
NAMES = {
 'revenues': ['revenues', 'revenue', 'total revenue', 'total revenues', 'net revenue', 'net revenues', 'net sales', 'sales revenue net', 'revenue from contracts with customers', 'revenue from contract with customer excluding assessed tax'],
 'net_income': ['net income loss', 'net income', 'net loss', 'net loss for the period', 'net income for the period', 'profit loss', 'loss for the period', 'profit for the period', 'net income loss available to common stockholders basic'],
 'operating_income': ['operating income loss', 'operating income', 'operating loss', 'loss from operations', 'income from operations', 'profit loss from operating activities', 'operating profit loss'],
 'cfo': ['net cash provided by used in operating activities', 'net cash provided by operating activities', 'net cash used in operating activities', 'net cash used in operating activities continuing operations', 'net cash flows from used in operating activities', 'cash flows from used in operating activities', 'net cash generated from operating activities', 'net cash from operating activities'],
 'cash': ['cash and cash equivalents', 'cash and cash equivalents at carrying value'],
 'total_assets': ['total assets', 'assets'],
 'stockholders_equity': ['stockholders equity', 'total stockholders equity', 'total stockholders deficit', 'stockholders deficit', 'total shareholders equity', 'total shareholders deficit', 'shareholders equity deficit', 'stockholders equity deficit', 'equity', 'equity attributable to owners of parent', 'total equity'],
 'long_term_debt': ['long term debt noncurrent', 'long term debt non current', 'long term debt net of current portion', 'long term borrowings noncurrent', 'noncurrent borrowings', 'non current borrowings', 'long term debt'],
 'current_debt': ['long term debt current', 'current portion of long term debt', 'current portion of noncurrent borrowings', 'current portion of non current borrowings', 'current portion of long term borrowings', 'total current borrowings', 'current borrowings'],
}
def words(value):
    value = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(value))
    return re.sub(r'[^a-z0-9 ]', ' ', value.lower()).strip()
def clean(value):
    return re.sub(r'\s+', ' ', words(value)).strip()
ALIASES = {clean(v): k for k, vals in NAMES.items() for v in vals}
def metric_for(value):
    label = re.sub(r'\([^)]*\)|\[[^]]*\]', '', str(value))
    return ALIASES.get(clean(label))
def numeric(value):
    raw = unescape(str(value)).strip().replace('\u2212', '-').replace('\u00a0', '')
    raw = re.sub(r'[\s$€£¥]', '', raw)
    raw = re.sub(r'^(?:USD|CAD|HKD|CNY|RMB)|[*†‡]+$', '', raw)
    if raw in {'', '-', '—', '–', 'N/A', 'n/a', 'nil'}:
        return None
    if re.fullmatch(r'\(?[+-]?\d{1,3}(?:\.\d{3})+,\d{1,2}\)?',raw):raw=raw.replace('.','').replace(',','.')
    elif re.fullmatch(r'\(?[+-]?\d+,\d{1,2}\)?',raw):raw=raw.replace(',','.')
    if not re.fullmatch(r'\(?[+-]?[\d,]+(?:\.\d+)?\)?', raw):
        return None
    neg = raw.startswith('(') and raw.endswith(')')
    try:
        value = float(raw.strip('()').replace(',', '')) * (-1 if neg else 1)
        return value if math.isfinite(value) else None
    except ValueError:
        return None
def currency_in(text, hint=None):
    patterns = [('USD', r'U\.?S\.?\s*dollars|US\$|United States dollars|USD'), ('CNY', r'renminbi|RMB|CNY'), ('CAD', r'Canadian dollars|CAD|C\$'), ('HKD', r'Hong Kong dollars|HK\$|HKD'), ('EUR', r'\bEUR\b|euros'), ('GBP', r'\bGBP\b|pounds sterling')]
    found = [unit for unit, pat in patterns if re.search(pat, text, re.I)]
    return found[0] if len(found) == 1 else hint if not found and re.fullmatch(r'[A-Z]{3}', hint or '') else None
def scale_in(text):
    if re.search(r'(?:in|amounts? in|expressed in)\s+millions', text, re.I): return 1_000_000
    if re.search(r'(?:in|amounts? in|expressed in)\s+thousands|\(000s?\)|\$[’\']000', text, re.I): return 1_000
    return 1
MONTHS = {name.lower(): i for i, name in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}
DATE_RE = re.compile(r'(' + '|'.join(MONTHS) + r')\s+(\d{1,2}),?\s+(20\d{2})', re.I)
def dates_in(text):
    out = []
    for m in DATE_RE.finditer(text):
        try: out.append(date(int(m[3]), MONTHS[m[1].lower()], int(m[2])).isoformat())
        except ValueError: pass
    out.extend(re.findall(r'\b20\d{2}-\d{2}-\d{2}\b', text))
    return list(dict.fromkeys(out))
def start_for(end, context):
    durations = [('three', 3), ('six', 6), ('nine', 9), ('twelve', 12)]
    context=context.replace('-',' ')
    options = [n for word, n in durations if re.search(r'\b(?:' + word + '|' + str(n) + r')\s+months?(?:\s+period)?\s+ended', context, re.I)]
    if len(set(options))>1:return None
    months = options[0] if options else None
    if months is None and re.search(r'(?:year|years|annual)\s+ended', context, re.I): months = 12
    if months is None: return None
    d = date.fromisoformat(end)
    # Only complete month periods. Irregular fiscal calendars require XBRL/review.
    import calendar
    if d.day != calendar.monthrange(d.year, d.month)[1]: return None
    index = d.year * 12 + d.month - months
    return date(index // 12, index % 12 + 1, 1).isoformat()


class FilingHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts, self.units, self.inline, self.tables = {}, {}, [], []
        self.ctx = self.unit = self.fact = self.capture = None
        self.skip = 0; self.recent = ''; self.table = None; self.row = None; self.cell = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); local = tag.split(':')[-1].lower()
        if local in {'script','style','exclude','sup'}: self.skip += 1
        if self.skip: return
        if local == 'context': self.ctx = {'id': a.get('id'), 'dimensions': 0}
        elif self.ctx is not None and local in {'identifier','startdate','enddate','instant'}: self.capture = [local, '']
        elif self.ctx is not None and local in {'segment','scenario'}: self.ctx['dimensions'] += 1
        elif local == 'unit': self.unit = {'id': a.get('id'), 'measures': []}
        elif self.unit is not None and local == 'measure': self.capture = ['measure', '']
        elif local in {'nonfraction','nonnumeric'} and tag.startswith('ix:'): self.fact = {**a, 'text':'', 'inline_type':local}
        if local == 'table' and self.table is None: self.table = {'context':self.recent[-1800:], 'rows':[]}
        elif local == 'tr' and self.table is not None: self.row = []
        elif local in {'td','th'} and self.row is not None: self.cell = {'text':'', 'colspan':min(12, max(1, int(a.get('colspan','1')) if a.get('colspan','1').isdigit() else 1))}
    def handle_data(self, data):
        if self.skip: return
        self.recent = (self.recent + ' ' + data)[-3000:]
        if self.capture is not None: self.capture[1] += data
        if self.fact is not None: self.fact['text'] += data
        if self.cell is not None: self.cell['text'] += ' ' + data
    def handle_endtag(self, tag):
        local = tag.split(':')[-1].lower()
        if local in {'script','style','exclude','sup'} and self.skip: self.skip -= 1; return
        if self.skip: return
        if self.capture is not None and self.capture[0] == local:
            key, val = self.capture
            if key == 'measure' and self.unit is not None: self.unit['measures'].append(val.strip().split(':')[-1])
            elif self.ctx is not None: self.ctx[key] = val.strip()
            self.capture = None
        if local == 'context' and self.ctx is not None: self.contexts[self.ctx['id']] = self.ctx; self.ctx = None
        if local == 'unit' and self.unit is not None: self.units[self.unit['id']] = '/'.join(self.unit['measures']); self.unit = None
        if self.fact is not None and local == self.fact['inline_type']:
            self.inline.append(self.fact); self.fact = None
        if local in {'td','th'} and self.cell is not None and self.row is not None:
            self.row.append(self.cell); self.cell = None
        if local == 'tr' and self.row is not None and self.table is not None: self.table['rows'].append(self.row); self.row = None
        if local == 'table' and self.table is not None: self.tables.append(self.table); self.table = None


def make_fact(meta, metric, value, start, end, currency, locator, kind, **extra):
    return {k: meta.get(k) for k in ['cik','form','filed','published_at','observed_at','source_url','source_sha256']} | {'metric':metric,'value':value,'start':start,'end':end,'currency':currency,'locator':locator,'kind':kind,'scope':'consolidated','confidence':'verified','explicit_zero':value == 0, **extra}


def economic_sign(metric,value,label):
    label=clean(label)
    negative=(metric=='cfo' and label in {'net cash used in operating activities','cash used in operating activities'}) or (metric=='net_income' and label in {'net loss','net loss for the period','loss for the period'})
    return -abs(value) if negative else value


def extract_html(text, meta, labels=None):
    parser = FilingHTML(); parser.feed(text)
    facts, candidates, issues = [], [], []
    for row in parser.inline:
        if row.get('inline_type') != 'nonfraction': continue
        tag = row.get('name',''); caption=(labels or {}).get(tag.split(':')[-1]);metric = metric_for(tag.split(':')[-1]) or metric_for(caption or '')
        if not metric: continue
        ctx = parser.contexts.get(row.get('contextref'), {}); unit = parser.units.get(row.get('unitref'))
        if ctx.get('dimensions') or str(ctx.get('identifier','')).lstrip('0') != str(meta['cik']).lstrip('0'): continue
        if not re.fullmatch(r'[A-Z]{3}', unit or ''): continue
        end, start = ctx.get('instant') or ctx.get('enddate'), ctx.get('startdate')
        if not end or (metric in FLOW) != bool(start): continue
        raw = row['text']; fmt = row.get('format','').lower()
        if 'commadecimal' in fmt or 'comma-decimal' in fmt: raw = raw.replace('.', '').replace(',', '.')
        value = numeric(raw)
        try:
            exponent = int(row.get('scale',0))
            if abs(exponent) > 12: continue
            if value is not None: value *= 10 ** exponent
            if value is not None and row.get('sign') == '-': value = -abs(value)
        except (ValueError, OverflowError): continue
        if value is None or not math.isfinite(value): continue
        value=economic_sign(metric,value,caption or tag.split(':')[-1])
        facts.append(make_fact(meta,metric,value,start,end,unit,'iXBRL '+tag+' context '+row.get('contextref',''), 'inline_xbrl',original_tag=tag))
    for number, table in enumerate(parser.tables):
        context = table['context']; rows = table['rows']
        if re.search(r'pro\s*forma|acquired business|parent.company.only|segment information', context[-1000:], re.I):
            issues.append({'reason':'non_consolidated_or_pro_forma_table','table':number+1}); continue
        if not re.search(r'\bconsolidated\s+(?:balance\s+sheets?|statements?\s+of\s+(?:cash\s+flows?|operations|income|comprehensive\s+(?:income|loss)|financial\s+position|profit|loss))',context,re.I):
            issues.append({'reason':'table_consolidation_scope_requires_review','table':number+1}); continue
        grid = []
        for row in rows:
            expanded=[]
            for cell in row: expanded.extend([re.sub(r'\s+',' ',cell['text']).strip()] * cell['colspan'])
            grid.append(expanded)
        if not grid: continue
        first_metric = next((i for i,r in enumerate(grid) if r and metric_for(r[0])),len(grid))
        headers=grid[:first_metric]; heading=' '.join(' '.join(r) for r in headers)
        table_context=context+' '+heading
        currency=currency_in(table_context,meta.get('currency_hint')); scale=scale_in(table_context)
        if not currency:
            issues.append({'reason':'currency_unresolved','table':number+1}); continue
        ends={}
        width=max(map(len,grid))
        for col in range(1,width):
            colheader=' '.join(r[col] for r in headers if col<len(r)); ends_here=dates_in(colheader)
            if len(ends_here)==1: ends[col]=ends_here[0]; continue
            years=re.findall(r'\b(20\d{2})\b',colheader)
            monthday=re.search(r'('+'|'.join(MONTHS)+r')\s+(\d{1,2})',heading,re.I)
            if not monthday:
                alternatives=list(re.finditer(r'('+'|'.join(MONTHS)+r')\s+(\d{1,2})',context,re.I));monthday=alternatives[-1] if alternatives else None
            if len(set(years))==1 and monthday:
                try: ends[col]=date(int(years[0]),MONTHS[monthday[1].lower()],int(monthday[2])).isoformat()
                except ValueError: pass
        if not ends:
            issues.append({'reason':'comparative_period_columns_unresolved','table':number+1}); continue
        # Currency symbols are often standalone cells. Use numeric columns only,
        # and inherit a header date only across an explicitly empty/symbol cell.
        for index,row in enumerate(grid[first_metric:], first_metric):
            if not row: continue
            metric=metric_for(row[0])
            if not metric: continue
            for col,end in ends.items():
                if col>=len(row): continue
                value=numeric(row[col]); selected=col
                if value is None and row[col] in {'$','US$','RMB',''} and col+1<len(row) and col+1 not in ends: value=numeric(row[col+1]); selected=col+1
                if value is None: continue
                colheader=' '.join(r[col] for r in headers if col<len(r))
                column_duration=bool(re.search(r'months?|years?|annual',colheader,re.I))
                start=start_for(end,colheader if column_duration else table_context) if metric in FLOW else None
                if metric in FLOW and not start:
                    issues.append({'reason':'flow_duration_unresolved','table':number+1,'metric':metric}); continue
                if metric in {'cfo','net_income','operating_income'} and re.search(r'\b(?:used|loss)\b',row[0],re.I) and not re.search(r'provided.*used|used.*provided|income.*loss|loss.*income|profit.*loss|loss.*profit',row[0],re.I): value=-abs(value)
                raw_value=str(row[selected]); places=len(raw_value.split('.')[-1].strip(')')) if '.' in raw_value else 0
                facts.append(make_fact(meta,metric,value*scale,start,end,currency,f'HTML table {number+1}, row {index+1}, column {selected+1}: {row[0]}','html_table',rounding_tolerance=scale*.5*10**(-places),original_label=row[0]))
    return facts,candidates,issues


def extract_xbrl(text,meta,labels=None):
    match=re.search(r'<(?:[A-Za-z0-9_]+:)?xbrl\b[\s\S]*?</(?:[A-Za-z0-9_]+:)?xbrl>',text,re.I)
    if not match:return []
    try:root=ET.fromstring(match[0])
    except ET.ParseError:return []
    local=lambda tag:tag.rsplit('}',1)[-1].split(':')[-1]
    contexts,units={},{}
    for node in root:
        name=local(node.tag)
        if name=='context':
            data={local(n.tag):n.text for n in node.iter() if local(n.tag) in {'identifier','startDate','endDate','instant'}}
            data['dimensioned']=any(local(n.tag) in {'segment','scenario','explicitMember','typedMember'} for n in node.iter());contexts[node.get('id')]=data
        if name=='unit':units[node.get('id')]=[n.text.split(':')[-1] for n in node.iter() if local(n.tag)=='measure' and n.text]
    facts=[]
    for node in root:
        name=local(node.tag);label=(labels or {}).get(name);metric=metric_for(name) or metric_for(label or '')
        if not metric:continue
        ctx=contexts.get(node.get('contextRef'),{});unit=units.get(node.get('unitRef'),[])
        if ctx.get('dimensioned') or str(ctx.get('identifier','')).lstrip('0')!=str(meta['cik']).lstrip('0') or len(unit)!=1 or not re.fullmatch(r'[A-Z]{3}',unit[0]):continue
        start,end=ctx.get('startDate'),ctx.get('instant') or ctx.get('endDate');value=numeric(node.text or '')
        if not end or value is None or (metric in FLOW)!=bool(start):continue
        facts.append(make_fact(meta,metric,economic_sign(metric,value,label or name),start,end,unit[0],'XBRL '+name+' context '+node.get('contextRef',''),'inline_xbrl',original_tag=node.tag))
    return facts


def extract_labels(text):
    # Only exact recognized labels are mapped. Unknown company concepts stay
    # reviewable; no loose substring matching of unrelated financial items.
    labels={}
    namespaces=' '.join(dict.fromkeys(re.findall(r'xmlns:[\w.-]+=["\'][^"\']+["\']',text)))
    for match in re.finditer(r'<(?:\w+:)?labelLink\b[\s\S]*?</(?:\w+:)?labelLink>',text,re.I):
        try:root=ET.fromstring('<wrapper '+namespaces+'>'+match[0]+'</wrapper>')[0]
        except ET.ParseError:continue
        attr=lambda n,k:next((v for a,v in n.attrib.items() if a.rsplit('}',1)[-1].split(':')[-1]==k),None)
        locs={attr(n,'label'):attr(n,'href') for n in root if n.tag.rsplit('}',1)[-1].split(':')[-1]=='loc'}
        resources={attr(n,'label'):(n.text or '') for n in root if n.tag.rsplit('}',1)[-1].split(':')[-1]=='label' and metric_for(n.text or '')}
        for n in root:
            if n.tag.rsplit('}',1)[-1].split(':')[-1]!='labelArc':continue
            href=locs.get(attr(n,'from'));label=resources.get(attr(n,'to'))
            if href and label:
                name=href.split('#')[-1].split('_',1)[-1];labels[name]=label
    return labels


def extract_pdf(raw, meta):
    import pymupdf
    facts,candidates,issues=[],[],[]
    with pymupdf.open(stream=raw,filetype='pdf') as doc:
        if doc.page_count>120: issues.append({'reason':'pdf_page_limit','pages':doc.page_count})
        for n in range(min(doc.page_count,120)):
            page=doc[n]; text=page.get_text()
            ocr=False
            if len(text.strip())<40:
                try:
                    tp=page.get_textpage_ocr(language='eng',dpi=180,full=True);text=page.get_text(textpage=tp);ocr=True
                except Exception:
                    issues.append({'reason':'ocr_unavailable_or_failed','page':n+1});continue
            if not re.search(r'cash flows|balance sheets|financial position|statements of operations|income statement|profit.*loss',text,re.I):continue
            try: tables=page.find_tables().tables if not ocr else []
            except Exception: tables=[]
            if not tables:
                # Preserve OCR/text evidence for explicit review; never guess
                # the ordering of multi-column PDF financial values.
                candidates.append({'kind':'ocr' if ocr else 'pdf_text','page':n+1,'text':text[:14000],'reason':'financial_table_needs_review'});continue
            for table in tables:
                cells=table.extract();html='<h2>'+unescape(text[:800])+'</h2><table>'+''.join('<tr>'+''.join('<td>'+unescape(str(c or ''))+'</td>' for c in row)+'</tr>' for row in cells)+'</table>'
                found,_,problems=extract_html(html,meta)
                for r in found:r['locator']=f'PDF page {n+1}; '+r['locator'];r['kind']='pdf_table'
                facts.extend(found);issues.extend(problems)
    return facts,candidates,issues


def extract_document(raw, meta):
    if len(raw)>64_000_000: raise ValueError('Financial document exceeds size limit')
    if not re.fullmatch(r'\d{1,10}',str(meta.get('cik',''))):raise ValueError('Expected issuer identity required')
    if not re.fullmatch(r'[a-f0-9]{64}',meta.get('source_sha256','')):meta={**meta,'source_sha256':hashlib.sha256(raw).hexdigest()}
    if meta.get('require_company_identity'):
        identity=re.sub(r'[^a-z0-9]','',str(meta.get('company','')).lower())
        if raw[:5]==b'%PDF-':
            import pymupdf
            with pymupdf.open(stream=raw,filetype='pdf') as proof: identity_text=' '.join(proof[n].get_text() for n in range(min(3,proof.page_count)))
        else:identity_text=re.sub(r'<[^>]+>',' ',raw[:100000].decode('utf-8',errors='replace'))
        if not identity or identity not in re.sub(r'[^a-z0-9]','',unescape(identity_text).lower()):
            return {'schema':VERSION,'facts':[],'candidates':[],'issues':[{'reason':'issuer_IR_document_identity_requires_review'}]}
    if raw[:5]==b'%PDF-':facts,candidates,issues=extract_pdf(raw,meta)
    else:
        text=raw.decode('utf-8',errors='replace')
        if re.search(r'<!ENTITY|<!DOCTYPE[^>]*\[',text,re.I):raise ValueError('External entities are prohibited')
        header=re.search(r'CENTRAL INDEX KEY:\s*(\d+)',text,re.I)
        if header and int(header[1])!=int(meta['cik']):return {'schema':VERSION,'facts':[],'candidates':[],'issues':[{'reason':'filing_header_issuer_mismatch'}]}
        documents=re.findall(r'<DOCUMENT>([\s\S]*?)</DOCUMENT>',text,re.I)
        facts,candidates,issues=[],[],[]
        labels=extract_labels(text)
        for part in documents[:80] if documents else [text]:
            kind=re.search(r'<TYPE>\s*([^\r\n<]+)',part,re.I)
            if kind and not re.match(r'(?:10-[KQ]|20-F|40-F|6-K|8-K|EX-99|EX-101.INS)',kind[1]):continue
            f,c,i=extract_html(part,meta,labels);facts.extend(f);facts.extend(extract_xbrl(part,meta,labels));candidates.extend(c);issues.extend(i)
    unique={json.dumps([f['metric'],f['start'],f['end'],f['currency'],f['value'],f['locator']]):f for f in facts}
    if len(unique)>5000:raise ValueError('Financial fact count limit')
    return {'schema':VERSION,'facts':list(unique.values()),'candidates':candidates[:50],'issues':issues[:100]}


if __name__=='__main__':
    payload=json.loads(sys.stdin.buffer.read(90_000_001))
    raw=base64.b64decode(payload['base64'],validate=True)
    print(json.dumps(extract_document(raw,payload['meta']),allow_nan=False))
