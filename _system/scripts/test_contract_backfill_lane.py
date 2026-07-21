import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_contract_backfill_queue as queue
import build_deep_dive_dispatch_matrix as matrix
import llm_call_gate
import marvin_pick_ticker as pick


class ContractBackfillLaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "_system" / "data").mkdir(parents=True)
        (self.root / "_system" / "portfolio").mkdir(parents=True)
        holdings = {
            "AAA": {"stance": "hold"},
            "BBB": {"stance": "watch"},
            "CCC": {"stance": "core"},
        }
        (self.root / "_system" / "portfolio" / "registry.json").write_text(
            json.dumps({"holdings": holdings}), encoding="utf-8"
        )
        # Almost-there: mapped + blocked
        self._write_contract("AAA", evidence_blocked=True, mapped=True)
        # Unmapped blocked
        self._write_contract("BBB", evidence_blocked=True, mapped=False)
        # Decision grade — should not queue
        self._write_contract("CCC", evidence_blocked=False, mapped=True)

        patches = [
            patch.object(queue, "ROOT", self.root),
            patch.object(queue, "QUEUE", self.root / "_system" / "data" / "contract_backfill_queue.json"),
            patch.object(queue, "REGISTRY", self.root / "_system" / "portfolio" / "registry.json"),
            patch.object(pick, "ROOT", self.root),
            patch.object(matrix, "ROOT", self.root),
            patch.object(matrix, "DEFAULT_QUEUE", self.root / "_system" / "data" / "deep_dive_dispatch_queue.json"),
            patch.object(matrix, "BACKFILL_QUEUE", self.root / "_system" / "data" / "contract_backfill_queue.json"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tmp.cleanup)

    def _write_contract(self, ticker: str, *, evidence_blocked: bool, mapped: bool):
        research = self.root / ticker / "research"
        research.mkdir(parents=True)
        contract = {
            "status": "evidence_blocked" if evidence_blocked else "decision_grade",
            "component_coverage": {
                "all_material_components_identified": mapped,
                "additive_component_count": 3 if mapped else 0,
            },
            "evidence": {"blockers": ["needs proof"]},
        }
        (research / "valuation_contract.json").write_text(json.dumps(contract), encoding="utf-8")

    def test_queue_puts_almost_there_first_and_authorizes(self):
        payload = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertEqual(payload["almost_there"], ["AAA"])
        self.assertEqual(payload["tickers"][0], "AAA")
        self.assertIn("BBB", payload["tickers"])
        self.assertNotIn("CCC", payload["tickers"])
        auth = json.loads((self.root / "AAA" / "research" / "authorized_evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(auth["purpose"], "contract_backfill")
        self.assertEqual(auth["cohort"], "almost_there")

    def test_matrix_prefers_backfill_queue_reason(self):
        queue.build_queue(wave_size=10, authorize_packets=False)
        jobs = matrix.resolve_jobs(
            queue_path=matrix.DEFAULT_QUEUE,
            use_queue=True,
            cli_csv=None,
            reason_override=None,
        )
        self.assertTrue(jobs)
        self.assertEqual(jobs[0]["reason"], "contract_backfill")
        self.assertEqual(jobs[0]["consumer"], "marvin_contract_backfill")

    def test_policy_admits_contract_backfill_consumer(self):
        policy = json.loads(
            (Path(__file__).resolve().parents[2] / "_system" / "config" / "llm_usage_policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("contract_backfill", policy["consumers"]["marvin_research"]["allowed_reasons"])
        self.assertEqual(policy["consumers"]["marvin_contract_backfill"]["daily_repo_limit"], 20)
        model = llm_call_gate.resolve_model(policy, "marvin_contract_backfill", reason="contract_backfill")
        self.assertEqual(model, policy["model_ladder"]["default_model"])

    def test_pick_uses_contract_backfill_when_queue_ready(self):
        queue.build_queue(wave_size=10, authorize_packets=True)
        # Stub research_candidate to accept the first backfill ticker.
        def fake_candidate(ticker, reason, *, force=False):
            if reason == "contract_backfill" and ticker == "AAA":
                return {"ticker": ticker, "reason": reason, "skip": False}
            return None

        with patch.object(pick, "research_candidate", side_effect=fake_candidate), patch.object(
            pick, "evidence_recovery_candidates", return_value=[]
        ), patch.object(pick, "onboard_pending_holdings", return_value=[]), patch.object(
            pick, "holdings_tickers", return_value=["AAA", "BBB", "CCC"]
        ), patch.object(pick, "_activity_snapshot", return_value={"deep_dive_at": object(), "trigger_at": None, "reason": None}):
            result = pick.pick_ticker()
        self.assertEqual(result["ticker"], "AAA")
        self.assertEqual(result["reason"], "contract_backfill")


if __name__ == "__main__":
    unittest.main()
