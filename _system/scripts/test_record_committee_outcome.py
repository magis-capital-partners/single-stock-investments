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

    def test_distinct_horizons_remain_distinct_measurements(self):
        six = {"ticker": "TPL", "decision_date": "2026-01-01", "measurement_date": "2026-07-01", "horizon_months": 6}
        twelve = {"ticker": "TPL", "decision_date": "2026-01-01", "measurement_date": "2027-01-01", "horizon_months": 12}
        self.assertEqual(len(upsert([six], twelve)), 2)

    def test_same_horizon_replaces_prior_measurement_date(self):
        original = {"ticker": "TPL", "decision_date": "2026-01-01", "measurement_date": "2026-07-01", "horizon_months": 6}
        revised = {**original, "measurement_date": "2026-07-02"}
        rows = upsert([original], revised)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["measurement_date"], "2026-07-02")


if __name__ == "__main__":
    unittest.main()
