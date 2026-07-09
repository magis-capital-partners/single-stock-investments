#!/usr/bin/env python3
"""Regression tests for deploy-only GitHub Pages validation (sparse checkout)."""
from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import validate_dashboard_data as validator  # noqa: E402


class PagesDeployOnlyActivistTests(unittest.TestCase):
    def test_missing_local_file_errors_without_sparse_mode(self) -> None:
        row = {
            "local_file": "TICKER/third-party-analyses/activist_reports/long/missing.htm",
            "file_exists": True,
        }
        err = validator.activist_missing_local_file_error(
            row,
            ROOT,
            pages_deploy_only=False,
        )
        self.assertIsNotNone(err)
        self.assertIn("missing file", err)

    def test_missing_local_file_allowed_in_pages_deploy_only_mode(self) -> None:
        row = {
            "local_file": "TICKER/third-party-analyses/activist_reports/long/missing.htm",
            "file_exists": True,
        }
        err = validator.activist_missing_local_file_error(
            row,
            ROOT,
            pages_deploy_only=True,
        )
        self.assertIsNone(err)

    def test_pages_deploy_only_mode_reads_env(self) -> None:
        with unittest.mock.patch.dict(validator.os.environ, {"CI_PAGES_DEPLOY_ONLY": "true"}):
            self.assertTrue(validator.pages_deploy_only_mode())
        with unittest.mock.patch.dict(validator.os.environ, {}, clear=True):
            self.assertFalse(validator.pages_deploy_only_mode())


if __name__ == "__main__":
    raise SystemExit(unittest.main())
