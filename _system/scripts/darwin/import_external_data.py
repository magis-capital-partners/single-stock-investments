"""Sync cross-asset context from etf-dashboard / ls-algo into Marvin market-data."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .external_sources import (
    EXTERNAL_ROOT,
    etf_data_path,
    risk_dashboard_latest,
    save_sources_manifest,
)
from .prices import RETURNS_DIR, fetch_yahoo_monthly

# etf_metrics_daily covers leveraged/YB names; macro indices via Yahoo fallback
ETF_METRICS_ALIASES: dict[str, list[str]] = {
    "SPY": ["SPXL", "SPXS"],
    "QQQ": ["TQQQ", "SQQQ"],
    "IWM": ["TNA", "TZA"],
    "TLT": ["TMF", "TBT"],
}

OBSERVATORY_TICKERS = [
    "SPY",
    "QQQ",
    "IWM",
    "TLT",
    "GLD",
    "HYG",
    "VIXY",
]


def _monthly_returns_from_daily_csv(path: Path, ticker: str, price_col: str = "underlying_adj_close") -> tuple[list[str], list[float]]:
    by_month: dict[str, float] = {}
    with path.open(encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("ticker") or "").upper() != ticker.upper():
                continue
            d = (row.get("date") or "")[:10]
            try:
                px = float(row.get(price_col) or row.get("close_price") or row.get("etf_adj_close") or "")
            except ValueError:
                continue
            if d and px > 0:
                by_month[d[:7]] = px
    months = sorted(by_month.keys())
    dates: list[str] = []
    rets: list[float] = []
    prev = None
    for m in months:
        c = by_month[m]
        if prev is not None and prev > 0:
            dates.append(f"{m}-01")
            rets.append((c / prev) - 1.0)
        prev = c
    return dates, rets


def write_returns_csv(ticker: str, dates: list[str], rets: list[float]) -> Path | None:
    if len(rets) < 6:
        return None
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    key = ticker.replace(".", "_")
    path = RETURNS_DIR / f"{key}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "monthly_return"])
        for d, r in zip(dates, rets):
            w.writerow([d, f"{r:.8f}"])
    return path


def extract_risk_dashboard_summary(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    book = data.get("book") or {}
    scenarios = data.get("scenarios") or data.get("portfolio_scenarios") or {}
    return {
        "run_date": data.get("run_date"),
        "nav_usd": data.get("nav_usd"),
        "gross_exposure_pct_nav": book.get("gross_exposure_pct_nav"),
        "net_exposure_pct_nav": book.get("net_exposure_pct_nav"),
        "pnl_today_pct_nav": book.get("pnl_today_pct_nav"),
        "breach_count": len(book.get("breaches") or []),
        "breaches": (book.get("breaches") or [])[:5],
        "scenario_horizons": scenarios.get("scenario_horizons") if isinstance(scenarios, dict) else None,
        "vix_shocks_pts": scenarios.get("vix_shocks_pts") if isinstance(scenarios, dict) else None,
    }


def load_json_snapshot(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def sync_external_market_data() -> dict:
    EXTERNAL_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = save_sources_manifest()
    report: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "returns_written": [],
        "errors": [],
    }

    metrics_csv = etf_data_path("etf_metrics_daily.csv")
    for t in OBSERVATORY_TICKERS:
        dates: list[str] = []
        rets: list[float] = []
        source = ""
        if metrics_csv:
            dates, rets = _monthly_returns_from_daily_csv(metrics_csv, t)
            source = "etf_metrics_daily"
        if len(rets) < 6 and metrics_csv:
            for alias in ETF_METRICS_ALIASES.get(t, []):
                dates, rets = _monthly_returns_from_daily_csv(metrics_csv, alias)
                if len(rets) >= 6:
                    # Scale 3x LETF monthly moves toward 1x index (exploratory proxy)
                    rets = [r / 3.0 for r in rets]
                    source = f"etf_proxy_{alias}"
                    break
        if len(rets) < 6:
            dates, rets, ysrc = fetch_yahoo_monthly(t, months=60)
            if len(rets) >= 6:
                source = ysrc
        out = write_returns_csv(t, dates, rets)
        if out:
            report["returns_written"].append(
                {
                    "ticker": t,
                    "path": str(out.relative_to(ROOT)),
                    "months": len(rets),
                    "source": source,
                }
            )
        elif metrics_csv or t:
            report["errors"].append(f"no_returns:{t}")
    if not metrics_csv:
        report["errors"].append("etf_metrics_daily.csv not found (yahoo-only path)")

    # Context JSON blobs (small)
    for label, fn in [
        ("vrp_health", "vrp_health.json"),
        ("borrow_spike_risk", "borrow_spike_risk.json"),
        ("macro_event_calendar", "macro_event_calendar.json"),
    ]:
        p = etf_data_path(fn)
        if p:
            snap = load_json_snapshot(p)
            if snap:
                dest = EXTERNAL_ROOT / f"{label}.json"
                dest.write_text(json.dumps(snap, indent=2)[:500000] + "\n", encoding="utf-8")

    rd = risk_dashboard_latest()
    if rd:
        summary = extract_risk_dashboard_summary(rd)
        (EXTERNAL_ROOT / "risk_dashboard_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        report["risk_dashboard"] = summary
    else:
        report["errors"].append("ls-algo risk_dashboard latest.json not found")

    (EXTERNAL_ROOT / "sync_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys

    r = sync_external_market_data()
    print(json.dumps(r, indent=2))
    sys.exit(1 if r.get("errors") and not r.get("returns_written") else 0)
