import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import build_memory_digest as digest


DAILY_ONE = """# Daily log — 2026-07-15

## ICE cloud refresh

- Routine sync.

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] ICE: Croupier with three fee segments; stance hold.
- [PROPOSED STAHL] Exchanges monetize volatility, not direction.
"""

DAILY_TWO = """# Daily log — 2026-07-18

## [PROPOSED MEMORY]

- [PROPOSED MUNGER] AXTI moat unproven due to customer concentration.
- [PROPOSED] Untagged idea about position sizing.
- [PROPOSED COMPANY] ICE: Croupier with three fee segments; stance hold.
"""

MEMORY = """# MEMORY

## Murray Stahl

- Exchanges monetize volatility, not direction.
"""

CORRECTIONS = """# Corrections Log

| Date | Ticker | Error | Correction | Source |
|------|--------|-------|------------|--------|
| 2026-07-16 | AXTI | Wrong share count | 65.4M diluted | 10-Q |
| 2026-06-01 | ICE | Old row outside window | n/a | n/a |
"""


class MemoryDigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        daily = root / "_system" / "memory" / "daily"
        daily.mkdir(parents=True)
        (daily / "2026-07-15.md").write_text(DAILY_ONE, encoding="utf-8")
        (daily / "2026-07-18.md").write_text(DAILY_TWO, encoding="utf-8")
        (root / "_system" / "memory" / "MEMORY.md").write_text(MEMORY, encoding="utf-8")
        (root / "_system" / "memory" / "corrections.md").write_text(CORRECTIONS, encoding="utf-8")
        pending = root / "_system" / "reviews" / "pending"
        pending.mkdir(parents=True)
        patches = [
            patch.object(digest, "ROOT", root),
            patch.object(digest, "DAILY_DIR", daily),
            patch.object(digest, "MEMORY_PATH", root / "_system" / "memory" / "MEMORY.md"),
            patch.object(digest, "CORRECTIONS_PATH", root / "_system" / "memory" / "corrections.md"),
            patch.object(digest, "PENDING_DIR", pending),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_digest_groups_proposals_and_skips_promoted(self):
        text, total = digest.render_digest(date(2026, 7, 20), 7)
        # 5 raw bullets, 1 already promoted (Stahl) -> 4 pending.
        self.assertEqual(total, 4)
        self.assertIn("## Company-specific (2)", text)
        self.assertIn("## Charlie Munger (1)", text)
        self.assertIn("## Untagged proposals (1)", text)
        self.assertNotIn("Exchanges monetize volatility", text)
        self.assertIn("(2026-07-18) AXTI moat unproven", text)

    def test_digest_includes_corrections_in_window_only(self):
        text, _ = digest.render_digest(date(2026, 7, 20), 7)
        self.assertIn("| 2026-07-16 | AXTI |", text)
        self.assertNotIn("2026-06-01", text)

    def test_never_touches_memory_md(self):
        before = digest.MEMORY_PATH.read_text(encoding="utf-8")
        digest.render_digest(date(2026, 7, 20), 7)
        self.assertEqual(digest.MEMORY_PATH.read_text(encoding="utf-8"), before)

    def test_empty_window_produces_zero_total(self):
        _, total = digest.render_digest(date(2026, 9, 1), 7)
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main()
