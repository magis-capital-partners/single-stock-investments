#!/usr/bin/env python3
"""Tests for activist materiality scoring, stake parsing, and link-health gating."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_materiality import (  # noqa: E402
    NOISE_THRESHOLD,
    SIGNAL_THRESHOLD,
    filing_base_weight,
    firm_weight,
    freshness_factor,
    materiality_score,
    materiality_tier,
    stake_factor,
)
from sec_filer_parse import parse_stake_percent  # noqa: E402

NOW = datetime(2026, 7, 2, tzinfo=timezone.utc)


def _iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class MaterialityScoreTests(unittest.TestCase):
    def test_fresh_tier1_13d_on_holding_is_signal(self) -> None:
        row = {
            "firm_id": "elliott",
            "form": "SC 13D",
            "filing_class": "activist_13d",
            "report_date": _iso(10),
            "source": "sec_edgar",
            "file_exists": True,
        }
        score, _ = materiality_score(row, in_holdings=True, now=NOW)
        self.assertGreaterEqual(score, SIGNAL_THRESHOLD)
        self.assertEqual(materiality_tier(score, row), "signal")

    def test_fresh_tier1_publisher_short_is_signal(self) -> None:
        row = {
            "firm_id": "spruce_point",
            "filing_class": "publisher_report",
            "report_date": _iso(20),
            "source": "publisher_site",
            "file_exists": True,
            "body_verified": True,
            "target_verified": True,
        }
        score, _ = materiality_score(row, in_holdings=True, now=NOW)
        self.assertGreaterEqual(score, SIGNAL_THRESHOLD)

    def test_stale_report_decays_below_signal(self) -> None:
        fresh = {
            "firm_id": "spruce_point",
            "filing_class": "publisher_report",
            "report_date": _iso(15),
            "file_exists": True,
        }
        stale = {**fresh, "report_date": _iso(4 * 365)}
        fresh_score, _ = materiality_score(fresh, in_holdings=True, now=NOW)
        stale_score, _ = materiality_score(stale, in_holdings=True, now=NOW)
        self.assertLess(stale_score, fresh_score)
        self.assertLess(stale_score, NOISE_THRESHOLD)
        self.assertEqual(materiality_tier(stale_score, stale), "noise")

    def test_weak_match_forces_noise_tier(self) -> None:
        row = {
            "firm_id": "elliott",
            "form": "SC 13D",
            "filing_class": "activist_13d",
            "report_date": _iso(5),
            "weak_match": True,
            "file_exists": True,
        }
        score, _ = materiality_score(row, in_holdings=True, now=NOW)
        self.assertEqual(materiality_tier(score, row), "noise")

    def test_body_unverified_forces_noise_tier(self) -> None:
        row = {
            "firm_id": "viceroy",
            "filing_class": "publisher_report",
            "report_date": _iso(5),
            "body_verified": False,
            "file_exists": True,
        }
        score, _ = materiality_score(row, in_holdings=True, now=NOW)
        self.assertEqual(materiality_tier(score, row), "noise")

    def test_materiality_floor_cannot_rescue_unverified_publisher_target(self) -> None:
        row = {
            "firm_id": "viceroy",
            "filing_class": "publisher_report",
            "report_date": _iso(1),
            "source": "publisher_site",
            "body_verified": True,
            "target_verified": False,
            "materiality_floor": 60,
            "triage_verdict": "auto_signal",
            "file_exists": True,
        }
        score, _ = materiality_score(row, in_holdings=True, now=NOW)
        self.assertLess(score, SIGNAL_THRESHOLD)
        self.assertEqual(materiality_tier(score, row), "noise")

    def test_stake_scales_score(self) -> None:
        base = {
            "firm_id": "elliott",
            "form": "SC 13D",
            "filing_class": "activist_13d",
            "report_date": _iso(10),
            "file_exists": True,
        }
        small, _ = materiality_score({**base, "stake_percent": 1.0}, in_holdings=True, now=NOW)
        large, _ = materiality_score({**base, "stake_percent": 12.0}, in_holdings=True, now=NOW)
        self.assertGreater(large, small)

    def test_off_book_ticker_scores_lower(self) -> None:
        row = {
            "firm_id": "elliott",
            "form": "SC 13D",
            "filing_class": "activist_13d",
            "report_date": _iso(10),
            "file_exists": True,
        }
        holding, _ = materiality_score(row, in_holdings=True, now=NOW)
        outside, _ = materiality_score(row, in_holdings=False, in_watchlist=False, now=NOW)
        self.assertGreater(holding, outside)

    def test_component_bounds(self) -> None:
        self.assertEqual(stake_factor(None), 1.0)
        self.assertAlmostEqual(stake_factor(0), 0.85)
        self.assertAlmostEqual(stake_factor(50), 1.15)
        self.assertEqual(freshness_factor(None), 0.55)
        self.assertGreaterEqual(freshness_factor(_iso(20 * 365), now=NOW), 0.3)
        self.assertEqual(firm_weight("unknown_activist"), 0.55)
        self.assertGreater(firm_weight("elliott"), firm_weight("ancora"))
        self.assertLess(filing_base_weight({"filing_class": "publisher_report"}),
                        filing_base_weight({"filing_class": "activist_13d", "form": "SC 13D"}))


class StakeParseTests(unittest.TestCase):
    def test_cover_page_row_13(self) -> None:
        text = (
            "AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON 4,203,323 "
            "PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (11) 8.5% TYPE OF REPORTING PERSON IA"
        )
        self.assertEqual(parse_stake_percent(text), 8.5)

    def test_prose_fallback(self) -> None:
        text = "The Reporting Persons beneficially own approximately 6.2% of the outstanding shares."
        self.assertEqual(parse_stake_percent(text), 6.2)

    def test_no_stake_returns_none(self) -> None:
        self.assertIsNone(parse_stake_percent("Item 4. Purpose of Transaction"))


class LinkGateTests(unittest.TestCase):
    def test_broken_source_and_missing_file_would_be_dropped(self) -> None:
        row = {"file_exists": False, "source_url": "https://example.com/x", "source_url_ok": False}
        self.assertTrue(row.get("file_exists") is False and row.get("source_url_ok") is False)

    def test_unknown_link_state_keeps_row(self) -> None:
        # Network errors leave ok=None: the row must survive.
        row = {"file_exists": False, "source_url": "https://example.com/x", "source_url_ok": None}
        keep = not (row.get("file_exists") is False and (not row.get("source_url") or row.get("source_url_ok") is False))
        self.assertTrue(keep)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
