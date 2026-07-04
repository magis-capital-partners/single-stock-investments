#!/usr/bin/env python3
"""Tests for KPI signal enhancements."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from kpi_signal_enhancements import (  # noqa: E402
    analyze_growth_regime,
    compute_leadership_risk,
    earnings_revision_signal,
    passes_materiality,
    peer_relative_signal,
    resolve_revenue_series,
    series_freshness,
    STALE_SERIES_MAX_DAYS,
)


class FreshnessTests(unittest.TestCase):
    def test_stale_series_detected(self) -> None:
        series = [{"period": "2020-07-31", "value": 100.0}]
        fresh = series_freshness(series, now=datetime(2026, 7, 3, tzinfo=timezone.utc))
        self.assertTrue(fresh["stale"])
        self.assertGreater(fresh["age_days"], STALE_SERIES_MAX_DAYS)

    def test_fresh_series(self) -> None:
        series = [{"period": "2026-04-30", "value": 100.0}]
        fresh = series_freshness(series, now=datetime(2026, 7, 3, tzinfo=timezone.utc))
        self.assertFalse(fresh["stale"])


class MaterialityTests(unittest.TestCase):
    def test_asymmetric_deceleration(self) -> None:
        self.assertTrue(passes_materiality(-0.03, "operating_income", direction="decelerating"))
        self.assertFalse(passes_materiality(0.03, "operating_income", direction="accelerating"))


class RegimeTests(unittest.TestCase):
    def test_downshift_confirmed(self) -> None:
        growths = [
            ("2023-01-31", 0.20),
            ("2023-04-30", 0.18),
            ("2023-07-31", 0.17),
            ("2023-10-31", 0.16),
            ("2024-01-31", 0.15),
            ("2024-04-30", 0.14),
            ("2024-07-31", 0.05),
            ("2024-10-31", 0.03),
            ("2025-01-31", -0.02),
            ("2025-04-30", -0.04),
        ]
        result = analyze_growth_regime(growths, metric_key="operating_income")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "downshift")
        self.assertIn(result["signal_tier"], ("confirmed", "emerging"))

    def test_rare_negative_quarter(self) -> None:
        growths = [(f"2024-{m:02d}-01", 0.15) for m in range(1, 9)]
        growths.extend([("2025-01-31", -0.03), ("2025-04-30", -0.04)])
        result = analyze_growth_regime(growths, metric_key="operating_income")
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "downshift")


class RevenueProxyTests(unittest.TestCase):
    def test_stale_revenue_uses_operating_income(self) -> None:
        metrics = {
            "revenues": [{"period": "2020-07-31", "value": 500.0}],
            "operating_income": [{"period": "2026-04-30", "value": 400.0}],
        }
        series, meta = resolve_revenue_series(metrics)
        self.assertTrue(meta.get("proxy"))
        self.assertEqual(series, metrics["operating_income"])


class LeadershipRiskTests(unittest.TestCase):
    def test_governance_news_scores(self) -> None:
        news = {
            "items": [
                {
                    "tickers": ["CPRT"],
                    "published_utc": "2026-06-29T12:00:00+00:00",
                    "title": "Copart CEO Jeff Liaw to Step Down; Jay Adair to Return as CEO",
                    "summary": "Leadership transition announced.",
                }
            ]
        }
        risk = compute_leadership_risk("CPRT", news, now=datetime(2026, 7, 3, tzinfo=timezone.utc))
        self.assertIn(risk["level"], ("watch", "elevated"))
        self.assertGreaterEqual(risk["score"], 1.0)


class PeerRelativeTests(unittest.TestCase):
    def test_lagging_peer_triggers_downshift(self) -> None:
        signal = peer_relative_signal(0.02, [0.12, 0.10, 0.11, 0.09], metric_key="revenues")
        self.assertIsNotNone(signal)
        self.assertEqual(signal["direction"], "downshift")
        self.assertEqual(signal["signal_type"], "peer_relative")


class EarningsRevisionTests(unittest.TestCase):
    def test_consecutive_misses(self) -> None:
        events = [
            {"reported": True, "date": "2026-03-01", "actual_eps": -0.20, "estimated_eps": -0.10},
            {"reported": True, "date": "2026-06-01", "actual_eps": -0.30, "estimated_eps": -0.15},
        ]
        signal = earnings_revision_signal(events)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["direction"], "decelerating")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
