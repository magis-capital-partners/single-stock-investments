#!/usr/bin/env python3
"""Bounded HTTPS-only public source refresh. No brokerage or market-data terminals.

Forecast inputs are versioned, reviewed transcriptions. This collector captures
publisher bytes and history, and flags changed publications for a new review;
it never silently relabels an old forecast as a new vintage.
"""
from __future__ import annotations

import argparse
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.request import Request, urlopen

from commodity_common import CONFIG_DIR, DEFAULT_PANEL, digest, load, save

def download(url):
    request = Request(url, headers={'User-Agent':'MagisResearch/1.0 (public commodity research)'})
    with urlopen(request, timeout=25) as response:
        data = response.read(25_000_001)
        if len(data)>25_000_000:
            raise ValueError('Source exceeds 25 MB limit')
        return data


def refresh(output=DEFAULT_PANEL, as_of=None, history=True):
    as_of = as_of or date.today()
    prior = load(output, {})
    from vault_paths import research_vault_root
    vault=research_vault_root()
    preserved=vault/'dashboard-private/commodity-inputs' if vault else None
    if not prior and preserved:
        prior=load(preserved/'observations.json',{})
        if (preserved/'forecast-vintages').is_dir():
            shutil.copytree(preserved/'forecast-vintages',output.parent/'forecast-vintages',dirs_exist_ok=True)
    refs = {s['id']:s for p in CONFIG_DIR.glob('*.json') for s in load(p)['sources']}
    result = {'as_of':as_of.isoformat(), 'sources':{}, 'series':{}}
    def capture(item):
        key, ref = item
        try:
            raw = download(ref['url'])
            resolved_url=ref['url']
            if ref.get('download_label'):
                from bs4 import BeautifulSoup
                soup=BeautifulSoup(raw,'html.parser')
                title=soup.find(string=lambda t:t and ref['download_label'] in t)
                link=title.parent.parent.select_one('[data-downloadurl]') if title else None
                if not link:raise ValueError('Requested publication download missing')
                resolved_url=link['data-downloadurl'];raw=download(resolved_url)
                if not raw.startswith(b'%PDF'):raise ValueError('Expected publisher PDF')
            if len(raw)<500 or (b'<html' in raw[:1000].lower() and b'access denied' in raw.lower()):
                raise ValueError('No publication content')
            path = output.parent/'objects'/digest(raw)
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists(): path.write_bytes(raw)
            return key, {'url':ref['url'],'resolved_url':resolved_url,'sha256':digest(raw),'fetched_at':as_of.isoformat(),'status':'fetched','bytes':len(raw)}
        except Exception as e:
            return key, {**prior.get('sources',{}).get(key,{}),'status':'fetch_failed','last_attempt':as_of.isoformat(),'error':type(e).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        result['sources']=dict(pool.map(capture,refs.items()))
    if history:
        from commodity_history import collect
        def capture_history(raw):
            path=output.parent/'objects'/digest(raw)
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_bytes(raw)
        result['series'],failures=collect(download,prior.get('series',{}),as_of,capture_history)
        result['history_refresh']={'status':'partial' if failures else 'complete','failed_series':failures}
        from commodity_vintages import collect as collect_vintages
        try:result['oil_forecast_validation']=collect_vintages(download,result['series'],output.parent/'forecast-vintages',as_of)
        except Exception as exc:result['oil_forecast_validation']={**prior.get('oil_forecast_validation',{}),'status':'fetch_failed','error':type(exc).__name__}
        # Archive every fetched vintage for later tests; do not overwrite history.
        save(output.parent/'vintages'/(as_of.isoformat()+'-'+digest(result['series'])[:12]+'.json'),result['series'])
    else:
        result['series']=prior.get('series',{})
        result['history_refresh']=prior.get('history_refresh',{'status':'not_requested'})
        result['oil_forecast_validation']=prior.get('oil_forecast_validation',{})
    save(output,result)
    return result


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_PANEL)
    parser.add_argument('--as-of',type=date.fromisoformat,default=date.today())
    parser.add_argument('--skip-history',action='store_true')
    args=parser.parse_args()
    doc=refresh(args.output,args.as_of,not args.skip_history)
    print({k:v['status'] for k,v in doc['sources'].items()})
