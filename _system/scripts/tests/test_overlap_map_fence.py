"""The overlap map is not an input to valuation, Darwin, or Peters."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NEEDLES = ("overlap_holdings", "overlap_map", "api/v1/research/overlap")
WATCH = [
    ROOT / "_system" / "scripts" / "decision_authority.py",
    ROOT / "_system" / "scripts" / "build_dashboard_data.py",
    ROOT / "_system" / "scripts" / "refresh_deep_dive_v2.py",
    ROOT / "_system" / "scripts" / "marvin_valuation.py",
    ROOT / "dashboard" / "functions" / "_lib" / "time_average_growth.js",
]


class FenceTest(unittest.TestCase):
    def test_valuation_darwin_and_peters_do_not_read_the_map(self):
        files = [path for path in WATCH if path.exists()]
        darwin = ROOT / "_system" / "scripts" / "darwin"
        if darwin.exists():
            files.extend(path for path in darwin.rglob("*.py"))
        hits = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for needle in NEEDLES:
                if needle in text:
                    hits.append(f"{path.relative_to(ROOT)} contains {needle}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
