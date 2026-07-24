#!/usr/bin/env python3
"""Regression tests for letter_index action buckets and eligibility."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_insights as bi  # noqa: E402


class LetterIndexActionTests(unittest.TestCase):
    def test_exit_not_duplicated_in_trims(self) -> None:
        letters = [
            {
                "fund_id": "hfa",
                "fund": "Hfa",
                "quarter": "2026Q2",
                "letter_date": "2026-06-17",
                "source_file": "_system/reference/superinvestor-letters/2026Q2/HFA-061726.txt",
                "tickers": ["MDB", "AMZN", "GOOGL"],
                "positions": [
                    {"ticker": "GOOGL", "action": "add"},
                    {"ticker": "AMZN", "action": "new"},
                    {"ticker": "MDB", "action": "exit"},
                ],
                "themes": [{"theme": "AI"}],
            }
        ]
        rows = bi.letter_index(letters, {"MDB", "AMZN", "GOOGL", "NVDA"})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["adds"], ["GOOGL", "AMZN"])
        self.assertEqual(row["trims"], [])
        self.assertEqual(row["exits"], ["MDB"])
        # UI concatenates trims+exits; must not double-count
        combined = row["trims"] + row["exits"]
        self.assertEqual(combined, ["MDB"])
        self.assertEqual(row["document_label"], "061726")

    def test_trim_and_exit_kept_distinct(self) -> None:
        letters = [
            {
                "fund_id": "demo",
                "fund": "Demo",
                "quarter": "2026Q1",
                "letter_date": "2026-03-31",
                "source_file": "demo/Demo-Letter.txt",
                "tickers": ["NVDA", "APLD"],
                "positions": [
                    {"ticker": "NVDA", "action": "trim"},
                    {"ticker": "APLD", "action": "exit"},
                    {"ticker": "NVDA", "action": "trim"},
                ],
                "themes": [],
            }
        ]
        row = bi.letter_index(letters, set())[0]
        self.assertEqual(row["trims"], ["NVDA"])
        self.assertEqual(row["exits"], ["APLD"])

    def test_conference_filename_ineligible_when_flag_missing(self) -> None:
        letter = {
            "fund_id": "sohn-investment-conference",
            "fund": "Sohn Investment Conference",
            "source_file": "_system/reference/superinvestor-letters/2026Q2/Sohn Investment Conference 2026 (1).txt",
        }
        self.assertFalse(bi.is_letter_eligible_for_index(letter))

    def test_explicit_ineligible_respected(self) -> None:
        letter = {
            "fund_id": "hfa",
            "fund": "Hfa",
            "letter_eligible": False,
            "document_type": "investor_letter",
            "source_file": "HFA-061726.txt",
        }
        self.assertFalse(bi.is_letter_eligible_for_index(letter))

    def test_investor_letter_eligible_by_document_type(self) -> None:
        letter = {
            "fund_id": "hfa",
            "fund": "Hfa",
            "document_type": "investor_letter",
            "source_file": "HFA-061726.txt",
        }
        self.assertTrue(bi.is_letter_eligible_for_index(letter))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
