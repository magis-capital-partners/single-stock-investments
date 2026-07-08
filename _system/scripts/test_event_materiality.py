#!/usr/bin/env python3
"""Unit tests for insights event materiality scoring."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from event_materiality import load_rules, materiality_score, materiality_tier  # noqa: E402


class EventMaterialityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_rules()

    def test_small_base_cash_dampens_score(self) -> None:
        event = {
            "source": "filing",
            "event_type": "filing_metric",
            "metric_name": "cash",
            "change_pct": 320,
            "prior_value": 500,
            "current_value": 2100,
            "confidence": "high",
            "freshness_days": 30,
            "in_our_book": True,
            "portfolio_relevance": 1.0,
            "verification": {"parser_confidence": "high"},
        }
        score, components = materiality_score(event, rules=self.rules)
        self.assertLess(score, 55)
        self.assertLess(components["magnitude"], 0.5)

    def test_confirmed_inflection_scores_higher(self) -> None:
        base = {
            "source": "kpi_trend",
            "event_type": "inflection",
            "confidence": "high",
            "freshness_days": 14,
            "in_our_book": True,
            "portfolio_relevance": 1.0,
        }
        plain, _ = materiality_score({**base, "trend_signal_tier": "watch"}, rules=self.rules)
        confirmed, _ = materiality_score({**base, "trend_signal_tier": "confirmed"}, rules=self.rules)
        self.assertGreater(confirmed, plain)

    def test_materiality_tier_thresholds(self) -> None:
        self.assertEqual(materiality_tier(60, rules=self.rules), "signal")
        self.assertEqual(materiality_tier(40, rules=self.rules), "context")
        self.assertEqual(materiality_tier(10, rules=self.rules), "noise")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
