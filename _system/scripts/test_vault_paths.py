#!/usr/bin/env python3
"""Unit tests for vault_paths resolution."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import vault_paths as vp  # noqa: E402


class VaultPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = os.environ.get("RESEARCH_VAULT_ROOT")
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["RESEARCH_VAULT_ROOT"] = self._tmpdir.name
        (Path(self._tmpdir.name) / "superinvestor-letters").mkdir()
        (Path(self._tmpdir.name) / "investment-wisdom").mkdir()

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("RESEARCH_VAULT_ROOT", None)
        else:
            os.environ["RESEARCH_VAULT_ROOT"] = self._old_env
        self._tmpdir.cleanup()

    def test_letters_root_uses_vault(self) -> None:
        root = vp.letters_root()
        self.assertTrue(str(root).endswith("superinvestor-letters"))
        self.assertEqual(root.parent, Path(self._tmpdir.name))

    def test_resolve_ref_to_path(self) -> None:
        txt = vp.letters_root() / "2026Q1/foo.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text("x", encoding="utf-8")
        ref = vp.letters_ref("2026Q1/foo.txt")
        resolved = vp.resolve_ref_to_path(ref)
        self.assertEqual(resolved, txt)

    def test_letters_ref_prefix_stable(self) -> None:
        self.assertTrue(vp.letters_ref("2026Q1/a.txt").startswith("_system/reference/superinvestor-letters/"))

    def test_vault_status(self) -> None:
        status = vp.vault_status()
        self.assertTrue(status["letters_exists"])
        self.assertTrue(status["using_vault"])


if __name__ == "__main__":
    unittest.main()
