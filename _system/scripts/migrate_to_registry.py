#!/usr/bin/env python3
"""One-time backfill: build registry.json from holdings.md, classification.json, us_ticker_config."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import (
    CLASS_PATH,
    EXCHANGE_META,
    HOLDINGS_PATH,
    REGISTRY_PATH,
    ROOT,
    US_CONFIG_PATH,
    build_download_block,
    save_registry,
)

SKIP_DIRS = {"_system", "dashboard", ".git", ".github", ".cursor"}


def parse_holdings_table() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    if not HOLDINGS_PATH.exists():
        return meta
    in_table = False
    for line in HOLDINGS_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.startswith("| Ticker |"):
            in_table = True
            continue
        if not in_table or not line.startswith("|") or line.startswith("|--------"):
            continue
        parts = [c.strip() for c in line.split("|")[1:-1]]
        if len(parts) >= 4 and parts[0] not in ("—", "-"):
            meta[parts[0]] = {
                "company": parts[2],
                "market": parts[3],
                "last_download": parts[4] if len(parts) > 4 and parts[4] not in ("—", "-") else None,
                "last_research": parts[5] if len(parts) > 5 and parts[5] not in ("—", "-") else None,
            }
    return meta


def list_ticker_folders() -> list[str]:
    return sorted(
        p.name
        for p in ROOT.iterdir()
        if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")
    )


def main() -> None:
    holdings = parse_holdings_table()
    classification = json.loads(CLASS_PATH.read_text(encoding="utf-8")) if CLASS_PATH.exists() else {}
    us_config = json.loads(US_CONFIG_PATH.read_text(encoding="utf-8")) if US_CONFIG_PATH.exists() else {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    registry_holdings: dict[str, dict] = {}
    for ticker in list_ticker_folders():
        h = holdings.get(ticker, {})
        company = h.get("company") or ticker
        market = h.get("market") or "US"
        cls = classification.get(ticker, {})
        entry = {
            "company": company,
            "market": market,
            "exchange": EXCHANGE_META.get(ticker, "—"),
            "onboarded": h.get("last_research") or h.get("last_download") or today,
            "download": build_download_block(ticker, market, us_config),
            "classification": {**cls} if cls else {},
        }
        if "predictive_attribute" in cls:
            entry["predictive_attribute"] = cls["predictive_attribute"]
        registry_holdings[ticker] = entry

    data = {
        "meta": {"version": 1, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "holdings": registry_holdings,
        "watchlist": {},
    }
    save_registry(data)
    print(f"Wrote {REGISTRY_PATH} with {len(registry_holdings)} holdings")


if __name__ == "__main__":
    main()
