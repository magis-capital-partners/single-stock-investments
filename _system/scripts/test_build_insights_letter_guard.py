#!/usr/bin/env python3
"""Tests for build_insights letter corpus preserve guard."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_insights as bi  # noqa: E402


class BuildInsightsLetterGuardTests(unittest.TestCase):
    def test_preserves_when_vault_below_floor(self) -> None:
        prior = {"letter_count": 19359, "letter_index": [{}] * 19359}
        preserve, reason = bi.should_preserve_letter_corpus(prior, vault_count=2500)
        self.assertTrue(preserve)
        self.assertIn("below floor", reason)

    def test_preserves_verified_classified_corpus_when_vault_is_empty(self) -> None:
        prior = {
            "classification_policy_version": 5,
            "letter_count": 12678,
            "letter_index": [{}] * 12678,
        }
        preserve, _ = bi.should_preserve_letter_corpus(prior, vault_count=0)
        self.assertTrue(preserve)

    def test_preserves_on_regression(self) -> None:
        prior = {"letter_count": 19359, "letter_index": [{}] * 19359}
        preserve, _ = bi.should_preserve_letter_corpus(prior, vault_count=16000)
        self.assertTrue(preserve)

    def test_allows_fresh_vault(self) -> None:
        prior = {"letter_count": 19359, "letter_index": [{}] * 19359}
        preserve, reason = bi.should_preserve_letter_corpus(prior, vault_count=19359)
        self.assertFalse(preserve)
        self.assertIn("current", reason)

    def test_skips_preserve_without_prior_corpus(self) -> None:
        preserve, _ = bi.should_preserve_letter_corpus(None, vault_count=100)
        self.assertFalse(preserve)

    def test_classified_marker_does_not_replace_with_incomplete_vault(self) -> None:
        self.assertFalse(
            bi.can_replace_preserved_letter_corpus(
                {"classification_policy_version": 5}, vault_count=0
            )
        )

    def test_complete_classified_vault_can_replace_preserved_corpus(self) -> None:
        self.assertTrue(
            bi.can_replace_preserved_letter_corpus(
                {"classification_policy_version": 5}, vault_count=bi.MIN_CLASSIFIED_LETTER_CORPUS
            )
        )

    def test_preserved_payload_keeps_classification_policy(self) -> None:
        preserved = bi.preserved_letter_payload_fields(
            {"classification_policy_version": 5, "letter_count": 19359}
        )
        self.assertEqual(preserved["classification_policy_version"], 5)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
