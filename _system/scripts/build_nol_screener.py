#!/usr/bin/env python3
"""Build NOL carryforward screener JSON for dashboard Watchlist tab.

Reads seed candidates + SEC XBRL company facts (deferred tax assets / valuation allowance).
Marks rows already in registry holdings or watchlist.

Usage:
  python _system/scripts/build_nol_screener.py
  python _system/scripts/build_nol_screener.py --write
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "_system" / "reference" / "market-data" / "screens" / "nol_seed.csv"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "nol_screener.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# XBRL tags seen on 10-K balance sheets / tax footnotes
DTA_TAGS = (
    "DeferredTaxAssetsGross",
    "DeferredTaxAssetsNet",
    "DeferredIncomeTaxAssetsNet",
    "DeferredTaxAssets",
)
ALLOWANCE_TAGS = (
    "ValuationAllowanceDeferredTaxAssets",
    "DeferredTaxAssetsValuationAllowance",
)


def load_registry_sets() -> tuple[set[str], set[str]]:
    if not REGISTRY_PATH.exists():
        return set(), set()
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    holdings = set((reg.get("holdings") or {}).keys())
    watchlist = set((reg.get("watchlist") or {}).keys())
    return holdings, watchlist


def load_seed_rows() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    rows = []
    with SEED_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "company": (row.get("company") or ticker).strip(),
                    "market": (row.get("market") or "US").strip().upper(),
                    "notes": (row.get("notes") or "").strip(),
                    "source": "seed",
                }
            )
    return rows


def fetch_sec_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def load_cik_map() -> dict[str, str]:
    data = fetch_sec_json(SEC_TICKERS_URL)
    if not data:
        return {}
    out: dict[str, str] = {}
    for row in data.values():
        t = str(row.get("ticker", "")).upper()
        cik = str(row.get("cik_str", "")).zfill(10)
        if t and cik:
            out[t] = cik
    return out


def latest_usd_fact(facts: dict, tags: tuple[str, ...]) -> tuple[float | None, str | None]:
    """Return most recent USD fact value and filing date across tag variants."""
    best_date = ""
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        block = us_gaap.get(tag)
        if not block:
            continue
        units = block.get("units", {})
        for unit_key, entries in units.items():
            if "USD" not in unit_key.upper():
                continue
            for entry in entries or []:
                if entry.get("form") not in ("10-K", "10-Q", None):
                    if entry.get("form") and not str(entry["form"]).startswith("10-"):
                        continue
                end = str(entry.get("end") or "")
                val = entry.get("val")
                if val is None or not end:
                    continue
                if end >= best_date:
                    best_date = end
                    best_val = float(val)
    return best_val, best_date or None


def screen_ticker(ticker: str, cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = fetch_sec_json(url)
    if not data:
        return {"sec_error": "companyfacts unavailable"}
    dta, dta_date = latest_usd_fact(data, DTA_TAGS)
    allowance, _ = latest_usd_fact(data, ALLOWANCE_TAGS)
    realizable = None
    if dta is not None and allowance is not None:
        realizable = max(0.0, dta - allowance)
    elif dta is not None:
        realizable = dta
    return {
        "cik": cik,
        "dta_gross_usd": dta,
        "valuation_allowance_usd": allowance,
        "dta_realizable_usd": realizable,
        "filing_as_of": dta_date,
        "sec_entity": data.get("entityName"),
    }


def fmt_usd_mm(val: float | None) -> str | None:
    if val is None:
        return None
    return f"${val / 1_000_000:.1f}M"


def build_rows() -> list[dict]:
    holdings, watchlist = load_registry_sets()
    cik_map = load_cik_map()
    seen: set[str] = set()
    out: list[dict] = []

    for seed in load_seed_rows():
        ticker = seed["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)

        row = {**seed}
        cik = cik_map.get(ticker.split(".")[0])  # ALS.TO → try ALS
        if not cik:
            cik = cik_map.get(ticker)

        sec = {}
        if cik:
            sec = screen_ticker(ticker, cik)
            if sec.get("sec_entity") and not row.get("company"):
                row["company"] = sec["sec_entity"]

        row.update(
            {
                "in_holdings": ticker in holdings,
                "in_watchlist": ticker in watchlist,
                "dta_gross_usd": sec.get("dta_gross_usd"),
                "valuation_allowance_usd": sec.get("valuation_allowance_usd"),
                "dta_realizable_usd": sec.get("dta_realizable_usd"),
                "dta_gross_display": fmt_usd_mm(sec.get("dta_gross_usd")),
                "dta_realizable_display": fmt_usd_mm(sec.get("dta_realizable_usd")),
                "filing_as_of": sec.get("filing_as_of"),
                "cik": sec.get("cik"),
                "sec_error": sec.get("sec_error"),
                "screen_status": "ok" if sec.get("dta_gross_usd") is not None else "pending_sec",
            }
        )
        out.append(row)

    # Sort: realizable DTA desc, then ticker
    out.sort(
        key=lambda r: (
            -(r.get("dta_realizable_usd") or r.get("dta_gross_usd") or 0),
            r["ticker"],
        ),
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NOL carryforward screener JSON")
    parser.add_argument("--write", action="store_true", help="Write dashboard/data/nol_screener.json")
    args = parser.parse_args()

    rows = build_rows()
    payload = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": (
            "Deferred tax assets (us-gaap) from SEC companyfacts; "
            "realizable ≈ gross DTA − valuation allowance. "
            "Seed list in _system/reference/market-data/screens/nol_seed.csv."
        ),
        "seed_path": str(SEED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "rows": rows,
    }

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUTPUT} ({len(rows)} rows)")
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
