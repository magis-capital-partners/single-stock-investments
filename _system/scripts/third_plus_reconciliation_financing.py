#!/usr/bin/env python3
"""Exhaustive source extraction. Leads and actual reviewed deals stay distinct."""
from __future__ import annotations
import gzip,hashlib,json,re
from pathlib import Path
from lxml import html
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'_system/data/reverse_splits/local/third_plus_signal_study/reconciliation'
VERSION='financing_primary_and_press_release.v3'
def clean(t):return re.sub(r'\s+',' ',t or '').strip()
def pieces(raw,form,kind):
    documents=re.findall(r'<DOCUMENT>\s*(.*?)</DOCUMENT>',raw,re.S|re.I)
    if not documents:return [(kind,raw)]
    result=[]
    for d in documents:
        typ=re.search(r'<TYPE>([^\r\n]+)',d,re.I)
        if not typ:continue
        typ=typ.group(1).strip()
        if typ==form or typ.startswith('EX-99'):
            body=re.search(r'<TEXT>\s*(.*?)</TEXT>',d,re.S|re.I)
            if body:result.append((typ,body.group(1)))
    return result

def paragraphs(raw):
    tree=html.document_fromstring(raw.encode('utf-8'),parser=html.HTMLParser(encoding='utf-8'))
    for n in tree.xpath('//script|//style'):n.drop_tree()
    result=[]
    for n in tree.iter():
        if str(n.tag).lower() not in ('p','div'):continue
        if any(str(c.tag).lower() in ('p','div','table') for c in n):continue
        t=clean(' '.join(n.itertext()))
        if len(t)>40:result.append(t)
    alltext=clean(' '.join(tree.itertext()))
    if alltext:result.append(alltext)
    return list(dict.fromkeys(result))

def money(text):
    result=[]
    for m in re.finditer(r'(?:(?:US|U\.S\.)\s*)?\$\s*(\d[\d,]*(?:\.\d+)?)\s*(million|billion|thousand)?',text,re.I):
        val=float(m.group(1).replace(',',''))*{'million':1e6,'billion':1e9,'thousand':1e3}.get((m.group(2) or '').lower(),1)
        before=text[max(0,m.start()-100):m.start()].lower()
        classification='other_or_unit_price'
        if re.search(r'net (?:cash )?proceeds[^.;]{0,70}$',before):classification='net_proceeds'
        elif re.search(r'gross proceeds[^.;]{0,70}$',before):classification='gross_proceeds'
        elif re.search(r'(?:aggregate (?:purchase|offering) price|aggregate proceeds|proceeds)[^.;]{0,60}$',before):classification='proceeds_scope_requires_review'
        if m.group(2) and float(m.group(1).replace(',',''))>=1e6:
            result.append({'value':None,'raw_arithmetic_value':val,'classification':'inconsistent_numeric_scale_requires_review','offset':m.start(),'literal':m.group(0)})
        else:
            if re.search(r'fees?|reimburs|expenses?',before) and classification=='gross_proceeds':classification='scope_requires_review'
            result.append({'value':val,'classification':classification,'offset':m.start(),'literal':m.group(0)})
    return result

def extract(text):
    equity=re.compile(r'common (?:stock|shares)|ordinary shares|pre.?funded|convertible (?:note|preferred|debt)|warrants|equity line|at.the.market',re.I)
    economics=re.compile(r'clos(?:ed|ing)|complet(?:ed|ion)|issued|sold|received|proceeds|entered|purchase agreement|financing',re.I)
    result=[]
    # Sentences split at whitespace after punctuation, never at a decimal point.
    sentences=re.split(r'(?<=[.;!?])\s+(?=[A-Z(“"\d])',text)
    for i,s in enumerate(sentences):
        window=' '.join(sentences[max(0,i-1):min(len(sentences),i+2)])
        if not equity.search(window) or not economics.search(s):continue
        if len(s)>5500:continue
        closed=bool(re.search(r'(?:the Company|we|Company|offering|placement|transaction|financing|sale)\s+(?:has |have |had |successfully )?(?:closed|completed|consummated)|(?:closed|completed|consummated)\s+(?:the |a |an |its )?(?:offering|sale|registered direct|public offering|private placement|financing)|(?:offering|sale|placement|transaction|financing)\s+(?:was |were )?(?:closed|completed)',s,re.I))
        closed=closed or bool(re.search(r'(?:closing of (?:the )?(?:offering|placement|financing|transaction)).{0,70}(?:occurred|was completed)|(?:parties|Company|we) (?:held|consummated) (?:an |the )?(?:additional |second |third |fourth )?closing',s,re.I))
        prospective=bool(re.search(r'(?:expects?|expected|will|anticipated|scheduled|intends?|subject to)[^.;]{0,110}(?:clos(?:e|ed|ing)|complet(?:e|ed|ion))|(?:upon|at|following|on)\s+(?:the )?(?:first |initial |final )?closing',s,re.I))
        actual_issuance=bool(re.search(r'(?:issued and sold|sold an aggregate|sold a total|received (?:net |gross )?proceeds|raised (?:gross |net )?proceeds)',s,re.I))
        actual_text=re.sub(r'(?:will|shall|may|would|are to)\s+(?:be\s+)?(?:issued and sold|issued|sold)','',s,flags=re.I)
        actual_issuance=bool(re.search(r'(?:issued and sold|sold an aggregate|sold a total|received (?:net |gross )?proceeds|raised (?:gross |net )?proceeds)',actual_text,re.I))
        if re.search(r'(?:if|in the event)[^.;]{0,100}(?:Company|we) (?:completed|consummated)',s,re.I):prospective=True
        status='explicit_completion_candidate' if closed and not prospective else 'actual_sale_or_cash_receipt_candidate' if actual_issuance and not prospective else 'terms_or_other_context'
        result.append({'sentence':s,'context':window[:7000],'completion_evidence':closed,'prospective_language':prospective,'state':status,'amounts':money(window),
                       'dates':re.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',window),
                       'share_quantities':[{'quantity':int(m.group(1).replace(',','')),'literal':m.group(0)} for m in re.finditer(r'(\d[\d,]*)\s+(?:shares of (?:its |our |the Company.s )?(?:common stock|ordinary shares)|common shares|ordinary shares)',window,re.I)]})
    return result

