"""Dashboard time-series: holdings snapshots and performance curves per policy."""
from __future__ import annotations

from typing import Callable

from .backtest import benchmark_buy_hold, simulate


PolicyFn = Callable[[list[str], int], dict[str, float]]


def _strip_series(bt: dict) -> dict:
    """Summary stats only (no monthly arrays)."""
    if bt.get("error"):
        return {"error": bt["error"]}
    keys = (
        "periods",
        "mean_monthly_return",
        "volatility_annualized",
        "sharpe_annualized",
        "cumulative_return",
        "max_drawdown_log",
        "max_drawdown_pct",
        "avg_turnover_one_way",
        "rebalance_frequency",
        "label",
    )
    return {k: bt[k] for k in keys if k in bt}


def _method_from_bt(bt: dict) -> dict:
    if bt.get("error"):
        return {"error": bt["error"], "stats": _strip_series(bt)}
    series = bt.get("series") or {}
    stats_src = {k: v for k, v in bt.items() if k != "series"}
    return {
        "stats": _strip_series(stats_src),
        "dates": series.get("dates") or [],
        "equity_index": series.get("equity_index") or [],
        "holdings_snapshots": series.get("holdings_snapshots") or [],
    }


def build_method_visualizations(
    *,
    tickers: list[str],
    dates: list[str],
    returns_by_ticker: dict[str, list[float]],
    spy_returns: list[float],
    mandate_effective: dict,
    falsifier_map: dict[str, int],
    policy_fns: dict[str, PolicyFn],
    rebalance_frequency: str,
    covered_call_bt: dict | None = None,
    covered_call_proxy_bt: dict | None = None,
    covered_call_proxy_key: str = "xyld",
) -> dict:
    """Run detailed simulate for each allocation method (dashboard charts)."""
    methods: dict[str, dict] = {}
    for name, pfn in policy_fns.items():
        bt = simulate(
            tickers,
            dates,
            returns_by_ticker,
            pfn,
            mandate_effective,
            falsifier_map,
            rebalance_frequency=rebalance_frequency,
            track_series=True,
        )
        if bt.get("error"):
            methods[name] = {"error": bt["error"], "stats": _strip_series(bt)}
            continue
        series = bt.pop("series", {})
        methods[name] = {
            "stats": _strip_series(bt),
            "dates": series.get("dates") or [],
            "equity_index": series.get("equity_index") or [],
            "holdings_snapshots": series.get("holdings_snapshots") or [],
        }

    spy_bt = benchmark_buy_hold(
        dates,
        spy_returns,
        rebalance_frequency,
        track_series=True,
    )
    if not spy_bt.get("error"):
        spy_series = spy_bt.pop("series", {})
        methods["spy"] = {
            "stats": _strip_series(spy_bt),
            "dates": spy_series.get("dates") or [],
            "equity_index": spy_series.get("equity_index") or [],
            "holdings_snapshots": spy_series.get("holdings_snapshots") or [],
        }
    else:
        methods["spy"] = {"error": spy_bt.get("error"), "stats": _strip_series(spy_bt)}

    if covered_call_bt and not covered_call_bt.get("error"):
        methods["covered_call"] = _method_from_bt(covered_call_bt)
    if covered_call_proxy_bt and not covered_call_proxy_bt.get("error"):
        methods[covered_call_proxy_key or "xyld"] = _method_from_bt(covered_call_proxy_bt)

    return {
        "calendar_start": dates[0] if dates else None,
        "calendar_end": dates[-1] if dates else None,
        "rebalance_frequency": rebalance_frequency,
        "methods": methods,
    }
