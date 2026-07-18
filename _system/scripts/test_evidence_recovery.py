from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_evidence_recovery_queue import collector_for


class EvidenceRecoveryTests(unittest.TestCase):
    def test_contract_and_filing_questions_use_primary_collector(self):
        self.assertEqual(collector_for("reconcile debt maturity from the 10-K filing"), "sec_primary_documents")

    def test_market_questions_use_market_collector(self):
        self.assertEqual(collector_for("normalize industry capacity and utilization"), "market_and_filing_facts")

    def test_model_gap_starts_with_primary_documents(self):
        self.assertEqual(collector_for("build component ownership schedule"), "primary_documents_then_model")


if __name__ == "__main__":
    unittest.main()
