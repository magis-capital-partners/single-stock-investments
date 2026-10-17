"""Recover quote-priced events with a dated identity but incomplete auctions."""
from collections import Counter
from datetime import timezone
import argparse
import json
import sqlite3

import numpy as np
import pandas as pd
import exchange_calendars as xc

from .config import load_config
from .execute import session_open
from .ledger import read_json,write_json
from .portfolio_data import collect,request_rows,supplemental_requests,quote_paths,depth_books


def candidates(cfg):
    source=cfg.local_dir/'expansion'/'expansion_v2'/'runs'/'20261013T224003582762Z'
    conn=sqlite3.connect((source/'prices.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row
    cal=xc.get_calendar('XNYS',start='2018-01-01',end='2027-01-01');rows=[];counts=Counter()
    for part in read_json(source/'event_outcomes.parts.json',{})['files']:
        for line in (source/part['path']).read_text().splitlines():
            e=json.loads(line)
            if e['verification'] not in {'primary_schedule_matched','structured_corporate_action'}:continue
            o=next(o for o in e['outcomes'] if o['cohort']=='ex_plus_1_h1')
            if o.get('reason') not in {'entry_or_exit_observation_unavailable','invalid_price_or_share_factor'}:continue
            if not e.get('ratio') or not 0<float(e['ratio'])<1:
                counts['invalid_reverse_ratio']+=1;continue
            counts['incomplete_price_candidates']+=1;day=o.get('entry_date');ticker=e.get('database_ticker',e['ticker'])
            found=conn.execute('SELECT * FROM official_auction_prices WHERE ticker=? AND date=?',(ticker,day)).fetchall() if day else []
            identities={(f['symbol'],f['dataset']) for f in found}
            if len(identities)!=1:counts['dated_security_identity_unavailable_or_conflicting']+=1;continue
            symbol,venue=next(iter(identities));opened=session_open(day).astimezone(timezone.utc);closed=cal.session_close(day).to_pydatetime()
            rows.append({'key':e['event_id'],'event_id':e['event_id'],'ticker':ticker,'symbol':symbol,'dataset':venue,
                'issuer':e['issuer'],'date':day,'opened':opened.isoformat(),'closed':closed.isoformat(),
                'open':1.,'close':1.,'cohorts':['extension'],'benchmark_basis':'quote_midpoint_pair'})
    conn.close();return rows,dict(counts)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--max-cost',type=float,default=0)
    args=parser.parse_args(argv);cfg=load_config()
    root=cfg.local_dir/'portfolio_research'/'20261013T224003582762Z__portfolio_v1';repair=root/'repair';repair.mkdir(exist_ok=True)
    rows,counts=candidates(cfg)
    stages=('sessions','supplemental','depth','repair/sessions','repair/supplemental')
    spent=sum(r.get('quoted_usd',0) for stage in stages for r in read_json(root/stage/'collection.json',[]) if r['status'] in {'cached','downloaded'})
    collect(repair/'sessions',request_rows(rows),max(0,args.max_cost-spent),workers=24)
    spent=sum(r.get('quoted_usd',0) for stage in stages for r in read_json(root/stage/'collection.json',[]) if r['status'] in {'cached','downloaded'})
    req=supplemental_requests(rows,read_json(root/'access_receipt.local.json',{}).get('ranges',{}))
    collect(repair/'supplemental',req,max(0,args.max_cost-spent),workers=24)
    index,points=quote_paths(repair,rows);selected=[];minute={}
    for r in rows:
        a=dict(np.load(repair/index[r['key']]['file']));mid=(a['bid']+a['ask'])/2
        if not np.isfinite(mid[0]) or not np.isfinite(mid[-1]):continue
        r['open']=float(mid[0]);r['close']=float(mid[-1]);selected.append(r)
        carried=pd.Series(mid).ffill().fillna(r['open']).to_numpy();times=[];closes=[]
        opened=int(pd.Timestamp(r['opened']).timestamp());closed=int(pd.Timestamp(r['closed']).timestamp())
        for end in range(opened+60,closed+1,60):
            i=min(len(a['ts'])-1,max(0,np.searchsorted(a['ts'],end,side='right')-1))
            times.append(pd.Timestamp(end-60,unit='s',tz='UTC').isoformat());closes.append(float(carried[i]))
        minute[r['key']]={'times':times,'close':closes,'high':closes,'bars':len(times),'basis':'completed_minute_quote_marks'}
    depth_books(repair,rows,points)
    write_json(repair/'targets.local.json',selected);write_json(repair/'minute_paths.local.json',minute)
    write_json(repair/'receipt.json',{'candidates':counts,'dated_identity_candidates':len(rows),'recovered_quote_pairs':len(selected),
        'by_year':dict(sorted(Counter(r['date'][:4] for r in selected).items())),
        'limits':'Retrospectively available paired continuous quotes; original auction sample unchanged. Unresolved identities remain excluded, and no earlier provider history is inferred.'})
    print('Quote recovery',len(selected),'/',len(rows),'dated candidates',flush=True)


if __name__=='__main__':main()
