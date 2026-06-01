"""Fetch monthly return panels for backtest (CSV vault / Yahoo)."""
from __future__ import annotations

import csv
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT

RETURNS_DIR = ROOT / "_system" / "reference" / "market-data" / "returns"

UA = "Mozilla/5.0 (compatible; DarwinPortfolio/1.0)"
YAHOO_UA = UA


def stooq_symbol(ticker: str, market: str) -> str | None:
    t = ticker.upper()
    m = (market or "US").upper()
    if m == "US" or m == "OTC":
        base = t.split(".")[0]
        return f"{base}.US".lower()
    if m == "JP" and t.endswith(".T"):
        return t.replace(".T", ".JP").lower()
    if m == "CA" and not t.endswith(".TO"):
        return f"{t}.TO".lower() if "." not in t else t.lower()
    if m == "SE" and t.endswith(".ST"):
        return t.replace(".ST", ".SE").lower()
    if "." in t:
        return t.lower()
    return f"{t}.US".lower()


def fetch_yahoo_monthly(ticker: str, months: int = 36) -> tuple[list[str], list[float], str]:
    """Return (month_end_dates, monthly_returns, source)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=months * 31)
    p1 = int(start.timestamp())
    p2 = int(end.timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={p1}&period2={p2}&interval=1mo"
    )
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=25).read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return [], [], f"yahoo_error:{exc}"

    by_month: dict[str, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
        by_month[d] = float(close)

    months_sorted = sorted(by_month.keys())
    if len(months_sorted) < 2:
        return [], [], "yahoo_insufficient"

    dates: list[str] = []
    rets: list[float] = []
    prev = None
    for m in months_sorted:
        c = by_month[m]
        if prev is not None and prev > 0:
            dates.append(f"{m}-01")
            rets.append((c / prev) - 1.0)
        prev = c
    return dates, rets, "yahoo"


def load_returns_csv(ticker: str) -> tuple[list[str], list[float], str] | None:
    """Load Tier A monthly returns if present."""
    key = ticker.replace(".", "_")
    path = RETURNS_DIR / f"{key}.csv"
    if not path.exists():
        path = RETURNS_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    dates: list[str] = []
    rets: list[float] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = row.get("date", "").strip()
            try:
                r = float(row.get("monthly_return", ""))
            except ValueError:
                continue
            if d:
                dates.append(d)
                rets.append(r)
    if len(rets) < 6:
        return None
    src = "csv_vault"
    return dates, rets, src


def build_return_panel(tickers: list[dict], months: int = 36) -> dict:
    """tickers: list of {ticker, market, irr_base_pct}."""
    panel: dict[str, dict] = {}
    common_dates: set[str] | None = None

    for row in tickers:
        sym = stooq_symbol(row["ticker"], row.get("market", "US"))
        from .symbols import yahoo_for_ticker

        yahoo_sym = yahoo_for_ticker(row["ticker"], row.get("market", "US"))
        loaded = load_returns_csv(row["ticker"])
        if loaded:
            dates, rets, src = loaded
        else:
            dates, rets, src = fetch_yahoo_monthly(yahoo_sym, months=months)
        if len(rets) < 6:
            # Synthetic from IRR prior (monthly drift)
            irr = (row.get("irr_base_pct") or 8.0) / 100.0
            monthly = (1 + irr) ** (1 / 12) - 1
            n = max(months - 1, 12)
            end = datetime.now(timezone.utc)
            dates = []
            rets = []
            for i in range(n, 0, -1):
                d = (end - timedelta(days=30 * i)).strftime("%Y-%m-01")
                dates.append(d)
                rets.append(monthly)
            src = "synthetic_irr_prior"
        panel[row["ticker"]] = {"dates": dates, "returns": rets, "source": src}
        ds = set(dates)
        common_dates = ds if common_dates is None else common_dates & ds

    aligned_dates = sorted(common_dates or [])
    if len(aligned_dates) < 4:
        # fallback: shortest series
        min_len = min(len(panel[t]["returns"]) for t in panel) if panel else 0
        aligned_dates = panel[next(iter(panel))]["dates"][-min_len:] if panel else []

    matrix: dict[str, list[float]] = {}
    for t, info in panel.items():
        d2r = dict(zip(info["dates"], info["returns"]))
        matrix[t] = [d2r.get(d, 0.0) for d in aligned_dates]

    return {
        "dates": aligned_dates,
        "returns_by_ticker": matrix,
        "sources": {t: panel[t]["source"] for t in panel},
    }
