#!/usr/bin/env python3
"""Build rock / aggregates screener JSON for the dashboard Ideas -> Screens tab.

Reads seed candidates + SEC XBRL company facts (revenue, operating income, DD&A,
CFO, capex, debt, equity) and Yahoo chart prices. Marks rows already in registry
holdings or watchlist.

Flow metrics (revenue, operating income, DD&A, CFO, capex) are taken from the
latest ANNUAL figure only, never a bare "latest fact". Aggregates volumes are
heavily seasonal -- Q1 is the weak quarter and Q3 the strong one -- so mixing a
quarterly figure for one company with an annual figure for another produces a
table that looks comparable and is not. An FY figure is up to twelve months
stale; it is never wrong about what it measures. Balance-sheet items take the
latest available reading, quarterly included, because a point-in-time stock has
no such comparability problem.

Usage:
  python _system/scripts/build_rock_aggregates_screener.py
  python _system/scripts/build_rock_aggregates_screener.py --write
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
SEED_PATH = ROOT / "_system" / "reference" / "market-data" / "screens" / "rock_aggregates_seed.csv"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "rock_aggregates_screener.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
YAHOO_UA = "MarvinResearch/1.0 (rock-aggregates-screener)"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
)
OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
# Depletion matters in a quarry business; prefer the tag that carries it.
DDA_TAGS = (
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "DepreciationDepletionAndAmortizationExcludingAmortizationOfDeferredFinancingCosts",
    "DepreciationAndAmortization",
)
CFO_TAGS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)
CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)
PPE_TAGS = ("PropertyPlantAndEquipmentNet",)
GOODWILL_TAGS = ("Goodwill",)
INTANGIBLE_TAGS = (
    "IntangibleAssetsNetExcludingGoodwill",
    "FiniteLivedIntangibleAssetsNet",
)
EQUITY_TAGS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
LT_DEBT_TAGS = (
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    # Arcosa and other lessee-heavy filers report debt only on the combined
    # debt-and-capital-lease concepts; without these the row loses net debt,
    # net debt/EBITDA, EV and EV/EBITDA in one go.
    "LongTermDebtAndCapitalLeaseObligations",
)
ST_DEBT_TAGS = (
    "LongTermDebtCurrent",
    "DebtCurrent",
    "ShortTermBorrowings",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
)
ASSETS_TAGS = ("Assets",)
INCOME_TAGS = (
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "ProfitLoss",
)
SHARES_TAGS = (
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
)

# Flat US statutory rate for NOPAT. A screener-grade approximation, labelled as
# one in `criteria`; an effective rate per company belongs in a deep dive.
NOPAT_TAX_RATE = 0.21

CAP_BUCKETS = (
    ("micro", 300_000_000),
    ("small", 2_000_000_000),
    ("mid", 10_000_000_000),
    ("large", None),
)

ROCK_TYPE_LABELS = {
    "aggregates_pure": "Aggregates (pure)",
    "aggregates_vertical": "Aggregates (integrated)",
    "cement": "Cement",
    "lime": "Lime",
    "asphalt_rollup": "Asphalt roll-up",
}
PURE_ROCK_TYPES = ("aggregates_pure", "aggregates_vertical")


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
            rock_type = (row.get("rock_type") or "").strip().lower()
            rows.append(
                {
                    "ticker": ticker,
                    "company": (row.get("company") or ticker).strip(),
                    "market": (row.get("market") or "US").strip().upper(),
                    "cap_tier_seed": (row.get("cap_tier") or "").strip().lower(),
                    "rock_type": rock_type,
                    "rock_type_label": ROCK_TYPE_LABELS.get(
                        rock_type, rock_type.replace("_", " ").title() or "—"
                    ),
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


def _usable_form(entry: dict) -> bool:
    form = entry.get("form")
    if form in ("10-K", "10-Q", "20-F", "40-F", None):
        return True
    return bool(form) and str(form).startswith(("10-", "20-", "40-"))


def _is_annual_entry(entry: dict) -> bool:
    """True only when the fact's own start/end span covers a full year.

    Neither the form nor `fp` can be trusted here. A 10-K carries its Q4 figures
    too, tagged `form="10-K"` with `fp="FY"` -- for MLM that is a $1.53B quarter
    sitting alongside the $6.15B year, both ending 2025-12-31. Keying off the form
    picks whichever the JSON happens to list last, which is how a 135% EBITDA
    margin reaches a dashboard looking like a real number. The duration is the
    only reliable discriminator, so a duration fact without start/end is rejected.
    """
    start, end = str(entry.get("start") or ""), str(entry.get("end") or "")
    if not (start and end):
        return False
    try:
        days = (
            datetime.strptime(end[:10], "%Y-%m-%d") - datetime.strptime(start[:10], "%Y-%m-%d")
        ).days
    except ValueError:
        return False
    return 330 <= days <= 400


def _latest_fact(
    facts: dict, tags: tuple[str, ...], *, annual_only: bool
) -> tuple[float | None, str | None]:
    """Latest USD fact across ALL tags, not the first tag that happens to have one.

    Scanning tag-by-tag and stopping at the first hit silently pins a company to a
    retired concept: Knife River tagged revenue as
    RevenueFromContractWithCustomerExcludingAssessedTax through FY2023 and switched
    to Revenues for FY2024-25, so first-tag-wins froze it two years in the past
    while still reporting a confident number. Every tag is scanned and the latest
    period wins; tag order only breaks ties on an identical end date.
    """
    best: tuple[str, int] | None = None
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for rank, tag in enumerate(tags):
        block = us_gaap.get(tag)
        if not block:
            continue
        for unit_key, entries in (block.get("units") or {}).items():
            if "USD" not in unit_key.upper():
                continue
            for entry in entries or []:
                if not _usable_form(entry):
                    continue
                if annual_only and not _is_annual_entry(entry):
                    continue
                end = str(entry.get("end") or "")
                val = entry.get("val")
                if val is None or not end:
                    continue
                # Later period wins; on a tie the earlier (preferred) tag wins.
                key = (end, -rank)
                if best is None or key > best:
                    best = key
                    best_val = float(val)
    return best_val, (best[0] if best else None)


def latest_annual_usd_fact(facts: dict, tags: tuple[str, ...]) -> tuple[float | None, str | None]:
    """Latest full-year USD figure, or (None, None). Never falls back to a quarter."""
    return _latest_fact(facts, tags, annual_only=True)


def latest_usd_fact(facts: dict, tags: tuple[str, ...]) -> tuple[float | None, str | None]:
    """Latest USD reading of a balance-sheet stock, quarterly included."""
    return _latest_fact(facts, tags, annual_only=False)


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
                for entry in entries or []:
                    end = str(entry.get("end") or "")
                    val = entry.get("val")
                    if val is None or not end or end < best_date:
                        continue
                    best_date = end
                    best_val = float(val)
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


def screen_ticker(cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = fetch_json(url)
    if not data:
        return {"sec_error": "companyfacts unavailable"}

    # IFRS filers (Cemex files 20-F under ifrs-full) carry no us-gaap namespace at
    # all. Say so on the row rather than returning a blank that reads as a bug.
    if not data.get("facts", {}).get("us-gaap"):
        namespaces = ", ".join(sorted(data.get("facts", {}).keys())) or "none"
        return {
            "cik": cik,
            "sec_entity": data.get("entityName"),
            "sec_error": f"IFRS filer (namespaces: {namespaces}); US-GAAP tag map does not apply",
        }

    revenue, revenue_date = latest_annual_usd_fact(data, REVENUE_TAGS)
    op_income, _ = latest_annual_usd_fact(data, OPERATING_INCOME_TAGS)
    dda, _ = latest_annual_usd_fact(data, DDA_TAGS)
    cfo, _ = latest_annual_usd_fact(data, CFO_TAGS)
    capex, _ = latest_annual_usd_fact(data, CAPEX_TAGS)
    net_income, _ = latest_annual_usd_fact(data, INCOME_TAGS)

    ppe, _ = latest_usd_fact(data, PPE_TAGS)
    goodwill, _ = latest_usd_fact(data, GOODWILL_TAGS)
    intangibles, _ = latest_usd_fact(data, INTANGIBLE_TAGS)
    equity, equity_date = latest_usd_fact(data, EQUITY_TAGS)
    cash, _ = latest_usd_fact(data, CASH_TAGS)
    lt_debt, _ = latest_usd_fact(data, LT_DEBT_TAGS)
    st_debt, _ = latest_usd_fact(data, ST_DEBT_TAGS)
    assets, assets_date = latest_usd_fact(data, ASSETS_TAGS)
    shares, shares_date = latest_shares_fact(data)

    filing_dates = [d for d in (equity_date, assets_date) if d]
    return {
        "cik": cik,
        "revenue_usd": revenue,
        "operating_income_usd": op_income,
        "dda_usd": dda,
        "cfo_usd": cfo,
        "capex_usd": capex,
        "net_income_usd": net_income,
        "ppe_net_usd": ppe,
        "goodwill_usd": goodwill,
        "intangibles_usd": intangibles,
        "equity_usd": equity,
        "cash_usd": cash,
        "long_term_debt_usd": lt_debt,
        "short_term_debt_usd": st_debt,
        "total_assets_usd": assets,
        "shares_outstanding": shares,
        "shares_as_of": shares_date,
        "fiscal_year_end": revenue_date,
        "filing_as_of": max(filing_dates) if filing_dates else None,
        "sec_entity": data.get("entityName"),
    }


def compute_rock_metrics(sec: dict, price: float | None, mcap: float | None) -> dict:
    revenue = sec.get("revenue_usd")
    op_income = sec.get("operating_income_usd")
    dda = sec.get("dda_usd")
    cfo = sec.get("cfo_usd")
    capex = sec.get("capex_usd")
    equity = sec.get("equity_usd")
    cash = sec.get("cash_usd")
    goodwill = sec.get("goodwill_usd")
    intangibles = sec.get("intangibles_usd")

    total_debt = None
    if sec.get("long_term_debt_usd") is not None or sec.get("short_term_debt_usd") is not None:
        total_debt = (sec.get("long_term_debt_usd") or 0.0) + (sec.get("short_term_debt_usd") or 0.0)

    net_debt = None
    if total_debt is not None:
        net_debt = total_debt - (cash or 0.0)

    ebitda = None
    if op_income is not None and dda is not None:
        ebitda = op_income + dda

    ebitda_margin_pct = None
    if ebitda is not None and revenue and revenue > 0:
        ebitda_margin_pct = round(100.0 * ebitda / revenue, 1)

    fcf = None
    if cfo is not None and capex is not None:
        fcf = cfo - capex

    fcf_conversion_pct = None
    if fcf is not None and ebitda and ebitda > 0:
        fcf_conversion_pct = round(100.0 * fcf / ebitda, 1)

    capex_pct_revenue = None
    if capex is not None and revenue and revenue > 0:
        capex_pct_revenue = round(100.0 * capex / revenue, 1)

    net_debt_ebitda = None
    if net_debt is not None and ebitda and ebitda > 0:
        net_debt_ebitda = round(net_debt / ebitda, 2)

    # Invested capital = equity + total debt - cash. Long-lived, heavily
    # depreciated quarry assets make book equity a poor denominator on its own.
    roic_pct = None
    if op_income is not None and equity is not None and total_debt is not None:
        invested = equity + total_debt - (cash or 0.0)
        if invested > 0:
            roic_pct = round(100.0 * (op_income * (1 - NOPAT_TAX_RATE)) / invested, 1)

    goodwill_equity_pct = None
    if equity and equity > 0:
        intangible_total = (goodwill or 0.0) + (intangibles or 0.0)
        if goodwill is not None or intangibles is not None:
            goodwill_equity_pct = round(100.0 * intangible_total / equity, 1)

    ev = None
    if mcap is not None and net_debt is not None:
        ev = mcap + net_debt

    ev_ebitda = None
    if ev is not None and ebitda and ebitda > 0:
        ev_ebitda = round(ev / ebitda, 1)

    fcf_yield_pct = None
    if fcf is not None and mcap and mcap > 0:
        fcf_yield_pct = round(100.0 * fcf / mcap, 1)

    return {
        "ebitda_usd": ebitda,
        "ebitda_margin_pct": ebitda_margin_pct,
        "fcf_usd": fcf,
        "fcf_conversion_pct": fcf_conversion_pct,
        "capex_pct_revenue": capex_pct_revenue,
        "total_debt_usd": total_debt,
        "net_debt_usd": net_debt,
        "net_debt_ebitda": net_debt_ebitda,
        "roic_pct": roic_pct,
        "goodwill_equity_pct": goodwill_equity_pct,
        "enterprise_value_usd": ev,
        "ev_ebitda": ev_ebitda,
        "fcf_yield_pct": fcf_yield_pct,
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


def fmt_usd(val: float | None) -> str | None:
    if val is None:
        return None
    sign = "-" if val < 0 else ""
    a = abs(val)
    if a >= 1_000_000_000:
        return f"{sign}${a / 1_000_000_000:.2f}B"
    return f"{sign}${a / 1_000_000:.0f}M"


def fmt_pct(val: float | None, digits: int = 1) -> str | None:
    if val is None:
        return None
    return f"{val:.{digits}f}%"


def fmt_multiple(val: float | None) -> str | None:
    if val is None:
        return None
    return f"{val:.1f}x"


def sort_key(row: dict):
    """Pure rock first, then cheapest on EV/EBITDA, then highest ROIC.

    Unlike the banks screen, holdings are NOT demoted to the bottom: VMC, MLM and
    CRH are the benchmark the rest of the table is read against, so burying them
    would make the screen harder to use, not easier.
    """
    return (
        0 if row.get("rock_type") in PURE_ROCK_TYPES else 1,
        row.get("ev_ebitda") if row.get("ev_ebitda") is not None else 999.0,
        -(row.get("roic_pct") or 0),
        row["ticker"],
    )


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
            sec = screen_ticker(cik)
            if sec.get("sec_entity") and (not row.get("company") or row["company"] == ticker):
                row["company"] = sec["sec_entity"]
            time.sleep(0.12)

        price, _ = fetch_yahoo_price(base_ticker)
        time.sleep(0.08)
        shares = sec.get("shares_outstanding")
        mcap = price * shares if (price is not None and shares and shares > 0) else None

        metrics = compute_rock_metrics(sec, price, mcap)
        cap_bucket = cap_bucket_from_mcap(mcap) or seed.get("cap_tier_seed") or None
        has_core = sec.get("revenue_usd") is not None or sec.get("equity_usd") is not None

        row.update(
            {
                "in_holdings": ticker in holdings,
                "in_watchlist": ticker in watchlist,
                "cik": sec.get("cik") or cik,
                "sec_error": sec.get("sec_error"),
                "screen_status": "ok" if has_core else "pending_sec",
                "flow_basis": "FY",
                "fiscal_year_end": sec.get("fiscal_year_end"),
                "revenue_usd": sec.get("revenue_usd"),
                "operating_income_usd": sec.get("operating_income_usd"),
                "dda_usd": sec.get("dda_usd"),
                "cfo_usd": sec.get("cfo_usd"),
                "capex_usd": sec.get("capex_usd"),
                "net_income_usd": sec.get("net_income_usd"),
                "ppe_net_usd": sec.get("ppe_net_usd"),
                "goodwill_usd": sec.get("goodwill_usd"),
                "intangibles_usd": sec.get("intangibles_usd"),
                "equity_usd": sec.get("equity_usd"),
                "cash_usd": sec.get("cash_usd"),
                "total_assets_usd": sec.get("total_assets_usd"),
                "shares_outstanding": shares,
                "shares_as_of": sec.get("shares_as_of"),
                "filing_as_of": sec.get("filing_as_of"),
                "cap_bucket": cap_bucket,
                "is_pure_rock": seed.get("rock_type") in PURE_ROCK_TYPES,
                # Reserve life and per-ton unit economics are not in XBRL. They land
                # via filing_panels once P3/P4 of the plan are built; the column
                # stays visibly empty until then rather than being hidden.
                "reserve_life_years": None,
                "cash_gross_profit_per_ton": None,
                **metrics,
                "revenue_display": fmt_usd(sec.get("revenue_usd")),
                "ebitda_display": fmt_usd(metrics["ebitda_usd"]),
                "ebitda_margin_display": fmt_pct(metrics["ebitda_margin_pct"]),
                "fcf_display": fmt_usd(metrics["fcf_usd"]),
                "fcf_conversion_display": fmt_pct(metrics["fcf_conversion_pct"]),
                "capex_pct_revenue_display": fmt_pct(metrics["capex_pct_revenue"]),
                "net_debt_display": fmt_usd(metrics["net_debt_usd"]),
                "net_debt_ebitda_display": fmt_multiple(metrics["net_debt_ebitda"]),
                "roic_display": fmt_pct(metrics["roic_pct"]),
                "goodwill_equity_display": fmt_pct(metrics["goodwill_equity_pct"]),
                "ev_ebitda_display": fmt_multiple(metrics["ev_ebitda"]),
                "fcf_yield_display": fmt_pct(metrics["fcf_yield_pct"]),
                "market_cap_display": fmt_usd(mcap),
                "reserve_life_display": None,
            }
        )
        row.pop("cap_tier_seed", None)
        out.append(row)

    out.sort(key=sort_key)
    return out


def build_payload(rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = build_rows()
    pure_rock_count = sum(1 for r in rows if r.get("is_pure_rock"))
    return {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": (
            "US aggregates, cement and lime producers (seed list). Flow metrics "
            "(revenue, operating income, DD&A, CFO, capex) are the latest FULL-YEAR "
            "figures only -- aggregates volumes are seasonal, so mixing a quarter for "
            "one company with a year for another would not be comparable. Balance-sheet "
            "items use the latest reading including quarters. EBITDA = operating income "
            "+ DD&A (depletion included). ROIC = operating income x (1 - 21% flat "
            "statutory rate) / (equity + total debt - cash); an effective rate belongs "
            "in a deep dive. EV = market cap + net debt; market cap = SEC shares x Yahoo "
            "chart price. Reserve life and cash gross profit per ton are NOT in XBRL and "
            "stay empty until the filing panels are built. "
            f"Seed: {SEED_PATH.relative_to(ROOT).as_posix()}."
        ),
        "seed_path": str(SEED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "pure_rock_count": pure_rock_count,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build rock / aggregates screener JSON")
    parser.add_argument(
        "--write", action="store_true", help="Write dashboard/data/rock_aggregates_screener.json"
    )
    args = parser.parse_args()

    payload = build_payload()
    rows = payload["rows"]

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUTPUT} ({len(rows)} rows, {payload['pure_rock_count']} pure rock)")
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
