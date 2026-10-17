#!/usr/bin/env python3
"""Refresh the public research companion and record failures without losing prior results."""
from __future__ import annotations

import argparse
from datetime import date

from energy_common import ROOT, atomic_json, load_json, now_iso
from fetch_energy_panel import refresh as refresh_panel
from fetch_energy_assets import refresh as refresh_assets
from build_energy_model import build


def refresh(as_of=None, *, offline=False, output_dir=None):
    directory = output_dir or ROOT / 'dashboard/data'
    previous = load_json(directory / 'energy_model.json', {})
    status = {'schema_version': '1.0', 'attempted_at': now_iso(), 'in_base_irr': False}
    try:
        refresh_panel(offline=offline)
        try:
            refresh_assets(offline=offline)
        except Exception as exc:
            # The national balance remains useful without a project inventory.
            print(f'Energy asset inventory unavailable: {exc}', flush=True)
        model, _ = build(as_of, output_dir=directory)
        status.update(status='updated', model_id=model['model_id'], as_of=model['as_of'],
                      warnings=model['warnings'])
    except Exception as exc:
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}'[:400],
                      last_success_as_of=previous.get('as_of'), model_id=previous.get('model_id'))
        print(f'::warning title=Energy companion refresh failed::{status["error"]}', flush=True)
    atomic_json(directory / 'energy_refresh_status.json', status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--as-of', type=date.fromisoformat)
    parser.add_argument('--optional', action='store_true', help='Retain the last energy results and allow the existing World Model lane to continue after a recorded failure')
    args = parser.parse_args()
    status = refresh(args.as_of, offline=args.offline)
    return 0 if status['status'] == 'updated' or args.optional else 1


if __name__ == '__main__':
    raise SystemExit(main())
