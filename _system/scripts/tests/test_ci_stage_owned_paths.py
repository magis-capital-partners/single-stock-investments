"""LS-algo must not force-add files the sparse checkout does not contain."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci_stage_owned_paths import stage_owned


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_sparse_add_does_not_force_outside_files(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    pdf = repo / "BN" / "investor-documents" / "ir-bn"
    pdf.mkdir(parents=True)
    (pdf / "bn-ir-day-presentation-2026.pdf").write_bytes(b"%PDF-1.4\n")
    data = repo / "dashboard" / "data"
    data.mkdir(parents=True)
    (data / "owned.json").write_text("{}\n", encoding="utf-8")
    (repo / "notes").mkdir()
    (repo / "notes" / "a.txt").write_text("note\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "sparse-checkout", "init", "--no-cone")
    _git(repo, "sparse-checkout", "set", "dashboard", "notes")
    # A new blob outside the sparse patterns, and an owned edit.
    outside = repo / "BN" / "investor-documents" / "ir-bn" / "new-outside.pdf"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"%PDF-new\n")
    (data / "owned.json").write_text('{"ok": true}\n', encoding="utf-8")
    refused = stage_owned(repo, ["dashboard/data", ":(glob)**/investor-documents/**"])
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    assert "dashboard/data/owned.json" in staged
    assert "BN/investor-documents/ir-bn/bn-ir-day-presentation-2026.pdf" not in staged
    assert "BN/investor-documents/ir-bn/new-outside.pdf" not in staged
    assert any(path.endswith("new-outside.pdf") or path.endswith("bn-ir-day-presentation-2026.pdf") for path in refused)
