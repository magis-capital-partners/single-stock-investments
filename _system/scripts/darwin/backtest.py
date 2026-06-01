"""Walk-forward quarterly backtest (Phase 1)."""
from __future__ import annotations

import math
from typing import Callable

from .constraints import apply_constraints


def quarterly_rebalance_points(dates: list[str]) -> list[int]:
    if not dates:
        return []
    points = [0]
    for i in range(1, len(dates)):
        y0, m0 = int(dates[i - 1][:4]), int(dates[i - 1][5:7])
        y1, m1 = int(dates[i][:4]), int(dates[i][5:7])
        if (y1, m1) != (y0, m0) and m1 in (3, 6, 9, 12):
            points.append(i)
    if points[-1] != len(dates) - 1:
        points.append(len(dates) - 1)
    return sorted(set(points))


def portfolio_return(weights: dict[str, float], rets: dict[str, float]) -> float:
    return sum(weights.get(t, 0.0) * rets.get(t, 0.0) for t in weights)


def simulate(
    tickers: list[str],
    dates: list[str],
    returns_by_ticker: dict[str, list[float]],
    policy_fn: Callable[[list[str], int], dict[str, float]],
    mandate: dict,
    falsifier_by_ticker: dict[str, int] | None = None,
) -> dict:
    rebals = quarterly_rebalance_points(dates)
    if len(rebals) < 2 or len(dates) < 4:
        return {"error": "insufficient_dates", "periods": 0}

    prev: dict[str, float] | None = None
    period_rets: list[float] = []
    turnovers: list[float] = []
    log_equity = [0.0]
    cost_bps = (mandate.get("mandate") or mandate).get("transaction_cost_bps", 10)

    for ri in range(len(rebals) - 1):
        start, end = rebals[ri], rebals[ri + 1]
        w = policy_fn(tickers, start)
        w, _ = apply_constraints(
            tickers,
            w,
            prev,
            mandate,
            falsifier_counts=falsifier_by_ticker,
        )
        if prev:
            turnovers.append(
                0.5 * sum(abs(w.get(t, 0) - prev.get(t, 0)) for t in set(w) | set(prev))
            )
        else:
            turnovers.append(0.0)
        prev = w
        for mi in range(start, end):
            r_row = {
                t: returns_by_ticker[t][mi]
                for t in tickers
                if mi < len(returns_by_ticker.get(t, []))
            }
            pr = portfolio_return(w, r_row)
            if mi == start:
                pr -= turnovers[-1] * (cost_bps / 10000.0)
            period_rets.append(pr)
            log_equity.append(log_equity[-1] + math.log1p(pr))

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

    return {
        "periods": len(period_rets),
        "mean_monthly_return": round(mean_r, 6),
        "sharpe_annualized": round(sharpe, 3),
        "cumulative_return": round(cum, 4),
        "max_drawdown_log": round(max_dd, 4),
        "avg_turnover_one_way": round(sum(turnovers) / len(turnovers), 4) if turnovers else 0.0,
    }
