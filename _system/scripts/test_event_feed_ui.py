#!/usr/bin/env python3
"""Node-backed unit tests for event feed filtering and diversification."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_system" / "scripts" / "event_feed_node_runner.cjs"


def run_node(action: str) -> dict:
    proc = subprocess.run(
        ["node", str(RUNNER), action], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


class EventFeedUiTests(unittest.TestCase):
    def test_first_twenty_are_template_diversified(self) -> None:
        result = run_node("diversify")
        self.assertEqual(result["head_count"], 20)
        self.assertLessEqual(result["max_template"], 5)

    def test_scope_filters_are_distinct(self) -> None:
        result = run_node("scope")
        self.assertEqual(result["holdings"], 35)
        self.assertEqual(result["watchlist"], 15)

    def test_tier_filter_counts_visible_results(self) -> None:
        result = run_node("tier")
        self.assertEqual(result["signals"], 35)
        self.assertEqual(result["context"], 15)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
