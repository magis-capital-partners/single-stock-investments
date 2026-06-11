#!/usr/bin/env python3
"""Build total-return panel: dividend sum, price vs total-return index, market cap.

Reads distribution history from valuation.json, fetches Yahoo full-history daily prices,
writes {TICKER}/research/total_return_panel.json, charts/total_return_{date}.svg,
and merges summary into valuation.json -> total_return_panel.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_equity_prices import fetch_price, yahoo_symbol_for  # noqa: E402
from portfolio_registry import load_registry  # noqa: E402

UA = "MarvinResearch/1.0 (total-return-panel)"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"


def registry_row(ticker: str) -> dict | None:
    return (load_registry().get("holdings") or {}).get(ticker.upper())


def tickers_from_registry() -> list[str]:
    holdings = (load_registry().get("holdings") or {})
    return sorted(holdings.keys())


def fetch_yahoo_daily_closes(symbol: str) -> tuple[list[str], list[float], str]:
    end = datetime.now(timezone.utc)
    url = (
        f"{YAHOO_CHART}/{symbol}?period1=0"
        f"&period2={int(end.timestamp())}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=30).read())
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception as exc:
        return [], [], f"yahoo_error:{exc}"

    by_day: dict[str, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day[d] = float(close)

    days = sorted(by_day.keys())
    if len(days) < 2:
        return [], [], "yahoo_insufficient"
    dates = days
    prices = [by_day[d] for d in days]
    return dates, prices, f"yahoo:{symbol}"


def distribution_map(val: dict) -> dict[int, float]:
    """Year -> per-share distribution from inputs.distribution_history."""
    inputs = val.get("inputs") or {}
    hist = inputs.get("distribution_history") or []
    out: dict[int, float] = {}
    for row in hist:
        try:
            yr = int(row.get("year") or row.get("fiscal_year"))
            amt = float(row["amount_per_share"])
        except (TypeError, ValueError, KeyError):
            continue
        out[yr] = amt
    if not out and inputs.get("dividend_per_share_annual"):
        try:
            yr = int(str(inputs.get("last_filing", ""))[:4] or date.today().year)
        except ValueError:
            yr = date.today().year
        out[yr] = float(inputs["dividend_per_share_annual"])
    return out


def build_series(
    dates: list[str],
    prices: list[float],
    dist_by_year: dict[int, float],
) -> tuple[list[float], list[float], float]:
    """Price index and total-return index (rebased 100). cum_div = sum of all distributions."""
    if not prices:
        return [], [], 0.0
    base = prices[0]
    price_idx = [100.0 * p / base for p in prices]
    tr_idx: list[float] = []
    tr_level = 100.0
    year_last_idx: dict[int, int] = {}
    for i, d in enumerate(dates):
        year_last_idx[int(d[:4])] = i
    for i, (d, p) in enumerate(zip(dates, prices)):
        if i > 0 and prices[i - 1] > 0:
            tr_level *= p / prices[i - 1]
        yr = int(d[:4])
        if year_last_idx.get(yr) == i and yr in dist_by_year and p > 0:
            tr_level *= 1.0 + dist_by_year[yr] / p
        tr_idx.append(tr_level)
    cum_div = sum(dist_by_year.values())
    return price_idx, tr_idx, cum_div


def svg_chart(
    dates: list[str],
    price_idx: list[float],
    tr_idx: list[float],
    *,
    ticker: str,
    market_cap_m: float | None,
    cum_div: float,
    width: int = 720,
    height: int = 360,
) -> str:
    margin = {"l": 56, "r": 24, "t": 48, "b": 52}
    plot_w = width - margin["l"] - margin["r"]
    plot_h = height - margin["t"] - margin["b"]
    n = len(dates)
    if n < 2:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            f'<text x="20" y="40">Insufficient price history for {ticker}</text></svg>'
        )

    all_vals = price_idx + tr_idx
    ymin = min(all_vals)
    ymax = max(all_vals)
    pad = (ymax - ymin) * 0.08 or 5.0
    ymin -= pad
    ymax += pad

    def x_at(i: int) -> float:
        return margin["l"] + (i / (n - 1)) * plot_w

    def y_at(v: float) -> float:
        return margin["t"] + plot_h - ((v - ymin) / (ymax - ymin)) * plot_h

    def poly(vals: list[float], color: str) -> str:
        pts = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(vals))
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'

    ticks = [0, n // 4, n // 2, 3 * n // 4, n - 1]
    x_labels = "".join(
        f'<text x="{x_at(i):.0f}" y="{height - 12}" font-size="11" text-anchor="middle" fill="#444">'
        f"{dates[i][:7]}</text>"
        for i in ticks
    )
    mcap_txt = f"${market_cap_m:.1f}M" if market_cap_m is not None else "n/a"
    title = (
        f"{ticker} total return (rebased 100) · cumulative distributions ${cum_div:,.2f}/sh"
        f" · market cap {mcap_txt}"
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#fafafa"/>
  <text x="{margin['l']}" y="22" font-size="13" font-family="sans-serif" fill="#222">{title}</text>
  <line x1="{margin['l']}" y1="{margin['t'] + plot_h}" x2="{margin['l'] + plot_w}" y2="{margin['t'] + plot_h}" stroke="#ccc"/>
  <line x1="{margin['l']}" y1="{margin['t']}" x2="{margin['l']}" y2="{margin['t'] + plot_h}" stroke="#ccc"/>
  {poly(price_idx, "#2563eb")}
  {poly(tr_idx, "#16a34a")}
  <text x="{margin['l'] + 4}" y="{margin['t'] + 14}" font-size="11" fill="#2563eb">Price index</text>
  <text x="{margin['l'] + 90}" y="{margin['t'] + 14}" font-size="11" fill="#16a34a">Total return (price + distributions)</text>
  {x_labels}
</svg>
"""


