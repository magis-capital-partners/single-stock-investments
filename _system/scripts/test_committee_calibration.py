import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from committee_calibration import summarize


class CommitteeCalibrationTests(unittest.TestCase):
    def test_missing_outcomes_do_not_create_fake_accuracy(self):
        result = summarize([{"return_status": "partial", "total_return_pct": 12}])
        self.assertEqual(result["status"], "insufficient_outcomes")
        self.assertEqual(result["completed_outcomes"], 0)

    def test_directional_accuracy_uses_completed_total_return(self):
        rows = [{"return_status": "complete", "total_return_pct": 18, "votes": [
            {"persona": "hk", "vote": "approve"}, {"persona": "pabrai", "vote": "reject"}
        ]}]
        result = summarize(rows)
        self.assertEqual(result["methods"]["hk"]["directional_accuracy_pct"], 100.0)
        self.assertEqual(result["methods"]["pabrai"]["directional_accuracy_pct"], 0.0)

    def test_expected_return_range_is_calibrated(self):
        rows = [{"return_status": "complete", "total_return_pct": 15, "votes": [
            {"persona": "hk", "vote": "approve", "expected_return_range_pct": [10, 20]}
        ]}]
        result = summarize(rows)["methods"]["hk"]
        self.assertEqual(result["expected_range_hit_rate_pct"], 100.0)
        self.assertEqual(result["mean_absolute_midpoint_error_pct"], 0.0)
        self.assertEqual(result["calibration_use"], "descriptive")


if __name__ == "__main__":
    unittest.main()
