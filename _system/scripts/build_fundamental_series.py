#!/usr/bin/env python3
"""Build per-ticker fundamental time series from SEC XBRL companyfacts.

Free, deterministic, zero-token source of quarterly fundamentals for every US
ticker with a CIK. Each datapoint carries a real fiscal period end and fiscal
period label (Q1-Q4/FY) straight from the XBRL filing, which eliminates the
extraction-date/scope-mixing artifacts that plagued filing_facts series.

US issuers are read from ``us-gaap``. Foreign private issuers that file
IFRS in a 40-F or 20-F (Franco-Nevada, Wheaton, Brookfield) are read from
``ifrs-full`` when that series is newer than the US-GAAP series.

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

# Same canonical metrics on the IFRS taxonomy used by 40-F and 20-F filers.
# Within a namespace the newest period still wins, then the longer series.
IFRS_METRIC_TAGS: dict[str, list[str]] = {
    "revenues": ["Revenue", "RevenueFromContractsWithCustomers"],
    "operating_income": ["ProfitLossFromOperatingActivities"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "eps_basic": ["BasicEarningsLossPerShare"],
    "cfo": ["CashFlowsFromUsedInOperatingActivities"],
    "cash": ["CashAndCashEquivalents"],
    "total_assets": ["Assets"],
    "stockholders_equity": ["EquityAttributableToOwnersOfParent", "Equity"],
    "long_term_debt": ["LongtermBorrowings", "NoncurrentBorrowings"],
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


# Duration classes for flow facts, in days. Filers report Q1 as a quarter and
# then six-, nine- and twelve-month cumulative figures, so Q2, Q3 and Q4 only
# exist as differences between consecutive cumulative facts.
DURATION_CLASSES = (("q", 70, 100), ("h", 160, 200), ("n", 250, 290), ("y", 340, 380))
PRIOR_CLASS = {"h": "q", "n": "h", "y": "n"}
# Per-share figures are not additive across periods (the share count moves),
# so they are never derived by subtraction.
NON_ADDITIVE_METRICS = {"eps_basic"}


def _duration_class(days: int | None) -> str | None:
    if days is None:
        return None
    for name, low, high in DURATION_CLASSES:
        if low <= days <= high:
            return name
    return None


def _one_quarter_before(end: str, candidates: dict[str, dict]) -> dict | None:
    """The cumulative fact whose period ends about one quarter before ``end``."""
    try:
        anchor = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return None
    best = None
    best_gap = None
    for period, point in candidates.items():
        try:
            gap = (anchor - datetime.strptime(period, "%Y-%m-%d")).days
        except ValueError:
            continue
        if 75 <= gap <= 105 and (best_gap is None or abs(gap - 91) < abs(best_gap - 91)):
            best, best_gap = point, gap
    return best


def derive_quarters(classes: dict[str, dict[str, dict]], *, additive: bool = True) -> dict[str, dict]:
    """Quarterly points: reported quarters plus YTD differences for the rest.

    Q2 = six-month minus Q1, Q3 = nine-month minus six-month, Q4 = annual
    minus nine-month. A derived point carries ``derived: "ytd_difference"``
    and the two filings it came from. A reported quarter always wins.
    """
    quarters = dict(classes.get("q") or {})
    if not additive:
        return quarters
    for longer in ("h", "n", "y"):
        for end, point in (classes.get(longer) or {}).items():
            if end in quarters:
                continue
            prior = _one_quarter_before(end, classes.get(PRIOR_CLASS[longer]) or {})
            if prior is None:
                continue
            quarters[end] = {
                "period": end,
                "value": float(point["value"]) - float(prior["value"]),
                "fy": point.get("fy"),
                "fp": point.get("fp"),
                "form": point.get("form"),
                "filed": max(str(point.get("filed") or ""), str(prior.get("filed") or "")),
                "tag": point.get("tag"),
                "derived": "ytd_difference",
                "from_periods": [prior["period"], end],
            }
    return quarters


def _unit_rank(unit: str, *, per_share: bool) -> tuple[int, int, str]:
    """USD before CAD. Per-share metrics prefer a ``/shares`` unit."""
    key = str(unit or "").upper().replace(" ", "")
    is_share = key.endswith("/SHARES") or key == "SHARES"
    currency = key.split("/")[0]
    currency_rank = {"USD": 0, "CAD": 1, "EUR": 2}.get(currency, 9)
    kind_rank = 0 if is_share == per_share else 1
    return (kind_rank, currency_rank, key)


def _currency_name(unit: str) -> str:
    return str(unit or "").split("/")[0].upper()


def _series_from_facts(
    facts: list,
    tag: str,
    *,
    is_flow: bool,
    additive: bool,
) -> dict[str, dict]:
    classes: dict[str, dict[str, dict]] = {name: {} for name, _, _ in DURATION_CLASSES}
    by_period: dict[str, dict] = {}
    for fact in facts:
        form = str(fact.get("form") or "")
        if form not in ACCEPTED_FORMS:
            continue
        end = str(fact.get("end") or "")[:10]
        if not end:
            continue
        val = fact.get("val")
        if val is None:
            continue
        bucket = by_period
        if is_flow:
            klass = _duration_class(duration_days(fact.get("start"), fact.get("end")))
            if klass is None:
                continue
            bucket = classes[klass]
        filed = str(fact.get("filed") or "")
        prev = bucket.get(end)
        if prev is None or filed > prev["filed"]:
            bucket[end] = {
                "period": end,
                "value": float(val),
                "fy": fact.get("fy"),
                "fp": fact.get("fp"),
                "form": form,
                "filed": filed,
                "tag": tag,
            }
    if is_flow:
        return derive_quarters(classes, additive=additive)
    return by_period


def series_for_tag(
    gaap: dict,
    tag: str,
    *,
    is_flow: bool,
    additive: bool = True,
    prefer_one_unit: bool = False,
    per_share: bool = False,
) -> dict[str, dict]:
    """Extract one tag into period -> point dict.

    Balance metrics keep instant values. Flow metrics keep every duration
    class and are reduced to quarters by ``derive_quarters``.

    ``prefer_one_unit`` (IFRS) keeps a single currency so USD and CAD facts
    are not mixed. US-GAAP leaves this off and keeps the prior tie-break.
    """
    node = gaap.get(tag)
    if not node:
        return {}
    units = node.get("units") or {}
    if prefer_one_unit:
        ordered = sorted(units, key=lambda unit: _unit_rank(unit, per_share=per_share))
        chosen = None
        for unit in ordered:
            parsed = _series_from_facts(
                units[unit], tag, is_flow=is_flow, additive=additive
            )
            if parsed:
                chosen = (unit, parsed)
                break
        if chosen is None:
            return {}
        unit_name, parsed = chosen
        currency = _currency_name(unit_name)
        if currency and currency != "USD":
            for point in parsed.values():
                point["currency"] = currency
        return parsed
    merged: list = []
    for unit_vals in units.values():
        merged.extend(unit_vals)
    return _series_from_facts(merged, tag, is_flow=is_flow, additive=additive)


def _best_tag_series(
    block: dict,
    tags: list[str],
    *,
    is_flow: bool,
    additive: bool,
    prefer_one_unit: bool,
    per_share: bool,
) -> dict[str, dict]:
    """Newest period wins, then the longer series. Same rule as before."""
    best: dict[str, dict] = {}
    best_latest = ""
    for tag in tags:
        by_period = series_for_tag(
            block,
            tag,
            is_flow=is_flow,
            additive=additive,
            prefer_one_unit=prefer_one_unit,
            per_share=per_share,
        )
        if not by_period:
            continue
        latest = max(by_period)
        if latest > best_latest or (latest == best_latest and len(by_period) > len(best)):
            best_latest = latest
            best = by_period
    return best


def extract_metric_series(facts: dict, metric: str) -> list[dict]:
    """Quarterly series for one metric from companyfacts.

    Flow metrics keep only ~quarter-length durations (70-100 days) so YTD and
    annual figures never mix into the series. Balance metrics keep instant
    values at each period end. When multiple tags carry the same metric, pick
    the tag whose series extends to the latest fiscal period (avoids stale
    tags like legacy Revenues blocking RevenueFromContractWithCustomer*).

    An IFRS series is used when it has no US-GAAP counterpart, or when its
    latest period is newer (then longer). A non-USD series records ``currency``.
    """
    root = facts.get("facts") or {}
    is_flow = metric in FLOW_METRICS
    additive = metric not in NON_ADDITIVE_METRICS
    per_share = metric in NON_ADDITIVE_METRICS
    gaap = _best_tag_series(
        root.get("us-gaap") or {},
        METRIC_TAGS[metric],
        is_flow=is_flow,
        additive=additive,
        prefer_one_unit=False,
        per_share=per_share,
    )
    ifrs = _best_tag_series(
        root.get("ifrs-full") or {},
        IFRS_METRIC_TAGS.get(metric) or [],
        is_flow=is_flow,
        additive=additive,
        prefer_one_unit=True,
        per_share=per_share,
    )
    chosen = gaap
    taxonomy = "us-gaap"
    if ifrs:
        gaap_latest = max(gaap) if gaap else ""
        ifrs_latest = max(ifrs)
        if (
            not gaap
            or ifrs_latest > gaap_latest
            or (ifrs_latest == gaap_latest and len(ifrs) > len(gaap))
        ):
            chosen = ifrs
            taxonomy = "ifrs-full"
    rows = [chosen[key] for key in sorted(chosen)]
    if taxonomy == "ifrs-full":
        for row in rows:
            row["taxonomy"] = "ifrs-full"
    return rows


def drop_discontinued_series(metrics: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Drop a tag whose last fact is more than two years behind the rest.

    FNV's long-term borrowings tag stops in 2019 while revenue and cash are
    current. A metric that is one quarter behind the balance sheet stays.
    """
    if not metrics:
        return metrics
    freshest = max(series[-1]["period"] for series in metrics.values() if series)
    fresh_dt = datetime.strptime(freshest, "%Y-%m-%d")
    return {
        name: series
        for name, series in metrics.items()
        if series and (fresh_dt - datetime.strptime(series[-1]["period"], "%Y-%m-%d")).days <= 730
    }


def build_ticker(ticker: str, cik: str) -> dict | None:
    facts = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if not facts:
        return None
    metrics: dict[str, list[dict]] = {}
    for metric in METRIC_TAGS:
        series = extract_metric_series(facts, metric)
        if len(series) >= 2:
            metrics[metric] = series[-24:]
    metrics = drop_discontinued_series(metrics)
    if not metrics:
        return None
    taxonomy = "ifrs-full" if any(
        point.get("taxonomy") == "ifrs-full"
        for series in metrics.values()
        for point in series
    ) else "us-gaap"
    return {
        "ticker": ticker,
        "cik": cik,
        "source": "sec_companyfacts",
        "taxonomy": taxonomy,
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
    missing = sorted(t for t in ciks if t not in covered)
    index = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(covered),
        "resolvable_ciks": len(ciks),
        "missing_fundamentals": missing,
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
