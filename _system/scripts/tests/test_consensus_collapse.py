#!/usr/bin/env python3
"""Tests for Consensus sibling-fund / identical-snippet collapse."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_insights import _collapse_consensus_rows, build_consensus  # noqa: E402
from fund_families import consensus_vote_key, family_id_for_fund  # noqa: E402

LONG = (
    "relationship with Progressive Insurance at the end of last year. "
    "This resulted in RBA taking the remaining salvage volumes from Copart over several months."
)


class TestFundFamilies(unittest.TestCase):
    def test_ancora_family(self):
        self.assertEqual(family_id_for_fund("ancora-bellator"), "ancora")
        self.assertEqual(consensus_vote_key("ancora-merlin", "Ancora Merlin", action="add"), "Ancora")
        self.assertIsNone(consensus_vote_key("ancora-merlin", "Ancora Merlin", action="discussed"))


class TestConsensusCollapse(unittest.TestCase):
    def test_collapse_identical_across_any_funds(self):
        rows = [
            {
                "ticker": "CPRT",
                "fund": "Ancora Bellator",
                "fund_id": "ancora-bellator",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": LONG,
            },
            {
                "ticker": "CPRT",
                "fund": "Ancora Catalyst",
                "fund_id": "ancora-catalyst",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": LONG,
            },
            {
                "ticker": "CPRT",
                "fund": "Ancora Merlin",
                "fund_id": "ancora-merlin",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": LONG,
            },
            {
                "ticker": "CPRT",
                "fund": "Incline Global",
                "fund_id": "incline-global",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "action": "discussed",
                "commentary": "sold numerous positions including Copart in the quarter.",
            },
        ]
        out = _collapse_consensus_rows(rows)
        self.assertEqual(len(out), 2)
        ancora = next(r for r in out if "Ancora" in (r.get("fund") or "") or r.get("family_id") == "ancora")
        self.assertIn("3 strategies", ancora["fund"])

    def test_discussed_does_not_inflate_fund_count(self):
        letters = [
            {
                "fund": "Ancora Bellator",
                "fund_id": "ancora-bellator",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [{"ticker": "CPRT", "action": "discussed", "commentary": LONG}],
            },
            {
                "fund": "Ancora Catalyst",
                "fund_id": "ancora-catalyst",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [{"ticker": "CPRT", "action": "discussed", "commentary": LONG}],
            },
            {
                "fund": "Incline Global",
                "fund_id": "incline-global",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [{"ticker": "CPRT", "action": "add", "commentary": "bought Copart this quarter after the pullback."}],
            },
        ]
        cons = build_consensus(letters, {"CPRT"}, {"CPRT": "Copart"})
        rows = cons["by_ticker"]["CPRT"]
        self.assertEqual(len(rows), 2)
        q = cons["by_quarter"]["2026Q1"]["most_discussed"][0]
        self.assertEqual(q["fund_count"], 1)
        self.assertEqual(q["sentiment"], "accumulating")
        self.assertGreaterEqual(q.get("mentioned_count", 0), 1)

    def test_prince_street_style_collapse(self):
        snippet = (
            "ZLAB remains a core holding across our Asia healthcare book with "
            "improving commercial execution in oncology."
        )
        letters = [
            {
                "fund": "Prince Street Digdec",
                "fund_id": "prince-street-digdec",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [{"ticker": "ZLAB", "action": "discussed", "commentary": snippet}],
            },
            {
                "fund": "Prince Street Long Short",
                "fund_id": "prince-street-long-short",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [{"ticker": "ZLAB", "action": "discussed", "commentary": snippet}],
            },
            {
                "fund": "Prince Street Opportunities",
                "fund_id": "prince-street-opportunities",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "positions": [{"ticker": "ZLAB", "action": "discussed", "commentary": snippet}],
            },
        ]
        cons = build_consensus(letters, {"ZLAB"}, {"ZLAB": "Zai Lab"})
        self.assertEqual(len(cons["by_ticker"]["ZLAB"]), 1)
        self.assertIn("3 strategies", cons["by_ticker"]["ZLAB"][0]["fund"])


if __name__ == "__main__":
    unittest.main()
