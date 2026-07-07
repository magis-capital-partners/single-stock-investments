#!/usr/bin/env python3
"""Tests for validate_dashboard_data letter drive link checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import validate_dashboard_data as validator  # noqa: E402


class LetterDriveLinksDenominatorTests(unittest.TestCase):
    def test_uses_full_index_when_corpus_not_preserved(self) -> None:
        compare_len = validator.letter_drive_links_denominator(
            letter_index_len=19359,
            links_letter_count=2529,
            corpus_preserved=False,
        )
        self.assertEqual(compare_len, 19359)

    def test_uses_vault_subset_when_corpus_preserved(self) -> None:
        compare_len = validator.letter_drive_links_denominator(
            letter_index_len=19359,
            links_letter_count=2529,
            corpus_preserved=True,
        )
        self.assertEqual(compare_len, 2529)

    def test_ci_preserve_scenario_passes_ratio(self) -> None:
        matched = 2528
        compare_len = validator.letter_drive_links_denominator(
            letter_index_len=19359,
            links_letter_count=2529,
            corpus_preserved=True,
        )
        ratio = matched / compare_len
        self.assertGreaterEqual(ratio, validator.LETTER_DRIVE_LINKS_MIN_RATIO)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
