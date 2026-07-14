#!/usr/bin/env python3
"""Guard insights/pages-fast CI rebuild: repair letter dates before build_insights."""
from __future__ import annotations

import os
import subprocess
import sys
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

    def test_full_profile_skips_drive_steps_without_google_credentials(self) -> None:
        env = os.environ.copy()
        env.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        proc = subprocess.run(
            [sys.executable, str(REBUILD), "full", "--dry-run"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        out = proc.stdout
        self.assertIn("~ skip (no GOOGLE_APPLICATION_CREDENTIALS): _system/scripts/audit_drive_pdf_store.py", out)
        self.assertIn(
            "~ skip (no GOOGLE_APPLICATION_CREDENTIALS): _system/scripts/sync_pdf_store_google_drive.py",
            out,
        )
        self.assertIn("+", out, "non-Drive steps should still run")
        self.assertNotIn("+ _system/scripts/audit_drive_pdf_store.py", out)
        self.assertNotIn("+ _system/scripts/sync_pdf_store_google_drive.py", out)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
