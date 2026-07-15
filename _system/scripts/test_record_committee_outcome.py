import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_committee_outcome import upsert


class RecordCommitteeOutcomeTests(unittest.TestCase):
    def test_upsert_is_idempotent_for_same_measurement(self):
        original = {"ticker": "TPL", "decision_date": "2026-01-01", "measurement_date": "2027-01-01", "total_return_pct": 10}
        revised = {**original, "total_return_pct": 12}
        rows = upsert([original], revised)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_return_pct"], 12)


if __name__ == "__main__":
    unittest.main()
