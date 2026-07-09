#!/usr/bin/env python3
"""Unit tests for Drive intake path parsing and CI exit behavior."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from import_drive_intake import (  # noqa: E402
    exit_code_for_report,
    parse_intake_path,
    partition_intake_errors,
)


class ImportDriveIntakeTests(unittest.TestCase):
    def test_parse_flat_vic_filename(self):
        parsed = parse_intake_path("VIC/FRMI.pdf")
        self.assertEqual(parsed["ticker"], "FRMI")
        self.assertEqual(parsed["intake_kind"], "vic")

    def test_parse_nested_legacy_admin_vic_path(self):
        parsed = parse_intake_path("VIC/Admin/VIC/FRMI.pdf")
        self.assertEqual(parsed["ticker"], "FRMI")
        self.assertEqual(parsed["intake_kind"], "vic")

    def test_numeric_vic_filename_is_validation_error(self):
        parsed = parse_intake_path("VIC/163625.pdf")
        self.assertEqual(parsed["error"], "missing_or_unknown_ticker")

    def test_validation_errors_do_not_fail_ci(self):
        report = {
            "errors": [
                {"error": "missing_or_unknown_ticker", "path": "VIC/163625.pdf"},
            ]
        }
        validation_errors, fatal_errors = partition_intake_errors(report["errors"])
        self.assertEqual(len(validation_errors), 1)
        self.assertEqual(fatal_errors, [])
        self.assertEqual(exit_code_for_report(report), 0)

    def test_fatal_errors_fail_ci(self):
        report = {"errors": [{"error": "download_failed", "path": "VIC/FRMI.pdf"}]}
        validation_errors, fatal_errors = partition_intake_errors(report["errors"])
        self.assertEqual(validation_errors, [])
        self.assertEqual(len(fatal_errors), 1)
        self.assertEqual(exit_code_for_report(report), 2)

    def test_mixed_errors_fail_ci(self):
        report = {
            "errors": [
                {"error": "missing_or_unknown_ticker", "path": "VIC/163625.pdf"},
                {"error": "download_failed", "path": "VIC/FRMI.pdf"},
            ]
        }
        self.assertEqual(exit_code_for_report(report), 2)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
