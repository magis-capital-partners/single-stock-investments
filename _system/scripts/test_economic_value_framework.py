import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from economic_value_framework import build_economic_value_analysis  # noqa: E402
from marvin_valuation import compute_valuation  # noqa: E402


def fixture(case: dict) -> dict:
    components = []
    groups = []
    for item in case["components"]:
        low, base, high = item["range"]
        components.append({
            "id": item["id"],
            "label": item["id"].replace("_", " ").title(),
            "category": item["category"],
            "overlap_key": item["id"],
            "treatment": "additive",
            "valuation": {
                "method": item["method"], "basis": "per_share", "low": low, "base": base, "high": high,
                "evidence_tier": "golden_case", "evidence": f"golden case {case['id']}",
                "cross_check": "Explicit regression assumption; replace with current primary evidence in live analysis.",
            },
        })
        groups.append({
            "id": item["id"], "label": item["id"], "component_ids": [item["id"]],
            "economic_claim": item["id"], "valuation_basis": item["method"],
            "adjustments": "Like-for-like economic claim, timing, capital, ownership, and realization adjustments.",
            "overlap_control": f"Unique overlap key {item['id']}.",
            "comparable_ids": item.get("comparable_ids", []),
            "risk_and_timing": {
                "probability_basis": "Risked low/base/high outcome range.",
                "timing_basis": "Scenario timing and discounting.",
                "remaining_capital_basis": "Remaining capital is deducted or reserved in the range.",
            },
        })
    return {
        "ticker": f"GOLD_{case['id'].upper()}", "method": "pending", "inputs": {"shares_outstanding": 100},
        "classification_inputs": {"archetype": case["archetype"]},
        "component_valuation": {"all_material_components_identified": True, "components": components},
        "economic_value": {
            "schema_version": "1.0",
            "economic_claim": {
                "description": "One common economic unit in the golden case.", "unit_label": "common economic unit",
                "unit_count": 100, "unit_source": "golden fixture",
                "enterprise_to_equity_reconciliation": "All operating assets, financial claims, liabilities, and reserves are included once in the additive schedule.",
            },
            "gaap_role": case["gaap_role"], "component_groups": groups,
        },
    }


class EconomicValueFrameworkTests(unittest.TestCase):
    def test_all_archetypes_complete_the_same_contract(self):
        cases = json.loads((ROOT / "_system/research/valuation_golden_cases.json").read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case=case["id"]):
                result = compute_valuation(fixture(case))
                economic = result["economic_value_analysis"]
                self.assertEqual(economic["status"], "complete")
                self.assertTrue(economic["complete_component_coverage"])
                self.assertEqual(len(economic["valuation_proof"]), len(case["components"]))
                self.assertTrue(all(row["falsifier"] for row in economic["valuation_proof"]))

    def test_missing_economic_claim_is_blocked(self):
        data = fixture({"id": "missing", "archetype": "compounder", "gaap_role": "cross_check", "components": [
            {"id": "operations", "category": "operating_business", "method": "owner_cash_dcf", "range": [1, 2, 3]}
        ]})
        compute_valuation(data)
        data["economic_value"].pop("economic_claim")
        analysis = build_economic_value_analysis(data)
        self.assertEqual(analysis["status"], "evidence_blocked")
        self.assertIn("economic_claim.description required", analysis["validation_errors"])

    def test_component_cannot_appear_in_two_groups(self):
        data = fixture({"id": "overlap", "archetype": "compounder", "gaap_role": "cross_check", "components": [
            {"id": "operations", "category": "operating_business", "method": "owner_cash_dcf", "range": [1, 2, 3]}
        ]})
        compute_valuation(data)
        data["economic_value"]["component_groups"].append(dict(data["economic_value"]["component_groups"][0], id="duplicate"))
        with self.assertRaisesRegex(ValueError, "double counts"):
            build_economic_value_analysis(data)


if __name__ == "__main__":
    unittest.main()
