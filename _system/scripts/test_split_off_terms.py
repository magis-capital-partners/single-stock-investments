#!/usr/bin/env python3
"""Split-off arithmetic: formula, cap, odd lot, proration, spread."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import split_off_terms as terms  # noqa: E402


class RatioTests(unittest.TestCase):
    def test_seven_percent_discount_uncapped(self):
        r = terms.implied_ratio(100.0, 20.0, 7.0, upper_limit_ratio=6.0)
        self.assertAlmostEqual(r.uncapped_ratio, 5.35)
        self.assertAlmostEqual(r.implied_ratio, 5.35)
        self.assertFalse(r.upper_limit_binding)
        self.assertAlmostEqual(r.realized_discount_pct, 7.0, places=6)

    def test_upper_limit_binds_and_shrinks_discount(self):
        r = terms.implied_ratio(100.0, 20.0, 7.0, upper_limit_ratio=5.0)
        self.assertTrue(r.upper_limit_binding)
        self.assertEqual(r.implied_ratio, 5.0)
        self.assertAlmostEqual(r.realized_discount_pct, 0.0, places=6)

    def test_upper_limit_can_turn_discount_negative(self):
        r = terms.implied_ratio(100.0, 25.0, 7.0, upper_limit_ratio=3.5)
        self.assertTrue(r.upper_limit_binding)
        self.assertLess(r.realized_discount_pct, 0)

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            terms.implied_ratio(0, 20.0, 7.0, None)
        with self.assertRaises(ValueError):
            terms.implied_ratio(100.0, 20.0, 80.0, None)


class OddLotTests(unittest.TestCase):
    def test_full_conversion_not_prorated(self):
        payoff = terms.odd_lot_payoff(100.0, 20.0, 5.35, friction_bps=0)
        self.assertEqual(payoff["shares"], 99)
        self.assertAlmostEqual(payoff["gain_pct"], 7.0, places=4)
        self.assertAlmostEqual(payoff["gain_usd"], 99 * (5.35 * 20 - 100), places=2)

    def test_hundred_shares_is_not_an_odd_lot(self):
        with self.assertRaises(ValueError):
            terms.odd_lot_payoff(100.0, 20.0, 5.35, shares=100)

    def test_friction_reduces_gain(self):
        clean = terms.odd_lot_payoff(100.0, 20.0, 5.35, friction_bps=0)
        costly = terms.odd_lot_payoff(100.0, 20.0, 5.35, friction_bps=50)
        self.assertLess(costly["gain_usd"], clean["gain_usd"])


class ProrationTests(unittest.TestCase):
    def test_reference_scenario_when_nothing_filed(self):
        p = terms.proration_scenarios()
        self.assertEqual(p["basis"], "reference_set")
        self.assertLess(p["low"], p["base"])
        self.assertLess(p["base"], p["high"])

    def test_filed_counts_replace_scenario(self):
        p = terms.proration_scenarios(parent_shares_tendered=800e6, parent_shares_accepted=200e6)
        self.assertEqual(p["basis"], "final_filed")
        self.assertAlmostEqual(p["base"], 0.25)

    def test_holder_gain_is_discount_times_accepted_fraction(self):
        gain = terms.holder_expected_gain_pct(7.0, {"low": 0.1, "base": 0.25, "high": 0.5})
        self.assertAlmostEqual(gain["base"], 1.75)


class SpreadSnapshotTests(unittest.TestCase):
    def test_no_spread_without_formula(self):
        self.assertIsNone(
            terms.spread_snapshot(
                parent_price=100, spinco_price=20, exchange={"discount_pct": 7.0},
                as_of=date(2026, 10, 1), settlement=date(2026, 10, 20),
            )
        )

    def test_spread_from_filing_formula(self):
        snap = terms.spread_snapshot(
            parent_price=100.0, spinco_price=20.0,
            exchange={"discount_pct": 7.0, "upper_limit_ratio": 6.0, "odd_lot_priority": True},
            as_of=date(2026, 10, 1), settlement=date(2026, 10, 31),
        )
        self.assertEqual(snap["basis"], "filing_formula")
        self.assertEqual(snap["days_to_settlement"], 30)
        self.assertGreater(snap["annualized_spread_pct"], 50)
        self.assertEqual(snap["proration"]["basis"], "reference_set")
        self.assertAlmostEqual(snap["holder_expected_gain_pct"]["base"], 7.0 * 0.25, places=2)

    def test_final_ratio_marks_basis_final(self):
        snap = terms.spread_snapshot(
            parent_price=100.0, spinco_price=20.0,
            exchange={"discount_pct": 7.0, "upper_limit_ratio": 6.0, "final_ratio": 5.2, "proration_factor": 0.238},
            as_of=date(2026, 10, 1), settlement=date(2026, 10, 3),
        )
        self.assertEqual(snap["basis"], "final_filed")
        self.assertEqual(snap["implied_ratio"], 5.2)
        self.assertEqual(snap["proration"]["basis"], "final_filed")


class SummaryTests(unittest.TestCase):
    def test_split_off_summary_names_the_cap(self):
        text = terms.terms_summary({
            "kind": "split_off",
            "terms": {"exchange": {"discount_pct": 7, "upper_limit_ratio": 8.0525, "odd_lot_priority": True}},
        })
        self.assertIn("7% discount", text)
        self.assertIn("8.0525", text)
        self.assertIn("odd-lot", text)

    def test_missing_terms_say_so(self):
        self.assertEqual(terms.terms_summary({"kind": "spin_off", "terms": {}}), "Terms are not extracted.")


if __name__ == "__main__":
    unittest.main()
