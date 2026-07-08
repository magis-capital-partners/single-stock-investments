#!/usr/bin/env python3
"""Unit tests for document period inference."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from document_date import infer_document_period  # noqa: E402


class DocumentDateTests(unittest.TestCase):
    def test_letter_folder(self):
        period = infer_document_period(
            {"drive_folder_path": "Letters/2026 Q2", "title": "Oakcliff Letter.pdf"}
        )
        self.assertEqual(period.document_quarter, "2026Q2")
        self.assertEqual(period.period_source, "folder")

    def test_company_half_year_title(self):
        period = infer_document_period(
            {
                "title": "1H 2025 Key Revenue Driver.pdf",
                "drive_folder_path": "Single Stocks/0388.HK/Company/ir-0388.hk",
                "source_type": "company_document",
            }
        )
        self.assertEqual(period.document_year, 2025)
        self.assertEqual(period.period_label, "1H 2025")
        self.assertEqual(period.document_quarter, "2025Q2")

    def test_yyyymm_title(self):
        period = infer_document_period(
            {
                "title": "202605 HKEX IR Pack v5 vF.pdf",
                "drive_folder_path": "Single Stocks/0388.HK/Company/ir-0388.hk",
            }
        )
        self.assertEqual(period.document_date, "2026-05-31")
        self.assertEqual(period.document_quarter, "2026Q2")

    def test_yymmdd_title(self):
        period = infer_document_period({"title": "250317sr e.pdf"})
        self.assertEqual(period.document_date, "2025-03-17")
        self.assertEqual(period.document_quarter, "2025Q1")

    def test_q1_2025_title(self):
        period = infer_document_period({"title": "Q1 2025 Earnings Presentation.pdf"})
        self.assertEqual(period.document_quarter, "2025Q1")

    def test_fy_title(self):
        period = infer_document_period({"title": "FY 2024 Annual Report.pdf"})
        self.assertEqual(period.period_label, "FY 2024")
        self.assertEqual(period.document_year, 2024)

    def test_q1_fy2027_company_deck(self):
        period = infer_document_period(
            {
                "title": "Q1 FY2027 Investor Presentation vFF",
                "drive_folder_path": "Single Stocks/SNOW/Company/ir-snow",
                "source_type": "company_document",
            }
        )
        self.assertEqual(period.document_quarter, "2026Q2")
        self.assertEqual(period.period_label, "Q1 FY2027")
        self.assertEqual(period.period_source, "fy_quarter")

    def test_unknown_title(self):
        period = infer_document_period({"title": "Investor Overview.pdf"})
        self.assertEqual(period.period_source, "unknown")
        self.assertIsNone(period.document_date)

    def test_hash_like_title_ignored(self):
        period = infer_document_period({"title": "e42c2068 bad5 4ab6 ae57 36ff8b2aeffd.pdf"})
        self.assertEqual(period.period_source, "unknown")

    def test_no_modified_at_fallback(self):
        period = infer_document_period(
            {
                "title": "Investor Overview.pdf",
                "modified_at": "2026-06-30T19:01:17Z",
            }
        )
        self.assertEqual(period.period_source, "unknown")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
