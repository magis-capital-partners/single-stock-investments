#!/usr/bin/env python3
"""Tests for Consensus sibling-fund collapse."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_insights import _collapse_consensus_rows, build_consensus  # noqa: E402
from fund_families import consensus_vote_key, family_id_for_fund  # noqa: E402


class TestFundFamilies(unittest.TestCase):
    def test_ancora_family(self):
        self.assertEqual(family_id_for_fund("ancora-bellator"), "ancora")
        self.assertEqual(family_id_for_fund("ancora-catalyst"), "ancora")
        self.assertEqual(consensus_vote_key("ancora-merlin", "Ancora Merlin"), "Ancora")
        self.assertEqual(consensus_vote_key("incline-global", "Incline Global"), "Incline Global")


class TestConsensusCollapse(unittest.TestCase):
    def test_collapse_identical_ancora_snippets(self):
        snippet = "relationship with Progressive Insurance at the end of last year."
        rows = [
            {
                "ticker": "CPRT",
                "fund": "Ancora Bellator",
                "fund_id": "ancora-bellator",
                "family_id": "ancora",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": snippet,
            },
            {
                "ticker": "CPRT",
                "fund": "Ancora Catalyst",
                "fund_id": "ancora-catalyst",
                "family_id": "ancora",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": snippet,
            },
            {
                "ticker": "CPRT",
                "fund": "Ancora Merlin",
                "fund_id": "ancora-merlin",
                "family_id": "ancora",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": snippet,
            },
            {
                "ticker": "CPRT",
                "fund": "Incline Global",
                "fund_id": "incline-global",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": "sold numerous positions including Copart",
            },
        ]
        out = _collapse_consensus_rows(rows)
        self.assertEqual(len(out), 2)
        ancora = next(r for r in out if (r.get("family_id") == "ancora" or "Ancora" in (r.get("fund") or "")))
        self.assertIn("3 strategies", ancora["fund"])
        self.assertEqual(len(ancora.get("sibling_funds") or []), 2)

    def test_build_consensus_family_vote(self):
        letters = [
            {
                "fund": "Ancora Bellator",
                "fund_id": "ancora-bellator",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [
                    {"ticker": "CPRT", "action": "discussed", "commentary": "same text about Copart"}
                ],
            },
            {
                "fund": "Ancora Catalyst",
                "fund_id": "ancora-catalyst",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [
                    {"ticker": "CPRT", "action": "discussed", "commentary": "same text about Copart"}
                ],
            },
            {
                "fund": "Incline Global",
                "fund_id": "incline-global",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [
                    {"ticker": "CPRT", "action": "discussed", "commentary": "other view"}
                ],
            },
        ]
        cons = build_consensus(letters, {"CPRT"}, {"CPRT": "Copart"})
        rows = cons["by_ticker"]["CPRT"]
        self.assertEqual(len(rows), 2)
        q = cons["by_quarter"]["2026Q1"]["most_discussed"][0]
        self.assertEqual(q["fund_count"], 2)
        self.assertIn("Ancora", q["funds"])


if __name__ == "__main__":
    unittest.main()
