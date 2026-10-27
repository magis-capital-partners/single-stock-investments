"""Retain published podcast history while applying a partial source refresh."""
from __future__ import annotations


def merge_podcast_catalogs(prior_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    merged={str(row['episode_id']):dict(row) for row in prior_rows if row.get('episode_id')}
    for row in new_rows:
        key=str(row.get('episode_id') or '')
        if not key:continue
        old=merged.get(key,{})
        update={k:v for k,v in row.items() if v is not None and v!='' and v!=[] and v!={}}
        if old.get('summary_status')=='ready' and row.get('summary_status')!='ready':
            update={k:v for k,v in update.items() if not k.startswith('summary_') and k!='has_summary'}
        merged[key]={**old,**update}
    return sorted(merged.values(),key=lambda row:(str(row.get('published') or ''),str(row.get('episode_id'))),reverse=True)
