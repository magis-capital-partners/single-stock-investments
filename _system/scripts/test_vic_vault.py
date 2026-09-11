#!/usr/bin/env python3
"""VIC vault staging and inventory status (licensed corpus, like SumZero)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import third_party_inventory as tpi  # noqa: E402
import vic_vault  # noqa: E402


class VicInventoryTests(unittest.TestCase):
    def test_vic_is_context_not_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vic = root / "TPL" / "third-party-analyses" / "vic"
            vic.mkdir(parents=True)
            (vic / "idea.md").write_text("# Foo thesis\nbody\n", encoding="utf-8")
            old = tpi.ROOT
            tpi.ROOT = root
            try:
                rows = tpi._vic_sources("TPL")
            finally:
                tpi.ROOT = old
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "context")
            self.assertEqual(rows[0]["title"], "Foo thesis")
            self.assertNotIn("approval required", (rows[0].get("use") or "").lower())


class VicVaultStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = os.environ.get("RESEARCH_VAULT_ROOT")
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["RESEARCH_VAULT_ROOT"] = self._tmpdir.name
        (Path(self._tmpdir.name) / "vic-research").mkdir()

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("RESEARCH_VAULT_ROOT", None)
        else:
            os.environ["RESEARCH_VAULT_ROOT"] = self._old_env
        self._tmpdir.cleanup()

    def test_stage_writes_pdf_and_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "idea.pdf"
            pdf.write_bytes(b"%PDF-1.4\nidea\n")
            result = vic_vault.stage_vic_to_vault(
                "TPL",
                pdf_path=pdf,
                extract_text=lambda _path: "VIC writeup text",
            )
        self.assertEqual(result["status"], "copied")
        self.assertEqual(result["text_status"], "extracted")
        self.assertTrue(result["vault_ref"].startswith("_system/reference/vic-research/TPL/"))
        dest = Path(self._tmpdir.name) / "vic-research" / "TPL" / "idea.pdf"
        self.assertTrue(dest.is_file())
        txt = dest.with_suffix(".txt")
        self.assertEqual(txt.read_text(encoding="utf-8"), "VIC writeup text")

    def test_stage_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "idea.pdf"
            pdf.write_bytes(b"%PDF-1.4\nidea\n")
            vic_vault.stage_vic_to_vault(
                "TPL", pdf_path=pdf, extract_text=lambda _path: "once"
            )
            again = vic_vault.stage_vic_to_vault(
                "TPL", pdf_path=pdf, extract_text=lambda _path: "should not rewrite"
            )
        self.assertEqual(again["status"], "already_present")
        self.assertEqual(again["text_status"], "already_present")
        txt = Path(self._tmpdir.name) / "vic-research" / "TPL" / "idea.txt"
        self.assertEqual(txt.read_text(encoding="utf-8"), "once")

    def test_skip_when_vault_missing(self) -> None:
        os.environ.pop("RESEARCH_VAULT_ROOT", None)
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "idea.pdf"
            pdf.write_bytes(b"%PDF-1.4\nidea\n")
            # Point at a path that does not exist and is not create=True at the vault root.
            os.environ["RESEARCH_VAULT_ROOT"] = str(Path(tmp) / "no-such-vault")
            result = vic_vault.stage_vic_to_vault("TPL", pdf_path=pdf)
        self.assertEqual(result["status"], "skipped_no_vault")


class VicVaultBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = os.environ.get("RESEARCH_VAULT_ROOT")
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["RESEARCH_VAULT_ROOT"] = self._tmpdir.name
        (Path(self._tmpdir.name) / "vic-research").mkdir()
        self._ssi = tempfile.TemporaryDirectory()
        self.ssi_root = Path(self._ssi.name)

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("RESEARCH_VAULT_ROOT", None)
        else:
            os.environ["RESEARCH_VAULT_ROOT"] = self._old_env
        self._tmpdir.cleanup()
        self._ssi.cleanup()

    def test_backfill_copies_existing_ticker_pdfs(self) -> None:
        vic = self.ssi_root / "EXPE" / "third-party-analyses" / "vic"
        vic.mkdir(parents=True)
        (vic / "writeup.pdf").write_bytes(b"%PDF-1.4\nexpe\n")
        (vic / "note.md").write_text("# EXPE note\n", encoding="utf-8")
        result = vic_vault.backfill_existing_vic(
            ssi_root=self.ssi_root,
            extract_text=lambda _path: "backfill text",
        )
        self.assertGreaterEqual(result["copied"], 1)
        vault_pdf = Path(self._tmpdir.name) / "vic-research" / "EXPE" / "writeup.pdf"
        self.assertTrue(vault_pdf.is_file())
        self.assertTrue((vault_pdf.with_suffix(".txt")).is_file())
        self.assertTrue((Path(self._tmpdir.name) / "vic-research" / "EXPE" / "note.md").is_file())


if __name__ == "__main__":
    unittest.main()
