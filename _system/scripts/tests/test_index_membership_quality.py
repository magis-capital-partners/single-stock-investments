#!/usr/bin/env python3
"""Regression tests for Index Watch quality gates (2026-07-17)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_index_membership import (  # noqa: E402
    collapse_style_announcements,
    finalize_scorecard,
    is_quality_gated_news,
    parse_effective_from_title,
    scorecard_russell,
)
from index_event_extract import extract_index_events  # noqa: E402


class TestQualityGate(unittest.TestCase):
    def test_apld_clear_join_is_quality_gated(self):
        self.assertTrue(
            is_quality_gated_news(
                title="Applied Digital (APLD) Joins Russell 1000 As Its Market Profile Shifts",
                action="add",
                style_subset=False,
                index_id="russell_1000",
                current_memberships=set(),
            )
        )

    def test_kim_spotlight_not_quality_gated(self):
        self.assertFalse(
            is_quality_gated_news(
                title="Kimco Realty (NYSE:KIM) Joins Russell 1000 Indexes Spotlight - Kalkine",
                action="add",
                style_subset=False,
                index_id="russell_1000",
                current_memberships=set(),
            )
        )

    def test_soft_noise_not_quality_gated(self):
        self.assertFalse(
            is_quality_gated_news(
                title="Kraft Heinz (KHC) Joins The Russell 1000 Index And Draws Fresh Interest",
                action="add",
                style_subset=False,
                index_id="russell_1000",
                current_memberships={"russell_1000", "sp500"},
            )
        )

    def test_completed_recon_add_still_quality_gated_when_seeded(self):
        self.assertTrue(
            is_quality_gated_news(
                title="Applied Digital (APLD) Joins Russell 1000 As Its Market Profile Shifts",
                action="add",
                style_subset=False,
                index_id="russell_1000",
                current_memberships={"russell_1000", "russell_midcap"},
            )
        )

    def test_style_reclassify_never_quality_gated(self):
        self.assertFalse(
            is_quality_gated_news(
                title="What Copart (CPRT)'s Index Reclassification Means",
                action="reclassify",
                style_subset=True,
                index_id="russell_1000",
            )
        )

    def test_effective_from_title(self):
        self.assertEqual(
            parse_effective_from_title(
                "Flex Ltd. (FLEX) to Join S&P 500 Index on June 22 - Yahoo Finance",
                "2026-06-20",
            ),
            "2026-06-22",
        )


class TestStyleCollapse(unittest.TestCase):
    def test_collapse_same_ticker_style_notes(self):
        rows = [
            {
                "ticker": "EBAY",
                "index": "russell_midcap",
                "action": "reclassify",
                "announced": "2026-06-28",
                "style_subset": True,
                "title": "EBAY added to Russell Midcap Growth Benchmark",
            },
            {
                "ticker": "EBAY",
                "index": "russell_1000",
                "action": "reclassify",
                "announced": "2026-06-29",
                "style_subset": True,
                "title": "EBAY added to Russell 1000 Growth Benchmark - marketscreener",
            },
            {
                "ticker": "APLD",
                "index": "russell_1000",
                "action": "add",
                "announced": "2026-06-29",
                "style_subset": False,
                "title": "APLD Joins Russell 1000",
            },
        ]
        out = collapse_style_announcements(rows)
        style = [r for r in out if r.get("style_subset")]
        self.assertEqual(len(style), 1)
        self.assertEqual(style[0]["ticker"], "EBAY")
        self.assertIn("russell_midcap", style[0].get("related_indexes") or [])
        self.assertIn("russell_1000", style[0].get("related_indexes") or [])
        self.assertEqual(len([r for r in out if not r.get("style_subset")]), 1)


class TestRussellMutex(unittest.TestCase):
    def test_above_breakpoint_only_r1000(self):
        mi = {"ticker": "X", "market_cap_usd": 6.0e9, "missing": []}
        r1 = scorecard_russell(
            "russell_1000",
            {"band_usd": [2.7e9, 9.6e9]},
            mi,
            False,
            {},
            breakpoint_mcap=5.7e9,
            breakpoint_source="config",
            band_usd=[2.7e9, 9.6e9],
        )
        r2 = scorecard_russell(
            "russell_2000",
            {"band_usd": [2.7e9, 9.6e9]},
            mi,
            False,
            {},
            breakpoint_mcap=5.7e9,
            breakpoint_source="config",
            band_usd=[2.7e9, 9.6e9],
        )
        self.assertEqual(r1["status"], "inclusion_candidate")
        self.assertNotEqual(r2["status"], "inclusion_candidate")

    def test_below_breakpoint_only_r2000(self):
        mi = {"ticker": "Y", "market_cap_usd": 5.0e9, "missing": []}
        r1 = scorecard_russell(
            "russell_1000",
            {"band_usd": [2.7e9, 9.6e9]},
            mi,
            False,
            {},
            breakpoint_mcap=5.7e9,
            breakpoint_source="config",
            band_usd=[2.7e9, 9.6e9],
        )
        r2 = scorecard_russell(
            "russell_2000",
            {"band_usd": [2.7e9, 9.6e9]},
            mi,
            False,
            {},
            breakpoint_mcap=5.7e9,
            breakpoint_source="config",
            band_usd=[2.7e9, 9.6e9],
        )
        self.assertNotEqual(r1["status"], "inclusion_candidate")
        self.assertEqual(r2["status"], "inclusion_candidate")


class TestFloorNoCandidate(unittest.TestCase):
    def test_floor_only_never_candidate(self):
        checks = {
            "market_cap": {"pass": True, "value": 5.1e9, "threshold": 5e9},
            "exchange": {"pass": True, "value": "NASDAQ"},
        }
        sc = finalize_scorecard(
            "nasdaq_100",
            checks,
            False,
            0.49,
            [],
            floor_only=True,
        )
        self.assertEqual(sc["status"], "n_a")


class TestEbayStyleExtract(unittest.TestCase):
    def test_ebay_growth_is_style(self):
        evs = extract_index_events(
            "EBay Inc.(NasdaqGS: EBAY) added to Russell 1000 Growth Benchmark",
            candidate_tickers=["EBAY"],
        )
        self.assertTrue(evs)
        self.assertTrue(evs[0].get("style_subset"))
        self.assertEqual(evs[0].get("action"), "reclassify")


if __name__ == "__main__":
    unittest.main()
