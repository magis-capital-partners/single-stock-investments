#!/usr/bin/env python3
"""Unit tests for insights event auto-triage."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from event_triage import cross_source_dedupe, load_rules, triage_event, triage_events  # noqa: E402

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
            "event_type": "context",
            "impact_axis": "growth",
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
