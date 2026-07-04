#!/usr/bin/env python3
"""Build per-ticker fundamental time series from SEC XBRL companyfacts.

Free, deterministic, zero-token source of quarterly fundamentals for every US
ticker with a CIK. Each datapoint carries a real fiscal period end and fiscal
period label (Q1-Q4/FY) straight from the XBRL filing, which eliminates the
extraction-date/scope-mixing artifacts that plagued filing_facts series.

Output: _system/reference/market-data/fundamentals/{TICKER}.json
        _system/reference/market-data/fundamentals/_index.json (coverage)

Cache policy: a ticker is re-fetched only when its cache file is older than
--max-age-days (default 7), so CI reruns are nearly free and respectful of
SEC fair-use limits.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
US_TICKER_CONFIG = ROOT / "_system" / "scripts" / "us_ticker_config.json"
FUNDAMENTALS_DIR = ROOT / "_system" / "reference" / "market-data" / "fundamentals"
CIK_MAP_CACHE = FUNDAMENTALS_DIR / "_sec_ticker_cik_map.json"

USER_AGENT = "single-stock-investments research pipeline (contact: dag5wd@virginia.edu)"
REQUEST_DELAY_S = 0.15
CIK_MAP_MAX_AGE_DAYS = 30

# Canonical metric -> ordered list of us-gaap tags (first hit wins per period).
METRIC_TAGS: dict[str, list[str]] = {
    "revenues": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueServicesNet",
        "SalesRevenueGoodsNet",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "eps_basic": ["EarningsPerShareBasic"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "total_assets": ["Assets"],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
}

# Flow metrics come from duration facts; balance metrics from instant facts.
FLOW_METRICS = {"revenues", "operating_income", "net_income", "eps_basic", "cfo"}

ACCEPTED_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F", "6-K"}


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    try:
        import gzip
        import io

        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return json.loads(raw)
    except Exception:
        return None


def file_age_days(path: Path) -> float | None:
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 86400.0


def sec_cik_map(*, max_age_days: float = CIK_MAP_MAX_AGE_DAYS) -> dict[str, str]:
    """ticker -> zero-padded CIK from the SEC's public map, cached."""
    age = file_age_days(CIK_MAP_CACHE)
    if age is not None and age < max_age_days:
        return load_json(CIK_MAP_CACHE, {})
    doc = fetch_json("https://www.sec.gov/files/company_tickers.json")
    if not doc:
        return load_json(CIK_MAP_CACHE, {})
    out = {}
    for row in doc.values():
        ticker = str(row.get("ticker") or "").upper()
        cik = row.get("cik_str")
        if ticker and cik:
            out[ticker] = f"{int(cik):010d}"
    CIK_MAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CIK_MAP_CACHE.write_text(json.dumps(out, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    return out


def resolve_ciks() -> dict[str, str]:
    """ticker -> 10-digit CIK for every holding we can resolve."""
    reg = load_json(REGISTRY_PATH, {})
    us_cfg = load_json(US_TICKER_CONFIG, {})
    holdings = reg.get("holdings") or {}
    sec_map: dict[str, str] | None = None
    out: dict[str, str] = {}
    for ticker, holding in holdings.items():
        cik = (holding.get("download") or {}).get("cik") or (us_cfg.get(ticker) or {}).get("cik")
        if cik:
            try:
                out[ticker] = f"{int(str(cik).strip()):010d}"
                continue
            except ValueError:
                pass
        market = (holding.get("market") or "").upper()
        if market in {"US", "OTC"}:
            if sec_map is None:
                sec_map = sec_cik_map()
            mapped = sec_map.get(ticker.upper()) or sec_map.get(ticker.upper().replace(".", "-"))
            if mapped:
                out[ticker] = mapped
    return out


def duration_days(start: str | None, end: str | None) -> int | None:
    try:
        d0 = datetime.strptime(str(start)[:10], "%Y-%m-%d")
        d1 = datetime.strptime(str(end)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return (d1 - d0).days


def series_for_tag(gaap: dict, tag: str, *, is_flow: bool) -> dict[str, dict]:
    """Extract one us-gaap tag into period -> point dict."""
    node = gaap.get(tag)
    if not node:
        return {}
    by_period: dict[str, dict] = {}
    for unit_vals in (node.get("units") or {}).values():
        for fact in unit_vals:
            form = str(fact.get("form") or "")
            if form not in ACCEPTED_FORMS:
                continue
            end = str(fact.get("end") or "")[:10]
            if not end:
                continue
            val = fact.get("val")
            if val is None:
                continue
            if is_flow:
                days = duration_days(fact.get("start"), fact.get("end"))
                if days is None or not (70 <= days <= 100):
                    continue
            filed = str(fact.get("filed") or "")
            prev = by_period.get(end)
            if prev is None or filed > prev["filed"]:
                by_period[end] = {
                    "period": end,
                    "value": float(val),
                    "fy": fact.get("fy"),
                    "fp": fact.get("fp"),
                    "form": form,
                    "filed": filed,
                    "tag": tag,
                }
    return by_period


def extract_metric_series(facts: dict, metric: str) -> list[dict]:
    """Quarterly series for one metric from a companyfacts us-gaap block.

    Flow metrics keep only ~quarter-length durations (70-100 days) so YTD and
    annual figures never mix into the series. Balance metrics keep instant
    values at each period end. When multiple tags carry the same metric, pick
    the tag whose series extends to the latest fiscal period (avoids stale
    tags like legacy Revenues blocking RevenueFromContractWithCustomer*).
    """
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    is_flow = metric in FLOW_METRICS
    best: dict[str, dict] = {}
    best_latest = ""
    for tag in METRIC_TAGS[metric]:
        by_period = series_for_tag(gaap, tag, is_flow=is_flow)
        if not by_period:
            continue
        latest = max(by_period)
        if latest > best_latest or (latest == best_latest and len(by_period) > len(best)):
            best_latest = latest
            best = by_period
    return [best[k] for k in sorted(best)]


def build_ticker(ticker: str, cik: str) -> dict | None:
    facts = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if not facts:
        return None
    metrics: dict[str, list[dict]] = {}
    for metric in METRIC_TAGS:
        series = extract_metric_series(facts, metric)
        if len(series) >= 2:
            metrics[metric] = series[-24:]
    if not metrics:
        return None
    return {
        "ticker": ticker,
        "cik": cik,
        "source": "sec_companyfacts",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fundamental series from SEC XBRL companyfacts.")
    parser.add_argument("--tickers", nargs="*", help="Limit to specific tickers")
    parser.add_argument("--max-age-days", type=float, default=7.0, help="Re-fetch when cache is older than this")
    parser.add_argument("--force", action="store_true", help="Ignore cache age")
    args = parser.parse_args()

    FUNDAMENTALS_DIR.mkdir(parents=True, exist_ok=True)
    ciks = resolve_ciks()
    targets = {t: c for t, c in ciks.items() if not args.tickers or t in {x.upper() for x in args.tickers}}

    fetched = refreshed = skipped = failed = 0
    for ticker, cik in sorted(targets.items()):
        out_path = FUNDAMENTALS_DIR / f"{ticker}.json"
        age = file_age_days(out_path)
        if not args.force and age is not None and age < args.max_age_days:
            skipped += 1
            continue
        payload = build_ticker(ticker, cik)
        time.sleep(REQUEST_DELAY_S)
        if payload is None:
            failed += 1
            continue
        out_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        if age is None:
            fetched += 1
        else:
            refreshed += 1

    covered = sorted(p.stem for p in FUNDAMENTALS_DIR.glob("*.json") if not p.stem.startswith("_"))
    index = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(covered),
        "resolvable_ciks": len(ciks),
        "tickers": covered,
    }
    (FUNDAMENTALS_DIR / "_index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    print(
        f"Fundamentals: {len(covered)} tickers cached "
        f"(new {fetched}, refreshed {refreshed}, fresh-skip {skipped}, failed {failed}, "
        f"resolvable CIKs {len(ciks)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
