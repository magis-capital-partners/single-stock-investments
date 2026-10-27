"""Idempotent source-aware publication and matched-session flow calibration."""
import hashlib
import json
from pathlib import Path


def fingerprint(payload):
    rows=[]
    for item in payload.get('components', []):
        row={k:v for k,v in item.items() if k not in {'published_at','generated_at','received_at'}}
        if row.get('quality_state')=='unavailable':
            row.pop('as_of',None)
            row.pop('session_date',None)
        rows.append(row)
    return hashlib.sha256(json.dumps({'components':sorted(rows,key=lambda r:(r.get('component',''),r.get('scope',''),r.get('symbol',''))),'expected_session':payload.get('expected_session'),'release_stage':payload.get('release_stage')},sort_keys=True).encode()).hexdigest()


def reconcile(payload, prior=None):
    pairs={r['key']:r for r in (prior or {}).get('pairs',[]) if r.get('key')}
    for row in payload.get('components',[]):
        name=row.get('component')
        if row.get('scope')!='market' or name not in {'letf_rebalance_intraday','letf_rebalance_close'}:
            continue
        day,universe=row.get('session_date'),row.get('universe_hash')
        if not day or not universe or row.get('value') is None or row.get('quality_state')=='unavailable':
            continue
        key=day+':'+universe
        pair=pairs.setdefault(key,{'key':key,'session_date':day,'universe_hash':universe})
        kind='forecast' if name.endswith('intraday') else 'close'
        pair[kind]={'value':row['value'],'as_of':row['as_of'],'source':row['source']}
        if pair.get('forecast') and pair.get('close'):
            pair['error_usd']=round(pair['forecast']['value']-pair['close']['value'],2)
            pair['direction_match']=(pair['forecast']['value']>=0)==(pair['close']['value']>=0)
    records=sorted(pairs.values(),key=lambda r:r['key'])[-252:]
    matched=[r for r in records if 'error_usd' in r]
    return {'pairs':records,'matched_sessions':len(matched),'mean_error_usd':round(sum(r['error_usd'] for r in matched)/len(matched),2) if matched else None,'mean_absolute_error_usd':round(sum(abs(r['error_usd']) for r in matched)/len(matched),2) if matched else None,'basis':'Matching trading session and underlying universe only; both legs are modeled estimates.'}


if __name__=='__main__':
    import sys
    old,new=map(Path,sys.argv[1:3])
    fresh=json.loads(new.read_text(encoding='utf-8'))
    try:
        previous=json.loads(old.read_text(encoding='utf-8'))
    except (ValueError,OSError):
        previous={}
    print('skip' if fingerprint(previous)==fingerprint(fresh) else 'commit')
