from __future__ import annotations

import unittest

from calculation_proof import component_proof, evaluate_calculation_proof


def reserve_proof() -> dict:
    source = {"ref": "issuer-filing.htm", "locator": "Balance sheet", "as_of": "2026-04-30"}
    return {
        "schema_version": "1.0", "method_id": "net_asset_value", "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {"id": "reserve_m", "kind": "fact", "value": 18.342, "unit": "USD_m", "locked": True, "source": source},
            {"id": "shares_m", "kind": "fact", "value": 13.12001, "unit": "shares_m", "locked": True, "source": source},
        ],
        "assumptions": [],
        "calculations": [{"id": "per_share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD_per_share"}],
        "outputs": {"low": "per_share", "base": "per_share", "high": "per_share"},
    }


class CalculationProofTests(unittest.TestCase):
    def test_reproduces_outputs_and_substituted_formula(self):
        result = evaluate_calculation_proof(reserve_proof())
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["outputs"], {"low": 1.398, "base": 1.398, "high": 1.398})
        self.assertIn("18.342", result["traces"]["base"][-1]["substituted_formula"])
        self.assertEqual(len(result["source_lineage"]), 2)

    def test_unbounded_judgment_invalidates_component(self):
        proof = reserve_proof()
        proof["assumptions"] = [{"id": "discount", "kind": "judgment", "value": .1, "unit": "ratio", "rationale": "risk"}]
        result = component_proof({"valuation_status": "bounded_estimate", "calculation_proof": proof})
        self.assertEqual(result["valuation_status"], "unpriced")
        self.assertTrue(any("allowed_range" in error for error in result["evaluation"]["checks"]["errors"]))

    def test_raw_ranges_are_legacy_and_excluded(self):
        result = component_proof({"low_per_share": 10, "base_per_share": 20, "high_per_share": 30})
        self.assertEqual(result["valuation_status"], "legacy_sensitivity")
        self.assertIsNone(result["evaluation"])
        self.assertEqual(result["legacy_range_per_share"]["base"], 20)


if __name__ == "__main__":
    unittest.main()
