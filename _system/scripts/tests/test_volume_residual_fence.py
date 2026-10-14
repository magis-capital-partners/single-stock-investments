#!/usr/bin/env python3
"""The volume residual stays out of valuation, Darwin, and the other clocks."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NEEDLES = ("volume_residual", "vol_volume_residual")
FILES = (
    "_system/scripts/decision_authority.py",
    "_system/scripts/build_dashboard_data.py",
    "_system/scripts/refresh_deep_dive_v2.py",
    "_system/scripts/marvin_valuation.py",
    "dashboard/functions/_lib/time_average_growth.js",
    "dashboard/functions/_lib/overlap_map.js",
)


class VolumeResidualFenceTests(unittest.TestCase):
    def test_listed_files_do_not_mention_the_residual(self):
        offenders = []
        paths = [ROOT / relative for relative in FILES]
        darwin = ROOT / "_system" / "scripts" / "darwin"
        if darwin.exists():
            paths.extend(darwin.rglob("*.py"))
        for path in paths:
            if not path.exists():
                offenders.append(f"missing {path}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for needle in NEEDLES:
                if needle in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {needle}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
