#!/usr/bin/env python3
"""CLI wrapper: archive harvest is automatic inside build_index_membership.py.

Use this only for a one-off dry run without rebuilding scorecards.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_index_membership import harvest_archive_announcements, load_json  # noqa: E402

REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
SEED = ROOT / "_system" / "data" / "index_memberships_seed.json"


def main() -> int:
    registry = load_json(REGISTRY, {"holdings": {}})
    holdings = registry.get("holdings") or {}
    company_names = {t: (h.get("company") or "") for t, h in holdings.items()}
    seed = load_json(SEED, {"by_ticker": {}})
    added = harvest_archive_announcements(
        seed=seed,
        company_names=company_names,
        holdings_tickers=set(holdings),
    )
    print(f"archive_harvested={len(added)}")
    for row in added:
        print(f"+ {row['ticker']} {row['action']} {row['index']} | {(row.get('title') or '')[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
