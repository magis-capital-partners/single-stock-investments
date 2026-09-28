from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_evidence_recovery_queue import _ensure_terminal_error, collector_for
from collect_evidence_recovery import retry_delay_hours, terminal_error


class EvidenceRecoveryTests(unittest.TestCase):
    def test_contract_and_filing_questions_use_primary_collector(self):
        self.assertEqual(collector_for("reconcile debt maturity from the 10-K filing"), "sec_primary_documents")

    def test_market_questions_use_market_collector(self):
        self.assertEqual(collector_for("normalize industry capacity and utilization"), "market_and_filing_facts")

    def test_model_gap_starts_with_primary_documents(self):
        self.assertEqual(collector_for("build component ownership schedule"), "primary_documents_then_model")

    def test_route_gaps_use_classification_collector(self):
        self.assertEqual(
            collector_for("resolve the Power Zone method route and archetype"),
            "primary_documents_then_classification",
        )

    def test_retry_backoff_is_bounded(self):
        self.assertEqual(retry_delay_hours(1), 1)
        self.assertEqual(retry_delay_hours(4), 8)
        self.assertEqual(retry_delay_hours(20), 24 * 7)

    def test_terminal_task_always_records_an_error(self):
        self.assertEqual(
            terminal_error({}, None),
            "Automated collection exhausted retry budget without satisfying acceptance test.",
        )
        self.assertEqual(
            terminal_error({"last_error": "missing primary source"}, None),
            "missing primary source",
        )
        self.assertEqual(
            terminal_error({}, "SEC returned HTTP 403"),
            "SEC returned HTTP 403",
        )
        self.assertEqual(
            _ensure_terminal_error({"status": "unavailable", "last_error": None})["last_error"],
            "Automated collection exhausted retry budget without satisfying acceptance test.",
        )

    def test_a_new_contract_blocker_counts_as_already_attempted(self):
        from build_evidence_recovery_queue import _task_from_gap

        task = _task_from_gap({"id": "contract_blocker:abc", "question": "price missing"})
        self.assertEqual(task["attempts"], 1)
        self.assertEqual(task["status"], "retry_scheduled")
        self.assertIn("contract rebuild", task["last_error"])

    def test_a_recorded_blocker_attempt_is_kept(self):
        from build_evidence_recovery_queue import _task_from_gap

        task = _task_from_gap(
            {"id": "contract_blocker:abc", "question": "price missing"},
            {"attempts": 2, "status": "retry_scheduled", "last_attempt_at": "2026-09-01T00:00:00Z",
             "last_error": "still blocked"},
        )
        self.assertEqual(task["attempts"], 2)
        self.assertEqual(task["last_attempt_at"], "2026-09-01T00:00:00Z")
        self.assertEqual(task["last_error"], "still blocked")

    def test_a_method_input_still_starts_unattempted(self):
        from build_evidence_recovery_queue import _task_from_gap

        task = _task_from_gap({"id": "method_input:shares", "question": "shares outstanding"})
        self.assertEqual(task["attempts"], 0)
        self.assertEqual(task["status"], "pending_collection")


if __name__ == "__main__":
    unittest.main()
