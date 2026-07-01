#!/usr/bin/env python3
"""Build NOL carryforward screener JSON for dashboard Watchlist tab.

Reads seed candidates + SEC XBRL company facts (deferred tax assets / valuation allowance).
Market cap = SEC shares outstanding × Yahoo chart price (v7 quote API is blocked).
Marks rows already in registry holdings or watchlist.

Usage:
  python _system/scripts/build_nol_screener.py
  python _system/scripts/build_nol_screener.py --write
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "_system" / "reference" / "market-data" / "screens" / "nol_seed.csv"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "nol_screener.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
YAHOO_UA = "MarvinResearch/1.0 (nol-screener)"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# XBRL tags seen on 10-K balance sheets / tax footnotes
DTA_TAGS = (
    "DeferredTaxAssetsGross",
    "DeferredTaxAssetsNet",
    "DeferredIncomeTaxAssetsNet",
    "DeferredTaxAssets",
)
NOL_DTA_TAGS = ("DeferredTaxAssetsOperatingLossCarryforwards",)
OPERATING_LOSS_TAGS = ("OperatingLossCarryforwards",)
ALLOWANCE_TAGS = (
    "ValuationAllowanceDeferredTaxAssets",
    "DeferredTaxAssetsValuationAllowance",
)
SHARES_TAGS = (
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
)
CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
DEBT_TAGS = (
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "DebtInstrumentCarryingAmount",
    "ShortTermBorrowings",
)

CAP_BUCKETS = (
    ("micro", 300_000_000),
    ("small", 2_000_000_000),
    ("mid", 10_000_000_000),
    ("large", None),
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
                    "cap_tier_seed": (row.get("cap_tier") or "").strip().lower(),
                    "notes": (row.get("notes") or "").strip(),
                    "source": "seed",
                }
            )
    return rows


def fetch_json(url: str, ua: str = SEC_UA) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def load_cik_map() -> dict[str, str]:
    data = fetch_json(SEC_TICKERS_URL)
    if not data:
        return {}
    out: dict[str, str] = {}
    for row in data.values():
        t = str(row.get("ticker", "")).upper()
        cik = str(row.get("cik_str", "")).zfill(10)
        if t and cik:
            out[t] = cik
    return out


def _pick_best_entry(entries: list[dict]) -> tuple[float | None, str | None]:
    best_date = ""
    best_val: float | None = None
    for entry in entries or []:
        form = entry.get("form")
        if form not in ("10-K", "10-Q", None):
            if form and not str(form).startswith("10-"):
                continue
        end = str(entry.get("end") or "")
        val = entry.get("val")
        if val is None or not end:
            continue
        if end >= best_date:
            best_date = end
            best_val = float(val)
    return best_val, best_date or None


def latest_usd_fact(facts: dict, tags: tuple[str, ...]) -> tuple[float | None, str | None]:
    """Return most recent USD fact value and period end across tag variants."""
    best_date = ""
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        block = us_gaap.get(tag)
        if not block:
            continue
        for unit_key, entries in (block.get("units") or {}).items():
            if "USD" not in unit_key.upper():
                continue
            val, end = _pick_best_entry(entries)
            if val is not None and end and end >= best_date:
                best_date = end
                best_val = val
    return best_val, best_date or None


def latest_shares_fact(facts: dict) -> tuple[float | None, str | None]:
    """Return most recent shares-outstanding fact (unit contains 'share')."""
    best_date = ""
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in SHARES_TAGS:
        block = us_gaap.get(tag)
        if not block:
            continue
        for unit_key, entries in (block.get("units") or {}).items():
            if "share" not in unit_key.lower():
                continue
            val, end = _pick_best_entry(entries)
            if val is not None and end and end >= best_date:
                best_date = end
                best_val = val
    return best_val, best_date or None


def fetch_yahoo_price(symbol: str) -> tuple[float | None, str | None]:
    """Latest regular market price from Yahoo chart API."""
    url = f"{YAHOO_CHART_URL}/{symbol}?interval=1d&range=5d"
    data = fetch_json(url, ua=YAHOO_UA)
    if not data:
        return None, None
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        if price is not None:
            return float(price), str(meta.get("currency") or "USD")
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return None, None


def compute_realizable(dta: float | None, allowance: float | None) -> float | None:
    if dta is None:
        return None
    if allowance is not None:
        return max(0.0, dta - allowance)
    return dta


def screen_ticker(ticker: str, cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = fetch_json(url)
    if not data:
        return {"sec_error": "companyfacts unavailable"}

    dta, dta_date = latest_usd_fact(data, DTA_TAGS)
    allowance, _ = latest_usd_fact(data, ALLOWANCE_TAGS)
    nol_dta, _ = latest_usd_fact(data, NOL_DTA_TAGS)
    operating_loss, _ = latest_usd_fact(data, OPERATING_LOSS_TAGS)
    shares, shares_date = latest_shares_fact(data)
    cash, _ = latest_usd_fact(data, CASH_TAGS)
    debt_long, _ = latest_usd_fact(data, ("LongTermDebtNoncurrent", "LongTermDebt"))
    debt_short, _ = latest_usd_fact(data, ("ShortTermBorrowings", "DebtCurrent"))

    realizable = compute_realizable(dta, allowance)
    total_debt = None
    if debt_long is not None or debt_short is not None:
        total_debt = (debt_long or 0.0) + (debt_short or 0.0)

    allowance_pct = None
    if dta and dta > 0 and allowance is not None:
        allowance_pct = round(100.0 * allowance / dta, 1)

    return {
        "cik": cik,
        "dta_gross_usd": dta,
        "valuation_allowance_usd": allowance,
        "dta_realizable_usd": realizable,
        "nol_dta_usd": nol_dta,
        "operating_loss_carryforward_usd": operating_loss,
        "allowance_pct": allowance_pct,
        "shares_outstanding": shares,
        "shares_as_of": shares_date,
        "cash_usd": cash,
        "total_debt_usd": total_debt,
        "filing_as_of": dta_date,
        "sec_entity": data.get("entityName"),
    }


def cap_bucket_from_mcap(mcap: float | None) -> str | None:
    if mcap is None or mcap <= 0:
        return None
    for name, ceiling in CAP_BUCKETS:
        if ceiling is None or mcap < ceiling:
            return name
    return "large"


def fmt_usd_mm(val: float | None) -> str | None:
    if val is None:
        return None
    return f"${val / 1_000_000:.1f}M"


def fmt_mcap(val: float | None) -> str | None:
    if val is None:
        return None
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    return f"${val / 1_000_000:.0f}M"


def fmt_pct(val: float | None) -> str | None:
    if val is None:
        return None
    return f"{val:.1f}%"


def fmt_per_share(val: float | None) -> str | None:
    if val is None:
        return None
    if val >= 1:
        return f"${val:.2f}"
    return f"${val:.3f}"


def enrich_metrics(
    sec: dict,
    price: float | None,
    mcap: float | None,
) -> dict:
    realizable = sec.get("dta_realizable_usd")
    shares = sec.get("shares_outstanding")
    cash = sec.get("cash_usd")
    debt = sec.get("total_debt_usd")

    dta_per_share = None
    if realizable is not None and shares and shares > 0:
        dta_per_share = realizable / shares

    dta_to_mcap_pct = None
    if realizable is not None and mcap and mcap > 0:
        dta_to_mcap_pct = round(100.0 * realizable / mcap, 1)

    enterprise_value = None
    dta_to_ev_pct = None
    if mcap is not None and mcap > 0:
        enterprise_value = mcap + (debt or 0.0) - (cash or 0.0)
        if enterprise_value > 0 and realizable is not None:
            dta_to_ev_pct = round(100.0 * realizable / enterprise_value, 1)

    fully_reserved = (
        sec.get("dta_gross_usd") is not None
        and sec.get("dta_gross_usd", 0) > 0
        and (realizable is None or realizable <= 0)
    )
    is_actionable = (
        realizable is not None
        and realizable > 0
        and not fully_reserved
    )

    return {
        "price_usd": price,
        "market_cap_usd": mcap,
        "market_cap_display": fmt_mcap(mcap),
        "enterprise_value_usd": enterprise_value if enterprise_value and enterprise_value > 0 else None,
        "dta_per_share_usd": dta_per_share,
        "dta_per_share_display": fmt_per_share(dta_per_share),
        "dta_to_mcap_pct": dta_to_mcap_pct,
        "dta_to_mcap_display": fmt_pct(dta_to_mcap_pct),
        "dta_to_ev_pct": dta_to_ev_pct,
        "dta_to_ev_display": fmt_pct(dta_to_ev_pct),
        "allowance_pct_display": fmt_pct(sec.get("allowance_pct")),
        "nol_dta_display": fmt_usd_mm(sec.get("nol_dta_usd")),
        "fully_reserved": fully_reserved,
        "is_actionable": is_actionable,
    }


def build_rows() -> list[dict]:
    holdings, watchlist = load_registry_sets()
    seeds = load_seed_rows()
    cik_map = load_cik_map()

    seen: set[str] = set()
    out: list[dict] = []

    for seed in seeds:
        ticker = seed["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)

        row = {**seed}
        base_ticker = ticker.split(".")[0]
        cik = cik_map.get(base_ticker) or cik_map.get(ticker)

        sec: dict = {}
        if cik:
            sec = screen_ticker(ticker, cik)
            if sec.get("sec_entity") and not row.get("company"):
                row["company"] = sec["sec_entity"]
            time.sleep(0.12)

        price, _ = fetch_yahoo_price(base_ticker)
        time.sleep(0.08)
        shares = sec.get("shares_outstanding")
        mcap = None
        if price is not None and shares and shares > 0:
            mcap = price * shares

        cap_bucket = cap_bucket_from_mcap(mcap) or seed.get("cap_tier_seed") or None
        metrics = enrich_metrics(sec, price, mcap)

        row.update(
            {
                "in_holdings": ticker in holdings,
                "in_watchlist": ticker in watchlist,
                "dta_gross_usd": sec.get("dta_gross_usd"),
                "valuation_allowance_usd": sec.get("valuation_allowance_usd"),
                "dta_realizable_usd": sec.get("dta_realizable_usd"),
                "nol_dta_usd": sec.get("nol_dta_usd"),
                "operating_loss_carryforward_usd": sec.get("operating_loss_carryforward_usd"),
                "allowance_pct": sec.get("allowance_pct"),
                "shares_outstanding": shares,
                "shares_as_of": sec.get("shares_as_of"),
                "dta_gross_display": fmt_usd_mm(sec.get("dta_gross_usd")),
                "dta_realizable_display": fmt_usd_mm(sec.get("dta_realizable_usd")),
                "filing_as_of": sec.get("filing_as_of"),
                "cik": sec.get("cik"),
                "sec_error": sec.get("sec_error"),
                "screen_status": "ok" if sec.get("dta_gross_usd") is not None else "pending_sec",
                "cap_bucket": cap_bucket,
                "is_small_cap": cap_bucket in ("micro", "small"),
            }
        )
        row.update(metrics)
        row.pop("cap_tier_seed", None)
        out.append(row)

    bucket_rank = {"micro": 0, "small": 1, "mid": 2, "large": 3}
    out.sort(
        key=lambda r: (
            0 if r.get("is_actionable") else 1,
            bucket_rank.get(r.get("cap_bucket") or "", 9),
            -(r.get("dta_to_mcap_pct") or 0),
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
    small_count = sum(1 for r in rows if r.get("is_small_cap"))
    actionable_count = sum(1 for r in rows if r.get("is_actionable"))
    payload = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": (
            "US deferred tax assets (SEC companyfacts) + market cap (SEC shares × Yahoo chart price). "
            "Realizable DTA ≈ gross − valuation allowance; NOL DTA from DeferredTaxAssetsOperatingLossCarryforwards. "
            "Sorted by actionable realizable DTA / market cap; small/micro caps prioritized for takeover tax-attribute optionality. "
            "Seed: _system/reference/market-data/screens/nol_seed.csv."
        ),
        "seed_path": str(SEED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "small_cap_count": small_count,
        "actionable_count": actionable_count,
        "rows": rows,
    }

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(
            f"Wrote {OUTPUT} ({len(rows)} rows, {small_count} small/micro, "
            f"{actionable_count} actionable)"
        )
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
