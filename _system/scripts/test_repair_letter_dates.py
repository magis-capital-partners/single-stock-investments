#!/usr/bin/env python3
"""Tests for repair_letter_dates.py."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import repair_letter_dates as rld  # noqa: E402


class RepairLetterDatesTests(unittest.TestCase):
    def test_repair_prefers_folder_quarter_over_bad_stored_quarter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            letters_dir = vault / "superinvestor-letters"
            letters_dir.mkdir()
            insights_path = letters_dir / "insights.json"
            source = "_system/reference/superinvestor-letters/2011Q4/Indaba Capital Quarterly Letter to Investors December 31 2011.txt"
            insights_path.write_text(
                json.dumps(
                    {
                        "letters": [
                            {
                                "fund_id": "indaba-to",
                                "quarter": "2031Q4",
                                "letter_date": "2031-12-31",
                                "source_file": source,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {"RESEARCH_VAULT_ROOT": str(vault)}):
                import importlib

                import vault_paths

                importlib.reload(vault_paths)
                importlib.reload(rld)

                self.assertEqual(rld.main(), 0)
                payload = json.loads(insights_path.read_text(encoding="utf-8"))
                letter = payload["letters"][0]
                self.assertEqual(letter["quarter"], "2011Q4")
                self.assertEqual(letter["letter_date"], "2011-12-31")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
