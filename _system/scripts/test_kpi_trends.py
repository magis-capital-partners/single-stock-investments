#!/usr/bin/env python3
"""Tests for second-derivative KPI trend analysis."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_kpi_trends import analyze_quarterly_yoy, analyze_series, news_flow_series  # noqa: E402


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
        # Strong Q4 seasonality but identical YoY growth every quarter:
        # sequential QoQ would whipsaw; YoY must read steady.
        base = [100.0, 80.0, 90.0, 150.0]
        values = base + [v * 1.10 for v in base] + [v * 1.21 for v in base]
        result = analyze_quarterly_yoy(quarterly(values))
        self.assertIsNotNone(result)
        self.assertEqual(result["basis"], "yoy")
        self.assertEqual(result["direction"], "steady")

    def test_yoy_acceleration_detected(self) -> None:
        # YoY growth 10% for 2024, then ramps sharply through 2025.
        base = [100.0, 80.0, 90.0, 150.0]
        y2 = [v * 1.10 for v in base]
        y3 = [base[0] * 1.10 * 1.12, base[1] * 1.10 * 1.20, base[2] * 1.10 * 1.35, base[3] * 1.10 * 1.60]
        result = analyze_quarterly_yoy(quarterly(base + y2 + y3))
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "accelerating")

    def test_yoy_deceleration_detected(self) -> None:
        base = [100.0, 80.0, 90.0, 150.0]
        y2 = [v * 1.30 for v in base]
        y3 = [base[0] * 1.30 * 1.28, base[1] * 1.30 * 1.18, base[2] * 1.30 * 1.06, base[3] * 1.30 * 0.90]
        result = analyze_quarterly_yoy(quarterly(base + y2 + y3))
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "decelerating")

    def test_qdel_regression_duplicate_snapshots_and_scope_mix(self) -> None:
        """The exact artifact that produced fake QDEL inflections.

        Three duplicate extracts of the same quarterly filing plus one
        annual-scope extract must never produce a signal: too few distinct
        periods and no year-apart matches.
        """
        series = [
            {"period": "2026-05-28", "value": 619.8},
            {"period": "2026-05-29", "value": 619.8},
            {"period": "2026-06-01", "value": 619.8},
            {"period": "2026-06-29", "value": 2730.2},
        ]
        self.assertIsNone(analyze_quarterly_yoy(series))

    def test_outlier_growth_excluded_as_suspect(self) -> None:
        # One quarter with a 40x value (unit error) must not fire a signal.
        base = [100.0, 80.0, 90.0, 150.0]
        values = base + [v * 1.10 for v in base] + [v * 1.21 for v in base]
        values[9] = values[9] * 40  # corrupt one quarter
        result = analyze_quarterly_yoy(quarterly(values))
        if result is not None:
            self.assertGreaterEqual(result.get("suspect_points", 0), 1)
            self.assertNotIn(result["direction"], ("accelerating",))

    def test_near_zero_denominator_skipped(self) -> None:
        # Prior-year quarter near zero would explode percentage growth.
        base = [0.001, 80.0, 90.0, 150.0]
        values = base + [50.0, 88.0, 99.0, 165.0] + [55.0, 96.8, 108.9, 181.5]
        result = analyze_quarterly_yoy(quarterly(values))
        # Either insufficient clean points (None) or a result that skipped it.
        if result is not None:
            self.assertLessEqual(abs(result["growth_latest"]), 5.0)

    def test_too_short_history_returns_none(self) -> None:
        self.assertIsNone(analyze_quarterly_yoy(quarterly([100.0, 105.0, 110.0, 120.0])))


class AnalyzeSeriesTests(unittest.TestCase):
    def test_acceleration_detected(self) -> None:
        # Growth: 5%, 5%, 5%, 20% -> latest accel is strongly positive.
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 105.0),
            ("2024-09-30", 110.25),
            ("2024-12-31", 115.76),
            ("2025-03-31", 138.91),
        ]
        result = analyze_series(points)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "accelerating")
        self.assertGreater(result["accel"], 0.1)

    def test_deceleration_detected(self) -> None:
        # Growth: 20%, 20%, 20%, 2% -> deceleration.
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 120.0),
            ("2024-09-30", 144.0),
            ("2024-12-31", 172.8),
            ("2025-03-31", 176.3),
        ]
        result = analyze_series(points)
        self.assertEqual(result["direction"], "decelerating")

    def test_steady_growth_does_not_fire(self) -> None:
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 110.0),
            ("2024-09-30", 121.0),
            ("2024-12-31", 133.1),
            ("2025-03-31", 146.4),
        ]
        result = analyze_series(points)
        self.assertEqual(result["direction"], "steady")

    def test_noisy_series_needs_bigger_move(self) -> None:
        # Highly volatile growth history raises the significance bar.
        points = [
            ("2024-03-31", 100.0),
            ("2024-06-30", 140.0),
            ("2024-09-30", 90.0),
            ("2024-12-31", 150.0),
            ("2025-03-31", 160.0),
        ]
        result = analyze_series(points)
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
        result = analyze_series(points, mode="diff")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "accelerating")


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