def main():
    manifest=json.loads((WORK/'financing_source_manifest.local.json').read_text(encoding='utf-8'))
    target=WORK/'financing_parsed';target.mkdir(exist_ok=True)
    stats={'documents':0,'sources':0,'cached':0,'parsed':0,'failures':[],'explicit_completion_documents':0,'sale_or_receipt_documents':0}
    for r in manifest:
        if r['status']!='ok':continue
        out=target/(r['accession'].replace('-','')+'.json')
        fingerprint=hashlib.sha256(json.dumps([s['sha256'] for s in r['sources']]).encode()).hexdigest()
        if out.exists():
            old=json.loads(out.read_text(encoding='utf-8'))
            if old.get('version')==VERSION and old.get('source_fingerprint')==fingerprint:
                stats['cached']+=1;stats['documents']+=1;stats['sources']+=len(r['sources'])
                stats['explicit_completion_documents']+=old['explicit_completion_candidates']>0
                stats['sale_or_receipt_documents']+=old['actual_sale_or_receipt_candidates']>0
                continue
        try:
            parts=[]
            for source in r['sources']:
                data=(ROOT/source['file']).read_bytes()
                if source.get('compression')=='gzip':data=gzip.decompress(data)
                if hashlib.sha256(data).hexdigest()!=source['sha256']:raise ValueError('Source hash mismatch')
                raw=data.decode('utf-8',errors='replace')
                for kind,body in pieces(raw,r['form'],source['kind']):
                    paras=paragraphs(body);claims=[]
                    for index,paragraph in enumerate(paras):
                        for claim in extract(paragraph):claims.append({**claim,'paragraph_index':index,'locator':'paragraph['+str(index)+']'})
                    claims=list({c['sentence']:c for c in claims}.values())
                    parts.append({'kind':kind,'url':source['url'],'source_sha256':source['sha256'],'paragraphs':paras,'claims':claims})
                stats['sources']+=1
            claims=[c for p in parts for c in p['claims']]
            result={'version':VERSION,'accession':r['accession'],'cik':r['cik'],'filed_at':r['filed_at'],'accepted_at':r.get('accepted_at'),'form':r['form'],'source_fingerprint':fingerprint,
                    'parts':parts,'explicit_completion_candidates':sum(c['state']=='explicit_completion_candidate' for c in claims),
                    'actual_sale_or_receipt_candidates':sum(c['state']=='actual_sale_or_cash_receipt_candidate' for c in claims),
                    'independent_review_complete':False,'transaction_reconciled':False}
            out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            stats['explicit_completion_documents']+=result['explicit_completion_candidates']>0
            stats['sale_or_receipt_documents']+=result['actual_sale_or_receipt_candidates']>0
            stats['documents']+=1;stats['parsed']+=1
        except Exception as e:stats['failures'].append({'accession':r['accession'],'error':str(e)})
        if (stats['parsed']+len(stats['failures']))%50==0:print('Parsed financing reports '+str(stats['parsed'])+'/'+str(len(manifest)),flush=True)
    (WORK/'financing_parse_status.local.json').write_text(json.dumps(stats,indent=2),encoding='utf-8');print(json.dumps(stats))
if __name__=='__main__':main()
