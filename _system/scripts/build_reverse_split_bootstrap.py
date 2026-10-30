"""Export source-bound earlier split dates only; never prices, returns, or future outcomes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'_system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z'
OUT=ROOT/'dashboard/cloudflare/reverse-split-live/bootstrap.json'

def build():
    manifest=RUN/'event_outcomes.parts.json'
    doc=json.loads(manifest.read_text(encoding='utf-8'));records={}
    for part in doc['files']:
        path=RUN/part['path'];raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=part['sha256']:
            raise ValueError('Historical catalogue changed')
        for line in raw.decode().splitlines():
            e=json.loads(line)
            if e.get('verification') not in ('primary_schedule_matched','structured_corporate_action') or not str(e.get('issuer','')).startswith('cik/') or not 0<e.get('ratio',0)<1:
                continue
            if not e.get('available_at') or not str(e.get('source_url','')).startswith('https://'):
                continue
            cik=str(int(e['issuer'].split('/')[1]));key=cik+':'+e['ex_date']
            row={'cik':cik,'effective_date':e['ex_date'],'known_at':e['available_at'],'verified':True,
                 'source_url':e['source_url'],'verification':e['verification'],'source_catalogue_sha256':part['sha256']}
            if key not in records or row['known_at']<records[key]['known_at']:
                records[key]=row
    body={'schema':'reverse_split_prior_history.v1','source_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'records':sorted(records.values(),key=lambda r:(r['cik'],r['effective_date']))}
    OUT.write_text(json.dumps(body,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'prior_actions':len(records),'bytes':OUT.stat().st_size}))

if __name__=='__main__':build()
