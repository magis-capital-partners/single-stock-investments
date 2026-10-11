#!/usr/bin/env python3
"""Separation flow legs: both sides, n_a discipline, policy gating."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import separation_flow_impact as flow  # noqa: E402
from separation_common import gate_state  # noqa: E402

REGISTRY = {
    "as_of": "2026-07-15",
    "stale_after_days": 120,
    "indices": {
        "sp500": {
            "family": "sp_dji",
            "index_total_mcap_usd": 50e12,
            "tiers": {
                "etf_observed": {"aum_usd": 1e12, "confidence": "observed"},
                "index_funds_est": {"aum_usd": 3e12, "confidence": "estimate"},
                "benchmarked_bmi": {"multiplier": 1.5, "confidence": "scenario"},
            },
        },
        "russell_1000": {
            "family": "russell",
            "index_total_mcap_usd": 50e12,
            "tiers": {
                "etf_observed": {"aum_usd": 0.5e12, "confidence": "observed"},
                "index_funds_est": {"aum_usd": 1e12, "confidence": "estimate"},
            },
        },
        "russell_midcap": {
            "family": "russell",
            "overlap_parent": "russell_1000",
            "index_total_mcap_usd": 10e12,
            "tiers": {"etf_observed": {"aum_usd": 0.2e12}, "index_funds_est": {"aum_usd": 0.3e12}},
        },
    },
}
RULES = {
    "separation_policy": {
        "sp_dji": {"spin_off_treatment": "add_then_review", "exclusion_window_sessions": 5},
        "russell": {"spin_off_treatment": "add_if_eligible_then_rerank", "exclusion_window_sessions": 5},
    }
}
TODAY = date(2026, 10, 11)


def spin_record(**terms):
    base = {
        "separation_id": "sep:test-spin",
        "kind": "spin_off",
        "parent_ticker": "PAR",
        "parent_cik": "0000000001",
        "spinco_ticker": "SPN",
        "spinco_name": "SpinCo",
        "dates": {"record": "2026-10-01", "distribution": "2026-10-15"},
        "terms": {"distribution_ratio": 0.5, **terms},
        "sources": [{"form": "10-12B", "accession": "x"}],
        "status": "filed",
        "lifecycle": "active",
    }
    return base


def split_record(**exchange):
    return {
        "separation_id": "sep:test-split",
        "kind": "split_off",
        "parent_ticker": "PAR",
        "parent_cik": "0000000001",
        "spinco_ticker": "SPN",
        "spinco_name": "SpinCo",
        "dates": {"offer_launch": "2026-09-14", "expiration": "2026-10-09", "settlement": "2026-10-14"},
        "terms": {"exchange": {"discount_pct": 7.0, "upper_limit_ratio": 4.5939, **exchange}},
        "sources": [{"form": "SC TO-I", "accession": "y"}],
        "status": "offer_open",
        "lifecycle": "active",
    }


PARENT_MI = {"shares_outstanding": 1_000_000_000, "float_pct": 0.95, "price": 90.0, "adv_shares": 6_000_000}
SPINCO_MI = {"shares_outstanding": 280_000_000, "float_pct": 0.10, "price": 22.0, "adv_shares": 2_000_000}


class SpinOffTests(unittest.TestCase):
    def test_index_exclusion_leg_is_a_sell_with_a_window(self):
        row = flow.compute_separation_flow(
            spin_record(), side="spinco", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI,
            parent_memberships=["sp500", "russell_1000", "russell_midcap"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        legs = {lg["leg"]: lg for lg in row["legs"] if lg["index"] in (None, "sp500")}
        excl = [lg for lg in row["legs"] if lg["leg"] == "index_exclusion_sale" and lg["index"] == "sp500"][0]
        self.assertEqual(excl["direction"], "sell")
        self.assertLess(excl["shares_base"], 0)
        # 3e12/50e12 = 6% of parent float 950M x ratio 0.5 = 28.5M shares
        self.assertAlmostEqual(excl["shares_base"], -28_500_000, delta=1)
        self.assertEqual(excl["window_start"], "2026-10-15")
        self.assertIsNotNone(excl["window_end"])
        self.assertEqual(excl["confidence"], "estimate")
        # subset index not double counted
        self.assertFalse(any(lg["index"] == "russell_midcap" for lg in row["legs"]))
        self.assertEqual(row["status"], "ok")
        self.assertLess(row["pct_of_float_base"], 0)
        self.assertEqual(row["authority"], "none")
        self.assertIn("mandate_mismatch_sale", legs)
        self.assertEqual(legs["mandate_mismatch_sale"]["confidence"], "n_a")

    def test_spinco_kept_in_index_has_no_exclusion_leg(self):
        row = flow.compute_separation_flow(
            spin_record(spinco_index_eligibility_after=["sp500"]), side="spinco",
            spinco_mi=SPINCO_MI, parent_mi=PARENT_MI, parent_memberships=["sp500"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        self.assertFalse(any(lg["leg"] == "index_exclusion_sale" for lg in row["legs"]))

    def test_missing_ratio_yields_na_not_a_number(self):
        rec = spin_record()
        rec["terms"]["distribution_ratio"] = None
        row = flow.compute_separation_flow(
            rec, side="spinco", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI, parent_memberships=["sp500"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        excl = [lg for lg in row["legs"] if lg["leg"] == "index_exclusion_sale"][0]
        self.assertEqual(excl["confidence"], "n_a")
        self.assertIsNone(excl["shares_base"])
        self.assertEqual(row["status"], "n_a")

    def test_parent_side_of_a_spin_has_no_mechanical_seller(self):
        row = flow.compute_separation_flow(
            spin_record(), side="parent", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI,
            parent_memberships=["sp500"], registry=REGISTRY, rules=RULES, today=TODAY,
        )
        self.assertEqual(row["status"], "n_a")
        self.assertIn("no_mechanical_parent_seller", row["reason"])

    def test_retained_stake_is_dated_overhang(self):
        row = flow.compute_separation_flow(
            spin_record(retained_stake_pct=19.9, retained_stake_disposal_deadline="2027-10-15"),
            side="spinco", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI, parent_memberships=["sp500"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        leg = [lg for lg in row["legs"] if lg["leg"] == "retained_stake_overhang"][0]
        self.assertAlmostEqual(leg["shares_base"], -280_000_000 * 0.199, delta=1)
        self.assertEqual(leg["window_end"], "2027-10-15")
        self.assertEqual(leg["confidence"], "observed")


class SplitOffTests(unittest.TestCase):
    def test_arb_unwind_from_accepted_and_ratio(self):
        row = flow.compute_separation_flow(
            split_record(final_ratio=4.5939, parent_shares_accepted=49_056_639, parent_shares_tendered=200_000_000),
            side="spinco", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI, parent_memberships=["sp500"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        arb = [lg for lg in row["legs"] if lg["leg"] == "arb_unwind_sale"][0]
        exchanged = 49_056_639 * 4.5939
        self.assertAlmostEqual(arb["shares_base"], -exchanged * 0.5, delta=1)
        self.assertEqual(arb["window_start"], "2026-10-14")
        self.assertEqual(row["status"], "ok")
        self.assertIsNotNone(row["pct_of_adv_days"])
        buy = [lg for lg in row["legs"] if lg["leg"] == "index_add_buy"][0]
        self.assertEqual(buy["confidence"], "n_a")  # eligibility not stated

    def test_offer_size_used_before_final_count(self):
        row = flow.compute_separation_flow(
            split_record(spinco_shares_offered=225_361_295), side="spinco",
            spinco_mi=SPINCO_MI, parent_mi=PARENT_MI, parent_memberships=["sp500"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        arb = [lg for lg in row["legs"] if lg["leg"] == "arb_unwind_sale"][0]
        self.assertAlmostEqual(arb["shares_base"], -225_361_295 * 0.5, delta=1)
        self.assertIn("fully subscribed", arb["source"])

    def test_parent_side_models_return_and_retirement(self):
        row = flow.compute_separation_flow(
            split_record(final_ratio=4.5939, parent_shares_accepted=49_056_639, parent_shares_tendered=200_000_000),
            side="parent", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI, parent_memberships=["sp500"],
            registry=REGISTRY, rules=RULES, today=TODAY,
        )
        legs = {lg["leg"]: lg for lg in row["legs"]}
        self.assertAlmostEqual(legs["unaccepted_parent_return"]["shares_base"], -(200_000_000 - 49_056_639) * 0.5, delta=1)
        self.assertAlmostEqual(legs["parent_share_retirement"]["shares_base"], -49_056_639 * 0.06, delta=1)
        self.assertEqual(row["status"], "ok")

    def test_no_counts_no_numbers(self):
        row = flow.compute_separation_flow(
            split_record(), side="parent", spinco_mi=SPINCO_MI, parent_mi=PARENT_MI,
            parent_memberships=["sp500"], registry=REGISTRY, rules=RULES, today=TODAY,
        )
        self.assertEqual(row["status"], "n_a")
        self.assertTrue(all(lg["shares_base"] is None for lg in row["legs"]))


class GateTests(unittest.TestCase):
    def test_split_off_without_upper_limit_is_discovery(self):
        rec = split_record()
        del rec["terms"]["exchange"]["upper_limit_ratio"]
        self.assertEqual(gate_state(rec)["status"], "discovery")
        self.assertIn("exchange.upper_limit_ratio", gate_state(rec)["terms"]["missing"])

    def test_complete_split_off_is_ranked(self):
        self.assertEqual(gate_state(split_record())["status"], "ranked")

    def test_spin_without_source_is_discovery(self):
        rec = spin_record()
        rec["sources"] = []
        self.assertEqual(gate_state(rec)["status"], "discovery")


if __name__ == "__main__":
    unittest.main()
