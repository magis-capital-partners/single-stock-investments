#!/usr/bin/env python3
"""Refresh only valuation surfaces in existing dashboard bundles.

This avoids rebuilding unrelated document, market, and portfolio catalogs when
the change is limited to valuation and committee research artifacts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from build_dashboard_data import (
    ROOT,
    investment_committee_summary,
    latest_deep_dive,
    load_power_zones,
    power_zones_for_ticker,
    property_register_summary,
    valuation_component_summary,
    valuation_decision_summary,
    valuation_queue_summary,
    valuation_workbench_summary,
)

DEFAULT_TICKERS = ("TPL", "LB", "WBI", "AZLCZ", "MSB", "C", "NVR", "NUE", "BIIB")
PROPERTY_SEED_TICKERS = ("STHO", "TPL", "LAND", "PCYO", "CDZI")
FOLLOWUPS = ROOT / "_system" / "reference" / "valuation_followups.json"


def cohort_tickers() -> tuple[str, ...]:
    if not FOLLOWUPS.exists():
        return DEFAULT_TICKERS
    try:
        doc = json.loads(FOLLOWUPS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_TICKERS
    names = set(DEFAULT_TICKERS)
    names.update(PROPERTY_SEED_TICKERS)
    for ticker, cfg in (doc.get("tickers") or {}).items():
        # Refresh any ticker that already has a workbench or is in the queue.
        ticker_dir = ROOT / ticker
        if (ticker_dir / "research" / "valuation_workbench.json").exists() or cfg.get("rollout_wave"):
            names.add(ticker)
        if (ticker_dir / "research" / "properties.json").exists():
            names.add(ticker)
    for row in doc.get("validation_cohort") or []:
        if row.get("ticker"):
            names.add(str(row["ticker"]))
    return tuple(sorted(names))


def refresh(path: Path, tickers: tuple[str, ...] | None = None) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    targeted = tickers is not None
    wanted = {ticker.upper() for ticker in (tickers or cohort_tickers())}
    # Always refresh decision summary for every row that has followups / workbench / CV.
    updated = 0
    for row in data.get("tickers") or []:
        ticker = str(row.get("ticker") or "")
        ticker_key = ticker.upper()
        ticker_dir = ROOT / ticker
        has_wb = (ticker_dir / "research" / "valuation_workbench.json").exists()
        has_props = (ticker_dir / "research" / "properties.json").exists()
        has_deep_dive = any((ticker_dir / "research").glob("deep_dive_*.md"))
        if has_deep_dive and (not targeted or ticker_key in wanted):
            row["deep_dive"] = latest_deep_dive(ticker_dir, row.get("classification") or {})
        if (targeted and ticker_key in wanted) or (not targeted and (ticker_key in wanted or has_wb or has_props)):
            if has_wb or ticker_key in {t.upper() for t in DEFAULT_TICKERS}:
                row["valuation_workbench"] = valuation_workbench_summary(ticker_dir)
                row["component_valuation"] = valuation_component_summary(ticker_dir)
            if has_props:
                row["properties"] = property_register_summary(ticker_dir)
            row["valuation_decision"] = valuation_decision_summary(
                ticker,
                ticker_dir,
                workbench=row.get("valuation_workbench"),
                component=row.get("component_valuation"),
            )
            row["investment_committee"] = investment_committee_summary(ticker_dir)
            row["power_zones"] = power_zones_for_ticker(ticker)
            updated += 1
        elif not targeted and (row.get("component_valuation") or row.get("valuation_workbench") or row.get("valuation_decision")):
            row["valuation_decision"] = valuation_decision_summary(
                ticker,
                ticker_dir,
                workbench=row.get("valuation_workbench"),
                component=row.get("component_valuation"),
            )
            updated += 1
    summary = data.setdefault("summary", {})
    summary.pop("onboard_workflow", None)
    summary.pop("onboard_dispatch_event", None)
    summary["universe_intake_workflow"] = "ls-algo-universe.yml"
    summary["universe_intake_dispatch_event"] = "sync-ls-algo-universe"
    if not targeted:
        data["valuation_queue"] = valuation_queue_summary(data.get("tickers") or [])
        counts = (data["valuation_queue"] or {}).get("counts") or {}
        summary["valuation_queue_tickers"] = counts.get("tickers")
        summary["valuation_evidence_blocked"] = counts.get("evidence_blocked")
        summary["valuation_critical_gaps"] = counts.get("critical_gaps")
    summary["with_property_register"] = sum(
        1 for r in (data.get("tickers") or []) if r.get("properties")
    )
    # The UI consumes this embedded copy, not dashboard/data/power_zones.json
    # directly.  Keep it synchronized even when we intentionally avoid a full
    # dashboard rebuild.
    power_zones = load_power_zones()
    if power_zones:
        data["power_zones"] = power_zones
    data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return updated


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*", type=str.upper, help="Refresh only named ticker rows.")
    args = parser.parse_args()
    # Preserve the distinction between no --tickers flag (refresh every
    # materialized deep dive plus the valuation cohort) and an explicit list.
    tickers = tuple(args.tickers) if args.tickers is not None else None
    for path in (ROOT / "dashboard" / "data" / "dashboard_data.json", ROOT / "docs" / "data" / "dashboard_data.json"):
        if path.exists():
            print(f"{path.relative_to(ROOT)}: {refresh(path, tickers)} valuation rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
