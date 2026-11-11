"""Check the published BTC context contract without broker/data sockets."""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate(doc: dict) -> list[str]:
    errors = []
    if doc.get('schema_version') != '2.0':
        errors.append('Expected BTC schema 2.0')
    if doc.get('in_base_irr') is not False or doc.get('valuation_authority') != 'none' or not doc.get('research_only'):
        errors.append('BTC context must have no valuation authority')
    if doc.get('horizon') != '2033-12-31':
        errors.append('Missing 2033 horizon')
    as_of = doc.get('as_of', '')
    demand, supply = doc.get('demand', {}), doc.get('supply', {})
    for field in ('model_path', 'unconstrained_path'):
        rows = demand.get(field, [])
        if not rows or rows[-1].get('d') != '2033-12-31':
            errors.append(f'{field} must reach 2033')
        if any(not isinstance(p.get('v'), (float,int)) or not math.isfinite(p['v']) or p['v'] <= 0 for p in rows):
            errors.append(f'{field} contains invalid prices')
    if any(p.get('d', '') > as_of for p in demand.get('actual_path', [])):
        errors.append('Actual prices include future dates')
    for label in ('naive_hk','mixed_base','efficiency_deflation','power_inflation'):
        scenario = supply.get('scenarios', {}).get(label, {})
        if not scenario.get('2033') or not scenario.get('path') or scenario['path'][-1].get('date') != '2033-12-31':
            errors.append(f'{label} must reach 2033')
    refs = {r['id']:r for v in doc.get('hk_reference', {}).get('vintages', []) for r in v['references']}
    if refs.get('q2_demand', {}).get('value') != 270438.05 or refs.get('q3_demand', {}).get('value') != 1000000:
        errors.append('Q2/Q3 demand references lost')
    if refs.get('q3_demand', {}).get('date_precision') != 'year' or 'date' in refs.get('q3_demand', {}):
        errors.append('Q3 2033 reference must retain year precision')
    if refs.get('q3_supply', {}).get('low') != 117000 or refs.get('q2_sota', {}).get('time_label') != 'Current at publication':
        errors.append('Q2/Q3 cost basis lost')
    for row in supply.get('fees', {}).get('scenarios', []):
        if row['fee_adjusted_breakeven_usd'] > row['production_cost_usd']:
            errors.append('Positive fees cannot increase breakeven')
    if supply.get('electricity_history', {}).get('observed_global_series') is not False:
        errors.append('Power proxy must not claim to be observed global tariffs')
    inputs = doc.get('freshness', {}).get('inputs', [])
    if len(inputs) < 7 or any(r.get('observed_through') and r['observed_through'] > as_of for r in inputs):
        errors.append('Missing or future-dated freshness metadata')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-fresh', action='store_true', help='Fail if core market observations are over seven days old')
    args = parser.parse_args()
    path = ROOT / 'dashboard/data/hk_snowball_model.json'
    raw = path.read_text(encoding='utf-8')
    doc = json.loads(raw)
    errors = validate(doc)
    if raw != (ROOT / '_system/reference/market-data/crypto/hk_snowball_model.json').read_text(encoding='utf-8'):
        errors.append('Dashboard/reference snapshots differ')
    for row in doc.get('freshness', {}).get('inputs', []):
        if row.get('stale'):
            print(f"WARNING: {row['label']} observed through {row.get('observed_through')}")
        if args.require_fresh and row['id'] in ('btc_spot_usd','btc_hash_rate_eh','btc_difficulty','btc_avg_fee_per_block_usd','btc_all_in_cost_usd'):
            day = row.get('observed_through')
            if not day or (date.today() - date.fromisoformat(day)).days > 7:
                errors.append(f"Core BTC input stale: {row['label']}")
    for error in errors:
        print('ERROR:', error)
    if not errors:
        print('BTC context: horizons, references, fees, freshness and valuation boundary passed')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
