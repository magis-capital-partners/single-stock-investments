#!/usr/bin/env python3
"""Build advantaged-banks screener JSON for dashboard Watchlist tab.

Reads seed candidates + SEC XBRL company facts (deposits, equity, income) and
Yahoo chart prices. Marks rows already in registry holdings or watchlist.

Usage:
  python _system/scripts/build_advantaged_banks_screener.py
  python _system/scripts/build_advantaged_banks_screener.py --write
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
SEED_PATH = ROOT / "_system" / "reference" / "market-data" / "screens" / "advantaged_banks_seed.csv"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "advantaged_banks_screener.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
YAHOO_UA = "MarvinResearch/1.0 (advantaged-banks-screener)"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

DEPOSITS_TAGS = ("Deposits",)
NONINTEREST_DEPOSIT_TAGS = (
    "NoninterestBearingDepositLiabilities",
    "NoninterestBearingDeposits",
)
INTEREST_EXPENSE_DEPOSITS_TAGS = (
    "InterestExpenseDeposits",
    "InterestExpenseDepositAccounts",
)
EQUITY_TAGS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
GOODWILL_TAGS = ("Goodwill",)
INTANGIBLE_TAGS = (
    "IntangibleAssetsNetExcludingGoodwill",
    "FiniteLivedIntangibleAssetsNet",
)
INCOME_TAGS = (
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "ProfitLoss",
)
ASSETS_TAGS = ("Assets",)
SHARES_TAGS = (
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
)

# Tunable low-cost franchise flags (Moore #1 buyer attribute)
LOW_COST_DEPOSITS_PCT = 1.5
HIGH_DDA_SHARE_PCT = 30.0

CAP_BUCKETS = (
    ("micro", 300_000_000),
    ("small", 2_000_000_000),
    ("mid", 10_000_000_000),
    ("large", None),
)

EDGE_LABELS = {
    "low_cost_deposits": "Low-cost deposits",
    "baas_fintech": "BaaS / fintech",
    "niche_platform": "Niche platform",
    "niche_community": "Niche community",
}


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
    seen: set[str] = set()
    with SEED_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            edge = (row.get("edge_type") or "").strip().lower()
            rows.append(
                {
                    "ticker": ticker,
                    "company": (row.get("company") or ticker).strip(),
                    "market": (row.get("market") or "US").strip().upper(),
                    "cap_tier_seed": (row.get("cap_tier") or "").strip().lower(),
                    "edge_type": edge,
                    "edge_label": EDGE_LABELS.get(edge, edge.replace("_", " ").title() or "—"),
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


def _pick_best_entry(entries: list[dict], *, prefer_annual: bool = False) -> tuple[float | None, str | None]:
    best_date = ""
    best_val: float | None = None
    best_rank = -1
    for entry in entries or []:
        form = entry.get("form")
        if form not in ("10-K", "10-Q", "20-F", "40-F", None):
            if form and not str(form).startswith(("10-", "20-", "40-")):
                continue
        end = str(entry.get("end") or "")
        val = entry.get("val")
        if val is None or not end:
            continue
        fp = str(entry.get("fp") or "")
        annual = 1 if (form in ("10-K", "20-F", "40-F") or fp == "FY") else 0
        rank = (1 if annual else 0) if prefer_annual else 0
        # Prefer later period; when prefer_annual, prefer FY over interim for same end
        key = (end, rank)
        best_key = (best_date, best_rank)
        if key >= best_key:
            best_date = end
            best_val = float(val)
            best_rank = rank
    return best_val, best_date or None


def _is_annual_entry(entry: dict) -> bool:
    form = entry.get("form")
    fp = str(entry.get("fp") or "")
    return form in ("10-K", "20-F", "40-F") or fp == "FY"


def latest_usd_fact(
    facts: dict,
    tags: tuple[str, ...],
    *,
    prefer_annual: bool = False,
) -> tuple[float | None, str | None]:
    """Latest USD fact. When prefer_annual, use the most recent FY figure if any exist."""
    annual_date = ""
    annual_val: float | None = None
    any_date = ""
    any_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        block = us_gaap.get(tag)
        if not block:
            continue
        for unit_key, entries in (block.get("units") or {}).items():
            if "USD" not in unit_key.upper():
                continue
            for entry in entries or []:
                form = entry.get("form")
                if form not in ("10-K", "10-Q", "20-F", "40-F", None):
                    if form and not str(form).startswith(("10-", "20-", "40-")):
                        continue
                end = str(entry.get("end") or "")
                val = entry.get("val")
                if val is None or not end:
                    continue
                fval = float(val)
                if end >= any_date:
                    any_date = end
                    any_val = fval
                if prefer_annual and _is_annual_entry(entry) and end >= annual_date:
                    annual_date = end
                    annual_val = fval
    if prefer_annual and annual_val is not None:
        return annual_val, annual_date or None
    return any_val, any_date or None


def latest_shares_fact(facts: dict) -> tuple[float | None, str | None]:
    best_date = ""
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})
    for namespace, tags in ((us_gaap, SHARES_TAGS), (dei, ("EntityCommonStockSharesOutstanding",))):
        for tag in tags:
            block = namespace.get(tag)
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


def screen_ticker(ticker: str, cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = fetch_json(url)
    if not data:
        return {"sec_error": "companyfacts unavailable"}

    deposits, deposits_date = latest_usd_fact(data, DEPOSITS_TAGS)
    noninterest, _ = latest_usd_fact(data, NONINTEREST_DEPOSIT_TAGS)
    interest_exp, interest_date = latest_usd_fact(
        data, INTEREST_EXPENSE_DEPOSITS_TAGS, prefer_annual=True
    )
    equity, equity_date = latest_usd_fact(data, EQUITY_TAGS)
    goodwill, _ = latest_usd_fact(data, GOODWILL_TAGS)
    intangibles, _ = latest_usd_fact(data, INTANGIBLE_TAGS)
    net_income, income_date = latest_usd_fact(data, INCOME_TAGS, prefer_annual=True)
    assets, assets_date = latest_usd_fact(data, ASSETS_TAGS)
    shares, shares_date = latest_shares_fact(data)

    tangible_equity = None
    if equity is not None:
        tangible_equity = equity - (goodwill or 0.0) - (intangibles or 0.0)

    filing_dates = [d for d in (deposits_date, equity_date, assets_date, income_date) if d]
    filing_as_of = max(filing_dates) if filing_dates else None

    return {
        "cik": cik,
        "deposits_total_usd": deposits,
        "deposits_noninterest_usd": noninterest,
        "interest_expense_deposits_usd": interest_exp,
        "interest_expense_as_of": interest_date,
        "equity_usd": equity,
        "goodwill_usd": goodwill,
        "intangibles_usd": intangibles,
        "tangible_equity_usd": tangible_equity,
        "net_income_usd": net_income,
        "net_income_as_of": income_date,
        "total_assets_usd": assets,
        "shares_outstanding": shares,
        "shares_as_of": shares_date,
        "filing_as_of": filing_as_of,
        "sec_entity": data.get("entityName"),
    }


def compute_bank_metrics(sec: dict, price: float | None, mcap: float | None) -> dict:
    deposits = sec.get("deposits_total_usd")
    noninterest = sec.get("deposits_noninterest_usd")
    interest_exp = sec.get("interest_expense_deposits_usd")
    equity = sec.get("equity_usd")
    tangible_equity = sec.get("tangible_equity_usd")
    net_income = sec.get("net_income_usd")
    shares = sec.get("shares_outstanding")

    dda_share_pct = None
    if deposits and deposits > 0 and noninterest is not None:
        dda_share_pct = round(100.0 * noninterest / deposits, 1)

    # Approximate: annual interest expense / period-end deposits (not avg balances)
    cost_of_deposits_pct = None
    if deposits and deposits > 0 and interest_exp is not None and interest_exp >= 0:
        cost_of_deposits_pct = round(100.0 * interest_exp / deposits, 2)

    tbv_per_share = None
    if tangible_equity is not None and shares and shares > 0:
        tbv_per_share = tangible_equity / shares

    p_tbv = None
    if price is not None and tbv_per_share and tbv_per_share > 0:
        p_tbv = round(price / tbv_per_share, 2)

    roe_pct = None
    if equity and equity > 0 and net_income is not None:
        roe_pct = round(100.0 * net_income / equity, 1)

    is_low_cost = bool(
        (cost_of_deposits_pct is not None and cost_of_deposits_pct < LOW_COST_DEPOSITS_PCT)
        or (dda_share_pct is not None and dda_share_pct > HIGH_DDA_SHARE_PCT)
    )

    return {
        "dda_share_pct": dda_share_pct,
        "cost_of_deposits_pct": cost_of_deposits_pct,
        "tbv_per_share_usd": tbv_per_share,
        "p_tbv": p_tbv,
        "roe_pct": roe_pct,
        "is_low_cost": is_low_cost,
        "price_usd": price,
        "market_cap_usd": mcap,
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
    if abs(val) >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    return f"${val / 1_000_000:.1f}M"


def fmt_mcap(val: float | None) -> str | None:
    if val is None:
        return None
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    return f"${val / 1_000_000:.0f}M"


def fmt_pct(val: float | None, digits: int = 1) -> str | None:
    if val is None:
        return None
    return f"{val:.{digits}f}%"


def fmt_multiple(val: float | None) -> str | None:
    if val is None:
        return None
    return f"{val:.2f}x"


def fmt_per_share(val: float | None) -> str | None:
    if val is None:
        return None
    return f"${val:.2f}"


def build_rows() -> list[dict]:
    holdings, watchlist = load_registry_sets()
    seeds = load_seed_rows()
    cik_map = load_cik_map()

    out: list[dict] = []
    for seed in seeds:
        ticker = seed["ticker"]
        row = {**seed}
        base_ticker = ticker.split(".")[0]
        cik = cik_map.get(base_ticker) or cik_map.get(ticker)

        sec: dict = {}
        if cik:
            sec = screen_ticker(ticker, cik)
            if sec.get("sec_entity") and (
                not row.get("company") or row["company"] == ticker
            ):
                row["company"] = sec["sec_entity"]
            time.sleep(0.12)

        price, _ = fetch_yahoo_price(base_ticker)
        time.sleep(0.08)
        shares = sec.get("shares_outstanding")
        mcap = None
        if price is not None and shares and shares > 0:
            mcap = price * shares

        metrics = compute_bank_metrics(sec, price, mcap)
        cap_bucket = cap_bucket_from_mcap(mcap) or seed.get("cap_tier_seed") or None
        has_core = sec.get("deposits_total_usd") is not None or sec.get("equity_usd") is not None

        row.update(
            {
                "in_holdings": ticker in holdings,
                "in_watchlist": ticker in watchlist,
                "cik": sec.get("cik") or cik,
                "sec_error": sec.get("sec_error"),
                "screen_status": "ok" if has_core else "pending_sec",
                "deposits_total_usd": sec.get("deposits_total_usd"),
                "deposits_noninterest_usd": sec.get("deposits_noninterest_usd"),
                "interest_expense_deposits_usd": sec.get("interest_expense_deposits_usd"),
                "equity_usd": sec.get("equity_usd"),
                "tangible_equity_usd": sec.get("tangible_equity_usd"),
                "net_income_usd": sec.get("net_income_usd"),
                "total_assets_usd": sec.get("total_assets_usd"),
                "shares_outstanding": shares,
                "shares_as_of": sec.get("shares_as_of"),
                "filing_as_of": sec.get("filing_as_of"),
                "cap_bucket": cap_bucket,
                "is_small_cap": cap_bucket in ("micro", "small"),
                "dda_share_pct": metrics["dda_share_pct"],
                "cost_of_deposits_pct": metrics["cost_of_deposits_pct"],
                "tbv_per_share_usd": metrics["tbv_per_share_usd"],
                "p_tbv": metrics["p_tbv"],
                "roe_pct": metrics["roe_pct"],
                "is_low_cost": metrics["is_low_cost"],
                "price_usd": metrics["price_usd"],
                "market_cap_usd": metrics["market_cap_usd"],
                "deposits_display": fmt_usd_mm(sec.get("deposits_total_usd")),
                "assets_display": fmt_usd_mm(sec.get("total_assets_usd")),
                "market_cap_display": fmt_mcap(mcap),
                "dda_share_display": fmt_pct(metrics["dda_share_pct"]),
                "cost_of_deposits_display": fmt_pct(metrics["cost_of_deposits_pct"], 2),
                "roe_display": fmt_pct(metrics["roe_pct"]),
                "tbv_per_share_display": fmt_per_share(metrics["tbv_per_share_usd"]),
                "p_tbv_display": fmt_multiple(metrics["p_tbv"]),
            }
        )
        row.pop("cap_tier_seed", None)
        out.append(row)

    bucket_rank = {"micro": 0, "small": 1, "mid": 2, "large": 3}
    out.sort(
        key=lambda r: (
            1 if r.get("in_holdings") else 0,
            0 if r.get("is_low_cost") else 1,
            r.get("cost_of_deposits_pct") if r.get("cost_of_deposits_pct") is not None else 999.0,
            -(r.get("roe_pct") or 0),
            bucket_rank.get(r.get("cap_bucket") or "", 9),
            r["ticker"],
        ),
    )
    return out


def build_payload(rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = build_rows()
    low_cost_count = sum(1 for r in rows if r.get("is_low_cost"))
    return {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": (
            "Advantaged / competitive-franchise banks (seed list). "
            "Metrics from SEC companyfacts: deposits, noninterest deposits (DDA share), "
            "approx. cost of deposits (annual InterestExpenseDeposits ÷ period-end Deposits), "
            "tangible book, ROE, P/TBV; market cap = SEC shares × Yahoo chart price. "
            "Low-cost flag: cost of deposits < 1.5% or DDA share > 30%. "
            "Framed by Moore community-bank handbook "
            "(_system/reference/investment-wisdom/moore/). "
            f"Seed: {SEED_PATH.relative_to(ROOT).as_posix()}."
        ),
        "seed_path": str(SEED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "low_cost_count": low_cost_count,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build advantaged-banks screener JSON")
    parser.add_argument("--write", action="store_true", help="Write dashboard/data/advantaged_banks_screener.json")
    args = parser.parse_args()

    payload = build_payload()
    rows = payload["rows"]
    low_cost = payload["low_cost_count"]

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUTPUT} ({len(rows)} rows, {low_cost} low-cost)")
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
