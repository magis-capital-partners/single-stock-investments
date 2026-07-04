#!/usr/bin/env python3
"""Extract quarterly/semi-annual KPI series from equity model panels and dossiers.

Writes dashboard/data/equity_kpi_series.json for build_kpi_trends.py (Tier-2
fundamentals for non-US and model-backed names without SEC XBRL).

Sources scanned per holding:
  - {TICKER}/research/model/panel_halfyear.csv
  - {TICKER}/research/model/panel_quarterly.csv
  - {TICKER}/research/fundamentals_quarterly.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "equity_kpi_series.json"

PANEL_METRICS = (
    "revenue",
    "net_income",
    "operating_income",
    "cfo",
    "ordinary",
    "base_fee",
    "perf_fee",
)


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def to_float(raw) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_metric_csv(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    metrics: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            period = (row.get("period_end") or row.get("period") or row.get("date") or "").strip()[:10]
            if not period:
                continue
            for field in PANEL_METRICS:
                value = to_float(row.get(field))
                if value is None:
                    continue
                metrics.setdefault(field, []).append({"period": period, "value": value})
    for field, series in metrics.items():
        by_period = {str(p["period"]): p for p in series if p.get("period")}
        metrics[field] = [by_period[k] for k in sorted(by_period)]
    return metrics


def universe_tickers() -> list[str]:
    reg = load_json(REGISTRY_PATH, {})
    return sorted((reg.get("holdings") or {}).keys())


def extract_ticker(ticker: str) -> dict | None:
    ticker_dir = ROOT / ticker
    sources: list[str] = []
    metrics: dict[str, list[dict]] = {}

    candidates = [
        ticker_dir / "research" / "model" / "panel_halfyear.csv",
        ticker_dir / "research" / "model" / "panel_quarterly.csv",
        ticker_dir / "research" / "fundamentals_quarterly.csv",
    ]
    for path in candidates:
        parsed = parse_metric_csv(path)
        if not parsed:
            continue
        sources.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        for field, series in parsed.items():
            if len(series) >= 2:
                metrics[field] = series[-24:]

    if not metrics:
        return None
    return {
        "source_files": sources,
        "metrics": metrics,
    }


def build() -> dict:
    tickers: dict[str, dict] = {}
    for ticker in universe_tickers():
        block = extract_ticker(ticker)
        if block:
            tickers[ticker] = block
    return {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(tickers),
        "tickers": tickers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract equity-model KPI observation series.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)} ({payload['ticker_count']} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
