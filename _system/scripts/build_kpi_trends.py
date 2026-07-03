#!/usr/bin/env python3
"""Build dashboard/data/kpi_trends.json - second-derivative KPI signals per ticker.

Assembles per-ticker time series from:
  - {TICKER}/research/evidence/filing_facts_*.json  (canonical filing metrics)
  - dashboard/data/equity_models.json               (model observation series)
  - dashboard/data/portfolio_news.json              (monthly news-flow counts)

For each series with enough points it computes growth (first derivative) and
the change in growth (second derivative), with a significance guard scaled to
the series' own volatility so small wiggles do not fire. The goal is to flag
accelerations and decelerations before they become consensus.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "kpi_trends.json"
EQUITY_MODELS_PATH = ROOT / "dashboard" / "data" / "equity_models.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
NEWS_HISTORY_PATH = ROOT / "_system" / "reference" / "market-data" / "news_flow_history.json"

MIN_POINTS = 4
MAX_POINTS = 8
NEWS_WINDOW_MONTHS = 8

METRIC_LABELS = {
    "revenues": "Revenue",
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "eps_basic": "EPS (basic)",
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
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def analyze_series(points: list[tuple[str, float]], *, mode: str = "pct") -> dict | None:
    """Compute first/second derivative for a (period, value) series.

    mode="pct":  growth as fractional change (financial series)
    mode="diff": growth as absolute change (count series with zeros)
    Returns None when the series is too short or degenerate.
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
            growths.append((cur - prev) / abs(prev))
    if len(growths) < 3:
        return None

    accels = [b - a for a, b in zip(growths, growths[1:])]
    latest_accel = accels[-1]
    history = accels[:-1]
    if len(history) >= 2:
        vol = statistics.pstdev(history)
    else:
        vol = abs(history[0]) if history else 0.0

    if mode == "diff":
        threshold = max(1.0, 0.75 * vol)
    else:
        threshold = max(0.02, 0.75 * vol)

    if latest_accel > threshold:
        direction = "accelerating"
    elif latest_accel < -threshold:
        direction = "decelerating"
    else:
        direction = "steady"

    return {
        "direction": direction,
        "growth_latest": round(growths[-1], 4),
        "growth_prior": round(growths[-2], 4),
        "accel": round(latest_accel, 4),
        "threshold": round(threshold, 4),
        "mode": mode,
        "points": [{"period": p, "value": v} for p, v in ordered],
    }


def filing_facts_series(ticker_dir: Path) -> dict[str, list[tuple[str, float]]]:
    """Assemble per-metric series across all filing_facts_*.json files."""
    evidence_dir = ticker_dir / "research" / "evidence"
    if not evidence_dir.is_dir():
        return {}
    series: dict[str, dict[str, float]] = {}
    for path in sorted(evidence_dir.glob("filing_facts_*.json")):
        doc = load_json(path)
        if not isinstance(doc, dict):
            continue
        meta = doc.get("filing_meta") or {}
        period = meta.get("period_end") or meta.get("filing_date") or doc.get("as_of")
        if not period:
            continue
        for name, metric in (doc.get("metrics") or {}).items():
            if not isinstance(metric, dict):
                continue
            current = to_float(metric.get("current"))
            if current is None:
                continue
            series.setdefault(name, {})[str(period)[:10]] = current
    return {name: sorted(points.items()) for name, points in series.items()}


def equity_model_series(ticker: str, models_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Extract observation series (lists of {period, <numeric>}) from equity models."""
    entry = ((models_doc or {}).get("tickers") or {}).get(ticker) or {}
    forms = ((entry.get("production") or {}).get("forms") or {})
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


def portfolio_ticker_dirs() -> list[Path]:
    out = []
    for p in sorted(ROOT.iterdir()):
        if p.is_dir() and not p.name.startswith((".", "_")) and p.name not in ("dashboard", "docs", "terminals"):
            out.append(p)
    return out


def build_trends() -> dict:
    models_doc = load_json(EQUITY_MODELS_PATH)
    news_doc = load_json(NEWS_PATH)
    news_series = merged_news_history(news_doc if isinstance(news_doc, dict) else {})

    by_ticker: dict[str, dict] = {}

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

    for ticker_dir in portfolio_ticker_dirs():
        ticker = ticker_dir.name
        for metric, points in filing_facts_series(ticker_dir).items():
            analysis = analyze_series(points, mode="pct")
            if analysis:
                add_metric(ticker, metric, "filing_facts", analysis, f"{ticker}/research/evidence")
        for metric, points in equity_model_series(ticker, models_doc).items():
            analysis = analyze_series(points, mode="pct")
            if analysis:
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
        "by_ticker": by_ticker,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KPI trend (second derivative) JSON.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build_trends()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output.relative_to(ROOT)} "
        f"({payload['ticker_count']} tickers, {payload['inflection_count']} inflections)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
