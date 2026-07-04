#!/usr/bin/env python3
"""Tests for second-derivative KPI trend analysis."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_kpi_trends import (  # noqa: E402
    analyze_quarterly_yoy,
    analyze_series,
    apply_display_cap,
    collapse_core_signals,
    derive_ratio_series,
    finalize_ticker_entry,
    news_flow_series,
    passes_materiality,
    robust_vol,
    signal_tier_from_accels,
)


def quarterly(values: list[float], start_year: int = 2023) -> list[dict]:
    """Build a quarterly series with realistic fiscal period ends."""
    ends = ["03-31", "06-30", "09-30", "12-31"]
    out = []
    for i, value in enumerate(values):
        year = start_year + i // 4
        out.append({"period": f"{year}-{ends[i % 4]}", "value": value})
    return out


class AnalyzeQuarterlyYoyTests(unittest.TestCase):
    def test_seasonal_series_reads_steady(self) -> None:
        base = [100.0, 80.0, 90.0, 150.0]
        values = base + [v * 1.10 for v in base] + [v * 1.21 for v in base]
        result = analyze_quarterly_yoy(quarterly(values), metric_key="revenues")
        self.assertIsNotNone(result)
        self.assertEqual(result["basis"], "yoy")
        self.assertEqual(result["direction"], "steady")

    def test_yoy_acceleration_detected(self) -> None:
        base = [100.0, 80.0, 90.0, 150.0]
        y2 = [v * 1.10 for v in base]
        y3 = [base[0] * 1.10 * 1.12, base[1] * 1.10 * 1.20, base[2] * 1.10 * 1.35, base[3] * 1.10 * 1.60]
        result = analyze_quarterly_yoy(quarterly(base + y2 + y3), metric_key="revenues")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "accelerating")
        self.assertIn(result["signal_tier"], ("confirmed", "emerging"))

    def test_yoy_deceleration_detected(self) -> None:
        base = [100.0, 80.0, 90.0, 150.0]
        y2 = [v * 1.30 for v in base]
        y3 = [base[0] * 1.30 * 1.28, base[1] * 1.30 * 1.18, base[2] * 1.30 * 1.06, base[3] * 1.30 * 0.90]
        result = analyze_quarterly_yoy(quarterly(base + y2 + y3), metric_key="revenues")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "decelerating")

    def test_qdel_regression_duplicate_snapshots_and_scope_mix(self) -> None:
        series = [
            {"period": "2026-05-28", "value": 619.8},
            {"period": "2026-05-29", "value": 619.8},
            {"period": "2026-06-01", "value": 619.8},
            {"period": "2026-06-29", "value": 2730.2},
        ]
        self.assertIsNone(analyze_quarterly_yoy(series))

    def test_outlier_growth_excluded_as_suspect(self) -> None:
        base = [100.0, 80.0, 90.0, 150.0]
        values = base + [v * 1.10 for v in base] + [v * 1.21 for v in base]
        values[9] = values[9] * 40
        result = analyze_quarterly_yoy(quarterly(values), metric_key="revenues")
        if result is not None:
            self.assertGreaterEqual(result.get("suspect_points", 0), 1)
            self.assertNotIn(result["direction"], ("accelerating",))

    def test_near_zero_denominator_skipped(self) -> None:
        base = [0.001, 80.0, 90.0, 150.0]
        values = base + [50.0, 88.0, 99.0, 165.0] + [55.0, 96.8, 108.9, 181.5]
        result = analyze_quarterly_yoy(quarterly(values), metric_key="revenues")
        if result is not None:
            self.assertLessEqual(abs(result["growth_latest"]), 5.0)

    def test_too_short_history_returns_none(self) -> None:
        self.assertIsNone(analyze_quarterly_yoy(quarterly([100.0, 105.0, 110.0, 120.0])))

    def test_materiality_suppresses_tiny_growth(self) -> None:
        self.assertFalse(passes_materiality(0.01, "revenues", direction="accelerating"))
        self.assertTrue(passes_materiality(0.05, "revenues", direction="accelerating"))
        self.assertTrue(passes_materiality(-0.03, "operating_income", direction="decelerating"))


class AnalyzeSeriesTests(unittest.TestCase):
    def test_acceleration_detected(self) -> None:
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 105.0),
            ("2024-09-30", 110.25),
            ("2024-12-31", 115.76),
            ("2025-03-31", 138.91),
        ]
        result = analyze_series(points, metric_key="revenues")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "accelerating")
        self.assertGreater(result["accel"], 0.1)

    def test_deceleration_detected(self) -> None:
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 125.0),
            ("2024-09-30", 156.25),
            ("2024-12-31", 195.31),
            ("2025-03-31", 210.9),
        ]
        result = analyze_series(points, metric_key="revenues")
        self.assertEqual(result["direction"], "decelerating")

    def test_steady_growth_does_not_fire(self) -> None:
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 110.0),
            ("2024-09-30", 121.0),
            ("2024-12-31", 133.1),
            ("2025-03-31", 146.4),
        ]
        result = analyze_series(points, metric_key="revenues")
        self.assertEqual(result["direction"], "steady")

    def test_noisy_series_needs_bigger_move(self) -> None:
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 140.0),
            ("2024-09-30", 90.0),
            ("2024-12-31", 150.0),
            ("2025-03-31", 160.0),
        ]
        result = analyze_series(points, metric_key="revenues")
        self.assertEqual(result["direction"], "steady")

    def test_too_few_points_returns_none(self) -> None:
        self.assertIsNone(analyze_series([("2024-03-31", 1.0), ("2024-06-30", 2.0)]))

    def test_zero_crossing_pct_series_returns_none(self) -> None:
        points = [
            ("2024-03-31", 0.0),
            ("2024-06-30", 5.0),
            ("2024-09-30", 10.0),
            ("2024-12-31", 20.0),
        ]
        self.assertIsNone(analyze_series(points, mode="pct"))

    def test_diff_mode_handles_zero_counts(self) -> None:
        points = [
            ("2025-11-01", 0.0),
            ("2025-12-01", 0.0),
            ("2026-01-01", 1.0),
            ("2026-02-01", 2.0),
            ("2026-03-01", 12.0),
        ]
        result = analyze_series(points, mode="diff", metric_key="news_flow")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "accelerating")


class SignalQualityTests(unittest.TestCase):
    def test_robust_vol_uses_mad(self) -> None:
        vol = robust_vol([0.1, 0.12, 0.11, 0.5])
        self.assertGreater(vol, 0)
        self.assertLess(vol, 0.5)

    def test_persistence_confirmed(self) -> None:
        tier = signal_tier_from_accels([0.05, 0.08], "accelerating", 0.04)
        self.assertEqual(tier, "confirmed")

    def test_persistence_emerging(self) -> None:
        tier = signal_tier_from_accels([0.01, 0.08], "accelerating", 0.04)
        self.assertEqual(tier, "emerging")

    def test_collapse_core_signals(self) -> None:
        metrics = [
            {
                "metric": "revenues",
                "direction": "accelerating",
                "signal_tier": "confirmed",
                "tier": "primary",
                "source": "sec_fundamentals",
                "basis": "yoy",
                "mode": "pct",
                "growth_latest": 0.15,
                "growth_prior": 0.08,
                "accel": 0.07,
                "threshold": 0.03,
                "points": [],
            },
            {
                "metric": "operating_income",
                "direction": "accelerating",
                "signal_tier": "confirmed",
                "tier": "primary",
                "source": "sec_fundamentals",
                "basis": "yoy",
                "mode": "pct",
                "growth_latest": 0.20,
                "growth_prior": 0.10,
                "accel": 0.10,
                "threshold": 0.04,
                "points": [],
            },
        ]
        merged = collapse_core_signals(metrics)
        composites = [m for m in merged if m.get("composite")]
        self.assertEqual(len(composites), 1)
        self.assertEqual(composites[0]["metric"], "core_business")
        self.assertFalse(metrics[0]["display"])
        self.assertFalse(metrics[1]["display"])

    def test_balance_sheet_hidden_by_default(self) -> None:
        entry = {
            "metrics": [
                {
                    "metric": "cash",
                    "direction": "accelerating",
                    "signal_tier": "confirmed",
                    "tier": "excluded",
                    "accel": 0.5,
                    "threshold": 0.1,
                    "strength": 5.0,
                },
                {
                    "metric": "revenues",
                    "direction": "accelerating",
                    "signal_tier": "confirmed",
                    "tier": "primary",
                    "accel": 0.08,
                    "threshold": 0.03,
                    "strength": 2.6,
                },
            ]
        }
        finalize_ticker_entry(entry)
        cash = entry["metrics"][0]
        rev = entry["metrics"][1]
        self.assertFalse(cash["display"])
        self.assertTrue(rev["display"])

    def test_derive_op_margin(self) -> None:
        rev = quarterly([100.0, 110.0, 120.0, 130.0] * 3)
        oi = [{"period": p["period"], "value": p["value"] * 0.2} for p in rev]
        margins = derive_ratio_series(oi, rev)
        self.assertEqual(len(margins), len(rev))
        self.assertAlmostEqual(margins[-1]["value"], 0.2)


class NewsFlowTests(unittest.TestCase):
    def test_counts_bucketed_by_month_and_ticker(self) -> None:
        doc = {
            "items": [
                {"tickers": ["AAA"], "published_utc": "2026-06-15T10:00:00+00:00"},
                {"tickers": ["AAA", "BBB"], "published_utc": "2026-06-20T10:00:00+00:00"},
            ]
        }
        series = news_flow_series(doc)
        self.assertEqual(dict(series["AAA"]).get("2026-06-01"), 2.0)
        self.assertEqual(dict(series["BBB"]).get("2026-06-01"), 1.0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
