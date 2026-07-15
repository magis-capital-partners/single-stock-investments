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
        self.assertEqual(components["total_equity_value_per_share"]["base"], 203.7)
        self.assertEqual(components["material_component_count"], 14)
        queue = out["component_review_queue"]
        self.assertEqual(queue["status"], "ready_for_committee_review")
        self.assertEqual(len(queue["items"]), 14)
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

    def test_driver_models_calculate_ranges_instead_of_accepting_marks(self):
        data = fixture()
        data["inputs"]["shares_outstanding"] = 10_000_000
        data["component_valuation"] = {
            "all_material_components_identified": True,
            "components": [{
                "id": "royalty",
                "label": "Royalty",
                "category": "operating_business",
                "overlap_key": "royalty",
                "treatment": "additive",
                "valuation": {
                    "method": "driver_dcf",
                    "evidence": "filing",
                    "driver_model": {
                        "type": "revenue_owner_cash_dcf",
                        "starting_revenue_m": 10,
                        "horizon_years": 10,
                        "scenarios": {
                            "low": {"after_tax_owner_cash_margin": .5, "growth_y1_5": 0, "growth_y6_10": 0, "terminal_owner_cash_multiple": 10, "discount_rate": .12},
                            "base": {"after_tax_owner_cash_margin": .6, "growth_y1_5": .04, "growth_y6_10": .02, "terminal_owner_cash_multiple": 15, "discount_rate": .10},
                            "high": {"after_tax_owner_cash_margin": .7, "growth_y1_5": .08, "growth_y6_10": .04, "terminal_owner_cash_multiple": 20, "discount_rate": .08},
                        },
                    },
                },
            }],
        }
        out = compute_valuation(data)
        result = out["component_valuation_results"]
        self.assertGreater(result["total_equity_value_per_share"]["base"], 8)
        self.assertEqual(result["additive_components"][0]["driver_model_type"], "revenue_owner_cash_dcf")

    def test_reinvestment_model_charges_growth_capital(self):
        data = fixture()
        data["inputs"]["shares_outstanding"] = 10_000_000
        common = {
            "after_tax_owner_cash_margin": .4,
            "growth_y1_5": .10,
            "growth_y6_10": .05,
            "terminal_owner_cash_multiple": 15,
            "discount_rate": .10,
        }
        components = []
        for component_id, model_type, roic in (("free", "revenue_owner_cash_dcf", None), ("funded", "reinvestment_return_dcf", .25)):
            scenarios = {key: {**common, **({"incremental_after_tax_roic": roic} if roic else {})} for key in ("low", "base", "high")}
            components.append({
                "id": component_id, "label": component_id, "category": "operating_business",
                "overlap_key": component_id, "treatment": "additive",
                "valuation": {"method": "driver_dcf", "evidence": "filing", "driver_model": {
                    "type": model_type, "starting_revenue_m": 10, "scenarios": scenarios,
                }},
            })
        data["component_valuation"] = {"all_material_components_identified": True, "components": components}
        out = compute_valuation(data)["component_valuation_results"]["additive_components"]
        self.assertGreater(out[0]["base_per_share"], out[1]["base_per_share"])

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
