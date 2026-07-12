#!/usr/bin/env python3
"""Guard insights/pages-fast CI rebuild: repair letter dates before build_insights."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REBUILD = ROOT / "_system" / "scripts" / "ci_rebuild_profile.py"


class InsightsRebuildStepsTests(unittest.TestCase):
    def test_insights_repairs_letter_dates_before_build_insights(self) -> None:
        text = REBUILD.read_text(encoding="utf-8")
        start = text.index('"insights": [')
        end = text.index('"activist": [', start)
        block = text[start:end]
        repair_idx = block.find("repair_letter_dates.py")
        insights_idx = block.find("build_insights.py")
        self.assertNotEqual(repair_idx, -1, "insights must run repair_letter_dates.py --apply")
        self.assertNotEqual(insights_idx, -1, "insights must run build_insights.py")
        self.assertLess(
            repair_idx,
            insights_idx,
            "repair_letter_dates must run before build_insights in insights",
        )

    def test_pages_fast_aliases_insights(self) -> None:
        text = REBUILD.read_text(encoding="utf-8")
        self.assertIn('"pages-fast": "insights"', text)

    def test_darwin_fast_not_a_profile(self) -> None:
        text = REBUILD.read_text(encoding="utf-8")
        self.assertIn('"pages-fast": "insights"', text)
        self.assertNotRegex(text, r'(?m)^\s*"darwin-fast"\s*:')
        # Rejection path remains in resolve_profile
        self.assertIn("darwin-fast", text)
        self.assertIn("profile 'darwin-fast' was removed", text)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
