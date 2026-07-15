#!/usr/bin/env python3
"""Build a split- and distribution-aware wealth series and dashboard panel.

Yahoo closes are split-adjusted but exclude dividends. Historical cash events are
normalized to that same share basis and reinvested at the ex-date close. The
plotted ending wealth is the sole source for cumulative and annualized return.
"""
from __future__ import annotations

import argparse
import bisect
import html
import json
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_equity_prices import fetch_price, yahoo_symbol_for  # noqa: E402
from portfolio_registry import load_registry  # noqa: E402

UA = "MarvinResearch/2.0 (dividend-aware-total-return)"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
CASH_TYPES = {"regular_dividend", "special_dividend", "trust_distribution", "return_of_capital", "liquidating_distribution"}


def registry_row(ticker: str) -> dict | None:
    return (load_registry().get("holdings") or {}).get(ticker.upper())


def tickers_from_registry() -> list[str]:
    return sorted((load_registry().get("holdings") or {}).keys())


def _iso_day(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


def fetch_yahoo_history(symbol: str) -> tuple[list[str], list[float], list[dict], dict, str]:
    end = datetime.now(timezone.utc)
    url = f"{YAHOO_CHART}/{symbol}?period1=0&period2={int(end.timestamp())}&interval=1d&events=div%2Csplits"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=30).read())
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception as exc:
        return [], [], [], {}, f"yahoo_error:{exc}"
    by_day = {_iso_day(ts): float(close) for ts, close in zip(timestamps, closes) if close is not None}
    dates = sorted(by_day)
    events: list[dict] = []
    raw_events = result.get("events") or {}
    for row in (raw_events.get("dividends") or {}).values():
        events.append({
            "ex_date": _iso_day(int(row["date"])), "amount_per_share": float(row["amount"]),
            "currency": (result.get("meta") or {}).get("currency"), "type": "regular_dividend",
            "source": f"yahoo:{symbol}", "source_tier": "vendor", "reconciliation_status": "discovered",
        })
    for row in (raw_events.get("splits") or {}).values():
        numerator = float(row.get("numerator") or 0)
        denominator = float(row.get("denominator") or 0)
        ratio = numerator / denominator if numerator > 0 and denominator > 0 else float(row.get("splitRatio", "1:1").split(":")[0]) / float(row.get("splitRatio", "1:1").split(":")[1])
        events.append({
            "ex_date": _iso_day(int(row["date"])), "type": "split", "split_factor": ratio,
            "source": f"yahoo:{symbol}", "source_tier": "vendor", "reconciliation_status": "discovered",
        })
    return dates, [by_day[d] for d in dates], sorted(events, key=lambda x: x["ex_date"]), result.get("meta") or {}, f"yahoo:{symbol}"


def load_event_ledger(ticker: str, vendor_events: list[dict]) -> tuple[list[dict], dict]:
    path = ROOT / ticker / "research" / "distribution_events.json"
    local = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    overrides = local.get("events") or []
    # A primary-source row replaces a vendor row on date/type family; splits remain separate.
    override_dates = {(r.get("ex_date"), "cash" if r.get("type") in CASH_TYPES else r.get("type")) for r in overrides}
    events = [r for r in vendor_events if (r.get("ex_date"), "cash" if r.get("type") in CASH_TYPES else r.get("type")) not in override_dates]
    events.extend(overrides)
    events.sort(key=lambda x: (x.get("ex_date") or "", x.get("type") or ""))
    coverage = local.get("coverage") or {
        "status": "vendor_only", "start": None, "end": None,
        "note": "Vendor events are discovery evidence; primary-source completeness has not been established.",
    }
    return events, {**coverage, "ledger_path": f"{ticker}/research/distribution_events.json" if path.exists() else None}


def effective_event_index(dates: list[str], event_date: str) -> int | None:
    idx = bisect.bisect_left(dates, event_date)
    return idx if idx < len(dates) else None


