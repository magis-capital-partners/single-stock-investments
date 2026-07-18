from __future__ import annotations

import unittest
from datetime import datetime, timezone

from llm_call_gate import evaluate


POLICY = {
    "default": {"daily_repo_limit": 2, "per_subject_daily_limit": 1, "duplicate_evidence_block": True},
    "consumers": {"test": {"cooldown_hours": 0}},
}
AT = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)


class LlmCallGateTests(unittest.TestCase):
    def test_completed_state_suppresses_same_evidence(self):
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="a" * 64,
            policy_doc=POLICY, ledger=[], state={"evidence_hash": "a" * 64}, at=AT,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["gate_reason"], "evidence_already_processed")

    def test_changed_evidence_is_admitted(self):
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="b" * 64,
            policy_doc=POLICY, ledger=[], state={"evidence_hash": "a" * 64}, at=AT,
        )
        self.assertTrue(result["approved"])

    def test_daily_budget_counts_reservations_not_completion_events(self):
        ledger = [
            {"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "reserved"},
            {"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "completed"},
        ]
        result = evaluate(
            consumer="test", subject="BBB", reason="material", evidence_hash="b" * 64,
            policy_doc=POLICY, ledger=ledger, at=AT,
        )
        self.assertTrue(result["approved"])

    def test_duplicate_reservation_is_suppressed(self):
        ledger = [{"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "reserved"}]
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="a" * 64,
            policy_doc=POLICY, ledger=ledger, at=AT,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["gate_reason"], "duplicate_evidence_hash")


if __name__ == "__main__":
    unittest.main()
