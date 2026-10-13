#!/usr/bin/env python3
"""Check the committed hub shards before a render or deployment verification.

This is read-only. Derived dashboard JSON must be rebuilt through the pipeline,
never repaired here. Counts and build timestamps describe observed artifacts,
not investment authority.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SHARDS = {'desk_briefs':'data/desk_briefs.json','reverse_splits':'data/reverse_splits.json'}
LANES = {'spinoffs','split_offs','mergers','warrants','restructurings','forced_sellers'}


def check(root=ROOT):
    errors, artifacts = [], {}
    docs = {}
    for name in ('core','desk_briefs','reverse_splits','short_alpha','special_situations','separations'):
        path = root/'dashboard/data'/(name+'.json')
        try:
            raw = path.read_bytes()
            doc = json.loads(raw)
            stamp = doc.get('generated_at') or doc.get('build_time')
            if not stamp:
                errors.append(f'{name}: no build timestamp')
            docs[name] = doc
            artifacts[name] = {'generated_at':stamp,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        except (OSError,ValueError) as exc:
            errors.append(f'{name}: {exc}')
    core = docs.get('core',{})
    for key, reference in REQUIRED_SHARDS.items():
        if core.get('shards',{}).get(key) != reference:
            errors.append(f'core: missing or incorrect {key} shard reference')
    short = docs.get('short_alpha',{})
    if short.get('schema_version') != '1.2':
        errors.append('short_alpha: expected schema version 1.2')
    count = len(short.get('candidates',[]))
    if short.get('summary',{}).get('candidate_count') != count:
        errors.append('short_alpha: candidate count does not reconcile')
    lanes = {row.get('id') for row in docs.get('special_situations',{}).get('lanes',[])}
    if lanes != LANES:
        errors.append('special_situations: expected six lanes including split_offs')
    for name in ('desk_briefs','reverse_splits','separations'):
        doc=docs.get(name,{})
        if (doc.get('research_only'),doc.get('in_base_irr'),doc.get('authority')) != (True,False,'none'):
            errors.append(f'{name}: research authority flags missing or invalid')
    return {'research_only':True,'in_base_irr':False,'authority':'none','status':'invalid' if errors else 'ok',
            'errors':errors,'artifacts':artifacts,'candidate_count':count,'lanes':sorted(lanes),
            'scope':'Committed artifact contract only; render and hosted delivery require separate evidence'}


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    report=check(args.root)
    text=json.dumps(report,indent=2)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(text,encoding='utf-8')
    print(text)
    return 1 if report['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
