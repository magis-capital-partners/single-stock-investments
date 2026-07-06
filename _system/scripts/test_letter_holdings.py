#!/usr/bin/env python3
"""Unit tests for holdings table parsing in letter_matching."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import letter_matching as lm  # noqa: E402


class HoldingsTableParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import json

        path = Path(__file__).resolve().parents[2] / "_system" / "reference" / "securities" / "security_master.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        cls.master = lm.SecurityMaster.from_dict(data)

    def test_pipe_table_with_change_column(self) -> None:
        text = """
        Portfolio holdings as of quarter end

        Ticker | Name | Weight | Change
        AMZN | Amazon | 8.2% | Added
        ICE | Intercontinental | 6.1% | Trimmed
        """
        rows = lm.parse_holdings_table_rows(text, self.master)
        tickers = {r["ticker"]: r["action"] for r in rows}
        self.assertIn("AMZN", tickers)
        self.assertEqual(tickers.get("AMZN"), "add")
        self.assertEqual(tickers.get("ICE"), "trim")

    def test_parenthetical_ticker_row(self) -> None:
        text = """
        Top ten holdings

        (GOOGL) Alphabet Inc 9.0% New
        (BN) Brookfield 7.5% Hold
        """
        rows = lm.parse_holdings_table_rows(text, self.master)
        actions = {r["ticker"]: r["action"] for r in rows}
        self.assertIn("GOOGL", actions)
        self.assertEqual(actions["GOOGL"], "new")


if __name__ == "__main__":
    unittest.main()
