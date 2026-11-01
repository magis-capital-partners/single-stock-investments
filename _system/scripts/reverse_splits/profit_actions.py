"""Mechanical share adjustments corroborated by dated primary clauses.

Read cached filings only. A price jump alone never establishes a split. These
automated reconciliations repair parser omissions; they are not manual approvals.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import math
import re
import sqlite3

from .profit_data import digest, sec_filing_url


def clause_factor(clause):
    text=clause.lower().replace('\u2011','-').replace('\u2013','-')
    pairs=re.findall(r'\b(\d+(?:\.\d+)?)\s*(?:-\s*)?for\s*(?:-\s*)?(\d+(?:\.\d+)?)\b',text)
    if not re.search(r'reverse\s+(?:stock\s+)?split|consolidat',text):return None
    factors=[]
    for a,b in pairs:
        x,y=float(a),float(b)
        # Both conventional wordings occur: 1-for-50 and 50-for-1.
        if min(x,y)!=1 or max(x,y)<=1:continue
        factors.append(max(x,y))
    unique=set(factors)
    return unique.pop() if len(unique)==1 else None


def primary_adjustments(root,price_source,series,catalogue):
    source=price_source.parent/'input.sqlite'
    conn=sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row
    candidates=defaultdict(list)
    for action in catalogue:
        if action.get('ratio') and action['ratio']>0 and action.get('cik'):
            candidates[str(int(action['cik']))].append(action)
    found=defaultdict(list)
    for row in conn.execute("SELECT ticker,cik,accession,scheduled,ratio,audit_json,text_file FROM disclosures WHERE audit_json LIKE '%scheduled_action%'"):
        if not row['cik'] or str(int(row['cik'])) not in candidates:continue
        audit=json.loads(row['audit_json'] or '{}')
        docs=[audit]+audit.get('documents',[])
        for doc in docs:
            if doc.get('category')!='scheduled_action':continue
            day=doc.get('announced_ex_date') or row['scheduled']
            dated=[a for a in doc.get('dated_actions',[]) if a.get('date')==day]
            if not dated:continue
            ratios=[clause_factor(a.get('clause','')) for a in dated]
            if doc.get('ratio') and 0<doc['ratio']<1:ratios.append(1/doc['ratio'])
            ratios=[f for f in ratios if f]
            for candidate in candidates[str(int(row['cik']))]:
                symbol=candidate['ticker']
                if candidate['ex_date']!=day or symbol not in series or day not in series[symbol]:continue
                inferred_factor=1/candidate['ratio']
                # Bind the primary issuer to its historical catalogue symbol;
                # current submission aliases must not lose old share adjustments.
                tolerance=.35 if str(candidate.get('ratio_basis','')).startswith('price_inferred') else .005
                matching={r for r in ratios if abs(r/inferred_factor-1)<tolerance}
                if len(matching)!=1:continue
                # A jump detector estimates a coarse ratio. The explicit primary
                # ratio supplies exact share units (e.g. 1:15, not inferred 1:12).
                factor=matching.pop()
                history=sorted(series[symbol]);i=history.index(day)
                if not i:continue
                jump=series[symbol][day]['o']/series[symbol][history[i-1]]['c']
                if not (jump>math.sqrt(factor) and .25<jump/factor<4):continue
                text_path=(Path(root)/row['text_file']).resolve()
                safe=(Path(root)/'_system/data/reverse_splits/local').resolve()
                if not text_path.is_relative_to(safe) or not text_path.exists():continue
                found[(symbol,day)].append({'ticker':symbol,'ex_date':day,'price_factor':factor,
                    'source_url':sec_filing_url(row['cik'],row['accession']),'source_sha256':digest(text_path),
                    'source_hash_basis':'cached_primary_text_bytes','clause':' '.join(a.get('clause','') for a in dated)[:900],
                    'verification':'automated_primary_clause_plus_catalogue_and_nominal_path_requires_review'})
    conn.close()
    out=[]
    for _,items in sorted(found.items()):
        if len({r['price_factor'] for r in items})!=1:continue
        out.append(sorted(items,key=lambda r:r['source_url'])[0])
    return out
