"""Reconcile trusted registry additions before consuming restored coverage."""
from __future__ import annotations

import json
import subprocess
import sys


def ensure_registered_coverage(root):
    registry = root / '_system/portfolio/registry.json'
    core = root / 'dashboard/data/core.json'
    if not registry.is_file() or not core.is_file():
        return  # The normal consumer reports missing coverage/configuration.
    holdings = json.loads(registry.read_text(encoding='utf-8'))
    snapshot = json.loads(core.read_text(encoding='utf-8'))
    if holdings.get('private_snapshot') or snapshot.get('private_snapshot'):
        raise ValueError('Restore authorized private coverage inputs before synchronizing listings')
    if set(holdings.get('holdings') or {}) - {r['ticker'] for r in snapshot.get('tickers') or []}:
        subprocess.run([sys.executable, str(root / '_system/scripts/build_dashboard_data.py'),
                        '--coverage-additions-only'], cwd=root, check=True, timeout=120)
