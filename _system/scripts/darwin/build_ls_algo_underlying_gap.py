#!/usr/bin/env python3
"""Create a deterministic LS-algo-underlying intake queue from its screener."""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from darwin.external_sources import ls_algo_screened_csv
from portfolio_registry import ROOT, load_registry

OUT = ROOT / "_system" / "data" / "ls_algo_underlying_gap.json"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
IGNORED = {"", "N/A", "NA", "NONE", "NULL", "CASH", "USD"}


def normalize(value: object) -> str:
    symbol = str(value or "").strip().upper().replace(" ", "")
    return symbol if symbol not in IGNORED and TICKER_RE.fullmatch(symbol) else ""


def first(row: dict[str, str], *keys: str) -> str:
    lookup = {str(k).strip().lower(): str(v or "").strip() for k, v in row.items()}
    for key in keys:
        if lookup.get(key.lower()):
            return lookup[key.lower()]
    return ""


def build() -> dict:
    source = ls_algo_screened_csv()
    if source is None:
        raise SystemExit("ls-algo screener is unavailable; clone _external/ls-algo first")
    registry = load_registry()
    known = {str(t).upper() for t in (registry.get("holdings") or {})} | {str(t).upper() for t in (registry.get("watchlist") or {})}
    rows: dict[str, dict] = {}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = normalize(first(row, "Underlying", "underlying", "Ticker", "Symbol"))
            if not ticker:
                continue
            rows.setdefault(ticker, {"ticker": ticker, "company": first(row, "Company", "Name", "Underlying Name") or ticker})
    candidates = [rows[ticker] | {"status": "already_registered" if ticker in known else "pending_onboard"} for ticker in sorted(rows)]
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "universe_count": len(candidates),
        "already_registered": sum(row["status"] == "already_registered" for row in candidates),
        "pending_onboard": sum(row["status"] == "pending_onboard" for row in candidates),
        "candidates": candidates,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = build()
    print(f"ls-algo gap: {result['universe_count']} names; {result['pending_onboard']} pending onboard")
