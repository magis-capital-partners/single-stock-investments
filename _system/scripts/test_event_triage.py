#!/usr/bin/env python3
"""Unit tests for insights event auto-triage."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from event_triage import (  # noqa: E402
    cross_source_dedupe,
    enrich_decision_fields,
    load_rules,
    triage_event,
    triage_events,
)

GOLDEN = ROOT / "_system" / "scripts" / "fixtures" / "event_triage_golden.jsonl"


class EventTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_rules()

    def _triage(self, case: dict) -> dict:
        event = {k: v for k, v in case.items() if not k.startswith("expected_")}
        return triage_event(event, rules=self.rules, activist_tickers=set())

    def test_golden_cases(self) -> None:
        if not GOLDEN.exists():
            self.skipTest("golden fixture missing")
        for line in GOLDEN.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            result = self._triage(case)
            self.assertEqual(
                result.get("tier"),
                case["expected_tier"],
                msg=f"{case.get('id')}: tier expected {case['expected_tier']}, got {result.get('tier')}",
            )
            self.assertEqual(
                result.get("triage_verdict"),
                case["expected_verdict"],
                msg=f"{case.get('id')}: verdict expected {case['expected_verdict']}, got {result.get('triage_verdict')}",
            )
            if "expected_feed_eligible" in case:
                self.assertEqual(result.get("feed_eligible"), case["expected_feed_eligible"])

    def test_cross_source_dedupe_marks_loser(self) -> None:
        winner = {
            "id": "win",
            "source": "kpi_trend",
            "event_type": "inflection",
            "impact_axis": "growth",
            "title": "Margin inflection confirmed",
            "summary": "Operating margin inflection confirmed by new evidence",
            "ticker": "ICE",
            "observed_at": "2026-06-01",
            "trend_signal_tier": "confirmed",
            "confidence": "high",
            "in_our_book": True,
            "portfolio_relevance": 1.0,
            "freshness_days": 10,
        }
        loser = {
            "id": "lose",
            "source": "news",
            "event_type": "inflection",
            "impact_axis": "growth",
            "title": "Margin inflection confirmed",
            "summary": "Operating margin inflection confirmed by new evidence",
            "ticker": "ICE",
            "observed_at": "2026-06-02",
            "confidence": "med",
            "in_our_book": True,
            "portfolio_relevance": 1.0,
            "freshness_days": 10,
        }
        merged = cross_source_dedupe([winner, loser], rules=self.rules)
        triaged = [triage_event(e, rules=self.rules, activist_tickers=set()) for e in merged]
        superseded = [e for e in triaged if e.get("superseded_by")]
        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded[0]["tier"], "noise")
        self.assertFalse(superseded[0]["feed_eligible"])
        winner_row = next(e for e in merged if not e.get("superseded_by"))
        self.assertEqual(winner_row["corroboration_count"], 2)

    def test_distinct_same_axis_events_are_preserved(self) -> None:
        base = {
            "ticker": "ICE",
            "impact_axis": "fundamentals",
            "observed_at": "2026-06-01",
            "confidence": "high",
            "in_our_book": True,
            "portfolio_relevance": 1.0,
            "freshness_days": 10,
        }
        rows = cross_source_dedupe(
            [
                {**base, "id": "revenue", "source": "filing", "event_type": "filing_metric", "title": "Revenue up 15%"},
                {**base, "id": "margin", "source": "kpi_trend", "event_type": "inflection", "title": "Margin inflection confirmed"},
            ],
            rules=self.rules,
        )
        self.assertEqual(len(rows), 2)
        self.assertFalse(any(row.get("superseded_by") for row in rows))

    def test_routine_governance_watch_is_context(self) -> None:
        result = self._triage(
            {
                "id": "routine-governance", "source": "kpi_trend", "event_type": "leadership_risk",
                "impact_axis": "governance", "title": "Leadership / governance on watch",
                "summary": "Two executive sales in 120d", "ticker": "ICE", "direction": "neutral",
                "confidence": "med", "freshness_days": 1, "in_our_book": True,
                "portfolio_relevance": 1.0,
            }
        )
        self.assertEqual(result["tier"], "context")
        self.assertEqual(result["triage_verdict"], "auto_context")

    def test_entity_mismatch_is_noise(self) -> None:
        result = self._triage(
            {
                "id": "bad-match", "source": "third_party", "event_type": "context",
                "impact_axis": "variant_view", "title": "Unrelated issuer research", "ticker": "ICE",
                "entity_verified": False, "confidence": "med", "freshness_days": 1,
                "in_our_book": True, "portfolio_relevance": 1.0,
            }
        )
        self.assertEqual(result["tier"], "noise")
        self.assertFalse(result["feed_eligible"])

    def test_scheduled_neutral_event_is_context(self) -> None:
        result = self._triage(
            {
                "id": "upcoming", "source": "earnings", "event_type": "upcoming_earnings",
                "impact_axis": "fundamentals", "title": "Upcoming earnings", "ticker": "ICE",
                "event_kind": "scheduled", "direction": "neutral", "confidence": "high",
                "freshness_days": -10, "in_our_book": True, "portfolio_relevance": 1.0,
            }
        )
        self.assertEqual(result["tier"], "context")
        self.assertTrue(result["feed_eligible"])

    def test_emerging_regime_shift_stays_context(self) -> None:
        result = self._triage(
            {
                "id": "emerging-regime", "source": "kpi_trend", "event_type": "regime_shift",
                "impact_axis": "fundamentals", "title": "Growth regime strengthening", "ticker": "ICE",
                "trend_signal_tier": "emerging", "direction": "bullish", "confidence": "high",
                "freshness_days": 2, "in_our_book": True, "portfolio_relevance": 1.0,
            }
        )
        self.assertEqual(result["tier"], "context")

    def test_decision_fields_explain_priority(self) -> None:
        event = {
            "id": "decision", "source": "filing", "source_label": "Filing",
            "event_type": "filing_metric", "impact_axis": "fundamentals",
            "title": "Revenue up 15%", "summary": "Revenue moved versus the prior period.",
            "ticker": "ICE", "direction": "bullish", "materiality": 80,
            "evidence_url": "https://example.com/filing",
        }
        enriched = enrich_decision_fields([event])[0]
        self.assertGreater(enriched["decision_priority"], 0)
        self.assertEqual(enriched["evidence_status"], "linked")
        self.assertTrue(enriched["why_it_matters"])
        self.assertTrue(enriched["recommended_follow_up"])

    def test_triage_summary_counts(self) -> None:
        events = []
        for line in GOLDEN.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        triaged, summary = triage_events(events, activist_tickers=set())
        self.assertGreater(summary["signal"], 0)
        self.assertGreaterEqual(len(triaged), len(events))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
