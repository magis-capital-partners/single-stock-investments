#!/usr/bin/env python3
"""Build dashboard/data/kpi_trends.json - second-derivative KPI signals per ticker.

Sources, in order of trust:
  - _system/reference/market-data/fundamentals/{TICKER}.json
        SEC XBRL companyfacts quarterly series (build_fundamental_series.py).
        Real fiscal period ends; quarterly scope enforced at extraction.
  - dashboard/data/equity_models.json  (model observation series)
  - dashboard/data/portfolio_news.json (monthly news-flow counts)

Quarterly fundamentals are analyzed on a year-over-year basis: growth compares
each quarter to the same quarter a year earlier (killing seasonality), and the
second derivative is the change in YoY growth between consecutive quarters.
A signal fires only when the latest change clears a threshold scaled to the
series' own volatility. Degenerate points (near-zero denominators, >500%
swings) are excluded and counted as suspect rather than published.

The legacy filing_facts_*.json source was removed: those extracts carry no
fiscal period or scope metadata, which produced false inflections (duplicate
snapshots + quarterly/annual mixing).
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "kpi_trends.json"
FUNDAMENTALS_DIR = ROOT / "_system" / "reference" / "market-data" / "fundamentals"
EQUITY_MODELS_PATH = ROOT / "dashboard" / "data" / "equity_models.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
NEWS_HISTORY_PATH = ROOT / "_system" / "reference" / "market-data" / "news_flow_history.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

MIN_POINTS = 4
MAX_POINTS = 8
NEWS_WINDOW_MONTHS = 8

# YoY analysis knobs
YOY_MIN_QUARTERS = 8          # need 2+ years to compute enough YoY growth points
YOY_MIN_GROWTH_POINTS = 4     # 3 accels: >=2 history + 1 latest
YOY_MATCH_WINDOW = (330, 400)  # days between a quarter and its prior-year match
GROWTH_OUTLIER_CAP = 5.0      # |growth| beyond 500% treated as data artifact
DENOMINATOR_FLOOR_FRAC = 0.05  # |prior| must be >= 5% of series median scale

METRIC_LABELS = {
    "revenues": "Revenue",
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "eps_basic": "EPS (basic)",
    "cfo": "Operating cash flow",
    "total_assets": "Total assets",
    "stockholders_equity": "Stockholders' equity",
    "long_term_debt": "Long-term debt",
    "cash": "Cash",
    "news_flow": "News flow",
}


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_date(period: str) -> datetime | None:
    try:
        return datetime.strptime(str(period)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def classify_accel(latest_accel: float, history: list[float], *, floor: float) -> tuple[str, float]:
    if len(history) >= 2:
        vol = statistics.pstdev(history)
    else:
        vol = abs(history[0]) if history else 0.0
    threshold = max(floor, 0.75 * vol)
    if latest_accel > threshold:
        return "accelerating", threshold
    if latest_accel < -threshold:
        return "decelerating", threshold
    return "steady", threshold


def analyze_quarterly_yoy(series: list[dict]) -> dict | None:
    """Second derivative of year-over-year growth for a quarterly series.

    series: [{"period": "YYYY-MM-DD", "value": float, ...}] with real fiscal
    period ends. Returns None when there is not enough clean history.
    """
    cleaned: dict[str, float] = {}
    for point in series:
        value = to_float(point.get("value"))
        period = str(point.get("period") or "")[:10]
        if value is None or not parse_date(period):
            continue
        cleaned[period] = value
    ordered = sorted(cleaned.items())
    if len(ordered) < YOY_MIN_QUARTERS:
        return None

    dates = [parse_date(p) for p, _v in ordered]
    values = [v for _p, v in ordered]
    nonzero = [abs(v) for v in values if abs(v) > 1e-9]
    scale = statistics.median(nonzero) if nonzero else 0.0
    denom_floor = max(1e-9, DENOMINATOR_FLOOR_FRAC * scale)

    growths: list[tuple[str, float]] = []
    suspect = 0
    lo, hi = YOY_MATCH_WINDOW
    for i in range(len(ordered)):
        match = None
        for j in range(i - 1, -1, -1):
            days = (dates[i] - dates[j]).days
            if lo <= days <= hi:
                match = j
                break
            if days > hi:
                break
        if match is None:
            continue
        prev, cur = values[match], values[i]
        if abs(prev) < denom_floor:
            suspect += 1
            continue
        growth = (cur - prev) / abs(prev)
        if abs(growth) > GROWTH_OUTLIER_CAP:
            suspect += 1
            continue
        growths.append((ordered[i][0], growth))

    if len(growths) < YOY_MIN_GROWTH_POINTS:
        return None

    gvals = [g for _p, g in growths]
    accels = [b - a for a, b in zip(gvals, gvals[1:])]
    direction, threshold = classify_accel(accels[-1], accels[:-1], floor=0.03)

    return {
        "direction": direction,
        "basis": "yoy",
        "growth_latest": round(gvals[-1], 4),
        "growth_prior": round(gvals[-2], 4),
        "accel": round(accels[-1], 4),
        "threshold": round(threshold, 4),
        "mode": "pct",
        "suspect_points": suspect,
        "points": [{"period": p, "value": v} for p, v in ordered[-MAX_POINTS:]],
    }


def analyze_series(points: list[tuple[str, float]], *, mode: str = "pct") -> dict | None:
    """Sequential first/second derivative for non-quarterly series.

    Used for equity-model observations (arbitrary cadence) and news-flow
    counts. mode="pct" uses fractional growth; mode="diff" absolute change.
    """
    cleaned: dict[str, float] = {}
    for period, value in points:
        if not period or value is None:
            continue
        cleaned[str(period)[:10]] = float(value)
    ordered = sorted(cleaned.items())[-MAX_POINTS:]
    if len(ordered) < MIN_POINTS:
        return None

    values = [v for _p, v in ordered]
    growths: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if mode == "diff":
            growths.append(cur - prev)
        else:
            if abs(prev) < 1e-9:
                return None
            growth = (cur - prev) / abs(prev)
            if abs(growth) > GROWTH_OUTLIER_CAP:
                return None
            growths.append(growth)
    if len(growths) < 3:
        return None

    accels = [b - a for a, b in zip(growths, growths[1:])]
    floor = 1.0 if mode == "diff" else 0.02
    direction, threshold = classify_accel(accels[-1], accels[:-1], floor=floor)

    return {
        "direction": direction,
        "basis": "seq",
        "growth_latest": round(growths[-1], 4),
        "growth_prior": round(growths[-2], 4),
        "accel": round(accels[-1], 4),
        "threshold": round(threshold, 4),
        "mode": mode,
        "points": [{"period": p, "value": v} for p, v in ordered],
    }


def fundamentals_series() -> dict[str, dict[str, list[dict]]]:
    """ticker -> metric -> quarterly series from the XBRL cache."""
    out: dict[str, dict[str, list[dict]]] = {}
    if not FUNDAMENTALS_DIR.is_dir():
        return out
    for path in sorted(FUNDAMENTALS_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        doc = load_json(path)
        metrics = doc.get("metrics") if isinstance(doc, dict) else None
        if not isinstance(metrics, dict):
            continue
        out[str(doc.get("ticker") or path.stem).upper()] = metrics
    return out


def equity_model_series(ticker: str, models_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Extract observation series (lists of {period, <numeric>}) from equity models."""
    entry = ((models_doc or {}).get("tickers") or {}).get(ticker) or {}
    forms = (entry.get("production") or {}).get("forms") or {}
    out: dict[str, list[tuple[str, float]]] = {}
    for form_key, form in forms.items():
        if not isinstance(form, dict):
            continue
        observations = form.get("observations")
        if not isinstance(observations, list):
            continue
        by_field: dict[str, list[tuple[str, float]]] = {}
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            period = obs.get("period")
            if not period:
                continue
            for field, raw in obs.items():
                if field == "period":
                    continue
                value = to_float(raw)
                if value is None:
                    continue
                by_field.setdefault(field, []).append((str(period)[:10], value))
        for field, points in by_field.items():
            out[f"{form_key}.{field}"] = points
    return out


