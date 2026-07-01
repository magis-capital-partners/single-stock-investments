#!/usr/bin/env python3
"""Unit tests for document_store URL resolution."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from document_store import best_document_label, best_document_url  # noqa: E402


class DocumentStoreTests(unittest.TestCase):
    def test_letter_pdf_prefers_pdf_over_txt(self):
        ref = "_system/reference/superinvestor-letters/2026Q1/Rowan Street Q1 2026 Letter - Alex Kopel.pdf"
        url = best_document_url(ref, "GoldmanDrew/single-stock-investments")
        self.assertIn(".pdf", url or "")
        self.assertNotIn(".txt", url or "")
        self.assertEqual(best_document_label(ref), "PDF")

    def test_letter_txt_maps_to_pdf(self):
        ref = "_system/reference/superinvestor-letters/2026Q1/Steamboat_2026_First_Quarter_Letter.txt"
        url = best_document_url(ref, "GoldmanDrew/single-stock-investments")
        self.assertIn("Steamboat_2026_First_Quarter_Letter.pdf", url or "")
        self.assertEqual(best_document_label(ref), "PDF")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
