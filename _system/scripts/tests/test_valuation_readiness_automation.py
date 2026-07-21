import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("automation", SCRIPTS / "automate_valuation_readiness.py")
automation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(automation)

from calculation_proof import evaluate_calculation_proof
from universal_valuation_contract import build_universal_valuation_contract, strict_contract_errors


def fact(field_id, value, unit):
    return {"field_id": field_id, "value": value, "unit": unit, "locked": True,
            "source": {"ref": "_system/reference/valuation_method_registry.json", "locator": field_id, "as_of": "2026-07-19"}}


class ValuationAutomationTests(unittest.TestCase):
    def test_etf_identity_never_routes_to_operating_company_default(self):
        identity = automation.resolve_identity("FUND", {"company": "Example Index ETF", "market": "US"}, {}, "2026-07-19")
        self.assertEqual(identity["security_type"], "exchange_traded_fund")
        self.assertEqual(identity["primary_method"], "net_asset_value")

    def test_evidence_ready_requires_matching_locked_field(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf"}
        ledger = {"facts": [fact("cash_m", 20, "USD millions")]}
        plan = automation.evidence_plan("TEST", identity, ledger, "2026-07-19")
        statuses = {row["field_id"]: row["status"] for row in plan["tasks"]}
        self.assertEqual(statuses["cash_m"], "evidence_ready")
        self.assertEqual(statuses["debt_m"], "pending_collection")

    def test_compiler_emits_valid_monotonic_proof(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf", "archetype": "compounder"}
        ledger = {"facts": [
            fact("normalized_owner_earnings_m", 100, "USD millions"),
            fact("shares_outstanding", 10_000_000, "shares"),
            fact("cash_m", 20, "USD millions"), fact("debt_m", 5, "USD millions"),
        ]}
        valuation = automation.compile_owner_earnings("TEST", "2026-07-19", identity, ledger)
        proof = valuation["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        result = evaluate_calculation_proof(proof)
        self.assertEqual(result["status"], "valid", result["checks"]["errors"])
        self.assertLessEqual(result["outputs"]["low"], result["outputs"]["base"])
        self.assertLessEqual(result["outputs"]["base"], result["outputs"]["high"])
        # Market price is required for decision_grade (live mark from fetch_equity_prices).
        valuation.setdefault("inputs", {})["price"] = 50.0
        contract = build_universal_valuation_contract(valuation, "quality_reinvestment")
        self.assertEqual(contract["status"], "decision_grade", contract.get("evidence", {}).get("blockers"))
        self.assertEqual(strict_contract_errors(valuation), [])

    def test_negative_owner_earnings_cannot_clear_model_gate(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf"}
        ledger = {"facts": [
            fact("normalized_owner_earnings_m", -10, "USD millions"),
            fact("shares_outstanding", 10_000_000, "shares"),
            fact("cash_m", 20, "USD millions"), fact("debt_m", 5, "USD millions"),
        ]}
        plan = automation.evidence_plan("TEST", identity, ledger, "2026-07-19")
        statuses = {row["field_id"]: row["status"] for row in plan["tasks"]}
        self.assertEqual(statuses["normalized_owner_earnings_m"], "pending_collection")
        self.assertEqual(statuses["component_model"], "pending_collection")


if __name__ == "__main__":
    unittest.main()
