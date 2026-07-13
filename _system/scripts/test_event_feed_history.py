#!/usr/bin/env python3
"""Regression tests for retained event history and scope metadata."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_insights import _retained_event_history  # noqa: E402


class EventFeedHistoryTests(unittest.TestCase):
    def test_retention_includes_upcoming_and_older_years(self) -> None:
        events = [
            {
                "id": "scheduled", "event_kind": "scheduled", "observed_at": "2026-08-01",
                "decision_priority": 50, "feed_eligible": True,
            },
            {
                "id": "current", "event_kind": "observed", "observed_at": "2026-07-01",
                "decision_priority": 90, "feed_eligible": True,
            },
            {
                "id": "historic", "event_kind": "observed", "observed_at": "2022-01-01",
                "decision_priority": 35, "feed_eligible": True,
            },
            {
                "id": "noise", "event_kind": "observed", "observed_at": "2021-01-01",
                "decision_priority": 5, "feed_eligible": False,
            },
        ]
        retained = _retained_event_history(events, max_events=20)
        ids = {event["id"] for event in retained}
        self.assertEqual(ids, {"scheduled", "current", "historic", "noise"})

    def test_retention_deduplicates_by_id(self) -> None:
        event = {
            "id": "same", "event_kind": "observed", "observed_at": "2026-07-01",
            "decision_priority": 90, "feed_eligible": True,
        }
        retained = _retained_event_history([event, dict(event)], max_events=20)
        self.assertEqual([row["id"] for row in retained], ["same"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
