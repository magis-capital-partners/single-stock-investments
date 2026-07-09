"""Walk-forward backtest with quarterly or semiannual rebalance."""
from __future__ import annotations

import math
from typing import Callable

from .constraints import apply_constraints

RowsProvider = Callable[[str, int], list[dict]]


def rebalance_points(dates: list[str], frequency: str = "quarterly") -> list[int]:
    if not dates:
        return []
    freq = (frequency or "quarterly").lower()
    semiannual_months = {6, 12}
    quarterly_months = {3, 6, 9, 12}
    months = semiannual_months if freq.startswith("semi") else quarterly_months

    points = [0]
    for i in range(1, len(dates)):
        y0, m0 = int(dates[i - 1][:4]), int(dates[i - 1][5:7])
        y1, m1 = int(dates[i][:4]), int(dates[i][5:7])
        if (y1, m1) != (y0, m0) and m1 in months:
            points.append(i)
    if points[-1] != len(dates) - 1:
        points.append(len(dates) - 1)
    return sorted(set(points))


def quarterly_rebalance_points(dates: list[str]) -> list[int]:
    return rebalance_points(dates, "quarterly")


def portfolio_return(weights: dict[str, float], rets: dict[str, float]) -> float:
    return sum(weights.get(t, 0.0) * rets.get(t, 0.0) for t in weights)


def _stats_from_series(period_rets: list[float], log_equity: list[float]) -> dict:
    if not period_rets:
        return {"error": "no_returns", "periods": 0}
    mean_r = sum(period_rets) / len(period_rets)
    var = sum((x - mean_r) ** 2 for x in period_rets) / max(len(period_rets) - 1, 1)
    std = math.sqrt(var) + 1e-9
    sharpe = (mean_r / std) * math.sqrt(12)
    cum = math.exp(log_equity[-1]) - 1.0
    max_dd = 0.0
    peak = 0.0
    for le in log_equity:
        peak = max(peak, le)
        max_dd = max(max_dd, peak - le)
    eq_index = [round(math.exp(le), 6) for le in log_equity]
    peak_idx = eq_index[0]
    max_dd_pct = 0.0
    for v in eq_index:
        peak_idx = max(peak_idx, v)
        if peak_idx > 0:
            max_dd_pct = max(max_dd_pct, (peak_idx - v) / peak_idx)
    return {
        "periods": len(period_rets),
        "mean_monthly_return": round(mean_r, 6),
        "volatility_annualized": round(std * math.sqrt(12), 4),
        "sharpe_annualized": round(sharpe, 3),
        "cumulative_return": round(cum, 4),
        "max_drawdown_log": round(max_dd, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
    }


def _snapshot_weights(weights: dict[str, float], top_n: int = 14) -> list[dict]:
    ranked = sorted(weights.items(), key=lambda x: -x[1])[:top_n]
    return [
        {"ticker": t, "weight_pct": round(w * 100, 2)}
        for t, w in ranked
        if w >= 0.001
    ]


def simulate(
    tickers: list[str],
    dates: list[str],
    returns_by_ticker: dict[str, list[float]],
    policy_fn: Callable[[list[str], int], dict[str, float]],
    mandate: dict,
    falsifier_by_ticker: dict[str, int] | None = None,
    rebalance_frequency: str | None = None,
    rows_provider: RowsProvider | None = None,
    dynamic_tickers: bool = False,
    track_series: bool = False,
) -> dict:
    m = mandate.get("mandate") or mandate
    freq = rebalance_frequency or m.get("rebalance_frequency", "quarterly")
    rebals = rebalance_points(dates, freq)
    if len(rebals) < 2 or len(dates) < 4:
        return {"error": "insufficient_dates", "periods": 0}

    prev: dict[str, float] | None = None
    period_rets: list[float] = []
    turnovers: list[float] = []
    log_equity = [0.0]
    cost_bps = m.get("transaction_cost_bps", 10)
    series_dates: list[str] = []
    series_equity: list[float] = []
    holdings_snapshots: list[dict] = []

    for ri in range(len(rebals) - 1):
        start, end = rebals[ri], rebals[ri + 1]
        as_of = dates[start] if start < len(dates) else dates[-1]
        active = tickers
        fmap = falsifier_by_ticker or {}
        if rows_provider:
            rows = rows_provider(as_of, start)
            active = [r["ticker"] for r in rows]
            fmap = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}

        w = policy_fn(active, start)
        w, _ = apply_constraints(
            active,
            w,
            prev,
            mandate,
            falsifier_counts=fmap,
        )
        if prev:
            turnovers.append(
                0.5 * sum(abs(w.get(t, 0) - prev.get(t, 0)) for t in set(w) | set(prev))
            )
        else:
            turnovers.append(0.0)
        prev = w
        if track_series:
            snap_date = dates[start] if start < len(dates) else dates[-1]
            holdings_snapshots.append(
                {"date": snap_date, "weights": _snapshot_weights(w)}
            )
        for mi in range(start, end):
            r_row = {
                t: returns_by_ticker[t][mi]
                for t in active
                if t in returns_by_ticker and mi < len(returns_by_ticker.get(t, []))
            }
            pr = portfolio_return(w, r_row)
            if mi == start:
                pr -= turnovers[-1] * (cost_bps / 10000.0)
            period_rets.append(pr)
            log_equity.append(log_equity[-1] + math.log1p(pr))
            if track_series:
                d = dates[mi] if mi < len(dates) else dates[-1]
                series_dates.append(d)
                series_equity.append(round(math.exp(log_equity[-1]), 6))

    if not period_rets:
        return {"error": "no_returns", "periods": 0}

    out = _stats_from_series(period_rets, log_equity)
    out["avg_turnover_one_way"] = round(sum(turnovers) / len(turnovers), 4) if turnovers else 0.0
    out["rebalance_frequency"] = freq
    if track_series:
        out["series"] = {
            "dates": series_dates,
            "equity_index": series_equity,
            "holdings_snapshots": holdings_snapshots,
        }
    return out


