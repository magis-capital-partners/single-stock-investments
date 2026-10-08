"""CUSIP join rules for the overlap map."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_overlap_holdings import company_key, resolve_mapped, structural


class JoinTest(unittest.TestCase):
    def test_a_contingent_value_right_is_not_a_common_stock(self):
        self.assertTrue(structural("ABMD.CVR"))
        ticker, reason = resolve_mapped(["ABMD.CVR"], {"ABMD.CVR", "JNJ"})
        self.assertIsNone(ticker)
        self.assertEqual(reason, "not_common_stock")

    def test_two_universe_stocks_for_one_cusip_stay_unresolved(self):
        ticker, reason = resolve_mapped(["AAA", "BBB"], {"AAA", "BBB"})
        self.assertIsNone(ticker)
        self.assertEqual(reason, "ambiguous")

    def test_one_universe_stock_is_kept(self):
        ticker, reason = resolve_mapped(["AAA"], {"AAA", "BBB"})
        self.assertEqual(ticker, "AAA")
        self.assertIsNone(reason)

    def test_company_key_strips_a_legal_suffix(self):
        self.assertEqual(company_key("Acme Incorporated"), "acme")


if __name__ == "__main__":
    unittest.main()