def build_wealth_series(dates: list[str], prices: list[float], events: list[dict], *, prices_split_adjusted: bool = True) -> dict:
    if not dates or not prices or len(dates) != len(prices):
        return {"price_index": [], "total_return_index": [], "cash_by_type": {}, "event_counts": {}}
    events_at: dict[int, list[dict]] = {}
    for event in events:
        idx = effective_event_index(dates, event.get("ex_date") or "")
        if idx is not None:
            events_at.setdefault(idx, []).append(event)
    split_events = sorted(
        (e for e in events if e.get("type") == "split" and float(e.get("split_factor") or 1) > 0),
        key=lambda e: e.get("ex_date") or "",
    )

    def amount_on_price_basis(event: dict) -> float:
        amount = float(event.get("amount_per_share") or 0)
        if not prices_split_adjusted:
            return amount
        future_factor = 1.0
        for split in split_events:
            if (split.get("ex_date") or "") > (event.get("ex_date") or ""):
                future_factor *= float(split["split_factor"])
        return amount / future_factor
    price_shares = total_shares = 1.0
    initial_price = prices[0]
    price_idx: list[float] = []
    total_idx: list[float] = []
    cash_by_type: Counter = Counter()
    counts: Counter = Counter()
    for i, price in enumerate(prices):
        day_events = events_at.get(i, [])
        # Every same-day cash entitlement uses the pre-reinvestment share count.
        entitlement_shares = total_shares
        day_cash = 0.0
        for event in day_events:
            kind = event.get("type")
            counts[kind] += 1
            if kind == "split":
                factor = float(event.get("split_factor") or 1)
                if factor > 0 and not prices_split_adjusted:
                    price_shares *= factor
                    total_shares *= factor
            elif kind in CASH_TYPES:
                amount = amount_on_price_basis(event)
                cash = entitlement_shares * amount
                cash_by_type[kind] += cash
                day_cash += cash
            elif kind == "spin_off":
                value = float(event.get("fair_value_per_parent_share") or 0) * total_shares
                cash_by_type[kind] += value
                if price > 0:
                    total_shares += value / price
        if day_cash and price > 0:
            total_shares += day_cash / price
        price_idx.append(100 * price_shares * price / initial_price)
        total_idx.append(100 * total_shares * price / initial_price)
    return {
        "price_index": price_idx, "total_return_index": total_idx,
        "cash_by_type": {k: round(v, 6) for k, v in cash_by_type.items()},
        "event_counts": dict(counts),
    }


def annualized_from_index(index_end: float | None, span_days: int) -> float | None:
    if index_end is None or index_end <= 0 or span_days <= 0:
        return None
    return ((index_end / 100) ** (365.25 / span_days) - 1) * 100


def coverage_status(coverage: dict, history_start: str | None, history_end: str | None, events: list[dict]) -> tuple[str, str | None]:
    if not history_start or not history_end:
        return "insufficient_price_history", "price history unavailable"
    if coverage.get("status") != "complete":
        return "partial", coverage.get("note") or "distribution history is not primary-source complete"
    if not coverage.get("start") or coverage["start"] > history_start or not coverage.get("end") or coverage["end"] < history_end:
        return "evidence_blocked", "verified distribution coverage does not span the plotted price history"
    unresolved = [e for e in events if e.get("reconciliation_status") not in ("reconciled", "not_applicable")]
    if unresolved:
        return "evidence_blocked", f"{len(unresolved)} distribution or split event(s) remain unreconciled"
    return "complete", None


def _polyline(values: list[float], n: int, x_at, y_at, color: str, width: int = 2) -> str:
    if not values:
        return ""
    points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values[:n]))
    return f'<polyline fill="none" stroke="{color}" stroke-width="{width}" points="{points}"/>'


