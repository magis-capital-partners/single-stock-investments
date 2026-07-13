#!/usr/bin/env python3
"""Guards against sparse CI rebuilds clobbering holdings infra stats."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_dashboard_data as bdd  # noqa: E402


class SparseInfraGuardTests(unittest.TestCase):
    def test_preserve_infra_from_prior(self):
        rows = [
            {
                "ticker": "AAPL",
                "pdf_count": 0,
                "readme": False,
                "research_dir": False,
                "completeness": 0,
            }
        ]
        prior = {
            "AAPL": {
                "ticker": "AAPL",
                "pdf_count": 12,
                "readme": True,
                "research_dir": True,
                "completeness": 90,
                "sec_filings": 3,
            }
        }
        restored = bdd.preserve_infra_from_prior(rows, prior)
        self.assertEqual(restored, 1)
        self.assertEqual(rows[0]["pdf_count"], 12)
        self.assertTrue(rows[0]["readme"])
        self.assertTrue(rows[0]["research_dir"])
        self.assertEqual(rows[0]["completeness"], 90)

    def test_refuse_infra_collapse(self):
        payload = {
            "summary": {
                "ticker_count": 100,
                "total_pdfs": 0,
                "with_research": 0,
            }
        }
        prior = {
            f"T{i}": {"pdf_count": 5, "research_dir": True} for i in range(80)
        }
        with self.assertRaises(SystemExit):
            bdd.refuse_infra_collapse(payload, prior)

    def test_refuse_allows_healthy_payload(self):
        payload = {
            "summary": {
                "ticker_count": 100,
                "total_pdfs": 500,
                "with_research": 80,
            }
        }
        prior = {f"T{i}": {"pdf_count": 5, "research_dir": True} for i in range(80)}
        bdd.refuse_infra_collapse(payload, prior)  # no raise


if __name__ == "__main__":
    raise SystemExit(unittest.main())
