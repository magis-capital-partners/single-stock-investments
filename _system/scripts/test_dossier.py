#!/usr/bin/env python3
"""Tests for the dossier merge logic in build_dashboard_data.build_dossier_view."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_dashboard_data import (
    DOSSIER_DELTA_MIN_SCORE,
    build_dossier_view,
    coverage_gap_reasons,
    essential_needs_work_reasons,
)


def recent_date(days_ago: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()


def agent_dossier(as_of: str | None = None) -> dict:
    return {
        "ticker": "TEST",
        "as_of": as_of or recent_date(10),
        "timeline": [
            {
                "date": "2024-05-01",
                "type": "capital_allocation",
                "label": "Announced $2B buyback replacing dividend growth plan",
                "evidence_url": "https://example.com/8k",
            },
            {
                "date": "2023-11-15",
                "type": "management_change",
                "label": "CFO retired; insider promoted",
            },
        ],
        "industry": {
            "structure": "Three-player oligopoly with regulated pricing.",
            "share_shift": "Leader gaining share from regional players.",
            "trend": "Electronic trading displacing voice brokerage.",
            "peers": ["PEER1", "PEER2"],
        },
    }


class DossierViewTests(unittest.TestCase):
    def test_none_when_no_dossier_and_no_events(self):
        self.assertIsNone(build_dossier_view(None, []))

    def test_agent_timeline_preserved_and_sorted(self):
        view = build_dossier_view(agent_dossier(), [])
        self.assertIsNotNone(view)
        self.assertTrue(view["has_agent_dossier"])
        self.assertEqual(view["auto_added"], 0)
        dates = [e["date"] for e in view["timeline"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(view["timeline"][0]["source"], "dossier")
        self.assertEqual(view["industry"]["peers"], ["PEER1", "PEER2"])

    def test_high_score_events_appended_as_auto(self):
        events = [
            {
                "observed_at": recent_date(3),
                "score": DOSSIER_DELTA_MIN_SCORE + 5,
                "summary": "Regulator approved the merger with conditions",
                "event_type": "regulatory",
                "evidence_url": "https://example.com/news",
            },
            {
                "observed_at": recent_date(4),
                "score": DOSSIER_DELTA_MIN_SCORE - 20,
                "summary": "Routine conference appearance",
            },
        ]
        view = build_dossier_view(agent_dossier(), events)
        self.assertEqual(view["auto_added"], 1)
        auto = [e for e in view["timeline"] if e["source"] == "auto"]
        self.assertEqual(len(auto), 1)
        self.assertIn("merger", auto[0]["label"])
        self.assertEqual(auto[0]["type"], "regulatory")

    def test_duplicate_events_not_double_added(self):
        events = [
            {
                "observed_at": "2024-05-01",
                "score": 90,
                "summary": "Announced $2B buyback replacing dividend growth plan",
            }
        ]
        view = build_dossier_view(agent_dossier(), events)
        self.assertEqual(view["auto_added"], 0)
        self.assertEqual(len([e for e in view["timeline"] if e["date"] == "2024-05-01"]), 1)

    def test_events_only_view_without_agent_dossier(self):
        events = [
            {
                "observed_at": recent_date(2),
                "score": 85,
                "summary": "Activist disclosed a 6% stake",
                "event_type": "ownership",
            }
        ]
        view = build_dossier_view(None, events)
        self.assertIsNotNone(view)
        self.assertFalse(view["has_agent_dossier"])
        self.assertTrue(view["stale"])
        self.assertEqual(view["timeline"][0]["source"], "auto")
        self.assertIsNone(view["industry"])

    def test_staleness_flag(self):
        fresh = build_dossier_view(agent_dossier(recent_date(30)), [])
        self.assertFalse(fresh["stale"])
        old = build_dossier_view(agent_dossier(recent_date(300)), [])
        self.assertTrue(old["stale"])


class NeedsWorkReasonTests(unittest.TestCase):
    def base_row(self) -> dict:
        return {
            "in_holdings": True,
            "essential_insights": {
                "bullets": [{"evidence_url": "https://example.com"}],
                "freshness_days": 5,
                "source_mix": ["third_party"],
                "ticker_specific": True,
            },
            "classification": {"analysis_as_of": recent_date(5)},
        }

    def test_missing_dossier_not_in_attention(self):
        row = self.base_row()
        row["dossier"] = None
        self.assertNotIn("no dossier", essential_needs_work_reasons(row))
        self.assertIn("no dossier", coverage_gap_reasons(row))

    def test_stale_dossier_in_coverage_only(self):
        row = self.base_row()
        row["dossier"] = {"has_agent_dossier": True, "stale": True}
        self.assertNotIn("stale dossier", essential_needs_work_reasons(row))
        self.assertIn("stale dossier", coverage_gap_reasons(row))

    def test_fresh_dossier_not_in_coverage(self):
        row = self.base_row()
        row["dossier"] = {"has_agent_dossier": True, "stale": False}
        self.assertNotIn("no dossier", coverage_gap_reasons(row))
        self.assertNotIn("stale dossier", coverage_gap_reasons(row))

    def test_watchlist_not_flagged(self):
        row = self.base_row()
        row["in_holdings"] = False
        row["dossier"] = None
        self.assertEqual(essential_needs_work_reasons(row), [])
        self.assertEqual(coverage_gap_reasons(row), [])

    def test_no_ticker_coverage_is_attention(self):
        row = self.base_row()
        row["essential_insights"]["ticker_specific"] = False
        self.assertIn("no ticker coverage", essential_needs_work_reasons(row))

    def test_stale_valuation_180d(self):
        row = self.base_row()
        row["classification"]["analysis_as_of"] = recent_date(100)
        self.assertNotIn("stale valuation", essential_needs_work_reasons(row))
        row["classification"]["analysis_as_of"] = recent_date(200)
        self.assertIn("stale valuation", essential_needs_work_reasons(row))

    def test_third_party_in_coverage_only(self):
        row = self.base_row()
        row["essential_insights"]["source_mix"] = ["insider"]
        row["dossier"] = {"has_agent_dossier": True, "stale": False}
        self.assertNotIn("no third-party check", essential_needs_work_reasons(row))
        self.assertIn("no third-party check", coverage_gap_reasons(row))


if __name__ == "__main__":
    unittest.main()