def svg_chart(dates: list[str], price_idx: list[float], total_idx: list[float], benchmark_idx: list[float], *, ticker: str, contributions: dict, width: int = 820, height: int = 410) -> str:
    if len(dates) < 2:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><text x="20" y="40">Insufficient price history for {html.escape(ticker)}</text></svg>'
    margin = {"l": 60, "r": 24, "t": 54, "b": 78}
    plot_w, plot_h = width - margin["l"] - margin["r"], height - margin["t"] - margin["b"]
    all_values = price_idx + total_idx + benchmark_idx
    ymin, ymax = min(all_values), max(all_values)
    pad = (ymax - ymin) * .08 or 5
    ymin, ymax = ymin - pad, ymax + pad
    x_at = lambda i: margin["l"] + i / (len(dates) - 1) * plot_w
    y_at = lambda v: margin["t"] + plot_h - (v - ymin) / (ymax - ymin) * plot_h
    ticks = sorted(set([0, len(dates)//4, len(dates)//2, 3*len(dates)//4, len(dates)-1]))
    labels = "".join(f'<text x="{x_at(i):.0f}" y="{height-48}" font-size="11" text-anchor="middle" fill="#64748b">{dates[i][:7]}</text>' for i in ticks)
    regular = sum(v for k, v in contributions.items() if k in ("regular_dividend", "trust_distribution"))
    special = contributions.get("special_dividend", 0)
    other = sum(v for k, v in contributions.items() if k not in ("regular_dividend", "trust_distribution", "special_dividend"))
    contribution = f"Regular ${regular:,.2f} · Special ${special:,.2f} · Other ${other:,.2f} per initial share path"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="{width}" height="{height}" fill="#fafafa"/><text x="{margin['l']}" y="24" font-size="14" font-family="sans-serif" fill="#0f172a">{html.escape(ticker)} wealth index · dividends reinvested on ex-date</text>
<text x="{margin['l']}" y="42" font-size="10" font-family="sans-serif" fill="#64748b">{html.escape(contribution)}</text>
<line x1="{margin['l']}" y1="{margin['t']+plot_h}" x2="{margin['l']+plot_w}" y2="{margin['t']+plot_h}" stroke="#cbd5e1"/>
{_polyline(price_idx, len(dates), x_at, y_at, '#2563eb')}{_polyline(total_idx, len(dates), x_at, y_at, '#16a34a', 3)}{_polyline(benchmark_idx, len(dates), x_at, y_at, '#94a3b8')}
<text x="{margin['l']}" y="{height-18}" font-size="11" fill="#2563eb">Price + splits</text><text x="{margin['l']+100}" y="{height-18}" font-size="11" fill="#16a34a">Total return</text><text x="{margin['l']+190}" y="{height-18}" font-size="11" fill="#64748b">SPY total return</text>{labels}</svg>'''


def align_benchmark(main_dates: list[str], benchmark_dates: list[str], benchmark_values: list[float]) -> list[float]:
    if not main_dates or not benchmark_dates or not benchmark_values:
        return []
    by_day = dict(zip(benchmark_dates, benchmark_values))
    available = sorted(by_day)
    out = []
    for day in main_dates:
        idx = bisect.bisect_right(available, day) - 1
        out.append(by_day[available[max(0, idx)]])
    base = out[0]
    return [100 * value / base for value in out] if base else []


def build_panel(ticker: str, as_of: str | None = None, *, merge: bool = True) -> bool:
    t = ticker.upper()
    research, vpath = ROOT / t / "research", ROOT / t / "research" / "valuation.json"
    if not vpath.exists():
        print(f"SKIP {t}: no valuation.json")
        return False
    val = json.loads(vpath.read_text(encoding="utf-8"))
    inputs, row = val.get("inputs") or {}, registry_row(t) or {}
    symbol = yahoo_symbol_for(t, row.get("market", "US"), row.get("exchange", ""))
    dates, prices, vendor_events, meta, source = fetch_yahoo_history(symbol)
    events, coverage = load_event_ledger(t, vendor_events)
    # A verified ledger may intentionally define a shorter honest plot window.
    if dates and coverage.get("status") == "complete" and coverage.get("start"):
        start_idx = bisect.bisect_left(dates, coverage["start"])
        dates, prices = dates[start_idx:], prices[start_idx:]
        events = [e for e in events if (e.get("ex_date") or "") >= coverage["start"]]
    wealth = build_wealth_series(dates, prices, events)
    price_idx, total_idx = wealth["price_index"], wealth["total_return_index"]
    b_dates, b_prices, b_events, _, _ = fetch_yahoo_history("SPY")
    b_wealth = build_wealth_series(b_dates, b_prices, b_events)
    benchmark_idx = align_benchmark(dates, b_dates, b_wealth["total_return_index"])
    status, error = coverage_status(coverage, dates[0] if dates else None, dates[-1] if dates else None, events)
    span_days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days if len(dates) > 1 else 0
    price_ann = annualized_from_index(price_idx[-1] if price_idx else None, span_days)
    total_ann = annualized_from_index(total_idx[-1] if total_idx else None, span_days)
    benchmark_ann = annualized_from_index(benchmark_idx[-1] if benchmark_idx else None, span_days)
    price = inputs.get("price")
    if price is None:
        price, _, _ = fetch_price(t)
    shares = inputs.get("shares_outstanding")
    market_cap_m = round(float(price) * float(shares) / 1_000_000, 2) if price and shares else None
    as_of = as_of or date.today().isoformat()
    chart_rel = f"{t}/research/charts/total_return_{as_of}.svg"
    chart_path = ROOT / chart_rel
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text(svg_chart(dates, price_idx, total_idx, benchmark_idx, ticker=t, contributions=wealth["cash_by_type"]), encoding="utf-8")
    cumulative_cash = round(sum(wealth["cash_by_type"].values()), 4)
    panel = {
        "schema_version": "2.0", "ticker": t, "as_of": as_of, "status": status, "error": error,
        "price_source": source, "currency": meta.get("currency"), "return_currency": meta.get("currency"), "fx_basis": "listing_currency_nominal",
        "history_start": dates[0] if dates else None, "history_end": dates[-1] if dates else None, "price_points": len(prices), "price_interval": "1d",
        "return_contract": "split-adjusted close excluding dividends; event amounts normalized for later splits; cash reinvested at ex-date close; pre-tax nominal",
        "coverage": coverage, "event_count": sum(wealth["event_counts"].values()), "event_counts": wealth["event_counts"],
        "cash_distributions_on_initial_share_path": cumulative_cash, "distribution_contribution_by_type": wealth["cash_by_type"],
        "cumulative_distributions_per_share": cumulative_cash,
        "start_price": round(prices[0], 4) if prices else None, "end_price": round(prices[-1], 4) if prices else None,
        "price_index_end": round(price_idx[-1], 2) if price_idx else None, "total_return_index_end": round(total_idx[-1], 2) if total_idx else None,
        "benchmark": "SPY", "benchmark_index_end": round(benchmark_idx[-1], 2) if benchmark_idx else None,
        "price_only_annualized_pct": round(price_ann, 2) if price_ann is not None else None,
        "total_return_annualized_pct": round(total_ann, 2) if total_ann is not None else None,
        "benchmark_annualized_pct": round(benchmark_ann, 2) if benchmark_ann is not None else None,
        "market_cap_m": market_cap_m, "shares_outstanding": shares, "price_for_market_cap": price, "chart": chart_rel,
    }
    panel_path = research / "total_return_panel.json"
    panel_path.write_text(json.dumps(panel, indent=2) + "\n", encoding="utf-8")
    if merge:
        val["total_return_panel"] = {**panel, "panel_json": f"{t}/research/total_return_panel.json"}
        vpath.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    print(f"{'OK' if status == 'complete' else 'WARN'} {t}: {status}; total={total_ann}; events={panel['event_count']}")
    return status == "complete"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--no-merge", action="store_true")
    args = parser.parse_args()
    tickers = tickers_from_registry() if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        parser.error("provide tickers or use --all")
    results = [build_panel(t, args.date, merge=not args.no_merge) for t in tickers]
    print(f"SUMMARY: complete={sum(results)} partial={len(results)-sum(results)} total={len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
