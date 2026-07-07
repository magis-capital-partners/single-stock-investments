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


if __name__ == "__main__":
    raise SystemExit(unittest.main())
