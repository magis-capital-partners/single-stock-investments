#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_insights import dedupe_canonical_letters  # noqa: E402
from letter_dedup import _near_duplicate, deduplicate_letter_files  # noqa: E402


class LetterDedupTests(unittest.TestCase):
    def test_exact_normalized_duplicates_choose_clean_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "Starfort Letter Q1 2026.txt"
            copy = root / "Starfort Letter (1) Q1 2026.txt"
            clean.write_text("Dear Partners,\n\nThe fund returned 4%." * 30, encoding="utf-8")
            copy.write_text("Dear Partners,  The fund returned 4%." * 30, encoding="utf-8")
            files, metadata, audit = deduplicate_letter_files([copy, clean])
            self.assertEqual(files, [clean])
            self.assertEqual(audit["exact_duplicates_suppressed"], 1)
            row = metadata[str(clean.resolve()).lower()]
            self.assertEqual(row["duplicate_count"], 1)
            self.assertTrue(row["canonical_document_id"].startswith("letter-"))

    def test_conservative_near_duplicate_detection(self) -> None:
        base = ("The portfolio owns a durable compounder with recurring revenue. " * 30).strip()
        variant = base.replace("durable compounder", "durable  compounder", 1)
        unrelated = ("A completely different investor letter about energy markets. " * 30).strip()
        self.assertTrue(_near_duplicate(base.lower(), variant.lower()))
        self.assertFalse(_near_duplicate(base.lower(), unrelated.lower()))

    def test_downstream_guard_keeps_one_canonical_document(self) -> None:
        rows, suppressed = dedupe_canonical_letters(
            [
                {"canonical_document_id": "letter-abc", "source_file": "a.txt"},
                {"canonical_document_id": "letter-abc", "source_file": "b.txt"},
                {"canonical_document_id": "letter-def", "source_file": "c.txt"},
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(suppressed, 1)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
