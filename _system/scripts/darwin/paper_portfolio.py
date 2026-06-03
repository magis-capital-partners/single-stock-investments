"""Paper portfolio tracking: inception today, daily marks, adaptation log."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .accounts import AccountCtx
from .prices import fetch_yahoo_monthly
from .symbols import yahoo_for_ticker


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_last_close(ticker: str, market: str = "US") -> tuple[float | None, str]:
    """Latest daily close via Yahoo chart API (1mo window)."""
    import urllib.error
    import urllib.request

    sym = yahoo_for_ticker(ticker, market)
    end = datetime.now(timezone.utc)
    start = end.timestamp() - 45 * 86400
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?period1={int(start)}&period2={int(end.timestamp())}&interval=1d"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DarwinPaper/1.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        for c in reversed(closes):
            if c is not None and c > 0:
                return float(c), sym
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        pass
    # fallback: last monthly close
    dates, rets, src = fetch_yahoo_monthly(sym, months=3)
    if dates:
        return None, src
    return None, "unavailable"


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


def _append_history(ctx: AccountCtx, row: dict) -> None:
    ctx.paper_history_path.parent.mkdir(parents=True, exist_ok=True)
    with ctx.paper_history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _append_adaptation(ctx: AccountCtx, row: dict) -> None:
    ctx.adaptation_log_path.parent.mkdir(parents=True, exist_ok=True)
    with ctx.adaptation_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _weights_to_shares(
    weights: dict[str, float],
    nav: float,
    features_by_ticker: dict[str, dict],
) -> list[dict]:
    positions: list[dict] = []
    for ticker, w in weights.items():
        if w <= 1e-6:
            continue
        row = features_by_ticker.get(ticker, {})
        px, src = fetch_last_close(ticker, row.get("market", "US"))
        if not px or px <= 0:
            positions.append(
                {
                    "ticker": ticker,
                    "weight_pct": round(w * 100, 2),
                    "shares": 0.0,
                    "last_price": None,
                    "price_source": src,
                    "notional_usd": round(nav * w, 2),
                }
            )
            continue
        notional = nav * w
        shares = notional / px
        positions.append(
            {
                "ticker": ticker,
                "weight_pct": round(w * 100, 2),
                "shares": round(shares, 4),
                "last_price": round(px, 4),
                "price_source": "yahoo_daily",
                "notional_usd": round(notional, 2),
            }
        )
    return positions


def _nav_from_positions(positions: list[dict]) -> float:
    total = 0.0
    for p in positions:
        px = p.get("last_price")
        sh = p.get("shares") or 0.0
        if px and sh:
            total += px * sh
        else:
            total += p.get("notional_usd") or 0.0
    return total


def _mark_positions(
    positions: list[dict],
    features_by_ticker: dict[str, dict],
) -> list[dict]:
    out = []
    for p in positions:
        t = p["ticker"]
        row = features_by_ticker.get(t, {})
        px, src = fetch_last_close(t, row.get("market", "US"))
        sh = p.get("shares") or 0.0
        if px and sh:
            out.append(
                {
                    **p,
                    "last_price": round(px, 4),
                    "price_source": "yahoo_daily",
                    "notional_usd": round(px * sh, 2),
                }
            )
        else:
            out.append({**p, "price_source": src})
    return out


def update_paper_portfolio(
    ctx: AccountCtx,
    mandate_doc: dict,
    target_w: dict[str, float],
    features_by_ticker: dict[str, dict],
    policy_id: str,
    regime: dict,
    backtest: dict[str, Any],
) -> dict:
    """Initialize or mark paper book; log adaptations when weights/policy shift."""
    paper_cfg = mandate_doc.get("paper") or {}
    initial_nav = float(paper_cfg.get("initial_nav_usd", 100_000))
    today = _today()
    state = _load_state(ctx)
    champion_bt = (backtest.get("benchmarks") or {}).get("champion") or backtest.get("champion") or {}

    backtest_ref = {
        "cumulative_return_pct": round((champion_bt.get("cumulative_return") or 0) * 100, 2),
        "sharpe_annualized": champion_bt.get("sharpe_annualized"),
        "periods": champion_bt.get("periods"),
        "policy_id": policy_id,
        "as_of": backtest.get("generated_at"),
    }

    if state is None:
        positions = _weights_to_shares(target_w, initial_nav, features_by_ticker)
        nav = _nav_from_positions(positions) or initial_nav
        state = {
            "account_id": ctx.account_id,
            "account_profile": mandate_doc.get("account_profile"),
            "inception_date": today,
            "initial_nav_usd": initial_nav,
            "policy_id": policy_id,
            "regime": regime.get("label"),
            "positions": positions,
            "target_weights": {t: round(w * 100, 2) for t, w in target_w.items()},
            "last_mark": {
                "date": today,
                "nav_usd": round(nav, 2),
                "daily_return_pct": 0.0,
                "cumulative_return_pct": 0.0,
            },
            "backtest_at_inception": backtest_ref,
            "status": "live",
        }
        _append_adaptation(
            ctx,
            {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "event": "inception",
                "policy_id": policy_id,
                "nav_usd": nav,
                "note": "Paper portfolio started",
            },
        )
    else:
        prev_nav = (state.get("last_mark") or {}).get("nav_usd") or initial_nav
        prev_weights = state.get("target_weights") or {}
        new_weights = {t: round(w * 100, 2) for t, w in target_w.items()}
        policy_changed = state.get("policy_id") != policy_id
        weight_drift = 0.5 * sum(
            abs(new_weights.get(t, 0) - prev_weights.get(t, 0))
            for t in set(new_weights) | set(prev_weights)
        )
        min_drift = float(paper_cfg.get("min_weight_change_for_rebalance_pct", 1.0))
        do_rebalance = policy_changed or (
            paper_cfg.get("rebalance_on_policy_change", True) and weight_drift >= min_drift
        )

        if do_rebalance:
            positions = _weights_to_shares(target_w, prev_nav, features_by_ticker)
            _append_adaptation(
                ctx,
                {
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "event": "rebalance",
                    "policy_id": policy_id,
                    "prev_policy": state.get("policy_id"),
                    "weight_drift_pct": round(weight_drift, 2),
                    "regime": regime.get("label"),
                },
            )
            state["policy_id"] = policy_id
            state["target_weights"] = new_weights
            state["positions"] = positions
        else:
            positions = _mark_positions(state.get("positions") or [], features_by_ticker)

        nav = _nav_from_positions(positions) or prev_nav
        daily_ret = (nav / prev_nav - 1.0) if prev_nav > 0 else 0.0
        inception = state.get("initial_nav_usd") or initial_nav
        cum_ret = (nav / inception - 1.0) if inception > 0 else 0.0
        last_date = (state.get("last_mark") or {}).get("date")
        if last_date != today:
            state["last_mark"] = {
                "date": today,
                "nav_usd": round(nav, 2),
                "daily_return_pct": round(daily_ret * 100, 3),
                "cumulative_return_pct": round(cum_ret * 100, 3),
            }
            state["positions"] = positions
            state["regime"] = regime.get("label")
            state["backtest_latest"] = backtest_ref
            _append_history(
                ctx,
                {
                    "date": today,
                    "nav_usd": round(nav, 2),
                    "daily_return_pct": round(daily_ret * 100, 3),
                    "cumulative_return_pct": round(cum_ret * 100, 3),
                    "policy_id": policy_id,
                },
            )
        else:
            state["last_mark"]["nav_usd"] = round(nav, 2)
            state["last_mark"]["daily_return_pct"] = round(daily_ret * 100, 3)
            state["last_mark"]["cumulative_return_pct"] = round(cum_ret * 100, 3)
            state["positions"] = positions
            state["backtest_latest"] = backtest_ref

    _save_state(ctx, state)
    return {
        "account_id": ctx.account_id,
        "inception_date": state.get("inception_date"),
        "last_mark": state.get("last_mark"),
        "backtest_at_inception": state.get("backtest_at_inception"),
        "backtest_latest": state.get("backtest_latest") or backtest_ref,
        "policy_id": state.get("policy_id"),
        "positions_count": len(state.get("positions") or []),
        "status": state.get("status"),
    }
