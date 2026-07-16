#!/usr/bin/env python3
"""Unit tests for index float-impact (HK reconstitution axioms)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from index_flow_impact import (  # noqa: E402
    compute_event_impact,
    expand_migration_legs,
    load_aum_registry,
)


class TestIndexFlowImpact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_aum_registry()
        cls.assertTrue(cls.reg.get("indices"), "index_aum.json missing")

    def test_apld_graduation_both_sides_no_double_count(self):
        """APLD R2000→R1000/Midcap: both sides modeled; Microcap skipped for top-of-R2000."""
        mi = {
            "market_cap_usd": 285.77e6 * 37.77,
            "float_pct": 0.916,
            "adv_dollar": 21.8e6 * 37.77,
        }
        impact = compute_event_impact(
            ticker="APLD",
            mi=mi,
            primary_index="russell_1000",
            action="add",
            registry=self.reg,
            title="Applied Digital (APLD) Joins Russell 1000 As Its Market Profile Shifts",
            current_memberships=["russell_2000"],
            confidence="news_unconfirmed",
        )
        self.assertEqual(impact["status"], "ok")
        self.assertTrue(impact["is_russell_breakpoint_migration"])
        legs = {lg["index"]: lg for lg in impact["legs"]}
        self.assertIn("russell_1000", legs)
        self.assertIn("russell_2000", legs)
        self.assertIn("russell_midcap", legs)
        self.assertEqual(legs["russell_1000"]["sign"], +1)
        self.assertEqual(legs["russell_2000"]["sign"], -1)
        self.assertEqual(legs["russell_midcap"]["sign"], +1)
        # Top-of-R2000: Microcap must not appear (skip_if_also / weight gate)
        self.assertNotIn("russell_microcap", legs)
        # No duplicate legs
        self.assertEqual(len(impact["legs"]), len(legs))
        # Net selling in all stacks (HK axiom: graduation ≠ inflow)
        for stack in ("low", "base", "high"):
            pct = impact["stacks"][stack]["pct_of_float"]
            self.assertIsNotNone(pct)
            self.assertLess(pct, 0, f"{stack} should be net selling")
        # Low (ETF-observed) in the validated ~3–5% band
        low = impact["stacks"]["low"]["pct_of_float"]
        self.assertGreaterEqual(low, -6.0)
        self.assertLessEqual(low, -2.0)
        # HK cliff diagnostic present and >> 1
        self.assertIsNotNone(impact["hk_weight_cliff_ratio"])
        self.assertGreater(impact["hk_weight_cliff_ratio"], 3.0)

    def test_graduation_never_one_sided(self):
        legs = expand_migration_legs(
            "russell_1000",
            "add",
            title="Joins Russell 1000",
            registry=self.reg,
            current_memberships=[],
        )
        signs = {(lg["index"], lg["sign"]) for lg in legs}
        self.assertIn(("russell_1000", +1), signs)
        self.assertIn(("russell_2000", -1), signs)

    def test_demotion_buys_r2000(self):
        mi = {
            "market_cap_usd": 6e9,
            "float_pct": 0.9,
            "adv_dollar": 50e6,
        }
        impact = compute_event_impact(
            ticker="DEMO",
            mi=mi,
            primary_index="russell_1000",
            action="delete",
            registry=self.reg,
            title="Dropped from Russell 1000",
            current_memberships=["russell_1000", "russell_midcap"],
        )
        legs = {lg["index"]: lg["sign"] for lg in impact["legs"]}
        self.assertEqual(legs.get("russell_1000"), -1)
        self.assertEqual(legs.get("russell_2000"), +1)
        # Demotion should be net buying (positive % float) at low/base
        self.assertGreater(impact["stacks"]["base"]["pct_of_float"], 0)

    def test_missing_mcap_is_n_a(self):
        impact = compute_event_impact(
            ticker="X",
            mi={},
            primary_index="russell_1000",
            action="add",
            registry=self.reg,
        )
        self.assertEqual(impact["status"], "n_a")
        self.assertEqual(impact["reason"], "missing_market_cap")

    def test_float_unknown_flagged(self):
        impact = compute_event_impact(
            ticker="X",
            mi={"market_cap_usd": 10e9, "adv_dollar": 100e6},
            primary_index="russell_2000",
            action="add",
            registry=self.reg,
        )
        self.assertEqual(impact["float_flag"], "float_unknown")
        self.assertEqual(impact["status"], "float_unknown")

    def test_sp500_models_midcap_offset(self):
        legs = expand_migration_legs(
            "sp500",
            "add",
            title="Joins the S&P 500",
            registry=self.reg,
            current_memberships=["sp400"],
        )
        signs = {(lg["index"], lg["sign"]) for lg in legs}
        self.assertIn(("sp500", +1), signs)
        self.assertIn(("sp400", -1), signs)


if __name__ == "__main__":
    unittest.main()
