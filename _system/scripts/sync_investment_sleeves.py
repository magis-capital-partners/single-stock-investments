#!/usr/bin/env python3
"""Sync investment_sleeves.json membership into registry.json classification.investment_sleeve."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import CLASS_PATH, REGISTRY_PATH, load_registry, save_registry

ROOT = Path(__file__).resolve().parents[2]
SLEEVES_PATH = ROOT / "_system" / "portfolio" / "investment_sleeves.json"


def load_sleeve_index() -> dict[str, str]:
    doc = json.loads(SLEEVES_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for sleeve_id, meta in (doc.get("sleeves") or {}).items():
        for ticker in meta.get("tickers") or []:
            out[str(ticker).upper()] = sleeve_id
    return out


def main() -> None:
    sleeve_index = load_sleeve_index()
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    updated = 0
    missing: list[str] = []

    for ticker in sorted(holdings.keys()):
        sleeve = sleeve_index.get(ticker.upper())
        if not sleeve:
            missing.append(ticker)
            continue
        cls = holdings[ticker].setdefault("classification", {})
        if cls.get("investment_sleeve") != sleeve:
            cls["investment_sleeve"] = sleeve
            updated += 1

    save_registry(reg)

    # Refresh classification.json from registry
    out: dict[str, dict] = {}
    for ticker, h in sorted(holdings.items()):
        from portfolio_registry import DEFAULT_CLASSIFICATION

        cls = {**DEFAULT_CLASSIFICATION, **(h.get("classification") or {})}
        if h.get("predictive_attribute"):
            cls["predictive_attribute"] = h["predictive_attribute"]
        out[ticker] = cls
    CLASS_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"Synced sleeves: {updated} registry updates, {len(sleeve_index)} mapped tickers")
    if missing:
        print(f"WARNING: {len(missing)} tickers without sleeve: {', '.join(missing)}")


if __name__ == "__main__":
    main()
