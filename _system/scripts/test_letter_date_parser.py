#!/usr/bin/env python3
"""Unit tests for letter_date_parser gold corpus and edge cases."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from letter_date_parser import pick_letter_date, sanity_year  # noqa: E402

GOLD_PATH = Path(__file__).resolve().parent / "_eval" / "letter_date_gold.jsonl"


class LetterDateParserTests(unittest.TestCase):
    def test_gold_corpus(self) -> None:
        self.assertTrue(GOLD_PATH.exists(), f"missing {GOLD_PATH}")
        rows = [json.loads(line) for line in GOLD_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            iso, source, confidence = pick_letter_date(row["stem"], None, row.get("folder_q"))
            self.assertEqual(iso, row["expect_date"], f"{row['stem']}: got {iso} via {source}")
            if row.get("expect_source"):
                self.assertEqual(source, row["expect_source"], row["stem"])
            self.assertGreaterEqual(confidence, 40, row["stem"])

    def test_no_future_year_from_day_digits(self) -> None:
        iso, source, _ = pick_letter_date(
            "Monness Crespi Hardt Idea Dinner -- March 27 2023",
            None,
            "2023Q1",
        )
        self.assertEqual(iso, "2023-03-27")
        self.assertNotEqual(iso[:4], "2027")

    def test_sanity_year_caps_at_next_year(self) -> None:
        self.assertIsNone(sanity_year(2031, today=date(2026, 7, 7)))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
