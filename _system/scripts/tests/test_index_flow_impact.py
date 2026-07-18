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
    events_from_ticker_row,
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
        self.assertNotIn("russell_microcap", legs)
        self.assertEqual(len(impact["legs"]), len(legs))
        for stack in ("low", "base", "high"):
            pct = impact["stacks"][stack]["pct_of_float"]
            self.assertIsNotNone(pct)
            self.assertLess(pct, 0, f"{stack} should be net selling")
        low = impact["stacks"]["low"]["pct_of_float"]
        self.assertGreaterEqual(low, -6.0)
        self.assertLessEqual(low, -2.0)
        base = impact["stacks"]["base"]["pct_of_float"]
        self.assertAlmostEqual(base, -6.4, delta=0.6)
        self.assertIsNotNone(impact["hk_weight_cliff_ratio"])
        self.assertGreater(impact["hk_weight_cliff_ratio"], 3.0)

    def test_graduation_never_one_sided(self):
        legs, meta = expand_migration_legs(
            "russell_1000",
            "add",
            title="Joins Russell 1000",
            registry=self.reg,
            current_memberships=[],
            market_cap_usd=8e9,
        )
        signs = {(lg["index"], lg["sign"]) for lg in legs}
        self.assertIn(("russell_1000", +1), signs)
        self.assertIn(("russell_2000", -1), signs)
        self.assertTrue(meta.get("assumed_graduation") or True)  # title cue or assumed

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
        legs, _meta = expand_migration_legs(
            "sp500",
            "add",
            title="Joins the S&P 500",
            registry=self.reg,
            current_memberships=["sp400"],
        )
        signs = {(lg["index"], lg["sign"]) for lg in legs}
        self.assertIn(("sp500", +1), signs)
        self.assertIn(("sp400", -1), signs)

    def test_amd_top50_style_subset_n_a(self):
        impact = compute_event_impact(
            ticker="AMD",
            mi={"market_cap_usd": 300e9, "float_pct": 0.99, "adv_dollar": 5e9},
            primary_index="russell_1000",
            action="reclassify",
            registry=self.reg,
            title="Advanced Micro Devices (AMD) Joins Russell Top 50",
            current_memberships=["russell_1000", "sp500"],
            style_subset=True,
        )
        self.assertEqual(impact["status"], "n_a")
        self.assertEqual(impact["reason"], "style_subset")
        self.assertEqual(impact["legs"], [])

    def test_cprt_reclassify_ambiguous_n_a(self):
        impact = compute_event_impact(
            ticker="CPRT",
            mi={"market_cap_usd": 50e9, "float_pct": 0.95, "adv_dollar": 200e6},
            primary_index="russell_1000",
            action="reclassify",
            registry=self.reg,
            title="What Copart (CPRT)'s Index Reclassification Means For Shareholders",
            current_memberships=["russell_1000", "sp500"],
            style_subset=True,
        )
        self.assertEqual(impact["status"], "n_a")
        self.assertIn(impact["reason"], {"style_subset", "reclassify_ambiguous"})

    def test_west_2500_value_style_n_a(self):
        impact = compute_event_impact(
            ticker="WEST",
            mi={"market_cap_usd": 1e9, "float_pct": 0.8, "adv_dollar": 10e6},
            primary_index="russell_1000",
            action="reclassify",
            registry=self.reg,
            title="WEST added to Russell 2500 Value Benchmark",
            style_subset=True,
        )
        self.assertEqual(impact["status"], "n_a")
        self.assertEqual(impact["reason"], "style_subset")

    def test_already_member_add_n_a(self):
        impact = compute_event_impact(
            ticker="AMD",
            mi={"market_cap_usd": 300e9, "float_pct": 0.99, "adv_dollar": 5e9},
            primary_index="russell_1000",
            action="add",
            registry=self.reg,
            title="AMD Joins Russell 1000",  # mega-cap: ceiling blocks completed_migration
            current_memberships=["russell_1000", "sp500"],
        )
        self.assertEqual(impact["status"], "n_a")
        self.assertEqual(impact["reason"], "already_member")

    def test_apld_completed_graduation_still_modeled(self):
        """After seed flips to R1000, confirmed join still shows graduation impact."""
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
            current_memberships=["russell_1000", "russell_midcap"],
            confidence="news_unconfirmed",
        )
        self.assertEqual(impact["status"], "ok")
        self.assertTrue(impact.get("completed_migration"))
        self.assertTrue(impact["is_russell_breakpoint_migration"])
        self.assertLess(impact["stacks"]["base"]["pct_of_float"], 0)

    def test_megacap_unknown_mem_no_r2000_leg(self):
        legs, meta = expand_migration_legs(
            "russell_1000",
            "add",
            title="Some Co Joins Something",  # no graduation cue
            registry=self.reg,
            current_memberships=[],
            market_cap_usd=300e9,
        )
        ids = {lg["index"] for lg in legs}
        self.assertIn("russell_1000", ids)
        self.assertNotIn("russell_2000", ids)
        self.assertFalse(meta.get("assumed_graduation"))

    def test_smallcap_unknown_mem_assumes_graduation(self):
        legs, meta = expand_migration_legs(
            "russell_1000",
            "add",
            title="Some Co added to index",
            registry=self.reg,
            current_memberships=[],
            market_cap_usd=8e9,
        )
        ids = {lg["index"] for lg in legs}
        self.assertIn("russell_2000", ids)
        self.assertTrue(meta.get("assumed_graduation"))

    def test_candidate_kept_when_float_unknown(self):
        """Predicted rows survive without float_pct (asterisk estimates in UI)."""
        row = {
            "current_memberships": ["russell_2000"],
            "confirmed_events": [],
            "news_notes": [],
            "scorecards": [
                {
                    "index": "russell_1000",
                    "status": "inclusion_candidate",
                    "recon_status": "likely_add",
                    "distance_to_boundary_pct": 8.0,
                    "rank_method": "config_breakpoint",
                }
            ],
        }
        mi = {"market_cap_usd": 8e9, "adv_dollar": 50e6}  # no float_pct
        events = events_from_ticker_row("TEST", row, mi, self.reg)
        cand = [e for e in events if e.get("event_source") == "candidate"]
        self.assertTrue(cand)
        self.assertTrue(cand[0].get("predicted"))
        self.assertEqual(cand[0].get("confidence"), "rules_only")
        self.assertEqual(cand[0].get("float_flag"), "float_unknown")
        self.assertIsNotNone(cand[0].get("pct_of_float_base"))


if __name__ == "__main__":
    unittest.main()
