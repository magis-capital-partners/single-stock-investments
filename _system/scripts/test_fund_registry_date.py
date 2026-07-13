#!/usr/bin/env python3
"""Tests for letter date/quarter sanity in fund_registry."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from fund_registry import (  # noqa: E402
    canonicalize_fund_identity,
    normalize_fund_key,
    parse_letter_date,
    parse_quarter_from_stem,
    resolve_quarter,
    sanity_year,
)


class FundRegistryDateTests(unittest.TestCase):
    def test_sanity_year_rejects_future(self) -> None:
        self.assertIsNone(sanity_year(2031, today=date(2026, 7, 5)))

    def test_indaba_2011_stem(self) -> None:
        stem = "Indaba Capital Quarterly Letter to Investors December 31 2011"
        iso, source = parse_letter_date(stem, None, "2011Q4")
        self.assertEqual(iso, "2011-12-31")
        self.assertIn(source, ("filename", "content", "quarter", "override"))

    def test_parse_letter_date_uses_filename_over_insane_quarter_hint(self) -> None:
        stem = "Indaba Capital Quarterly Letter to Investors December 31 2011"
        iso, source = parse_letter_date(stem, None, "2031Q4")
        self.assertEqual(iso, "2011-12-31")
        self.assertTrue(
            source.startswith("filename") or source in ("content", "override")
        )

    def test_parse_letter_date_monness_march_day_year(self) -> None:
        stem = "Monness Crespi Hardt Idea Dinner -- March 27 2023"
        iso, source = parse_letter_date(stem, None, "2023Q1")
        self.assertEqual(iso, "2023-03-27")
        self.assertNotEqual(iso[:4], "2027")

    def test_resolve_quarter_prefers_folder(self) -> None:
        path = Path("_system/reference/superinvestor-letters/2011Q4/Indaba Capital Quarterly Letter to Investors December 31 2011.txt")
        q = resolve_quarter(path, path.stem, "2031-12-31", "filename")
        self.assertEqual(q, "2011Q4")

    def test_stem_quarter_rejects_insane_year(self) -> None:
        self.assertIsNone(parse_quarter_from_stem("something 4Q 2031"))

    def test_normalize_fund_key_strips_compact_quarter(self) -> None:
        fund_id, display = normalize_fund_key("683Capital_Letter_2016Q2")
        self.assertEqual(fund_id, "683capital")
        self.assertEqual(display, "683capital")

    def test_canonicalize_legacy_suffix_quarter(self) -> None:
        self.assertEqual(
            canonicalize_fund_identity("683capital-2016q2", "683capital 2016q2"),
            ("683capital", "683capital"),
        )

    def test_canonicalize_legacy_prefix_quarter(self) -> None:
        self.assertEqual(
            canonicalize_fund_identity("2024q1-nishkama", "2024q1 Nishkama"),
            ("nishkama", "Nishkama"),
        )

    def test_canonicalize_quarter_attached_to_name(self) -> None:
        self.assertEqual(
            canonicalize_fund_identity("gator2012q4", "Gator2012q4"),
            ("gator", "Gator"),
        )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
