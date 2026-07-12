"""Covered-call research overlay (synthetic + optional live IV marks).

Not Darwin AI Ventures proprietary model. Formulas documented in
`_system/frameworks/darwin_source_alignment.md` § Covered-call arithmetic.
"""
from __future__ import annotations

import math
from typing import Any


def tenor_premium_monthly(
    annual_yield_pct: float,
    tenor_days: int = 7,
    bid_ask_haircut: float = 0.15,
    rolls_per_month: float | None = None,
) -> float:
    """Map annual premium yield to a monthly earn rate for short-dated rolls.

    rolls_per_month ≈ 30.4 / tenor_days (or override).
    per_roll ≈ (annual/100) / rolls_per_year, then haircut for bid-ask.
    monthly ≈ per_roll * rolls_per_month.
    """
    tenor = max(1, int(tenor_days))
    rpm = float(rolls_per_month) if rolls_per_month is not None else (30.4 / tenor)
    rolls_per_year = max(rpm * 12.0, 1.0)
    per_roll = (float(annual_yield_pct) / 100.0) / rolls_per_year
    haircut = max(0.0, min(0.9, float(bid_ask_haircut)))
    per_roll *= 1.0 - haircut
    return per_roll * rpm


def upside_cap_from_otm(
    otm_pct: float,
    tenor_days: int = 7,
    rolls_per_month: float | None = None,
) -> float:
    """Approximate monthly upside retained before call strike (OTM %).

    Monthly cap ≈ otm_pct/100 * rolls_per_month / (rolls that would exhaust the OTM cushion).
    Simple: monthly_cap = otm_pct/100  (one roll's OTM cushion scaled to month via rpm factor
    but capped so we don't invent free upside). Use otm * (rpm / max(rpm,1)) clipped.
    """
    otm = max(0.0, float(otm_pct)) / 100.0
    tenor = max(1, int(tenor_days))
    rpm = float(rolls_per_month) if rolls_per_month is not None else (30.4 / tenor)
    # One roll caps upside at OTM; multiple rolls in a month stack only if rewritten —
    # for monthly equity returns we use a single effective monthly cap ≈ otm * sqrt(rpm)
    # (volatility-of-rolls heuristic) clipped to [otm, 3*otm].
    eff = otm * math.sqrt(max(rpm, 1.0))
    return max(otm, min(eff, otm * 3.0))


def realized_vol_annual(returns: list[float]) -> float | None:
    if not returns or len(returns) < 6:
        return None
    mean_r = sum(returns) / len(returns)
    var = sum((x - mean_r) ** 2 for x in returns) / max(len(returns) - 1, 1)
    return math.sqrt(var) * math.sqrt(12)


def name_level_cc_params(
    ticker: str,
    base: dict,
    row: dict | None,
    returns: list[float] | None,
    iv_hint: float | None = None,
    liquidity_bucket: str | None = None,
) -> dict[str, float]:
    """Per-name premium, cap, coverage from vol + conviction."""
    annual = float(base.get("premium_yield_annual_pct", 8.0))
    tenor = int(base.get("tenor_days", 7))
    otm = float(base.get("otm_pct", 2.0))
    haircut = float(base.get("bid_ask_haircut", 0.15))
    base_cov = float(base.get("coverage_fraction", 0.20))

    rvol = realized_vol_annual(returns or [])
    # Scale premium with IV or realized vol vs 20% baseline
    vol = iv_hint if iv_hint and iv_hint > 0 else rvol
    vol_scale = 1.0
    if vol is not None and vol > 0:
        vol_scale = max(0.5, min(2.0, float(vol) / 0.20))

    stance = ((row or {}).get("classification") or {}).get("stance") or "hold"
    stance = str(stance).lower()
    # Preserve upside on core compounders; write more on watch/hold
    stance_cov = {
        "core": 0.55,
        "accumulate": 0.75,
        "hold": 1.0,
        "watch": 1.25,
        "trim": 1.35,
        "exit": 0.0,
    }.get(stance, 1.0)

    bucket = (liquidity_bucket or ((row or {}).get("liquidity_bucket")) or "B").upper()
    bucket_cov = {"A": 1.15, "B": 1.0, "C": 0.7, "D": 0.4}.get(bucket, 1.0)

    premium_m = tenor_premium_monthly(annual * vol_scale, tenor, haircut)
    cap_m = upside_cap_from_otm(otm, tenor)
    # Higher vol → slightly wider effective cap (harder to pin)
    if vol is not None and vol > 0.35:
        cap_m *= 1.1
    cov = max(0.0, min(1.0, base_cov * stance_cov * bucket_cov))

    return {
        "premium_monthly": premium_m,
        "upside_cap": cap_m,
        "coverage": cov,
        "vol_annual": float(vol) if vol is not None else None,
        "vol_scale": vol_scale,
        "stance": stance,
        "liquidity_bucket": bucket,
    }


