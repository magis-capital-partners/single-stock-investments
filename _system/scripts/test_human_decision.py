from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import decision_authority
import record_human_decision


class HumanDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.research = self.root / "AAA" / "research"
        self.research.mkdir(parents=True)
        committee = {
            "ticker": "AAA",
            "final_state": "committee_complete_decision_pending",
            "evidence_packet": {"packet_hash": "0123456789abcdef"},
        }
        (self.research / "committee_2026-07-18.json").write_text(json.dumps(committee), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_completed_committee_and_attestation_are_required(self):
        with patch.object(record_human_decision, "ROOT", self.root), patch.object(
            decision_authority, "ROOT", self.root, create=True
        ), patch.object(record_human_decision, "write_valuation_workbench"):
            with self.assertRaisesRegex(ValueError, "attestation"):
                record_human_decision.record("AAA", "hold", None, "owner", "Reviewed dissent", None, "wrong")

    def test_records_actionable_human_authority(self):
        with patch.object(record_human_decision, "ROOT", self.root), patch.object(
            record_human_decision, "write_valuation_workbench"
        ):
            output = record_human_decision.record(
                "AAA",
                "accumulate",
                "2% starter",
                "portfolio owner",
                "The dissent is valid; size is capped until the named evidence arrives.",
                "2026-10-18",
                record_human_decision.ATTESTATION,
            )
        saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(saved["committee_source"], "committee_2026-07-18.json")
        authority = decision_authority.resolve_authority(self.research)
        self.assertTrue(authority["actionable"])
        self.assertEqual(authority["authority_level"], "human_decision")
        self.assertEqual(authority["decision"], "accumulate")


if __name__ == "__main__":
    unittest.main()
