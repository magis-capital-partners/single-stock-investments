#!/usr/bin/env python3
"""Build spend-based value factor for biotech quant universe (Verdad-style).

spend ≈ revenue − CFO (cash out the door)
spend_value = market_cap / cumulative_spend  (lower = cheaper → higher quintile)

Pulls from local fundamentals/{TICKER}.json when present; otherwise fetches
SEC companyfacts for mapped universe tickers (cached under fundamentals/).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_fundamental_series import (  # noqa: E402
    extract_metric_series,
    fetch_json,
    sec_cik_map,
)
from ownership_common import (  # noqa: E402
    FUNDAMENTALS_PATH,
    SIGNALS_PATH,
    load_json,
    now_iso,
    portfolio_universe,
    save_json,
)

FUND_SERIES_DIR = ROOT / "_system" / "reference" / "market-data" / "fundamentals"
SEC_CIK_MAP = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json"
USER_AGENT_SLEEP = 0.15


def assign_quintiles(values: dict[str, float], higher_is_better: bool) -> dict[str, int]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_is_better)
    n = len(ordered)
    out: dict[str, int] = {}
    for i, (ticker, _) in enumerate(ordered):
        out[ticker] = 5 - min(4, int(i * 5 / max(n, 1)))
    return out


def ensure_series(ticker: str, cik_map: dict[str, str], *, fetch: bool) -> tuple[dict, bool]:
    """Load or fetch fundamentals/{TICKER}.json with revenues + cfo.

    Returns (payload, newly_fetched).
    """
    path = FUND_SERIES_DIR / f"{ticker.upper()}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")), False
        except json.JSONDecodeError:
            pass
    if not fetch:
        return {}, False
    cik = cik_map.get(ticker.upper()) or cik_map.get(ticker.upper().replace(".", "-"))
    if not cik:
        return {}, False
    facts = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    time.sleep(USER_AGENT_SLEEP)
    if not facts:
        return {}, False
    metrics = {
        "revenues": extract_metric_series(facts, "revenues"),
        "cfo": extract_metric_series(facts, "cfo"),
    }
    payload = {
        "ticker": ticker.upper(),
        "cik": cik,
        "source": "sec_companyfacts",
        "fetched_at": now_iso(),
        "metrics": metrics,
    }
    FUND_SERIES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload, True


def as_points(metric) -> list[dict]:
    if metric is None:
        return []
    if isinstance(metric, list):
        return [p for p in metric if isinstance(p, dict)]
    if isinstance(metric, dict):
        pts = metric.get("points")
        if isinstance(pts, list):
            return [p for p in pts if isinstance(p, dict)]
    return []


def ttm_sum(points: list[dict], key: str = "value") -> float | None:
    vals = []
    for pt in points[-4:]:
        v = pt.get(key)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return sum(vals) if vals else None


def cumulative_sum(points: list[dict], key: str = "value") -> float | None:
    vals = []
    for pt in points:
        v = pt.get(key)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return sum(vals) if vals else None


def market_cap_proxy(ticker: str, signals: dict) -> float | None:
    """Issuer capitalization only; fund position value is not issuer size."""
    from ownership_common import FUNDAMENTALS_PATH, load_json as own_load  # noqa: WPS433

    funda = (own_load(FUNDAMENTALS_PATH, {"by_ticker": {}}).get("by_ticker") or {}).get(ticker) or {}
    if funda.get("issuer_market_cap"):
        try:
            return float(funda["issuer_market_cap"])
        except (TypeError, ValueError):
            pass
    row = (signals.get("by_ticker") or {}).get(ticker) or {}
    if row.get("issuer_market_cap"):
        try:
            return float(row["issuer_market_cap"])
        except (TypeError, ValueError):
            pass
    # valuation.json price * shares if present
    val_path = ROOT / ticker / "research" / "valuation.json"
    if val_path.exists():
        try:
            val = json.loads(val_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            val = {}
        price = val.get("price") or (val.get("market") or {}).get("price")
        shares = val.get("shares_diluted") or (val.get("market") or {}).get("shares")
        try:
            if price and shares:
                return float(price) * float(shares)
        except (TypeError, ValueError):
            pass
    return None


def build(*, fetch_missing: bool = True, max_fetch: int = 80) -> dict:
    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    tickers = list((signals.get("by_ticker") or {}).keys())
    if not tickers:
        # fall back to portfolio healthcare sleeve
        port, _ = portfolio_universe()
        tickers = [
            t
            for t, m in port.items()
            if str(m.get("investment_sleeve") or "").lower() in {"healthcare_pharma", "biotech_pharma", "life_sciences"}
            or m.get("biotech_watchlist")
        ]

    previous = load_json(FUNDAMENTALS_PATH, {})
    by_ticker: dict[str, dict] = {t: dict(r) for t, r in (previous.get("by_ticker") or {}).items()}
    spend_values: dict[str, float] = {}
    cik_map = sec_cik_map() if fetch_missing else load_json(SEC_CIK_MAP, {})
    fetched = 0

    for ticker in tickers:
        if ":" in ticker or ticker.startswith("CUSIP"):
            continue
        # This file is shared with issuer-capitalization enrichment. Preserve
        # those observations and explicitly clear only this factor's fields.
        base = by_ticker.setdefault(ticker, {"ticker": ticker})
        base.update(spend_value=None, spend_value_quintile=None,
                    spend_status="missing", spend_missing_reason="Aligned revenue and cash-flow periods, issuer capitalization and dates are required.")
        do_fetch = fetch_missing and fetched < max_fetch
        series, newly = ensure_series(ticker, cik_map, fetch=do_fetch)
        if newly:
            fetched += 1
        metrics = series.get("metrics") or series
        rev_pts = as_points(metrics.get("revenues") or metrics.get("revenue"))
        cfo_pts = as_points(metrics.get("cfo"))

        rev_ttm = ttm_sum(rev_pts) if rev_pts else None
        cfo_ttm = ttm_sum(cfo_pts) if cfo_pts else None
        # Missing reported revenue is not reported zero revenue. The two series
        # must describe the same periods before they can be subtracted.
        if rev_ttm is None or cfo_ttm is None or len(rev_pts) < 4 or len(cfo_pts) < 4:
            continue
        if [p.get("period") for p in rev_pts] != [p.get("period") for p in cfo_pts]:
            base["spend_missing_reason"] = "Revenue and operating cash-flow periods do not align."
            continue
        rev = rev_ttm or 0.0
        cfo = cfo_ttm or 0.0
        spend_ttm = rev - cfo
        # Verdad: cash out the door; if CFO negative (burn), spend rises
        cum_rev = cumulative_sum(rev_pts) if rev_pts else rev
        cum_cfo = cumulative_sum(cfo_pts) if cfo_pts else cfo
        cumulative_spend = (cum_rev or 0) - (cum_cfo or 0)
        if cumulative_spend <= 0 and spend_ttm > 0:
            cumulative_spend = spend_ttm
        if cumulative_spend <= 0:
            continue
        mcap = market_cap_proxy(ticker, signals)
        if not mcap or mcap <= 0:
            base["spend_missing_reason"] = "Issuer market capitalization is unavailable; specialist holdings value cannot replace it."
            continue
        spend_value = mcap / cumulative_spend
        by_ticker[ticker] = {**base,
            "ticker": ticker,
            "revenue_ttm": rev_ttm,
            "cfo_ttm": cfo_ttm,
            "spend_ttm": spend_ttm,
            "cumulative_spend": cumulative_spend,
            "market_cap_proxy": mcap,
            "spend_value": round(spend_value, 4),
            "spend_status": "period_basis_review",
            "spend_missing_reason": "Verify annual versus quarterly cash-flow durations and reporting currency before decision use.",
            "observed_at": min(rev_pts[-1]["period"], cfo_pts[-1]["period"]),
            "source_ref": str((FUND_SERIES_DIR / f"{ticker}.json").relative_to(ROOT)).replace("\\", "/"),
        }
        # Legacy series can mix annual CFO with quarterly revenue. Preserve the
        # diagnostic, but only an explicit reviewed period/currency contract
        # can supply the ranking factor.
        if series.get("period_basis_verified") is True and series.get("currency") == "USD":
            by_ticker[ticker].update(spend_status="verified", spend_missing_reason=None)
            spend_values[ticker] = spend_value
        else:
            by_ticker[ticker]["spend_value_diagnostic"] = by_ticker[ticker]["spend_value"]
            by_ticker[ticker]["spend_value"] = None

    # Lower spend_value = cheaper = better → higher quintile
    quintiles = assign_quintiles(spend_values, higher_is_better=False)
    for ticker, row in by_ticker.items():
        row["spend_value_quintile"] = quintiles.get(ticker)

    return {
        "generated_at": now_iso(),
        "ticker_count": len(by_ticker), "factor_populated": len(spend_values),
        "by_ticker": by_ticker,
        "notes": "spend_value = market_cap_proxy / cumulative_spend; Q5 = cheapest on spend.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-fetch", action="store_true", help="Use local fundamentals only")
    parser.add_argument("--offline", action="store_true", help="Alias for --no-fetch (CI-safe)")
    parser.add_argument("--max-fetch", type=int, default=80, help="Max SEC companyfacts fetches")
    args = parser.parse_args()
    payload = build(fetch_missing=not (args.no_fetch or args.offline), max_fetch=args.max_fetch)
    save_json(FUNDAMENTALS_PATH, payload)
    # merge into signals if present
    signals = load_json(SIGNALS_PATH, {})
    if signals.get("by_ticker"):
        for ticker, row in (payload.get("by_ticker") or {}).items():
            if ticker in signals["by_ticker"]:
                signals["by_ticker"][ticker]["spend_value"] = row.get("spend_value")
                signals["by_ticker"][ticker]["spend_value_quintile"] = row.get("spend_value_quintile")
                signals["by_ticker"][ticker]["cumulative_spend"] = row.get("cumulative_spend")
        save_json(SIGNALS_PATH, signals)
    print(f"Wrote spend value for {payload['ticker_count']} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
