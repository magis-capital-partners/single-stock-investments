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
from aggregates_facts import collect, financial_history, balance_at

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


def screen_ticker(cik: str, facts: dict | None = None) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = facts if facts is not None else fetch_json(url)
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

    observed = datetime.now(timezone.utc).isoformat()
    observations = collect(data, '', cik, observed)
    history = financial_history(observations)
    annual = [r for r in history if r['period_type']=='FY' and r.get('revenue_usd') is not None]
    if not annual:
        return {'cik':cik,'sec_error':'No comparable full-year USD financial observations'}
    latest = annual[-1]
    balance_dates = sorted({r['period_end'] for r in observations if r['period_type']=='instant'})
    balance_date = balance_dates[-1] if balance_dates else latest['period_end']
    balance = balance_at(observations,balance_date)
    fy_balance = balance_at(observations,latest['period_end'])
    prior = annual[-2] if len(annual)>1 else None
    prior_balance = balance_at(observations,prior['period_end']) if prior else {}
    shares,shares_date=latest_shares_fact(data)
    share_history=[]
    for namespace,tag in [('us-gaap','CommonStockSharesOutstanding'),('dei','EntityCommonStockSharesOutstanding')]:
        for unit,entries in data.get('facts',{}).get(namespace,{}).get(tag,{}).get('units',{}).items():
            if 'share' in unit.lower():share_history.extend(entries)
    return {**latest,**{k:v for k,v in balance.items() if k!='sources'},'cik':cik,'fiscal_year_end':latest['period_end'],
        'filing_as_of':balance_date,'shares_outstanding':shares,'shares_as_of':shares_date,'sec_entity':data.get('entityName'),
        'annual_balance':fy_balance,'prior_annual_balance':prior_balance,'financial_history':history,'financial_observations':observations,
        'flow_basis':'FY','financial_sources':latest['sources'],'balance_sources':balance.get('sources',[]),
        'financial_vintages':collect(data,'',cik,observed,retain_vintages=True),'share_history':share_history}


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

    total_debt = sec.get('total_debt_usd')
    if total_debt is None and sec.get('long_term_debt_usd') is not None and sec.get('short_term_debt_usd') is not None:
        total_debt = sec['long_term_debt_usd'] + sec['short_term_debt_usd']
    net_debt = total_debt - cash if total_debt is not None and cash is not None else None

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
    if op_income is not None and equity is not None and total_debt is not None and cash is not None:
        invested = equity + total_debt - (cash or 0.0)
        if invested > 0:
            roic_pct = round(100.0 * (op_income * (1 - NOPAT_TAX_RATE)) / invested, 1)

    goodwill_equity_pct = None
    if equity and equity > 0 and goodwill is not None and intangibles is not None:
        goodwill_equity_pct = round(100.0 * (goodwill + intangibles) / equity, 1)

    ev = None
    if mcap is not None and net_debt is not None:
        ev = mcap + net_debt

    ev_ebitda = None
    if ev is not None and ebitda and ebitda > 0:
        ev_ebitda = round(ev / ebitda, 1)

    fcf_yield_pct = None
    if fcf is not None and mcap and mcap > 0:
        fcf_yield_pct = round(100.0 * fcf / mcap, 1)

    average_roic = None
    balances = [sec.get('annual_balance',{}),sec.get('prior_annual_balance',{})]
    capital = [b['equity_usd']+b['total_debt_usd']-b['cash_usd'] for b in balances if all(b.get(k) is not None for k in ['equity_usd','total_debt_usd','cash_usd'])]
    if len(capital)==2 and sum(capital)>0 and op_income is not None:
        average_roic=round(100*op_income*(1-NOPAT_TAX_RATE)/(sum(capital)/2),2)
    return {
        'roic_average_pct':average_roic,
        'roic_basis':'FY operating income at a labeled 21% tax assumption / average fiscal-year invested capital',
        'ebitda_basis':'operating income plus DD&A proxy',
        'roic_proxy_pct':roic_pct,
        'financial_basis':'period-aligned FY flows; balance date stated separately',
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
    from aggregates_pipeline import run
    return run(ROOT, write=False)['rows']


def build_payload(rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = build_rows()
    pure_rock_count = sum(1 for r in rows if r.get("is_pure_rock"))
    return {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": (
            "US materials peers with period-aligned FULL-YEAR financial flows and dated operating evidence. "
            "Corporate EBITDA is operating income plus DD&A. ROIC uses an explicit 21% tax assumption. "
            "Missing inputs remain null; aggregates and integrated/adjacent peer groups remain separate."
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
    parser.add_argument('--offline', action='store_true', help='Rebuild from cached and verified evidence only')
    parser.add_argument('--refresh-operating', action='store_true', help='Discover five years of issuer filings and quarter tables')
    parser.add_argument('--check', action='store_true', help='Validate the published snapshot and detail references')
    args = parser.parse_args()
    from aggregates_pipeline import run, check
    if args.check:
        check(ROOT)
    else:
        payload=run(ROOT, offline=args.offline, refresh_operating=args.refresh_operating, write=args.write)
        print(json.dumps({'rows':payload['row_count'],'coverage':payload['coverage']},sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
