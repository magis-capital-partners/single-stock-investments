#!/usr/bin/env python3
"""Validate identities, scenario labels and independence from stock base returns."""
from __future__ import annotations

from commodity_common import ROOT, VERSION, finite, load


def validate(doc):
    errors=[]
    if doc.get('schema_version')!=VERSION:errors.append('Unknown commodity schema')
    if doc.get('in_base_irr') is not False:errors.append('Base IRR must exclude commodity scenarios')
    models=doc.get('models',[])
    if [m.get('id') for m in models]!=['crude','copper','gold','silver']:errors.append('All four engines required in dependency order')
    for m in models:
        prefix=m['id']
        if m.get('in_base_irr') is not False:errors.append(prefix+': base IRR inclusion')
        if not m.get('sources') or not m.get('falsifiers'):errors.append(prefix+': provenance or falsifiers missing')
        for s in m.get('sources',[]):
            if s.get('published_at','9999')>doc['as_of']:errors.append(prefix+': future source')
            if not s.get('transcription_sha256'):errors.append(prefix+': missing reviewed-input hash')
        for c in m.get('validation',[]):
            if c.get('passed') is False:errors.append(prefix+': '+c['check'])
        for s in m.get('scenarios',[]):
            periods=[]
            for r in s.get('rows',[]):
                periods.append(r['period'])
                if r.get('price') is not None and (not finite(r['price']) or r['price']<=0):errors.append(prefix+': invalid scenario price')
                if not r.get('basis') or not r.get('price_status'):errors.append(prefix+': unlabeled scenario')
                for key in ['stock_residual','balance_residual']:
                    if abs(r.get(key,0))>0.011:errors.append(prefix+': '+key)
                if r.get('oecd_stock_mb') is not None and r['oecd_stock_mb']<=0:errors.append(prefix+': impossible stock')
                if prefix=='silver' and abs(r['balance_moz']-r['etp_moz']-r['balance_less_etp_moz'])>.011:errors.append('silver: ETP counted incorrectly')
                if r['basis']=='published_forecast' and prefix!='crude':errors.append(prefix+': assumed price mislabeled published')
                if r['basis']=='published_forecast' and r['period']>m.get('reference',{}).get('published_forecast_end',''):
                    errors.append(prefix+': published forecast exceeds source horizon')
                if prefix=='copper':
                    concentrate=m.get('concentrate',{}).get('balance_kt')
                    if concentrate is None and r.get('concentrate_balance_kt') is not None:
                        errors.append('copper: concentrate balance without measured inputs')
                    if abs(r['refined_kt']-r['use_kt']-r['balance_kt'])>.011:
                        errors.append('copper: refined identity')
            if periods!=sorted(set(periods)):errors.append(prefix+': unordered or duplicate periods')
    return errors


if __name__=='__main__':
    import sys
    errors=validate(load(sys.argv[1] if len(sys.argv)>1 else ROOT/'dashboard/data/commodity_models.json',{}))
    if errors:raise SystemExit('\n'.join(errors))
    print('Commodity provenance, balances and context-only rules passed')
