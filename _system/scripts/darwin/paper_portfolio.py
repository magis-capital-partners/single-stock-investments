"""Paper book: weights + NAV from returns CSV (no per-ticker live API in hot path)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .accounts import AccountCtx
from .prices import load_returns_csv


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _last_monthly_return(ticker: str) -> float | None:
    loaded = load_returns_csv(ticker)
    if not loaded or not loaded[1]:
        return None
    return float(loaded[1][-1])


def _weighted_return(weights: dict[str, float]) -> tuple[float, list[str]]:
    """Portfolio return for last month in vault."""
    total = 0.0
    missing: list[str] = []
    for t, w in weights.items():
        r = _last_monthly_return(t)
        if r is None:
            missing.append(t)
            continue
        total += w * r
    return total, missing


def _append_event(ctx: AccountCtx, row: dict) -> None:
    ctx.paper_events_path.parent.mkdir(parents=True, exist_ok=True)
    with ctx.paper_events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _load_state(ctx: AccountCtx) -> dict | None:
    if not ctx.paper_state_path.exists():
        return None
    try:
        return json.loads(ctx.paper_state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_state(ctx: AccountCtx, state: dict) -> None:
    ctx.paper_state_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.paper_state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def update_paper_portfolio(
    ctx: AccountCtx,
    mandate_doc: dict,
    target_w: dict[str, float],
    policy_id: str,
    regime: dict,
    backtest: dict[str, Any],
) -> dict:
    paper_cfg = mandate_doc.get("paper") or {}
    initial_nav = float(paper_cfg.get("initial_nav_usd", 100_000))
    today = _today()
    champion_bt = (backtest.get("benchmarks") or {}).get("champion") or {}
    backtest_ref = {
        "cumulative_return_pct": round((champion_bt.get("cumulative_return") or 0) * 100, 2),
        "sharpe_annualized": champion_bt.get("sharpe_annualized"),
        "policy_id": policy_id,
    }
    weights_pct = {t: round(w * 100, 2) for t, w in target_w.items()}

    state = _load_state(ctx)
    if state is None:
        state = {
            "account_id": ctx.account_id,
            "inception_date": today,
            "initial_nav_usd": initial_nav,
            "policy_id": policy_id,
            "regime": regime.get("label"),
            "weights_pct": weights_pct,
            "last_mark": {
                "date": today,
                "nav_usd": initial_nav,
                "period_return_pct": 0.0,
                "cumulative_return_pct": 0.0,
            },
            "backtest_at_inception": backtest_ref,
        }
        _append_event(
            ctx,
            {
                "date": today,
                "event": "inception",
                "nav_usd": initial_nav,
                "policy_id": policy_id,
                "weights_pct": weights_pct,
            },
        )
    else:
        prev_nav = (state.get("last_mark") or {}).get("nav_usd") or initial_nav
        prev_weights = state.get("weights_pct") or {}
        drift = 0.5 * sum(
            abs(weights_pct.get(t, 0) - prev_weights.get(t, 0))
            for t in set(weights_pct) | set(prev_weights)
        )
        rebalanced = (
            state.get("policy_id") != policy_id
            or drift >= float(paper_cfg.get("min_weight_change_for_rebalance_pct", 1.0))
        )
        period_ret, missing = _weighted_return(target_w)
        # One pipeline run ≈ one period step (monthly return proxy)
        nav = prev_nav * (1.0 + period_ret) if period_ret else prev_nav
        cum = (nav / initial_nav - 1.0) * 100 if initial_nav else 0.0

        if rebalanced:
            _append_event(
                ctx,
                {
                    "date": today,
                    "event": "rebalance",
                    "nav_usd": round(nav, 2),
                    "policy_id": policy_id,
                    "weight_drift_pct": round(drift, 2),
                    "weights_pct": weights_pct,
                },
            )
            state["policy_id"] = policy_id
            state["weights_pct"] = weights_pct

        last_date = (state.get("last_mark") or {}).get("date")
        if last_date != today or rebalanced:
            state["last_mark"] = {
                "date": today,
                "nav_usd": round(nav, 2),
                "period_return_pct": round(period_ret * 100, 3),
                "cumulative_return_pct": round(cum, 3),
            }
            state["regime"] = regime.get("label")
            state["backtest_latest"] = backtest_ref
            if missing:
                state["returns_missing"] = missing
            _append_event(
                ctx,
                {
                    "date": today,
                    "event": "mark",
                    "nav_usd": round(nav, 2),
                    "period_return_pct": round(period_ret * 100, 3),
                    "cumulative_return_pct": round(cum, 3),
                },
            )

    _save_state(ctx, state)
    return {
        "account_id": ctx.account_id,
        "inception_date": state.get("inception_date"),
        "last_mark": state.get("last_mark"),
        "backtest_at_inception": state.get("backtest_at_inception"),
        "backtest_latest": state.get("backtest_latest", backtest_ref),
        "policy_id": state.get("policy_id"),
    }
