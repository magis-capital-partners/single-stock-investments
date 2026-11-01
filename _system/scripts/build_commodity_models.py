#!/usr/bin/env python3
"""Build four independent, auditable commodity scenario panels."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from commodity_common import CONFIG_DIR, DEFAULT_PANEL, ROOT, VERSION, load, save
import commodity_engines as engines


def build(as_of=None, config_dir=CONFIG_DIR, panel_path=DEFAULT_PANEL):
    as_of=as_of or date.today()
    panel=load(panel_path,{})
    models=[]
    for name in ['crude','copper','gold','silver']:
        config=load(config_dir/f'{name}.json')
        if config.get('in_base_irr') is not False:
            raise ValueError('Commodity contexts must be excluded from base IRR')
        extra=[models[-1]] if name=='silver' else []
        models.append(getattr(engines,name)(config,panel,as_of,*extra))
    return {'schema_version':VERSION,'as_of':as_of.isoformat(),'in_base_irr':False,'models':models,
            'refresh_policy':{'oil_days':45,'copper_days':45,'gold_days':120,'silver_days':400},
            'bridges':[{'from':'gold','to':'silver','included_in_balance':True,'reason':'Silver price reads the named gold scenario and an explicit assumed ratio.'},
                       {'from':'copper','to':'silver','included_in_balance':False,'reason':'Byproduct sensitivity is already represented in silver assumptions; no additive supply term.'},
                       {'from':'energy','to':'metals','included_in_balance':False,'reason':'Operating-cost context only; no duplicate physical demand.'}]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of',type=date.fromisoformat,default=date.today())
    parser.add_argument('--panel',type=Path,default=DEFAULT_PANEL)
    parser.add_argument('--output',type=Path,default=ROOT/'dashboard/data/commodity_models.json')
    args=parser.parse_args()
    doc=build(args.as_of,panel_path=args.panel)
    from validate_commodity_models import validate
    errors=validate(doc)
    if errors:raise SystemExit('\n'.join(errors))
    save(args.output,doc)
    print(f"Built {len(doc['models'])} context models through 2032; base IRR unchanged")
