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
    next_calendar_for_indices,
    parse_effective_from_title,
    report_tier_boost,
    scorecard_russell,
)
from datetime import date  # noqa: E402
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

    def test_inside_band_is_banding_hold(self):
        # 1% above breakpoint → inside ±2.5% band
        mi = {"ticker": "Z", "market_cap_usd": 5.7e9 * 1.01, "missing": []}
        r1 = scorecard_russell(
            "russell_1000",
            {"band_pct": 0.025, "band_usd": [2.7e9, 9.6e9]},
            mi,
            False,
            {},
            breakpoint_mcap=5.7e9,
            breakpoint_source="config",
            band_usd=[2.7e9, 9.6e9],
        )
        self.assertEqual(r1["status"], "banding_hold")
        self.assertEqual(r1.get("recon_status"), "banding_hold")

    def test_outside_band_is_likely_add(self):
        mi = {"ticker": "Z2", "market_cap_usd": 5.7e9 * 1.08, "missing": []}
        r1 = scorecard_russell(
            "russell_1000",
            {"band_pct": 0.025, "band_usd": [2.7e9, 9.6e9]},
            mi,
            False,
            {},
            breakpoint_mcap=5.7e9,
            breakpoint_source="config",
            band_usd=[2.7e9, 9.6e9],
        )
        self.assertEqual(r1["status"], "inclusion_candidate")
        self.assertEqual(r1.get("recon_status"), "likely_add")


class TestReconWatchBoost(unittest.TestCase):
    def test_provisional_beats_rumor(self):
        boost_p, tier_p = report_tier_boost(
            [{"confidence": "provisional", "index": "russell_1000", "action": "add"}]
        )
        boost_r, tier_r = report_tier_boost(
            [{"confidence": "rumor", "index": "russell_1000", "action": "add"}]
        )
        self.assertEqual(tier_p, "provisional")
        self.assertEqual(tier_r, "rumor")
        self.assertGreater(boost_p, boost_r)
        self.assertGreater(boost_p, 0)

    # The June 2026 APLD Russell 1000 add (effective 2026-06-26) kept adding its
    # 0.25 "announced" boost months after the recon had completed.
    APLD_ROW = {
        "ticker": "APLD",
        "index": "russell_1000",
        "action": "add",
        "confidence": "announced",
        "as_of": "2026-06-06",
        "effective": "2026-06-26",
    }

    def test_boost_live_through_effective_plus_grace(self):
        boost, tier = report_tier_boost([self.APLD_ROW], date(2026, 6, 20))
        self.assertEqual((boost, tier), (0.25, "announced"))
        # exactly 14 days after effective is still live
        boost, tier = report_tier_boost([self.APLD_ROW], date(2026, 7, 10))
        self.assertEqual((boost, tier), (0.25, "announced"))

    def test_boost_expires_after_grace(self):
        boost, tier = report_tier_boost([self.APLD_ROW], date(2026, 7, 11))
        self.assertEqual(boost, 0.0)
        self.assertIsNone(tier)
        boost, tier = report_tier_boost([self.APLD_ROW], date(2026, 10, 11))
        self.assertEqual((boost, tier), (0.0, None))

    def test_expired_row_does_not_shadow_live_lower_tier(self):
        live_rumor = {"confidence": "rumor", "index": "sp400", "action": "add", "effective": "2026-12-19"}
        boost, tier = report_tier_boost([self.APLD_ROW, live_rumor], date(2026, 10, 11))
        self.assertEqual(tier, "rumor")
        self.assertAlmostEqual(boost, 0.08)

    def test_row_without_effective_or_today_never_expires(self):
        undated = {"confidence": "provisional", "index": "russell_2000", "action": "add"}
        self.assertEqual(report_tier_boost([undated], date(2030, 1, 1))[1], "provisional")
        # legacy call without today: everything counts
        self.assertEqual(report_tier_boost([self.APLD_ROW])[1], "announced")


class TestWatchIndexCalendar(unittest.TestCase):
    """The calendar event shown must belong to the watch scorecard's index."""

    CAL = {
        "events": [
            {"id": "russell_annual_2026", "indices": ["russell_1000", "russell_2000"], "effective": "2026-06-26"},
            {"id": "russell_semi_2026", "indices": ["russell_1000", "russell_2000"], "effective": "2026-12-11"},
            {"id": "sp_share_update_2026q4", "indices": ["sp500", "sp400", "sp600"], "effective": "2026-12-19"},
            {"id": "msci_nov_2026", "indices": ["msci_usa", "msci_acwi"], "effective": "2026-11-30"},
        ]
    }
    ALL_IDS = ["sp500", "sp400", "sp600", "russell_1000", "russell_2000", "msci_usa", "msci_acwi"]
    TODAY = date(2026, 10, 9)

    def test_no_preference_keeps_soonest_across_all(self):
        ev = next_calendar_for_indices(self.CAL, self.ALL_IDS, self.TODAY)
        self.assertEqual(ev["id"], "msci_nov_2026")
        self.assertEqual(ev["days_out"], 52)

    def test_sp400_candidate_sees_sp_share_update(self):
        # APLD: S&P 400 inclusion_candidate must not display the MSCI review
        ev = next_calendar_for_indices(self.CAL, self.ALL_IDS, self.TODAY, prefer_indices=["sp400"])
        self.assertEqual(ev["id"], "sp_share_update_2026q4")
        self.assertEqual(ev["days_out"], 71)

    def test_russell_candidate_sees_russell_semi(self):
        # LB: Russell 1000 inclusion_candidate
        ev = next_calendar_for_indices(self.CAL, self.ALL_IDS, self.TODAY, prefer_indices=["russell_1000"])
        self.assertEqual(ev["id"], "russell_semi_2026")

    def test_preferred_index_without_event_falls_back(self):
        ev = next_calendar_for_indices(self.CAL, self.ALL_IDS, self.TODAY, prefer_indices=["djia"])
        self.assertEqual(ev["id"], "msci_nov_2026")

    def test_empty_preference_is_legacy(self):
        a = next_calendar_for_indices(self.CAL, self.ALL_IDS, self.TODAY, prefer_indices=None)
        b = next_calendar_for_indices(self.CAL, self.ALL_IDS, self.TODAY, prefer_indices=[])
        self.assertEqual(a["id"], b["id"], "msci_nov_2026")


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
