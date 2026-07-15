#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from marvin_valuation import compute_valuation, run_full_scenario  # noqa: E402


def fixture() -> dict:
    return {
        "ticker": "TEST",
        "method": "full",
        "valuation_mode": "optionality",
        "valuation_overlay": "segment_cashflow",
        "classification_inputs": {"moat": "stable", "dhando": "partial"},
        "inputs": {"price": 100.0, "fcf_per_share": 5.0},
        "scenarios": {
            "bear": {"growth_y1_5": 0.0, "growth_y6_end": 0.0, "exit_pfcf_end": 10},
            "base": {"growth_y1_5": 0.04, "growth_y6_end": 0.02, "exit_pfcf_end": 15},
            "bull": {"growth_y1_5": 0.08, "growth_y6_end": 0.04, "exit_pfcf_end": 20},
        },
        "segment_build": {
            "horizon_years": 7,
            "discount_rate_explicit": 0.10,
            "segments": [
                {"owner_cash_y0_per_share": 3.0, "growth_y1_5": 0.03, "growth_y6_end": 0.02, "exit_pfcf_end": 14},
                {"owner_cash_y0_per_share": 2.0, "growth_y1_5": 0.06, "growth_y6_end": 0.03, "exit_pfcf_end": 16},
            ],
        },
        "valuation_methodology": {
            "mode": "separated_views",
            "horizon_years": 7,
            "entry_hurdles_pct": [10, 15],
            "asset_ledger": [
                {"overlap_key": "core", "evidence_status": "supported", "include_in_decision_value": False, "value_per_share": None},
                {"overlap_key": "option", "evidence_status": "illustrative_only", "include_in_decision_value": False, "value_per_share": None},
            ],
        },
    }


class SeparatedValuationTests(unittest.TestCase):
    def test_new_horizon_keys_and_legacy_keys_both_work(self):
        new = run_full_scenario(100, 5, {"growth_y1_5": 0.04, "growth_y6_end": 0.02, "exit_pfcf_end": 15}, years=7)
        old = run_full_scenario(100, 5, {"growth_y1_5": 0.04, "growth_y6_10": 0.02, "exit_pfcf_y10": 15}, years=7)
        self.assertEqual(new, old)

    def test_separated_views_disable_weighted_synthesis(self):
        data = fixture()
        data["growth_explanation"] = {"status": "complete"}
        data["results_growth_theory"] = {"theory_implied": {"return_pct": 99.0}}
        out = compute_valuation(data)
        self.assertEqual(out["synthesis"]["status"], "disabled_separated_views")
        self.assertNotIn("total_synthesis_pct", out["synthesis"])
        self.assertNotIn("results_growth_theory", out)
        self.assertFalse(out["growth_explanation"]["decision_use"])
        self.assertEqual(out["implied_return"]["base_pct"], out["results"]["base"]["return_pct"])
        self.assertEqual(
            set(out["valuation_views"]),
            {"decision_rule", "operating", "assets", "components", "reverse_expectations", "entry_prices"},
        )
        self.assertGreater(out["valuation_views"]["entry_prices"]["10%"], out["valuation_views"]["entry_prices"]["15%"])

    def test_unsupported_asset_cannot_enter_decision_value(self):
        data = fixture()
        data["valuation_methodology"]["asset_ledger"][1]["include_in_decision_value"] = True
        data["valuation_methodology"]["asset_ledger"][1]["value_per_share"] = 20
        with self.assertRaisesRegex(ValueError, "unsupported asset"):
            compute_valuation(data)

    def test_overlap_keys_must_be_unique(self):
        data = fixture()
        data["valuation_methodology"]["asset_ledger"][1]["overlap_key"] = "core"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            compute_valuation(data)

    def test_tpl_uses_owner_cash_and_separate_views(self):
        data = json.loads((ROOT / "TPL" / "research" / "valuation.json").read_text(encoding="utf-8"))
        out = compute_valuation(copy.deepcopy(data))
        self.assertEqual(out["inputs"]["fcf_per_share"], 7.02)
        components = out["component_valuation_results"]
        self.assertEqual(components["status"], "complete")
        self.assertTrue(components["all_material_components_identified"])
        self.assertEqual(components["total_equity_value_per_share"]["base"], 163.02)
        self.assertEqual(components["material_component_count"], 7)
        queue = out["component_review_queue"]
        self.assertEqual(queue["status"], "ready_for_committee_review")
        self.assertEqual(len(queue["items"]), 7)
        self.assertEqual(queue["items"][0]["status"], "open")
        self.assertEqual(out["synthesis"]["status"], "disabled_separated_views")
        self.assertLess(out["results"]["base"]["return_pct"], 0)

    def test_component_schedule_requires_complete_ranges_and_no_double_count(self):
        data = fixture()
        data["component_valuation"] = {
            "all_material_components_identified": True,
            "components": [{
                "id": "core",
                "label": "Core",
                "category": "operating_business",
                "overlap_key": "core",
                "treatment": "additive",
                "valuation": {"method": "dcf", "evidence": "filing", "low": 50, "base": 60, "high": 70},
            }],
        }
        out = compute_valuation(data)
        self.assertEqual(out["component_valuation_results"]["total_equity_value_per_share"]["base"], 60.0)
        data["component_valuation"]["components"][0]["valuation"].pop("high")
        with self.assertRaisesRegex(ValueError, "missing valuation.high"):
            compute_valuation(data)

    def test_full_valuation_gets_a_universal_operating_fallback(self):
        data = fixture()
        data.pop("component_valuation", None)
        data["valuation_methodology"] = {"mode": "standard"}
        out = compute_valuation(data)
        result = out["component_valuation_results"]
        self.assertEqual(result["status"], "inferred_minimal")
        self.assertFalse(result["all_material_components_identified"])
        self.assertEqual(result["additive_component_count"], 1)

    def test_yield_curve_gets_a_dated_payoff_fallback(self):
        data = {
            "ticker": "TEST",
            "method": "yield_curve",
            "classification_inputs": {"moat": "stable", "dhando": "partial"},
            "inputs": {"price": 80.0},
            "scenarios": {"base": {"price": 80.0, "payoff": 100.0, "years": 3}},
        }
        out = compute_valuation(data)
        result = out["component_valuation_results"]
        self.assertEqual(result["status"], "inferred_minimal")
        self.assertEqual(result["total_equity_value_per_share"]["base"], 100.0)


if __name__ == "__main__":
    unittest.main()
