#!/usr/bin/env python3
"""Unit tests for letter_drive_links validation helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import validate_dashboard_data as validator  # noqa: E402


class LetterDriveLinksValidationTests(unittest.TestCase):
    def test_no_issue_when_insights_ratio_meets_floor(self):
        self.assertIsNone(
            validator.letter_drive_links_issue(
                matched=19166,
                letter_index_len=19359,
                links_letter_count=19359,
                corpus_preserved=False,
            )
        )

    def test_warn_when_links_cover_smaller_committed_corpus(self):
        issue = validator.letter_drive_links_issue(
            matched=2528,
            letter_index_len=19359,
            links_letter_count=2529,
            corpus_preserved=False,
        )
        self.assertIsNotNone(issue)
        severity, msg = issue
        self.assertEqual(severity, "warn")
        self.assertIn("links current for 2529 letters", msg)

    def test_darwin_fast_vault_subset_link_mismatch_stays_warn(self):
        """Deploy Dashboard at c9d24d3cd failed validate with ERROR; must stay WARN."""
        issue = validator.letter_drive_links_issue(
            matched=2528,
            letter_index_len=19359,
            links_letter_count=2529,
            corpus_preserved=False,
        )
        self.assertIsNotNone(issue)
        severity, msg = issue
        self.assertEqual(severity, "warn")
        self.assertNotEqual(severity, "error")
        self.assertIn("13.1%", msg)

    def test_no_issue_when_preserved_corpus_matches_vault_subset(self):
        self.assertIsNone(
            validator.letter_drive_links_issue(
                matched=2528,
                letter_index_len=19359,
                links_letter_count=2529,
                corpus_preserved=True,
            )
        )

    def test_warn_when_preserved_corpus_and_vault_links_stale(self):
        issue = validator.letter_drive_links_issue(
            matched=100,
            letter_index_len=19359,
            links_letter_count=2529,
            corpus_preserved=True,
        )
        self.assertIsNotNone(issue)
        severity, msg = issue
        self.assertEqual(severity, "warn")
        self.assertIn("vault subset", msg)

    def test_error_when_links_and_insights_both_stale(self):
        issue = validator.letter_drive_links_issue(
            matched=100,
            letter_index_len=19359,
            links_letter_count=19359,
            corpus_preserved=False,
        )
        self.assertIsNotNone(issue)
        severity, _msg = issue
        self.assertEqual(severity, "error")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
