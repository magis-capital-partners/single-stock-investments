from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import run_security_decision_pipeline as pipeline


class SecurityDecisionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = pipeline.ROOT
        pipeline.ROOT = Path(self.tmp.name)

    def tearDown(self):
        pipeline.ROOT = self.old_root
        self.tmp.cleanup()

    def write(self, relative: str, value: dict) -> None:
        path = pipeline.ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_contract_stage_marks_legacy_only_model_evidence_blocked(self):
        self.write(
            "AAA/research/valuation.json",
            {"ticker": "AAA", "method": "full", "inputs": {"price": 10}, "implied_return": {"base_pct": 15}},
        )
        self.write(
            "AAA/research/valuation_route.json",
            {"profile_id": "quality_reinvestment", "status": "routed", "label": "High-return compounder"},
        )
        result = pipeline.stage_contracts(["AAA"], dry_run=False)
        self.assertEqual(result["errors"], [])
        contract = json.loads((pipeline.ROOT / "AAA/research/valuation_contract.json").read_text())
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(contract["legacy_reference_present"])

    def test_price_trigger_does_not_bypass_evidence_gate(self):
        self.write(
            "BBB/research/valuation_workbench.json",
            {"decision": {"status": "evidence_blocked"}, "committee": {"status": "not_started"}},
        )
        self.write("BBB/research/pricing_analysis.json", {"price": 10, "primary_entry_price_15pct_base": 20})
        old_entries = pipeline.registry_entries
        pipeline.registry_entries = lambda: {"BBB": {"classification": {"stance": "watch"}}}
        try:
            result = pipeline.stage_committees(["BBB"], "2026-07-18", dry_run=True)
        finally:
            pipeline.registry_entries = old_entries
        self.assertEqual(result["initiated"], [])
        self.assertEqual(result["triggered_evidence_tasks"][0]["ticker"], "BBB")

    def test_priority_scope_is_core_hold_and_accumulate_only(self):
        old_entries = pipeline.registry_entries
        pipeline.registry_entries = lambda: {
            "CORE": {"classification": {"stance": "core"}},
            "HOLD": {"classification": {"stance": "hold"}},
            "WATCH": {"classification": {"stance": "watch"}},
        }
        try:
            self.assertEqual(pipeline.selected_tickers("priority"), ["CORE", "HOLD"])
        finally:
            pipeline.registry_entries = old_entries


if __name__ == "__main__":
    unittest.main()
