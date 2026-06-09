#!/usr/bin/env python3
"""Validate dashboard_data.json against registry holdings and deep dive files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "dashboard" / "data" / "dashboard_data.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not DATA_PATH.exists():
        print(f"ERROR: missing {DATA_PATH}", file=sys.stderr)
        return 1

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    holdings = sorted((registry.get("holdings") or {}).keys())
    rows = payload.get("tickers") or []
    dash_tickers = [r.get("ticker") for r in rows]

    for pseudo in dash_tickers:
        if not pseudo or pseudo.startswith("_"):
            errors.append(f"pseudo-ticker in dashboard: {pseudo}")

    missing = sorted(set(holdings) - set(dash_tickers))
    extra = sorted(set(dash_tickers) - set(holdings))
    if missing:
        errors.append(f"registry holdings missing from dashboard: {', '.join(missing)}")
    if extra:
        errors.append(f"dashboard tickers not in registry: {', '.join(extra)}")

    for row in rows:
        ticker = row.get("ticker")
        if not ticker or ticker.startswith("_"):
            continue
        research = ROOT / ticker / "research"
        dive_files = sorted(research.glob("deep_dive_*.md")) if research.is_dir() else []
        dd = row.get("deep_dive")
        if dive_files and not dd:
            errors.append(f"{ticker}: deep_dive_*.md on disk but deep_dive missing in JSON")
        elif dive_files and dd:
            latest = max(dive_files, key=lambda p: p.name)
            expected = str(latest.relative_to(ROOT)).replace("\\", "/")
            if dd.get("path") != expected:
                errors.append(f"{ticker}: stale deep_dive path {dd.get('path')} (expected {expected})")
            if not dd.get("github_url"):
                errors.append(f"{ticker}: deep_dive missing github_url")
            if not dd.get("executive_summary"):
                warnings.append(f"{ticker}: deep_dive has no executive_summary")

        lenses = row.get("lenses")
        ds = row.get("decision_summary")
        if lenses and not ds:
            errors.append(f"{ticker}: lenses present but decision_summary missing")
        elif ds:
            for key in (
                "stance",
                "stance_source",
                "house_irr_pct",
                "lens_blend_pct",
                "agreement_pct",
                "as_of",
            ):
                if key not in ds:
                    errors.append(f"{ticker}: decision_summary missing key {key}")
        if lenses is not None and "active_lenses" not in row:
            errors.append(f"{ticker}: lenses present but active_lenses missing")
        if lenses is not None and "silent_lens_count" not in row:
            errors.append(f"{ticker}: lenses present but silent_lens_count missing")

        onboard = row.get("onboard") or {}
        if onboard.get("deep_dive_pending") is False and dive_files and not dd:
            errors.append(f"{ticker}: onboard marks deep dive complete but JSON has no deep_dive")

    for msg in warnings:
        print(f"WARN: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}", file=sys.stderr)

    if errors:
        return 1
    print(f"OK: {len(holdings)} holdings, {len(rows)} dashboard rows validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
