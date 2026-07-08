#!/usr/bin/env python3
"""Unit tests for theme proximity ticker tagging."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_superinvestor_insights import extract_themes, tickers_near_keyword  # noqa: E402


class ThemeExtractionTests(unittest.TestCase):
    def test_tickers_near_keyword(self):
        text = "We remain constructive on artificial intelligence. NVDA and AMD lead the GPU cycle."
        tickers = ["NVDA", "AMD", "JPM", "BAC"]
        near = tickers_near_keyword(text, "artificial intelligence", tickers)
        self.assertIn("NVDA", near)
        self.assertIn("AMD", near)
        self.assertNotIn("JPM", near)

    def test_extract_themes_differs_by_theme(self):
        text = (
            "Bank credit quality remains a focus; we like JPM and BAC. "
            "Separately, artificial intelligence demand supports NVDA."
        )
        tickers = ["JPM", "BAC", "NVDA", "AMD"]
        themes = extract_themes(text, tickers)
        by_name = {t["theme"]: t["tickers"] for t in themes}
        self.assertIn("Banking", by_name)
        self.assertIn("AI", by_name)
        banking = set(by_name["Banking"])
        ai = set(by_name["AI"])
        self.assertTrue(banking & {"JPM", "BAC"})
        self.assertTrue(ai & {"NVDA"})


if __name__ == "__main__":
    raise SystemExit(unittest.main())
