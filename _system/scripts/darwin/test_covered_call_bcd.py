#!/usr/bin/env python3
"""Unit tests for Darwin covered-call Phase B–D helpers."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.covered_call import (  # noqa: E402
    apply_covered_call_overlay,
    regime_coverage_multiplier,
    stress_case_returns,
    tenor_premium_monthly,
    upside_cap_from_otm,
)
from darwin.policies import cc_suitability_score, policy_ira_marvin_cc  # noqa: E402


def test_tenor_premium_positive_and_haircut():
    raw = tenor_premium_monthly(12.0, tenor_days=7, bid_ask_haircut=0.0)
    cut = tenor_premium_monthly(12.0, tenor_days=7, bid_ask_haircut=0.15)
    assert raw > 0
    assert cut < raw
    assert abs(cut / raw - 0.85) < 1e-9


def test_upside_cap_scales_with_otm():
    c1 = upside_cap_from_otm(2.0, 7)
    c2 = upside_cap_from_otm(4.0, 7)
    assert c2 > c1 > 0


def test_stress_cases_shape():
    cases = stress_case_returns(
        {"premium_yield_annual_pct": 8.0, "tenor_days": 7, "otm_pct": 2.0, "coverage_fraction": 0.2, "bid_ask_haircut": 0.15}
    )
    # Bull: CC lags stock (cap binds)
    assert cases["bull_month"]["cc_ret"] < cases["bull_month"]["stock_ret"]
    # Crash: premium cushions but still negative
    assert cases["crash_month"]["cc_ret"] > cases["crash_month"]["stock_ret"]
    assert cases["crash_month"]["cc_ret"] < 0
    # Sideways: CC earns premium
    assert cases["sideways"]["cc_ret"] > cases["sideways"]["stock_ret"]


def test_overlay_unit():
    assert abs(apply_covered_call_overlay(0.05, 0.08 / 12, 0.02, 0.2) - 0.045333333333333344) < 1e-6
    assert abs(apply_covered_call_overlay(0.0, 0.01, 0.02, 1.0) - 0.01) < 1e-9
    assert abs(apply_covered_call_overlay(0.10, 0.0, 0.02, 1.0) - 0.02) < 1e-9


def test_regime_coverage():
    cfg = {"coverage_mult_calm": 1.2, "coverage_mult_stressed": 0.3, "pause_overlay_when_stressed": False}
    assert regime_coverage_multiplier({"label": "calm"}, cfg) == 1.2
    assert regime_coverage_multiplier({"label": "stressed"}, cfg) == 0.3
    assert regime_coverage_multiplier({"label": "stressed"}, {**cfg, "pause_overlay_when_stressed": True}) == 0.0


def test_cc_suitability_and_dual_policy():
    rows = [
        {
            "ticker": "AAA",
            "irr_base_pct": 12.0,
            "market": "US",
            "classification": {"stance": "hold", "dhando": "partial", "moat": "stable"},
            "falsifier_count": 0,
            "days_since_deep_dive": 30,
        },
        {
            "ticker": "BBB",
            "irr_base_pct": 10.0,
            "market": "US",
            "classification": {"stance": "core", "dhando": "full", "moat": "stable"},
            "falsifier_count": 0,
            "days_since_deep_dive": 10,
        },
    ]
    s = cc_suitability_score(rows[0], {}, iv_hint=0.30, liquidity_bucket="A")
    assert 0.5 < s < 1.8
    w = policy_ira_marvin_cc(
        rows,
        {
            "min_irr_pct_for_weight": 6.0,
            "max_names_cc": 2,
            "min_names": 1,
            "iv_by_ticker": {"AAA": 0.35, "BBB": 0.15},
            "liquidity_by_ticker": {"AAA": "A", "BBB": "B"},
        },
    )
    assert set(w.keys()) <= {"AAA", "BBB"}
    assert abs(sum(w.values()) - 1.0) < 1e-6


if __name__ == "__main__":
    test_tenor_premium_positive_and_haircut()
    test_upside_cap_scales_with_otm()
    test_stress_cases_shape()
    test_overlay_unit()
    test_regime_coverage()
    test_cc_suitability_and_dual_policy()
    print("all covered_call / dual-score tests ok")
