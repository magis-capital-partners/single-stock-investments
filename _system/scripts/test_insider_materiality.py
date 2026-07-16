"""Tests for insider_materiality (activist-parity Form 4 scoring)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from insider_materiality import (
    SIGNAL_THRESHOLD,
    materiality_score,
    materiality_tier,
    score_form4_event,
)


NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


class InsiderMaterialityTests(unittest.TestCase):
    def test_open_market_buy_cluster_can_reach_signal(self):
        row = {
            "action": "purchase",
            "transaction_code": "P",
            "acquired_disposed": "A",
            "value_usd": 2_500_000,
            "is_ceo": True,
            "cluster_size": 3,
            "distinct_insiders": 2,
            "as_of": "2026-07-01",
            "is_10b5_1": False,
        }
        score, comps = materiality_score(row, in_holdings=True, ics=7.0, now=NOW)
        self.assertGreaterEqual(score, SIGNAL_THRESHOLD)
        self.assertEqual(materiality_tier(score, row), "signal")
        self.assertEqual(comps["plan"], 1.0)
        self.assertGreaterEqual(comps["type"], 0.9)

    def test_routine_sale_is_context_or_noise(self):
        row = {
            "action": "sale",
            "transaction_code": "S",
            "acquired_disposed": "D",
            "value_usd": 80_000,
            "is_officer": True,
            "cluster_size": 1,
            "as_of": "2026-07-01",
            "is_10b5_1": False,
        }
        score, _ = materiality_score(row, in_holdings=True, ics=2.0, now=NOW)
        tier = materiality_tier(score, row)
        self.assertIn(tier, {"context", "noise"})
        self.assertLess(score, SIGNAL_THRESHOLD)

    def test_10b5_1_sale_is_noise(self):
        row = {
            "action": "sale",
            "transaction_code": "S",
            "value_usd": 500_000,
            "is_ceo": True,
            "as_of": "2026-07-01",
            "is_10b5_1": True,
        }
        score, comps = materiality_score(row, in_holdings=True, ics=5.0, now=NOW)
        self.assertLess(comps["plan"], 0.5)
        self.assertEqual(materiality_tier(score, row), "noise")

    def test_score_form4_event_attaches_fields(self):
        row = {
            "action": "purchase",
            "transaction_code": "P",
            "value_usd": 1_200_000,
            "is_director": True,
            "as_of": "2026-06-15",
        }
        out = score_form4_event(row, in_holdings=True, ics=6.0, now=NOW)
        self.assertIn("materiality", out)
        self.assertIn("tier", out)
        self.assertIn("materiality_components", out)
        self.assertEqual(out["ics"], 6.0)


if __name__ == "__main__":
    unittest.main()
