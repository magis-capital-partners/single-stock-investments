#!/usr/bin/env python3
"""Regression tests for Drive letter import skip/dedup path resolution."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import import_drive_letter_orphans as imp  # noqa: E402


class ResolveLocalPdfTests(unittest.TestCase):
    def test_reuses_existing_basename_when_size_matches(self) -> None:
        """Existing basename must skip — not mint a file-id suffix path."""
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            pdf = dest_dir / "Fund Letter Q1 2024.pdf"
            payload = b"%PDF-1.4 existing letter bytes"
            pdf.write_bytes(payload)

            path, skip = imp.resolve_local_pdf(
                dest_dir,
                "Fund Letter Q1 2024.pdf",
                "abcdefghijklmnop",
                drive_size=len(payload),
                manifest_entry=None,
            )
            self.assertTrue(skip)
            self.assertEqual(path, pdf)

    def test_unique_dest_alone_would_mint_suffix_on_collision(self) -> None:
        """Document the old failure mode that resolve_local_pdf repairs."""
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            pdf = dest_dir / "Fund Letter Q1 2024.pdf"
            pdf.write_bytes(b"%PDF-1.4 existing")
            alt = imp.unique_dest(dest_dir, "Fund Letter Q1 2024.pdf", "abcdefghijklmnop")
            self.assertNotEqual(alt, pdf)
            self.assertIn("abcdefgh", alt.name)

    def test_mints_suffix_only_when_basename_is_different_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            pdf = dest_dir / "Fund Letter Q1 2024.pdf"
            pdf.write_bytes(b"%PDF-1.4 other content that is longer!!")

            path, skip = imp.resolve_local_pdf(
                dest_dir,
                "Fund Letter Q1 2024.pdf",
                "abcdefghijklmnop",
                drive_size=12,  # size mismatch vs local
                manifest_entry=None,
            )
            self.assertFalse(skip)
            self.assertEqual(path, dest_dir / "Fund Letter Q1 2024-abcdefgh.pdf")

    def test_reuses_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "2024Q1"
            dest_dir.mkdir()
            pdf = dest_dir / "Fund Letter Q1 2024.pdf"
            payload = b"%PDF-1.4 manifest-backed"
            pdf.write_bytes(payload)
            entry = {
                "local_pdf_path": str(pdf).replace("\\", "/"),
                "sha256": __import__("hashlib").sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
            path, skip = imp.resolve_local_pdf(
                dest_dir,
                "Fund Letter Q1 2024.pdf",
                "fileid1234567890",
                drive_size=len(payload),
                manifest_entry=entry,
            )
            self.assertTrue(skip)
            self.assertEqual(path, pdf)

    def test_extract_skips_existing_nontrivial_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "letter.pdf"
            txt = root / "letter.txt"
            pdf.write_bytes(b"%PDF-1.4")
            # Make text older than PDF mtime to simulate download churn.
            txt.write_text("Dear Partners,\n\n" + ("Alpha " * 40), encoding="utf-8")
            import os
            import time

            older = time.time() - 3600
            os.utime(txt, (older, older))
            os.utime(pdf, None)  # now
            updated = imp.extract_texts([pdf])
            self.assertEqual(updated, 0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
