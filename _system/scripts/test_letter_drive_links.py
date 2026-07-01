#!/usr/bin/env python3
"""Unit tests for letter Drive link builders."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_letter_drive_links as letter_links  # noqa: E402
import document_store as ds  # noqa: E402


class LetterDriveLinkTests(unittest.TestCase):
    def test_resolve_exact_filename_from_index(self):
        index = {
            "rowan street q1 2026 letter - alex kopel.pdf": {
                "webViewLink": "https://drive.google.com/file/d/abc123/view",
                "parents": ["1QxQd4VhLv7HK1qa45izn80MMYFcS-gxg"],
            }
        }
        letter = {
            "fund": "Rowan Street Alex Kopel",
            "quarter": "2026Q1",
            "source_document": "_system/reference/superinvestor-letters/2026Q1/Rowan Street Q1 2026 Letter - Alex Kopel.pdf",
        }
        link = letter_links.resolve_letter_link(letter, index, {})
        self.assertEqual(link, "https://drive.google.com/file/d/abc123/view")

    def test_document_store_prefers_letter_drive_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            links_path = Path(tmp) / "letter_drive_links.json"
            links_path.write_text(
                json.dumps(
                    {
                        "links": {
                            "_system/reference/superinvestor-letters/2026Q1/Rowan Street Q1 2026 Letter - Alex Kopel.pdf": "https://drive.google.com/file/d/abc123/view"
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(ds, "LETTER_DRIVE_LINKS_PATH", links_path):
                ds._LETTER_DRIVE_LINKS = None
                url = ds.drive_link_for_letter(
                    source_ref="_system/reference/superinvestor-letters/2026Q1/Rowan Street Q1 2026 Letter - Alex Kopel.pdf",
                    quarter="2026Q1",
                    fund="Rowan Street Alex Kopel",
                )
                self.assertEqual(url, "https://drive.google.com/file/d/abc123/view")
                self.assertEqual(
                    ds.letter_evidence_label(url),
                    "PDF",
                )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