def annualized_return(start_price: float, end_price: float, years: float, cum_div: float) -> float | None:
    if start_price <= 0 or years <= 0:
        return None
    total = (end_price + cum_div) / start_price
    if total <= 0:
        return None
    return (total ** (1.0 / years) - 1.0) * 100.0


def build_panel(ticker: str, as_of: str | None = None, *, merge: bool = True) -> bool:
    t = ticker.upper()
    research = ROOT / t / "research"
    vpath = research / "valuation.json"
    if not vpath.exists():
        print(f"SKIP {t}: no valuation.json")
        return False

    val = json.loads(vpath.read_text(encoding="utf-8"))
    inputs = val.get("inputs") or {}
    row = registry_row(t) or {}
    market = row.get("market", "US")
    exchange = row.get("exchange", "")
    ysym = yahoo_symbol_for(t, market, exchange)

    dates, prices, src = fetch_yahoo_daily_closes(ysym)
    dist = distribution_map(val)
    panel_status = "complete"
    panel_error = None
    price_idx: list[float] = []
    tr_idx: list[float] = []
    cum_div = sum(dist.values())
    if len(prices) >= 2:
        price_idx, tr_idx, cum_div = build_series(dates, prices, dist)
    else:
        panel_status = "insufficient_price_history"
        panel_error = src

    price = inputs.get("price")
    if price is None:
        live, _, _ = fetch_price(t)
        price = live
    shares = inputs.get("shares_outstanding")
    market_cap_m = None
    if price and shares:
        market_cap_m = round(float(price) * float(shares) / 1_000_000, 2)

    start_price = prices[0] if prices else None
    end_price = prices[-1] if prices else None
    if len(dates) >= 2:
        span_days = max(1, (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days)
        span_years = max(0.5, span_days / 365.25)
    else:
        span_years = None
    price_ann = (
        annualized_return(start_price, end_price, span_years, 0.0)
        if start_price is not None and end_price is not None and span_years is not None
        else None
    )
    tr_ann = (
        annualized_return(start_price, end_price, span_years, cum_div)
        if start_price is not None and end_price is not None and span_years is not None
        else None
    )

    as_of = as_of or date.today().isoformat()
    charts_dir = research / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_name = f"total_return_{as_of}.svg"
    chart_path = charts_dir / chart_name
    svg = svg_chart(
        dates,
        price_idx,
        tr_idx,
        ticker=t,
        market_cap_m=market_cap_m,
        cum_div=cum_div,
    )
    chart_path.write_text(svg, encoding="utf-8")

    panel = {
        "ticker": t,
        "as_of": as_of,
        "price_source": src,
        "status": panel_status,
        "error": panel_error,
        "history_start": dates[0] if dates else None,
        "history_end": dates[-1] if dates else None,
        "price_points": len(prices),
        "price_interval": "1d",
        "start_price": round(start_price, 4) if start_price is not None else None,
        "end_price": round(end_price, 4) if end_price is not None else None,
        "cumulative_distributions_per_share": round(cum_div, 4),
        "distribution_years": len(dist),
        "distribution_history_sum": round(sum(dist.values()), 4),
        "price_index_end": round(price_idx[-1], 2) if price_idx else None,
        "total_return_index_end": round(tr_idx[-1], 2) if tr_idx else None,
        "price_only_annualized_pct": round(price_ann, 2) if price_ann is not None else None,
        "total_return_annualized_pct": round(tr_ann, 2) if tr_ann is not None else None,
        "market_cap_m": market_cap_m,
        "shares_outstanding": shares,
        "price_for_market_cap": price,
        "chart": f"{t}/research/charts/{chart_name}",
    }

    panel_path = research / "total_return_panel.json"
    panel_path.write_text(json.dumps(panel, indent=2) + "\n", encoding="utf-8")

    if merge:
        val["total_return_panel"] = {
            "as_of": as_of,
            "status": panel_status,
            "error": panel_error,
            "cumulative_distributions_per_share": panel["cumulative_distributions_per_share"],
            "distribution_history_sum": panel["distribution_history_sum"],
            "market_cap_m": market_cap_m,
            "total_return_annualized_pct": panel["total_return_annualized_pct"],
            "chart": panel["chart"],
            "panel_json": f"{t}/research/total_return_panel.json",
        }
        vpath.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")

    if panel_status == "complete":
        print(
            f"OK {t}: cum_div=${cum_div:.2f}/sh market_cap={market_cap_m}M "
            f"chart={chart_path.relative_to(ROOT)}"
        )
        return True
    print(f"WARN {t}: {panel_status} ({panel_error})")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--all", action="store_true", help="Build panels for all registry holdings")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()
    tickers = [t.upper() for t in args.tickers]
    if args.all:
        tickers = tickers_from_registry()
    if not tickers:
        ap.error("provide tickers or use --all")

    ok = 0
    warn = 0
    for t in tickers:
        if build_panel(t, args.date, merge=not args.no_merge):
            ok += 1
        else:
            warn += 1
    print(f"SUMMARY: ok={ok} warn={warn} total={len(tickers)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
