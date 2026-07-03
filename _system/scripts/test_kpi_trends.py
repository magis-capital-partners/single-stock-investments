#!/usr/bin/env python3
"""Tests for second-derivative KPI trend analysis."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_kpi_trends import analyze_series, news_flow_series  # noqa: E402


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
