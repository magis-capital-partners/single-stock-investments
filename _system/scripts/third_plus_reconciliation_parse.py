#!/usr/bin/env python3
"""Extract filing-context facts without relying on SEC companyfacts tag coverage."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from lxml import html
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'_system/data/reverse_splits/local/third_plus_signal_study/reconciliation'
KEEP=re.compile(r'Cash|OperatingActivities|(?:Common|Ordinary).*Shares(?:Outstanding|Issued)|EntityCommonStockSharesOutstanding|^(?:Assets|Liabilities|StockholdersEquity|Revenues|RevenueFromContractWithCustomerExcludingAssessedTax|NetIncomeLoss|ProfitLoss)$',re.I)
def local(tag):
    return str(tag).split('}')[-1].split(':')[-1].lower()
def clean(text):
    return re.sub(r'\s+',' ',text or '').strip()
def value(text,attrs):
    if any(local(k)=='nil' and v.lower()=='true' for k,v in attrs.items()): return None
    fmt=attrs.get('format','').lower()
    text=clean(text).replace('\u2212','-').replace('\u2013','-').replace('\u00a0','')
    if text in ('-','—',''):
        if 'zero' in fmt or text in ('-','—'): return 0.0
        return None
    negative=text.startswith('(') and text.endswith(')')
    if negative: text=text[1:-1]
    text=text.replace(',','').replace(' ','').replace('$','').replace('%','')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',text): return None
    answer=float(text)*10**int(attrs.get('scale','0'))
    if attrs.get('sign')=='-' or negative: answer=-abs(answer)
    return answer

def primary_document(text,form=None):
    if '<SEC-DOCUMENT>' not in text[:1000]: return text
    documents=re.findall(r'<DOCUMENT>\s*(.*?)</DOCUMENT>',text,re.S|re.I)
    for doc in documents:
        typ=re.search(r'<TYPE>([^\r\n]+)',doc,re.I)
        if typ and (not form or typ.group(1).strip()==form):
            body=re.search(r'<TEXT>\s*(.*?)</TEXT>',doc,re.S|re.I)
            if body:return body.group(1)
    return text

def parse_document(text,cik,accession,form=None):
    primary=primary_document(text,form)
    tree=html.document_fromstring(primary.encode('utf-8'),parser=html.HTMLParser(encoding='utf-8'))
    nodes=list(tree.iter())
    contexts={}; units={}
    for n in nodes:
        if local(n.tag)=='context':
            fields={};dimensions=[];identifier=None
            for p in n.iter():
                tag=local(p.tag)
                if tag in ('instant','startdate','enddate'):fields[tag]=clean(''.join(p.itertext()))
                if tag=='identifier':identifier=clean(''.join(p.itertext()))
                if tag in ('explicitmember','typedmember'):dimensions.append({'axis':p.get('dimension'),'member':clean(''.join(p.itertext()))})
            contexts[n.get('id')]={**fields,'dimensions':dimensions,'identifier':identifier}
        elif local(n.tag)=='unit':
            units[n.get('id')]=[clean(''.join(p.itertext())).split(':')[-1] for p in n.iter() if local(p.tag)=='measure']
    facts=[];non_numeric={}
    for n in nodes:
        tag=local(n.tag)
        if tag=='nonnumeric':
            name=n.get('name','')
            if name.split(':')[-1] in ('DocumentPeriodEndDate','DocumentType','EntityRegistrantName','DocumentFiscalYearFocus'):
                non_numeric[name.split(':')[-1]]=clean(''.join(n.itertext()))
        if tag!='nonfraction':continue
        name=n.get('name','');short=name.split(':')[-1]
        if not KEEP.search(short):continue
        context=contexts.get(n.get('contextref'))
        if not context:continue
        identifier=context.get('identifier')
        try:
            if identifier and int(identifier)!=int(cik):continue
        except ValueError:continue
        amount=value(''.join(n.itertext()),dict(n.attrib))
        if amount is None:continue
        unit=units.get(n.get('unitref'),[])
        facts.append({'tag':name,'value':amount,'start':context.get('startdate'),'end':context.get('instant') or context.get('enddate'),
                      'unit':unit[0] if len(unit)==1 else '/'.join(unit),'dimensions':context['dimensions'],'context_id':n.get('contextref'),
                      'fact_id':n.get('id'),'row_label':next((clean(' '.join(p.itertext()))[:1400] for p in n.iterancestors() if local(p.tag)=='tr'),None),'decimals':n.get('decimals'),'accession':accession,'cik':int(cik)})
    # An untagged dash is a zero only when its table column has a unique,
    # repeatedly established duration context. Blank layout cells are never facts.
    from collections import Counter
    from datetime import date
    for tr in [n for n in nodes if local(n.tag)=='tr']:
        tagged=[n for n in tr.iter() if local(n.tag)=='nonfraction' and ('OperatingActivities' in n.get('name','') or 'OperatingCashFlows' in n.get('name',''))]
        if not tagged:continue
        table=next((n for n in tr.iterancestors() if local(n.tag)=='table'),None)
        if table is None:continue
        cells=[n for n in tr if local(n.tag) in ('td','th')]
        if not cells:continue
        def column(cell,row):
            answer=0
            for child in row:
                if child is cell:return answer
                if local(child.tag) in ('td','th'):answer+=int(child.get('colspan','1'))
            return -1
        observed={}
        for other in table.iter():
            if local(other.tag)!='nonfraction':continue
            context=contexts.get(other.get('contextref'),{})
            if not context.get('startdate') or context.get('dimensions'):continue
            row=next((n for n in other.iterancestors() if local(n.tag)=='tr'),None)
            cell=next((n for n in other.iterancestors() if local(n.tag) in ('td','th')),None)
            if row is not None and cell is not None:observed.setdefault(column(cell,row),Counter())[other.get('contextref')]+=1
        for reference in tagged:
            name=reference.get('name');rc=contexts.get(reference.get('contextref'),{})
            if not rc.get('startdate') or rc.get('dimensions'):continue
            duration=(date.fromisoformat(rc['enddate'])-date.fromisoformat(rc['startdate'])).days
            for cell in cells:
                literal=clean(''.join(cell.itertext()))
                if literal not in ('-','—','–'):continue
                candidates=[]
                for key,count in observed.get(column(cell,tr),{}).items():
                    ctx=contexts[key];days=(date.fromisoformat(ctx['enddate'])-date.fromisoformat(ctx['startdate'])).days
                    if abs(days-duration)>20 or abs((date.fromisoformat(ctx['enddate'])-date.fromisoformat(rc['enddate'])).days)>390:continue
                    candidates.append((count,key))
                candidates.sort(reverse=True)
                if not candidates or candidates[0][0]<2 or (len(candidates)>1 and candidates[0][0]==candidates[1][0]):continue
                key=candidates[0][1];ctx=contexts[key]
                if any(f['tag']==name and f['context_id']==key for f in facts):continue
                unit=units.get(reference.get('unitref'),[])
                facts.append({'tag':name,'value':0.0,'start':ctx['startdate'],'end':ctx['enddate'],'unit':unit[0] if len(unit)==1 else '/'.join(unit),
                              'dimensions':[],'context_id':key,'fact_id':None,'decimals':'INF','accession':accession,'cik':int(cik),
                              'row_label':clean(' '.join(tr.itertext()))[:1400],'derived_from_literal_zero_cell':True,
                              'zero_locator':tree.getroottree().getpath(cell)})
    # Recover literal share counts in a balance-sheet caption when no standard
    # numeric tag exists. The sentence must explicitly say issued AND outstanding.
    month=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    date_re=month+r'\s+\d{1,2},?\s+\d{4}'
    from datetime import datetime
    def iso_date(s):return datetime.strptime(s.replace(',',''),'%B %d %Y').date().isoformat()
    for tr in [n for n in nodes if local(n.tag)=='tr']:
        caption=clean(' '.join(tr.itertext()))
        if len(caption)>900 or not re.search(r'common stock',caption,re.I) or not re.search(r'issued and outstanding',caption,re.I):continue
        pair=re.search(r'(\d[\d,]*)\s+and\s+(\d[\d,]*)\s+(?:Class\s+([AB])\s+)?shares issued and outstanding',caption,re.I)
        dated=re.search(r'(\d[\d,]*)\s+shares issued and outstanding at\s+('+date_re+r')\s+and\s+(\d[\d,]*)\s+at\s+('+date_re+r')',caption,re.I)
        values=[]
        if dated:values=[(int(dated.group(1).replace(',','')),iso_date(dated.group(2))),(int(dated.group(3).replace(',','')),iso_date(dated.group(4))) ]
        elif pair:
            dates=re.findall(date_re,caption)
            if len(dates)<2:
                table=next((n for n in tr.iterancestors() if local(n.tag)=='table'),None)
                dates=re.findall(date_re,clean(' '.join(table.itertext()))[:500]) if table is not None else []
            if len(dates)>=2:values=[(int(pair.group(1).replace(',','')),iso_date(dates[0])),(int(pair.group(2).replace(',','')),iso_date(dates[1]))]
        dims=[]
        klass=re.search(r'Class\s+([AB])',caption,re.I)
        if klass:dims=[{'axis':'us-gaap:StatementClassOfStockAxis','member':'us-gaap:CommonClass'+klass.group(1).upper()+'Member'}]
        for amount,end in values:
            if any(f['tag'].split(':')[-1]=='CommonStockSharesOutstanding' and f['end']==end and f['value']==amount and f['dimensions']==dims for f in facts):continue
            facts.append({'tag':'caption:CommonStockSharesOutstanding','value':amount,'start':None,'end':end,'unit':'shares','dimensions':dims,
                          'context_id':'literal_caption_'+end,'fact_id':None,'decimals':'INF','accession':accession,'cik':int(cik),
                          'row_label':caption,'derived_from_explicit_issued_and_outstanding_caption':True,'caption_locator':tree.getroottree().getpath(tr)})
    # Keep prose/table order and decimal points; never split transactions at a decimal.
    for n in list(tree.xpath('//script|//style')):n.drop_tree()
    paragraphs=[]
    for n in tree.iter():
        if local(n.tag) in ('p','tr','div'):
            if local(n.tag)=='div' and any(local(x.tag) in ('p','tr','div') for x in n):continue
            t=clean(' '.join(n.itertext()))
            if len(t)>35:paragraphs.append(t)
    alltext=clean(' '.join(tree.itertext()))
    return {'cik':int(cik),'accession':accession,'metadata':non_numeric,'facts':facts,'paragraphs':list(dict.fromkeys(paragraphs)),
            'text':alltext,'parser_version':'original_inline_contexts.v6'}

def main():
    arg=argparse.ArgumentParser();arg.add_argument('--manifest',type=Path,default=WORK/'filing_manifest.local.json');a=arg.parse_args()
    manifest=json.loads(a.manifest.read_text(encoding='utf-8'));target=WORK/'parsed';target.mkdir(exist_ok=True)
    stats={'parsed':0,'cached':0,'failures':[],'no_inline_facts':[]}
    for r in manifest:
        if r['status']!='ok':continue
        out=target/(r['accession'].replace('-','')+'.json')
        if out.exists():
            prior=json.loads(out.read_text(encoding='utf-8'))
            if prior.get('source_sha256')==r['sha256'] and prior.get('parser_version')=='original_inline_contexts.v6':stats['cached']+=1;continue
        try:
            source=ROOT/r['file'];b=source.read_bytes()
            if hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Source hash mismatch')
            result=parse_document(b.decode('utf-8',errors='replace'),r['cik'],r['accession'],r.get('form'))
            result.update({'source_sha256':r['sha256'],'source_url':r['url'],'filed_at':r.get('filed_at'),'accepted_at':r.get('accepted_at'),'form':r.get('form')})
            out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');stats['parsed']+=1
            if not result['facts']:stats['no_inline_facts'].append(r['accession'])
        except Exception as e:stats['failures'].append({'accession':r['accession'],'error':str(e)})
    (WORK/'parse_status.local.json').write_text(json.dumps(stats,indent=2));print(json.dumps(stats))
if __name__=='__main__':main()
