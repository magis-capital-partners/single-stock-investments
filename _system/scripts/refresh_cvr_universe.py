#!/usr/bin/env python3
"""Refresh CVR universe → sleeve membership → registry classification.

  python _system/scripts/refresh_cvr_universe.py
  python _system/scripts/refresh_cvr_universe.py --discover
  python _system/scripts/refresh_cvr_universe.py --ingest-csv path/to/screener.csv

Reads `_system/reference/cvr/cvr_universe.json` and per-ticker `research/cvr_terms.json`.
Syncs `investment_sleeves.json` sleeve `cvr_contingent`, ensures registry holdings
exist for universe tickers, then runs `sync_investment_sleeves.py`.

Discovery (--discover) queries SEC EDGAR full-text for recent CVR mentions and
appends new pre-close candidates (context tier until terms are filled).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import (  # noqa: E402
    DEFAULT_CLASSIFICATION,
    EXCHANGE_META,
    load_registry,
    save_registry,
)

UNIVERSE_PATH = ROOT / "_system" / "reference" / "cvr" / "cvr_universe.json"
SLEEVES_PATH = ROOT / "_system" / "portfolio" / "investment_sleeves.json"
UA = "MarvinResearchBot/1.0 (single-stock-investments; cvr-refresh; contact: local)"
SEC_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"


def _today() -> str:
    return date.today().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_universe() -> dict:
    if not UNIVERSE_PATH.exists():
        return {
            "as_of": _today(),
            "operating_model": {},
            "pre_close_opportunities": [],
            "post_close_universe": [],
            "discovery_feeds": [],
        }
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def save_universe(doc: dict) -> None:
    doc["as_of"] = _today()
    doc["last_refresh_utc"] = _utc_now()
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def universe_tickers(doc: dict) -> list[str]:
    out: list[str] = []
    for row in doc.get("pre_close_opportunities") or []:
        t = str(row.get("ticker") or "").strip()
        if t and t not in out:
            out.append(t)
    for row in doc.get("post_close_universe") or []:
        t = str(row.get("ticker") or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def sync_sleeve_membership(doc: dict) -> list[str]:
    tickers = sorted(universe_tickers(doc), key=str.upper)
    sleeves = json.loads(SLEEVES_PATH.read_text(encoding="utf-8"))
    sleeve = (sleeves.setdefault("sleeves", {})).setdefault(
        "cvr_contingent",
        {
            "label": "CVRs",
            "description": "Pre-close contingent deals and post-close CVR claims",
            "tickers": [],
        },
    )
    sleeve["label"] = "CVRs"
    sleeve["tickers"] = tickers
    SLEEVES_PATH.write_text(json.dumps(sleeves, indent=2) + "\n", encoding="utf-8")
    return tickers


def ensure_registry_entries(tickers: list[str], doc: dict) -> int:
    """Add missing holdings rows so dashboard list_tickers() includes CVR names."""
    reg = load_registry()
    holdings = reg.setdefault("holdings", {})
    by_ticker = {
        str(r.get("ticker") or "").upper(): r
        for r in (doc.get("pre_close_opportunities") or [])
        + (doc.get("post_close_universe") or [])
    }
    added = 0
    for ticker in tickers:
        if ticker in holdings:
            cls = holdings[ticker].setdefault("classification", {})
            if cls.get("investment_sleeve") != "cvr_contingent":
                cls["investment_sleeve"] = "cvr_contingent"
                cls.setdefault("payoff_lens", "event")
            continue
        urow = by_ticker.get(ticker.upper()) or {}
        stage = urow.get("stage") or (
            "pre_close" if ticker.upper() == "MFBP" else "post_close"
        )
        company = None
        terms_path = ROOT / ticker / "research" / "cvr_terms.json"
        if terms_path.exists():
            try:
                terms = json.loads(terms_path.read_text(encoding="utf-8"))
                company = terms.get("instrument_label")
            except json.JSONDecodeError:
                company = None
        if not company:
            company = f"{ticker} CVR / contingent"
        holdings[ticker] = {
            "company": company,
            "market": "US",
            "exchange": EXCHANGE_META.get(ticker, "OTC"),
            "onboarded": _today(),
            "download": {"type": "us_shared", "ir_roots": []},
            "classification": {
                **DEFAULT_CLASSIFICATION,
                "investment_sleeve": "cvr_contingent",
                "payoff_lens": "event",
                "irr_method": "binary_milestone" if stage == "post_close" else "scenario",
            },
        }
        added += 1
    if added:
        save_registry(reg)
    else:
        # Still persist sleeve classification updates on existing rows.
        save_registry(reg)
    return added


def refresh_display_fields(doc: dict) -> int:
    """Compute simple display metrics on cvr_terms.json when possible."""
    updated = 0
    for row in (doc.get("pre_close_opportunities") or []) + (
        doc.get("post_close_universe") or []
    ):
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        path = ROOT / ticker / "research" / "cvr_terms.json"
        if not path.exists():
            continue
        try:
            terms = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        max_payout = (
            row.get("max_contingent_usd")
            or row.get("max_payout_usd")
            or terms.get("max_payout_usd")
        )
        display = terms.setdefault("display", {})
        display["as_of"] = _today()
        display["stage"] = row.get("stage") or terms.get("stage")
        display["max_payout_usd"] = max_payout
        # Naive market-implied success only if price already stored on terms.
        price = terms.get("price_live") or display.get("price_live")
        if price is not None and max_payout:
            try:
                p = float(price) / float(max_payout)
                display["p_market"] = round(max(0.0, min(p, 1.0)), 4)
            except (TypeError, ValueError):
                pass
        terms["last_refresh_utc"] = _utc_now()
        path.write_text(json.dumps(terms, indent=2) + "\n", encoding="utf-8")
        updated += 1
    return updated


def _http_get_json(url: str, timeout: int = 45) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"WARN: SEC fetch failed: {exc}")
        return None


def discover_sec_cvrs(doc: dict, *, days: int = 30, limit: int = 25) -> int:
    """Append new pre-close candidates from SEC full-text search (best-effort)."""
    # EDGAR full-text API: forms 8-K with CVR language.
    query = '"Contingent Value Right" OR "CVR Agreement" OR "contingent value rights"'
    params = urllib.parse.urlencode(
        {
            "q": query,
            "dateRange": "custom",
            "startdt": (date.today().fromordinal(date.today().toordinal() - days)).isoformat(),
            "enddt": _today(),
            "forms": "8-K",
        }
    )
    # Public search endpoint used by SEC UI (may rate-limit / change).
    url = f"https://efts.sec.gov/LATEST/search-index?{params}"
    payload = _http_get_json(url)
    if not payload:
        print("WARN: SEC discovery returned no payload; skipping discover")
        return 0

    hits = []
    if isinstance(payload, dict):
        hits = payload.get("hits", {}).get("hits") or payload.get("hits") or []
    if not isinstance(hits, list):
        hits = []

    existing = {str(r.get("ticker") or "").upper() for r in doc.get("pre_close_opportunities") or []}
    existing |= {str(r.get("ticker") or "").upper() for r in doc.get("post_close_universe") or []}
    added = 0
    for hit in hits[:limit]:
        src = hit.get("_source") or hit
        display_tickers = src.get("display_names") or src.get("tickers") or []
        # Prefer equity ticker tokens that look like symbols.
        tickers = []
        for t in display_tickers:
            t = str(t).strip().upper()
            if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z]{1,2})?", t):
                tickers.append(t)
        if not tickers:
            continue
        ticker = tickers[0]
        if ticker in existing:
            continue
        file_url = None
        adsh = src.get("adsh") or src.get("file_num")
        if src.get("file_url"):
            file_url = src["file_url"]
        elif adsh:
            file_url = f"https://www.sec.gov/Archives/edgar/data/{adsh.replace('-', '')}/"
        row = {
            "id": f"{ticker}.CVR_CANDIDATE",
            "ticker": ticker,
            "stage": "pre_close",
            "tradeable_vehicle": ticker,
            "role": "opportunity",
            "source": "sec_full_text",
            "source_tier": "context",
            "discovered_at": _today(),
            "sec_hint": file_url,
            "notes": "Auto-discovered; agent must extract cvr_terms.json from merger exhibits before sizing.",
        }
        doc.setdefault("pre_close_opportunities", []).append(row)
        existing.add(ticker)
        added += 1
        time.sleep(0.15)
    return added


def ingest_screener_csv(doc: dict, csv_path: Path) -> int:
    """Context-tier ingest for AlphaRank / special-sit CSV uploads."""
    if not csv_path.exists():
        print(f"WARN: CSV not found: {csv_path}")
        return 0
    existing = {str(r.get("ticker") or "").upper() for r in doc.get("pre_close_opportunities") or []}
    existing |= {str(r.get("ticker") or "").upper() for r in doc.get("post_close_universe") or []}
    added = 0
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticker = (
                row.get("ticker")
                or row.get("Ticker")
                or row.get("symbol")
                or row.get("Symbol")
                or ""
            ).strip().upper()
            if not ticker or ticker in existing:
                continue
            cvr_flag = (
                row.get("cvr")
                or row.get("CVR")
                or row.get("has_cvr")
                or row.get("consideration")
                or ""
            )
            text = " ".join(str(v) for v in row.values()).lower()
            if "cvr" not in text and str(cvr_flag).lower() not in ("1", "true", "yes", "y"):
                continue
            doc.setdefault("pre_close_opportunities", []).append(
                {
                    "id": f"{ticker}.CVR_CANDIDATE",
                    "ticker": ticker,
                    "stage": "pre_close",
                    "tradeable_vehicle": ticker,
                    "role": "opportunity",
                    "source": "screener_csv",
                    "source_tier": "context",
                    "discovered_at": _today(),
                    "notes": f"Ingested from {csv_path.name}; confirm with SEC primary docs.",
                }
            )
            existing.add(ticker)
            added += 1
    return added


def run_sync_investment_sleeves() -> None:
    subprocess.check_call([sys.executable, str(SCRIPTS / "sync_investment_sleeves.py")], cwd=str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--discover", action="store_true", help="Query SEC for new CVR 8-K mentions")
    ap.add_argument("--ingest-csv", type=Path, help="Optional screener CSV (context tier)")
    ap.add_argument("--skip-sync", action="store_true", help="Do not run sync_investment_sleeves.py")
    ap.add_argument("--discover-days", type=int, default=30)
    args = ap.parse_args()

    doc = load_universe()
    discovered = 0
    if args.discover:
        discovered = discover_sec_cvrs(doc, days=args.discover_days)
        print(f"SEC discover: +{discovered} pre-close candidates")
    if args.ingest_csv:
        n = ingest_screener_csv(doc, args.ingest_csv)
        print(f"CSV ingest: +{n} pre-close candidates")
        discovered += n

    tickers = sync_sleeve_membership(doc)
    print(f"Sleeve cvr_contingent: {len(tickers)} tickers -> {', '.join(tickers)}")
    added = ensure_registry_entries(tickers, doc)
    print(f"Registry: +{added} holdings entries (sleeve classification refreshed)")
    refreshed = refresh_display_fields(doc)
    print(f"Terms display refresh: {refreshed} files")
    save_universe(doc)

    if not args.skip_sync:
        run_sync_investment_sleeves()
        print("Ran sync_investment_sleeves.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
