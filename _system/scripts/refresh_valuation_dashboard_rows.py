#!/usr/bin/env python3
"""Refresh only valuation surfaces in existing dashboard bundles.

This avoids rebuilding unrelated document, market, and portfolio catalogs when
the change is limited to valuation and committee research artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path

from build_dashboard_data import ROOT, valuation_component_summary, valuation_workbench_summary

DEFAULT_TICKERS = ("TPL", "LB", "WBI", "AZLCZ", "MSB", "C", "NVR", "NUE", "BIIB")


def refresh(path: Path, tickers: tuple[str, ...] = DEFAULT_TICKERS) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    wanted = set(tickers)
    updated = 0
    for row in data.get("tickers") or []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in wanted:
            continue
        ticker_dir = ROOT / ticker
        row["valuation_workbench"] = valuation_workbench_summary(ticker_dir)
        row["component_valuation"] = valuation_component_summary(ticker_dir)
        updated += 1
    missing = wanted - {str(row.get("ticker") or "").upper() for row in data.get("tickers") or []}
    if missing:
        raise ValueError(f"dashboard bundle is missing cohort tickers: {sorted(missing)}")
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return updated


def main() -> int:
    for path in (ROOT / "dashboard" / "data" / "dashboard_data.json", ROOT / "docs" / "data" / "dashboard_data.json"):
        if path.exists():
            print(f"{path.relative_to(ROOT)}: {refresh(path)} valuation rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