def benchmark_buy_hold(
    dates: list[str],
    returns_series: list[float],
    rebalance_frequency: str = "semiannual",
    track_series: bool = False,
    label: str = "spy_buy_hold",
) -> dict:
    """SPY or equal-weight benchmark on same calendar."""
    if len(returns_series) < 4:
        return {"error": "insufficient_dates", "periods": 0}
    rebals = rebalance_points(dates, rebalance_frequency)
    period_rets: list[float] = []
    log_equity = [0.0]
    series_dates: list[str] = []
    series_equity: list[float] = []
    for ri in range(len(rebals) - 1):
        start, end = rebals[ri], rebals[ri + 1]
        for mi in range(start, end):
            if mi < len(returns_series):
                r = returns_series[mi]
                period_rets.append(r)
                log_equity.append(log_equity[-1] + math.log1p(r))
                if track_series:
                    d = dates[mi] if mi < len(dates) else dates[-1]
                    series_dates.append(d)
                    series_equity.append(round(math.exp(log_equity[-1]), 6))
    if not period_rets:
        return {"error": "no_returns", "periods": 0}
    out = _stats_from_series(period_rets, log_equity)
    out["label"] = label
    out["rebalance_frequency"] = rebalance_frequency
    if track_series:
        out["series"] = {
            "dates": series_dates,
            "equity_index": series_equity,
            "holdings_snapshots": [
                {"date": dates[0] if dates else "", "weights": [{"ticker": "SPY", "weight_pct": 100.0}]}
            ],
        }
    return out


def apply_covered_call_overlay(
    stock_ret: float,
    premium_monthly: float,
    upside_cap: float,
    coverage: float,
) -> float:
    """Blend uncovered stock return with a capped covered-call sleeve.

    Covered sleeve: min(stock_ret, upside_cap) + premium_monthly
    Uncovered sleeve: stock_ret
    Blend by coverage in [0, 1].
    """
    cov = max(0.0, min(1.0, float(coverage)))
    covered = min(float(stock_ret), float(upside_cap)) + float(premium_monthly)
    return (1.0 - cov) * float(stock_ret) + cov * covered


def benchmark_covered_call(
    dates: list[str],
    returns_by_ticker: dict[str, list[float]],
    weights: dict[str, float],
    params: dict,
    rebalance_frequency: str = "semiannual",
    track_series: bool = False,
) -> dict:
    """Synthetic buy-write on a fixed weight book (champion weights)."""
    if not weights or len(dates) < 4:
        return {"error": "insufficient_inputs", "periods": 0}
    annual_prem = float(params.get("premium_yield_annual_pct", 8.0))
    premium_monthly = annual_prem / 100.0 / 12.0
    upside_cap = float(params.get("upside_cap_monthly_pct", 2.0)) / 100.0
    coverage = float(params.get("coverage_fraction", 0.20))
    freq = rebalance_frequency or "semiannual"
    rebals = rebalance_points(dates, freq)
    if len(rebals) < 2:
        return {"error": "insufficient_dates", "periods": 0}

    period_rets: list[float] = []
    log_equity = [0.0]
    series_dates: list[str] = []
    series_equity: list[float] = []
    for ri in range(len(rebals) - 1):
        start, end = rebals[ri], rebals[ri + 1]
        for mi in range(start, end):
            r_row = {
                t: returns_by_ticker[t][mi]
                for t in weights
                if t in returns_by_ticker and mi < len(returns_by_ticker.get(t, []))
            }
            stock_pr = portfolio_return(weights, r_row)
            pr = apply_covered_call_overlay(stock_pr, premium_monthly, upside_cap, coverage)
            period_rets.append(pr)
            log_equity.append(log_equity[-1] + math.log1p(pr))
            if track_series:
                d = dates[mi] if mi < len(dates) else dates[-1]
                series_dates.append(d)
                series_equity.append(round(math.exp(log_equity[-1]), 6))
    if not period_rets:
        return {"error": "no_returns", "periods": 0}
    out = _stats_from_series(period_rets, log_equity)
    out["avg_turnover_one_way"] = 0.0
    out["rebalance_frequency"] = freq
    out["label"] = params.get("label") or "synthetic_covered_call"
    out["covered_call_params"] = {
        "premium_yield_annual_pct": annual_prem,
        "upside_cap_monthly_pct": upside_cap * 100.0,
        "coverage_fraction": coverage,
        "mode": params.get("mode") or "synthetic",
    }
    if track_series:
        out["series"] = {
            "dates": series_dates,
            "equity_index": series_equity,
            "holdings_snapshots": [
                {"date": dates[0] if dates else "", "weights": _snapshot_weights(weights)}
            ],
        }
    return out