def news_flow_series(news_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Monthly news item counts per ticker from the current feed window."""
    items = (news_doc or {}).get("items") or []
    counts: dict[str, dict[str, float]] = {}
    for item in items:
        published = str(item.get("published_utc") or "")[:7]
        if not published or len(published) != 7:
            continue
        for ticker in item.get("tickers") or []:
            bucket = counts.setdefault(str(ticker).upper(), {})
            bucket[published] = bucket.get(published, 0.0) + 1
    return {
        ticker: [(f"{m}-01", v) for m, v in sorted(by_month.items())]
        for ticker, by_month in counts.items()
    }


def merged_news_history(news_doc: dict, *, write: bool = True) -> dict[str, list[tuple[str, float]]]:
    """Merge the current 30-day feed into a persistent monthly history.

    The news feed only covers a rolling month, so long series must be
    accumulated across builds. Counts merge with max() so repeated runs over
    the same partial month converge without double counting. Only observed
    months are returned; the current (incomplete) month is excluded so it
    never reads as a false deceleration.
    """
    history = load_json(NEWS_HISTORY_PATH, {})
    by_ticker: dict[str, dict[str, float]] = {
        str(t).upper(): {str(m): float(v) for m, v in (months or {}).items()}
        for t, months in (history.get("by_ticker") or {}).items()
    }
    months_observed = set(history.get("months_observed") or [])

    current = news_flow_series(news_doc)
    for ticker, points in current.items():
        bucket = by_ticker.setdefault(ticker, {})
        for period, count in points:
            month = period[:7]
            months_observed.add(month)
            bucket[month] = max(bucket.get(month, 0.0), count)

    if write:
        NEWS_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        NEWS_HISTORY_PATH.write_text(
            json.dumps(
                {
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "months_observed": sorted(months_observed),
                    "by_ticker": by_ticker,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    usable_months = sorted(m for m in months_observed if m < this_month)
    out: dict[str, list[tuple[str, float]]] = {}
    for ticker, bucket in by_ticker.items():
        out[ticker] = [(f"{m}-01", bucket.get(m, 0.0)) for m in usable_months[-NEWS_WINDOW_MONTHS:]]
    return out


def build_trends() -> dict:
    models_doc = load_json(EQUITY_MODELS_PATH)
    news_doc = load_json(NEWS_PATH)
    news_series = merged_news_history(news_doc if isinstance(news_doc, dict) else {})
    fundamentals = fundamentals_series()
    registry = load_json(REGISTRY_PATH, {})
    universe = sorted((registry.get("holdings") or {}).keys())

    by_ticker: dict[str, dict] = {}
    suspect_excluded = 0

    def add_metric(ticker: str, metric: str, source: str, analysis: dict, evidence_ref: str | None) -> None:
        entry = by_ticker.setdefault(
            ticker,
            {"metrics": [], "summary": {"accelerating": 0, "decelerating": 0, "steady": 0}},
        )
        entry["metrics"].append(
            {
                "metric": metric,
                "label": METRIC_LABELS.get(metric, metric.replace("_", " ").title()),
                "source": source,
                "evidence_ref": evidence_ref,
                **analysis,
            }
        )
        entry["summary"][analysis["direction"]] += 1

    for ticker, metrics in sorted(fundamentals.items()):
        for metric, series in sorted(metrics.items()):
            analysis = analyze_quarterly_yoy(series)
            if analysis is None:
                continue
            suspect_excluded += analysis.pop("suspect_points", 0) or 0
            add_metric(
                ticker,
                metric,
                "sec_fundamentals",
                analysis,
                f"_system/reference/market-data/fundamentals/{ticker}.json",
            )

    equity_model_tickers = set()
    for ticker in sorted(((models_doc or {}).get("tickers") or {}).keys()):
        for metric, points in equity_model_series(ticker, models_doc).items():
            analysis = analyze_series(points, mode="pct")
            if analysis:
                equity_model_tickers.add(ticker)
                add_metric(ticker, metric, "equity_model", analysis, "dashboard/data/equity_models.json")

    for ticker, points in news_series.items():
        analysis = analyze_series(points, mode="diff")
        if analysis and analysis["direction"] != "steady":
            add_metric(ticker, "news_flow", "news_flow", analysis, "dashboard/data/portfolio_news.json")

    inflection_count = sum(
        1
        for entry in by_ticker.values()
        for metric in entry["metrics"]
        if metric["direction"] != "steady"
    )
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(by_ticker),
        "inflection_count": inflection_count,
        "coverage": {
            "universe": len(universe),
            "fundamentals_tickers": len(fundamentals),
            "equity_model_tickers": len(equity_model_tickers),
            "analyzed_tickers": len(by_ticker),
            "suspect_points_excluded": suspect_excluded,
        },
        "by_ticker": by_ticker,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KPI trend (second derivative) JSON.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build_trends()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cov = payload["coverage"]
    print(
        f"Wrote {args.output.relative_to(ROOT)} "
        f"({payload['ticker_count']} tickers, {payload['inflection_count']} inflections, "
        f"fundamentals {cov['fundamentals_tickers']}/{cov['universe']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
