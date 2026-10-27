#!/usr/bin/env python3
"""Source evidence for fees, cash allocations and capital terms; never assume fees are zero."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from third_plus_reconciliation_financing import paragraphs
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'_system/data/reverse_splits/local/third_plus_signal_study/reconciliation'
def parts(raw,form):
    out=[]
    for d in re.findall(r'<DOCUMENT>\s*(.*?)</DOCUMENT>',raw,re.S|re.I):
        typ=re.search(r'<TYPE>([^\r\n]+)',d,re.I);name=re.search(r'<FILENAME>([^\r\n]+)',d,re.I);body=re.search(r'<TEXT>\s*(.*?)</TEXT>',d,re.S|re.I)
        if not typ or not body:continue
        typ=typ.group(1).strip()
        if typ==form or typ.startswith(('EX-1.','EX-2.','EX-3.','EX-4.','EX-10','EX-99')):out.append((typ,name.group(1).strip() if name else None,body.group(1)))
    return out

def extract(text):
    patterns={'net_proceeds':r'net proceeds|proceeds[^.]{0,50}net of',
              'fees_and_expenses':r'cash (?:placement |advisory )?fee|placement agent.{0,35}(?:fee|commission)|expense (?:allowance|reimbursement)|reimburse.{0,70}(?:legal|expenses)|non.accountable|underwriting discount',
              'cash_allocations':r'cash collateral|controlled account|escrow|redeem.{0,70}(?:cash|proceeds)|proceeds.{0,100}(?:redeem|repay|acquire|purchase)',
              'purchase_price':r'purchase price|original issue discount|in cash|cash consideration',
              'registration':r'registration statement.{0,100}(?:effective|resale)|lock.up|restricted securities|unregistered securities'}
    evidence=[]
    for kind,pattern in patterns.items():
        for m in list(re.finditer(pattern,text,re.I))[:40]:
            start=max(0,m.start()-100);end=min(len(text),m.end()+420)
            evidence.append({'kind':kind,'locator':'normalized_text['+str(start)+':'+str(end)+']','quote':text[start:end]})
    return evidence

def main():
    rows=json.loads((WORK/'terms_source_manifest.local.json').read_text(encoding='utf-8'));target=WORK/'terms_parsed';target.mkdir(exist_ok=True)
    stats={'reports':0,'parts':0,'evidence':0,'failures':[]}
    for r in rows:
        if r['status']!='ok':continue
        try:
            b=(ROOT/r['file']).read_bytes()
            if hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Source hash mismatch')
            docs=[]
            for kind,name,body in parts(b.decode('utf-8',errors='replace'),r['form']):
                paras=paragraphs(body);text=paras[-1] if paras else '';evidence=extract(text)
                docs.append({'type':kind,'filename':name,'text':text,'evidence':evidence});stats['parts']+=1;stats['evidence']+=len(evidence)
            result={'accession':r['accession'],'cik':r['cik'],'filed_at':r['filed_at'],'source_url':r['url'],'source_sha256':r['sha256'],'parts':docs}
            f=target/(r['accession'].replace('-','')+'.json');temp=f.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');temp.replace(f);stats['reports']+=1
        except Exception as e:stats['failures'].append({'accession':r['accession'],'error':str(e)})
    (WORK/'terms_parse_status.local.json').write_text(json.dumps(stats,indent=2),encoding='utf-8');print(json.dumps(stats))
if __name__=='__main__':main()
