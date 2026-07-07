#!/usr/bin/env python3
"""Ensure dashboard_data.json keeps insights external to avoid GitHub size limits."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_dashboard_data import insights_external_ref  # noqa: E402

GITHUB_HARD_LIMIT = 100 * 1024 * 1024


class InsightsExternalRefTests(unittest.TestCase):
    def test_stub_is_small_and_marked_external(self) -> None:
        stub = insights_external_ref(
            {
                "generated_at": "2026-07-07T00:00:00Z",
                "record_count": 111296,
                "event_count": 400,
                "letter_count": 19359,
                "events": [{"id": "x"}],
                "fund_profiles": {"x": {"y": "z"}},
            }
        )
        encoded = json.dumps(stub)
        self.assertLess(len(encoded), 4096)
        self.assertTrue(stub["external"])
        self.assertEqual(stub["path"], "dashboard/data/insights.json")
        self.assertNotIn("events", stub)
        self.assertNotIn("fund_profiles", stub)

    def test_committed_dashboard_payload_under_github_limit(self) -> None:
        path = ROOT / "dashboard" / "data" / "dashboard_data.json"
        if not path.exists():
            self.skipTest("dashboard_data.json not present")
        size = path.stat().st_size
        if size > GITHUB_HARD_LIMIT:
            payload = json.loads(path.read_text(encoding="utf-8"))
            insights = payload.get("insights") or {}
            self.assertTrue(
                insights.get("external"),
                f"dashboard_data.json is {size / 1024 / 1024:.1f} MB; rebuild with external insights ref",
            )


if __name__ == "__main__":
    unittest.main()
