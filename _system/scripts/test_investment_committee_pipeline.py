import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investment_committee_pipeline import packet_hash, select_raters, validate_vote


class InvestmentCommitteePipelineTests(unittest.TestCase):
    def test_packet_hash_is_order_independent(self):
        rows = [
            {"path": "B", "sha256": "b" * 64, "bytes": 2},
            {"path": "A", "sha256": "a" * 64, "bytes": 1},
        ]
        self.assertEqual(packet_hash(rows), packet_hash(list(reversed(rows))))

    def test_raters_have_three_distinct_error_profiles(self):
        valuation = {"component_review_queue": {"items": [
            {"recommended_raters": ["hk", "marathon_capital_cycle"]},
            {"recommended_raters": ["hk", "klarman_asset_value"]},
        ]}}
        raters = select_raters(valuation)
        self.assertEqual(len(raters), 3)
        self.assertEqual(len({r["independence_group"] for r in raters}), 3)
        self.assertEqual(raters[0]["persona"], "hk")

    def test_incomplete_vote_is_rejected(self):
        expected = {"persona": "hk", "independence_group": "scarce_assets"}
        errors = validate_vote({"persona": "hk", "independence_group": "scarce_assets"}, expected)
        self.assertIn("all four calibrated scores are required", errors)
        self.assertIn("invalid vote", errors)


if __name__ == "__main__":
    unittest.main()
