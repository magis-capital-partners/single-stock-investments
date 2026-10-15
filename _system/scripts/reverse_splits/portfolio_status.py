"""Read cached national trading/SSR transitions; never connect to a broker."""
from collections import defaultdict
import hashlib
import json

import numpy as np
import pandas as pd

from .expansion import digest
from .ledger import read_json,write_json


def histories(cfg,root,rows):
    import databento as db
    groups=defaultdict(list)
    for r in rows:
        y,m,_=map(int,r['date'].split('-'));groups[f'{y}Q{(m-1)//3+1}'].append(r)
    sources=[]
    for period in sorted(groups):
        for suffix in ('dbn.zst','symbology.json'):
            p=cfg.databento_dir/'XNAS.ITCH'/'status'/(period+'.'+suffix)
            if p.exists():sources.append({'path':str(p.resolve()),'sha256':digest(p)})
    binding=hashlib.sha256(json.dumps({'rows':[(r['key'],r['symbol'],r['date']) for r in rows],'sources':sources},sort_keys=True).encode()).hexdigest()
    saved=read_json(root/'status_history.local.json',{})
    if saved.get('binding')==binding:return saved['histories']
    out={}
    for period,selected in sorted(groups.items()):
        p=cfg.databento_dir/'XNAS.ITCH'/'status'/(period+'.dbn.zst');mapping=p.with_name(period+'.symbology.json')
        if not p.exists() or not mapping.exists():continue
        symbols={r['symbol'] for r in selected};spans={int(k):v for k,v in read_json(mapping,{}).items() if any(s['s'] in symbols for s in v)}
        a=db.DBNStore.from_file(str(p)).to_ndarray();a=a[np.isin(a['instrument_id'],list(spans))]
        for r in selected:
            ids=[i for i,iv in spans.items() if any(s['s']==r['symbol'] and s['d0']<=r['date']<s['d1'] for s in iv)]
            data=np.sort(a[np.isin(a['instrument_id'],ids)],order='ts_recv')
            start=pd.Timestamp(r['opened']).value;end=pd.Timestamp(r['closed']).value
            fields={}
            for field in ('is_trading','is_short_sell_restricted'):
                f=data[np.isin(data[field],[b'Y',b'N'])];prior=f[f['ts_recv']<start]
                f=f[(f['ts_recv']>=start)&(f['ts_recv']<=end)]
                if len(prior):f=np.r_[prior[-1:],f]
                fields[field]={'ts':(f['ts_recv'].astype(float)/1e9).tolist(),'value':[v.decode() for v in f[field]]}
            out[r['key']]=fields
        print('Trading/SSR histories',period,len(selected),flush=True)
    write_json(root/'status_history.local.json',{'binding':binding,'sources':sources,'histories':out})
    return out


def at(history,field,timestamp):
    f=history.get(field,{});ts=f.get('ts',[])
    i=np.searchsorted(ts,timestamp,side='right')-1
    return f.get('value',[])[i] if i>=0 else None