def regime_coverage_multiplier(regime: dict | None, cc_cfg: dict) -> float:
    """Calm → higher coverage; stressed → cut or pause overlay."""
    label = ""
    if isinstance(regime, dict):
        label = str(regime.get("label") or regime.get("research") or "").lower()
    else:
        label = str(regime or "").lower()
    calm_m = float(cc_cfg.get("coverage_mult_calm", 1.15))
    adapting_m = float(cc_cfg.get("coverage_mult_adapting", 1.0))
    stressed_m = float(cc_cfg.get("coverage_mult_stressed", 0.35))
    pause = bool(cc_cfg.get("pause_overlay_when_stressed", False))
    if "stress" in label:
        return 0.0 if pause else stressed_m
    if "adapt" in label:
        return adapting_m
    if "calm" in label:
        return calm_m
    return 1.0


def apply_covered_call_overlay(
    stock_ret: float,
    premium_monthly: float,
    upside_cap: float,
    coverage: float,
    assignment_bps: float = 0.0,
) -> float:
    """Blend uncovered stock return with a capped covered-call sleeve."""
    cov = max(0.0, min(1.0, float(coverage)))
    assign = float(assignment_bps) / 10000.0
    covered = min(float(stock_ret), float(upside_cap)) + float(premium_monthly) - assign
    return (1.0 - cov) * float(stock_ret) + cov * covered


def portfolio_name_level_overlay(
    weights: dict[str, float],
    rets_row: dict[str, float],
    name_params: dict[str, dict],
    assignment_bps: float = 5.0,
) -> float:
    """Weight-average of per-name covered-call overlays for one month."""
    total = 0.0
    wsum = 0.0
    for t, w in weights.items():
        if w <= 0:
            continue
        r = rets_row.get(t)
        if r is None:
            continue
        p = name_params.get(t) or {}
        pr = apply_covered_call_overlay(
            r,
            float(p.get("premium_monthly", 0.0)),
            float(p.get("upside_cap", 0.02)),
            float(p.get("coverage", 0.0)),
            assignment_bps=assignment_bps,
        )
        total += w * pr
        wsum += w
    if wsum <= 0:
        return 0.0
    return total / wsum if abs(wsum - 1.0) > 1e-6 else total


def stress_case_returns(
    base_params: dict,
    cases: dict[str, float] | None = None,
) -> dict[str, dict]:
    """Document bull / crash / sideways payoff shape (unit-test friendly)."""
    cases = cases or {
        "bull_month": 0.10,
        "crash_month": -0.12,
        "sideways": 0.005,
    }
    prem = tenor_premium_monthly(
        float(base_params.get("premium_yield_annual_pct", 8.0)),
        int(base_params.get("tenor_days", 7)),
        float(base_params.get("bid_ask_haircut", 0.15)),
    )
    cap = upside_cap_from_otm(
        float(base_params.get("otm_pct", 2.0)),
        int(base_params.get("tenor_days", 7)),
    )
    cov = float(base_params.get("coverage_fraction", 0.20))
    out: dict[str, dict] = {}
    for name, stock_r in cases.items():
        cc = apply_covered_call_overlay(stock_r, prem, cap, cov)
        out[name] = {
            "stock_ret": stock_r,
            "cc_ret": cc,
            "lag_vs_stock": cc - stock_r,
            "premium_monthly": prem,
            "upside_cap": cap,
            "coverage": cov,
        }
    return out


def resolve_cc_cfg(mandate_doc: dict, regime: dict | None = None) -> dict[str, Any]:
    """Merge covered_call block with regime coverage multiplier."""
    cc = dict(mandate_doc.get("covered_call") or {})
    mult = regime_coverage_multiplier(regime, cc)
    base_cov = float(cc.get("coverage_fraction", 0.20))
    cc["coverage_fraction_effective"] = max(0.0, min(1.0, base_cov * mult))
    cc["regime_coverage_mult"] = mult
    cc.setdefault("tenor_days", 7)
    cc.setdefault("otm_pct", 2.0)
    cc.setdefault("roll_frequency", "weekly")
    cc.setdefault("bid_ask_haircut", 0.15)
    cc.setdefault("assignment_bps", 5.0)
    cc.setdefault("etf_proxy_ticker", "XYLD")
    cc.setdefault("proxy_tickers", ["XYLD", "QYLD"])
    return cc
