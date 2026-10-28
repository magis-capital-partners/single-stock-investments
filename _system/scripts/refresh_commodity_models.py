"""Refresh context models in the existing weekly research pipeline."""
import argparse
from datetime import date

from commodity_common import ROOT, load, save
from build_commodity_models import build
from fetch_commodity_panel import refresh as fetch
from validate_commodity_models import validate


def refresh(offline=False):
    output=ROOT/'dashboard/data/commodity_models.json'
    previous=load(output)
    try:
        if not offline:fetch()
        doc=build()
        errors=validate(doc)
        if errors:raise ValueError('; '.join(errors))
        incomplete=[m['id'] for m in doc['models'] if not m['input_coverage']['required_ready'] or any(s['fetch_status']=='fetch_failed' for s in m['sources'] if s.get('required',True))]
        doc['refresh']={'status':'partial' if incomplete else 'updated','attempted_at':date.today().isoformat(),'incomplete_models':incomplete}
        save(output,doc)
        return not incomplete
    except Exception as exc:
        if previous:
            previous['refresh']={'status':'failed','attempted_at':date.today().isoformat(),'reason':type(exc).__name__}
            save(output,previous)
        print(f'Commodity model refresh failed: {type(exc).__name__}: {exc}')
        return False


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--optional',action='store_true')
    args=parser.parse_args()
    if not refresh(args.offline) and not args.optional:raise SystemExit(1)
