#!/usr/bin/env python3
"""Unit tests for Drive intake path parsing and exit behavior."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import import_drive_intake as intake  # noqa: E402


class ImportDriveIntakePathTests(unittest.TestCase):
    def test_flat_vic_pdf(self) -> None:
        parsed = intake.parse_intake_path("VIC/FRMI.pdf")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["intake_kind"], "vic")
        self.assertEqual(parsed["ticker"], "FRMI")

    def test_legacy_admin_intake_layout(self) -> None:
        parsed = intake.parse_intake_path("Admin/Intake/Research/AMD.pdf")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["intake_kind"], "research")
        self.assertEqual(parsed["ticker"], "AMD")

    def test_numeric_vic_filename_is_unknown_ticker(self) -> None:
        parsed = intake.parse_intake_path("VIC/163625.pdf")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.get("error"), "missing_or_unknown_ticker")

    def test_unknown_ticker_does_not_fail_by_default(self) -> None:
        report = {
            "summary": {
                "imported_count": 0,
                "skipped_count": 31,
                "unknown_ticker_count": 31,
                "error_count": 0,
                "touched_ticker_count": 0,
            },
            "errors": [],
            "skipped": [{"reason": "unknown_ticker"}] * 31,
        }
        with patch.object(intake, "import_intake", return_value=report):
            with patch.object(sys, "argv", ["import_drive_intake.py", "--ensure-folders"]):
                self.assertEqual(intake.main(), 0)

    def test_strict_flag_fails_on_unknown_ticker(self) -> None:
        report = {
            "summary": {
                "imported_count": 0,
                "skipped_count": 1,
                "unknown_ticker_count": 1,
                "error_count": 0,
                "touched_ticker_count": 0,
            },
            "errors": [],
            "skipped": [{"reason": "unknown_ticker"}],
        }
        with patch.object(intake, "import_intake", return_value=report):
            with patch.object(sys, "argv", ["import_drive_intake.py", "--strict"]):
                self.assertEqual(intake.main(), 2)

    def test_real_errors_still_fail(self) -> None:
        report = {
            "summary": {
                "imported_count": 0,
                "skipped_count": 0,
                "unknown_ticker_count": 0,
                "error_count": 1,
                "touched_ticker_count": 0,
            },
            "errors": [{"error": "download_failed"}],
            "skipped": [],
        }
        with patch.object(intake, "import_intake", return_value=report):
            with patch.object(sys, "argv", ["import_drive_intake.py"]):
                self.assertEqual(intake.main(), 2)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
