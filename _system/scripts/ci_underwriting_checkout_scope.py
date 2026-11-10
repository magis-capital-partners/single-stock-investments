"""Select a complete checkout for exact-company underwriting data PR lint.

This selects files, never approval. All model/evidence/replay/lint gates remain.
Other research PRs keep the existing full history checkout.
"""
from __future__ import annotations
import argparse
from pathlib import Path, PurePosixPath
import re

RECEIPT=re.compile(r'([A-Za-z0-9][A-Za-z0-9._-]{0,30})/research/underwriting_receipt[.]json\Z')
RESEARCH=('valuation.json','valuation_contract.json','valuation_route.json','underwriting_contract.json',
          'underwriting_review.json','underwriting_receipt.json','underwriting_diagnostics.json','underwriting_outcomes.json')

def roots_for(files,expected_count):
    if type(expected_count) is not int or not 0<=expected_count<=3000 or len(files)!=expected_count or len(set(files))!=len(files):
        raise ValueError('PR file list is incomplete, duplicated or beyond the complete API bound')
    for value in files:
        parts=PurePosixPath(value).parts
        if not parts or value.startswith('/') or '\\' in value or any(p in ('.','..','.git') for p in value.split('/')) or any(c in value for c in '\r\n\0'):
            raise ValueError('Unsafe PR file path')
    tickers={m[1] for path in files if (m:=RECEIPT.fullmatch(path))}
    if len(tickers)!=1:return None
    ticker=next(iter(tickers))
    required={ticker+'/research/'+name for name in ('valuation.json','underwriting_contract.json','underwriting_review.json','underwriting_receipt.json')}
    allowed={'_system/data/underwriting_queue.json'}|{ticker+'/research/'+name for name in RESEARCH}
    allowed|={'_system/reference/market-data/'+name+'/'+ticker+'.json' for name in ('valuation_quotes','valuation_fundamentals')}
    if not required.issubset(files) or not set(files).issubset(allowed):return None
    # Preserve the entire company folder and all shared validation/reference
    # inputs. Cone mode includes root files. No company source is sampled.
    return ['_system','.github',ticker]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files',type=Path,required=True)
    parser.add_argument('--expected-count',type=int,required=True)
    parser.add_argument('--roots',type=Path,required=True)
    args=parser.parse_args()
    roots=roots_for(args.files.read_text(encoding='utf-8').splitlines(),args.expected_count)
    args.roots.write_text('' if roots is None else ''.join(root+'\n' for root in roots),encoding='utf-8')
    print('full' if roots is None else 'scoped')
if __name__=='__main__':main()
