import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_valuation_workbench as workbench  # noqa: E402


class ValuationWorkbenchTests(unittest.TestCase):
    def test_add_months_handles_month_end(self):
        self.assertEqual(workbench.add_months("2026-08-31", 6), "2027-02-28")

    def test_live_names_build_truthful_waiting_schedules(self):
        for ticker in ("TPL", "LB", "WBI", "AZLCZ"):
            with self.subTest(ticker=ticker):
                row = workbench.build(ticker, "2026-07-15")
                self.assertEqual(row["ticker"], ticker)
                self.assertIn(row["committee"]["status"], {"independent_review_open", "owner_decision_pending"})
                self.assertGreater(row["evidence"]["open_count"], 0)
                self.assertEqual(row["outcomes"]["status"], "waiting_for_owner_decision")
                self.assertTrue(all(slot["target_date"] is None for slot in row["outcomes"]["schedule"]))
                self.assertEqual(row["attribution"]["status"], "baseline_established")

    def test_attribution_identifies_probability_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            research = Path(tmp)
            (research / "valuation_history").mkdir()
            old = {
                "as_of": "2026-01-01",
                "component_valuation_results": {
                    "total_equity_value_per_share": {"base": 10},
                    "additive_components": [{"id": "option", "label": "Option", "base_per_share": 10, "evidence_tier": "a"}],
                },
                "economic_value_analysis": {"valuation_proof": [{"component_id": "option", "method": "option", "quantity": {"value": 1}, "comparable_ids": [], "adjustment": "x", "risk_and_timing": {"success_probability": 0.2, "timing_basis": "five years", "remaining_capital_m": 0}}]},
            }
            current = json.loads(json.dumps(old))
            current["as_of"] = "2026-07-01"
            current["component_valuation_results"]["total_equity_value_per_share"]["base"] = 15
            current["component_valuation_results"]["additive_components"][0]["base_per_share"] = 15
            current["economic_value_analysis"]["valuation_proof"][0]["risk_and_timing"]["success_probability"] = 0.3
            (research / "valuation_history" / "valuation_2026-01-01.json").write_text(json.dumps(old), encoding="utf-8")
            with patch.object(workbench, "ROOT", Path(tmp).parent):
                result = workbench.attribution_view(research, current)
            self.assertEqual(result["base_change_per_share"], 5)
            self.assertEqual(result["drivers"][0]["causes"], ["probability"])
            self.assertEqual(result["unexplained_per_share"], 0)

    def test_unconfigured_compounder_routes_to_quality_profile(self):
        config = workbench.read_json(workbench.CONFIG)
        view = workbench.method_fit_view(config, {}, {"classification_inputs": {"archetype": "compounder"}})
        self.assertEqual(view["profile_id"], "quality_reinvestment")
        self.assertIn("hohn", view["primary_personas"])


if __name__ == "__main__":
    unittest.main()
