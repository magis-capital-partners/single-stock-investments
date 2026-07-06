#!/usr/bin/env python3
"""Tests for letter date/quarter sanity in fund_registry."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from fund_registry import parse_letter_date, parse_quarter_from_stem, resolve_quarter, sanity_year  # noqa: E402


class FundRegistryDateTests(unittest.TestCase):
    def test_sanity_year_rejects_future(self) -> None:
        self.assertIsNone(sanity_year(2031, today=date(2026, 7, 5)))

    def test_indaba_2011_stem(self) -> None:
        stem = "Indaba Capital Quarterly Letter to Investors December 31 2011"
        iso, source = parse_letter_date(stem, None, "2011Q4")
        self.assertEqual(iso, "2011-12-31")
        self.assertIn(source, ("filename", "content", "quarter"))

    def test_parse_letter_date_rejects_insane_quarter_hint(self) -> None:
        stem = "Indaba Capital Quarterly Letter to Investors December 31 2011"
        iso, source = parse_letter_date(stem, None, "2031Q4")
        self.assertIsNone(iso)
        self.assertEqual(source, "none")

    def test_resolve_quarter_prefers_folder(self) -> None:
        path = Path("_system/reference/superinvestor-letters/2011Q4/Indaba Capital Quarterly Letter to Investors December 31 2011.txt")
        q = resolve_quarter(path, path.stem, "2031-12-31", "filename")
        self.assertEqual(q, "2011Q4")

    def test_stem_quarter_rejects_insane_year(self) -> None:
        self.assertIsNone(parse_quarter_from_stem("something 4Q 2031"))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
