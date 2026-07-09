#!/usr/bin/env python3
"""Guard pages-fast CI rebuild: repair letter dates before build_insights."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github" / "actions" / "rebuild-data" / "action.yml"


class PagesFastRebuildStepsTests(unittest.TestCase):
    def test_pages_fast_repairs_letter_dates_before_build_insights(self) -> None:
        text = ACTION.read_text(encoding="utf-8")
        marker = "Rebuild (pages-fast)"
        start = text.index(marker)
        next_block = text.find("\n    - name:", start + len(marker))
        block = text[start:next_block] if next_block != -1 else text[start:]
        repair_idx = block.find("repair_letter_dates.py --apply")
        insights_idx = block.find("build_insights.py")
        self.assertNotEqual(repair_idx, -1, "pages-fast must run repair_letter_dates.py --apply")
        self.assertNotEqual(insights_idx, -1, "pages-fast must run build_insights.py")
        self.assertLess(
            repair_idx,
            insights_idx,
            "repair_letter_dates must run before build_insights in pages-fast",
        )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
