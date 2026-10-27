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
# Decimal megabytes, matching validate_dashboard_data.CORE_MAX_MB. Do not raise it.
CORE_MAX_MB = 6.0
LANES = {'spinoffs','split_offs','mergers','warrants','restructurings','forced_sellers','buyback_events'}


def check(root=ROOT, core_max_mb=CORE_MAX_MB):
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
            if name == 'core' and len(raw) / 1e6 > core_max_mb:
                errors.append(
                    f'core: {len(raw) / 1e6:.2f} MB exceeds the {core_max_mb:.1f} MB boot budget; '
                    'slim rows further in build_dashboard_shards.py'
                )
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
        errors.append('special_situations: expected seven lanes including buyback_events')
    radar_path = root/'dashboard/data/buyback_radar.json'
    if radar_path.is_file():
        try:
            radar = json.loads(radar_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            errors.append(f'buyback_radar: {exc}')
            radar = {}
        env = radar.get('_envelope') or {}
        if env.get('schema_version') != 'magis.feed.v2' or not (env.get('health') or {}).get('status'):
            errors.append('buyback_radar: envelope missing schema or health')
        if radar_path.stat().st_size >= 100 * 1024:
            errors.append('buyback_radar: over the 100 KB L0 budget')
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
