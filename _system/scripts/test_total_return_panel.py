import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_total_return_panel import annualized_from_index, build_wealth_series, coverage_status, svg_chart


class TotalReturnPanelTests(unittest.TestCase):
    def test_chart_is_logarithmic_percentage_return_without_spy(self):
        chart = svg_chart(
            ["1980-01-01", "2026-01-01"], [100, 250], [100, 400],
            ticker="TPL", contributions={"regular_dividend": 10, "special_dividend": 2},
        )
        self.assertIn("logarithmic scale", chart)
        self.assertIn("Total return +300.0%", chart)
        self.assertIn("Price-only +150.0%", chart)
        self.assertNotIn("SPY", chart)

    def test_split_does_not_change_wealth(self):
        result = build_wealth_series(
            ["2024-01-01", "2024-01-02"], [50, 50],
            [{"ex_date": "2024-01-02", "type": "split", "split_factor": 2}],
        )
        self.assertEqual(result["price_index"], [100, 100])
        self.assertEqual(result["total_return_index"], [100, 100])

    def test_pre_split_distribution_is_normalized_to_adjusted_price_basis(self):
        result = build_wealth_series(
            ["2024-01-01", "2024-01-02", "2024-01-03"], [50, 50, 50],
            [
                {"ex_date": "2024-01-01", "type": "special_dividend", "amount_per_share": 10},
                {"ex_date": "2024-01-02", "type": "split", "split_factor": 2},
            ],
        )
        self.assertAlmostEqual(result["total_return_index"][-1], 110)

    def test_vendor_dividends_already_adjusted_for_splits_are_not_adjusted_twice(self):
        # Apple declared $0.82 before its Aug 2020 4:1 split; Yahoo reports
        # the same historical dividend as $0.205 on today's share basis.
        dates = ["2020-08-06", "2020-08-07", "2020-08-31"]
        split = {"ex_date": "2020-08-31", "type": "split", "split_factor": 4}
        primary = {"ex_date": "2020-08-07", "type": "regular_dividend", "amount_per_share": 0.82}
        vendor = {**primary, "amount_per_share": 0.205, "amount_basis": "split_adjusted"}
        raw_result = build_wealth_series(dates, [100, 100, 100], [primary, split])
        vendor_result = build_wealth_series(dates, [100, 100, 100], [vendor, split])
        self.assertEqual(raw_result["total_return_index"], vendor_result["total_return_index"])
        self.assertAlmostEqual(vendor_result["total_return_index"][-1], 100.205)

    def test_cash_before_the_observation_window_is_not_credited_to_the_investor(self):
        result = build_wealth_series(["2020-01-01", "2021-01-01"], [100, 100], [
            {"ex_date": "2019-01-01", "type": "regular_dividend", "amount_per_share": 10}])
        self.assertEqual(result["total_return_index"], [100, 100])

    def test_multiple_same_day_cash_events_are_additive_and_reinvested(self):
        result = build_wealth_series(
            ["2024-01-01", "2024-06-01"], [100, 100],
            [
                {"ex_date": "2024-06-01", "type": "regular_dividend", "amount_per_share": 2},
                {"ex_date": "2024-06-01", "type": "special_dividend", "amount_per_share": 8},
            ],
        )
        self.assertAlmostEqual(result["total_return_index"][-1], 110)
        self.assertEqual(result["cash_by_type"]["regular_dividend"], 2)
        self.assertEqual(result["cash_by_type"]["special_dividend"], 8)

    def test_non_trading_ex_date_uses_next_close(self):
        result = build_wealth_series(
            ["2024-01-05", "2024-01-08"], [100, 100],
            [{"ex_date": "2024-01-06", "type": "regular_dividend", "amount_per_share": 5}],
        )
        self.assertAlmostEqual(result["total_return_index"][-1], 105)

    def test_annualized_return_comes_from_wealth_endpoint(self):
        self.assertAlmostEqual(annualized_from_index(121, 730.5), 10, places=6)

    def test_incomplete_ledger_cannot_be_complete(self):
        status, _ = coverage_status({"status": "vendor_only"}, "2020-01-01", "2024-01-01", [])
        self.assertEqual(status, "partial")

    def test_unreconciled_event_blocks_complete_coverage(self):
        coverage = {"status": "complete", "start": "2020-01-01", "end": "2025-01-01"}
        status, _ = coverage_status(coverage, "2020-01-01", "2024-01-01", [{"reconciliation_status": "discovered"}])
        self.assertEqual(status, "evidence_blocked")


if __name__ == "__main__":
    unittest.main()
