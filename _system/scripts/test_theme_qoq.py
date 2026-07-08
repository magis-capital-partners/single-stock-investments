#!/usr/bin/env python3
"""Unit tests for theme QoQ aggregation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_insights import compute_theme_qoq_shifts, theme_qoq_by_quarter  # noqa: E402


class ThemeQoqTests(unittest.TestCase):
    def test_compute_shifts(self):
        current = [
            {"theme": "AI", "fund_count": 9, "bullish": 2, "bearish": 1, "top_tickers": ["NVDA"]},
            {"theme": "Rates", "fund_count": 5, "bullish": 0, "bearish": 1, "top_tickers": []},
        ]
        prior = [
            {"theme": "AI", "fund_count": 6, "bullish": 1, "bearish": 1, "top_tickers": ["NVDA"]},
            {"theme": "Energy", "fund_count": 4, "bullish": 0, "bearish": 0, "top_tickers": ["XOM"]},
        ]
        shifts = compute_theme_qoq_shifts(current, prior)
        by_theme = {s["theme"]: s for s in shifts}
        self.assertEqual(by_theme["AI"]["delta_funds"], 3)
        self.assertEqual(by_theme["Energy"]["delta_funds"], -4)
        self.assertEqual(by_theme["Rates"]["delta_funds"], 5)

    def test_by_quarter(self):
        theme_by_q = {
            "2026Q1": [{"theme": "AI", "fund_count": 4, "bullish": 0, "bearish": 0}],
            "2026Q2": [{"theme": "AI", "fund_count": 7, "bullish": 1, "bearish": 0}],
        }
        out = theme_qoq_by_quarter(theme_by_q)
        self.assertIn("2026Q2", out)
        self.assertEqual(out["2026Q2"]["prior_quarter"], "2026Q1")
        self.assertEqual(out["2026Q2"]["shifts"][0]["delta_funds"], 3)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
