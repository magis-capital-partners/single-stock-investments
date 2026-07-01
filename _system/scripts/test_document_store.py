#!/usr/bin/env python3
"""Unit tests for document_store URL resolution."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from document_store import (  # noqa: E402
    best_document_label,
    best_document_url,
    drive_link_for_letter,
    letter_evidence_label,
    letter_evidence_url,
)


class DocumentStoreTests(unittest.TestCase):
    def test_letter_pdf_on_drive_by_filename(self):
        ref = "_system/reference/superinvestor-letters/2024Q1/Rowan Street Q1 2024 Letter.pdf"
        url = best_document_url(ref, "GoldmanDrew/single-stock-investments")
        self.assertIn("drive.google.com/file/", url or "")
        self.assertEqual(best_document_label(ref), "PDF")

    def test_letter_missing_pdf_falls_back_to_quarter_folder(self):
        letter = {
            "fund": "Rowan Street Alex Kopel",
            "quarter": "2026Q1",
            "source_document": "_system/reference/superinvestor-letters/2026Q1/Rowan Street Q1 2026 Letter - Alex Kopel.pdf",
            "source_file": "_system/reference/superinvestor-letters/2026Q1/Rowan Street Q1 2026 Letter - Alex Kopel.txt",
        }
        url = letter_evidence_url(letter, "GoldmanDrew/single-stock-investments")
        self.assertIn("drive.google.com/", url or "")
        self.assertTrue(
            "drive.google.com/file/" in (url or "") or "drive.google.com/drive/folders/" in (url or "")
        )

    def test_letter_txt_maps_to_drive_when_pdf_name_matches(self):
        ref = "_system/reference/superinvestor-letters/2026Q1/Arquitos_Investor_Letter_Q1_2026.pdf"
        url = best_document_url(ref, "GoldmanDrew/single-stock-investments")
        self.assertIn("drive.google.com/file/", url or "")

    def test_drive_link_for_letter_exact_name(self):
        link = drive_link_for_letter(
            source_ref="_system/reference/superinvestor-letters/2026Q1/Starfort Letter Q1 2026.pdf",
            quarter="2026Q1",
            fund="Starfort",
        )
        self.assertIn("drive.google.com/file/", link or "")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
