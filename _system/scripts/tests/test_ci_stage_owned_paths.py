"""LS-algo must not force-add files the sparse checkout does not contain."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ci_stage_owned_paths as staging
from ci_stage_owned_paths import _in_sparse, _parse_name_status, _pattern_matcher, stage_owned


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
    (data / "remove.json").write_text('{"remove": true}\n', encoding="utf-8")
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
    (data / "remove.json").unlink()
    (data / "new-inside.json").write_text("{}\n", encoding="utf-8")
    (repo / "notes" / "a.txt").write_text("edited but not owned\n", encoding="utf-8")
    commands: list[list[str]] = []
    real_popen = subprocess.Popen

    def spy(cmd, *args, **kwargs):
        if isinstance(cmd, list):
            commands.append(cmd)
        return real_popen(cmd, *args, **kwargs)

    original = staging.subprocess.Popen
    staging.subprocess.Popen = spy
    try:
        refused = stage_owned(repo, ["dashboard/data", ":(glob)**/investor-documents/**"])
    finally:
        staging.subprocess.Popen = original
    assert commands, "stage_owned did not invoke git"
    assert all(part != "status" for cmd in commands for part in cmd)
    assert any(part == "diff" for cmd in commands for part in cmd)
    assert any(part == "ls-files" for cmd in commands for part in cmd)
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    assert "dashboard/data/owned.json" in staged
    assert "dashboard/data/remove.json" in staged
    assert "dashboard/data/new-inside.json" in staged
    assert "notes/a.txt" not in staged
    assert "BN/investor-documents/ir-bn/bn-ir-day-presentation-2026.pdf" not in staged
    assert "BN/investor-documents/ir-bn/new-outside.pdf" not in staged
    assert any("new-outside.pdf" in path for path in refused)
    flags = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-v", "--", "BN/investor-documents/ir-bn/bn-ir-day-presentation-2026.pdf"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert flags.startswith("S")


def test_pattern_matcher_matches_directory_boundaries():
    patterns = ["dashboard", "BN/investor-documents/DOWNLOAD_MANIFEST.json", "notes"]
    contains = _pattern_matcher(patterns)
    samples = [
        "dashboard",
        "dashboard/data/owned.json",
        "BN/investor-documents/DOWNLOAD_MANIFEST.json",
        "BN/investor-documents/ir-bn/new-outside.pdf",
        "notes/a.txt",
        "dashboard-extra/file",
        "BN/investor-documents/DOWNLOAD_MANIFEST.json.bak",
    ]
    for path in samples:
        assert contains(path) is _in_sparse(path, patterns), path


def test_name_status_splits_renames_and_ordinary_edits():
    blob = b"M\x00dashboard/data/owned.json\x00R100\x00old.txt\x00new.txt\x00D\x00gone.txt\x00"
    assert _parse_name_status(blob) == [
        ("M", "dashboard/data/owned.json"),
        ("D ", "old.txt"),
        ("A ", "new.txt"),
        ("D", "gone.txt"),
    ]


def test_many_sparse_patterns_do_not_stall(tmp_path: Path, capsys):
    repo = tmp_path / "wide"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    outside = repo / "out"
    outside.mkdir()
    for index in range(400):
        (outside / f"{index}.txt").write_text("x\n", encoding="utf-8")
    data = repo / "dashboard" / "data"
    data.mkdir(parents=True)
    (data / "owned.json").write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    pattern_file = repo / "patterns.txt"
    pattern_file.write_text(
        "dashboard\n" + "\n".join(f"out/{index}.txt" for index in range(400)) + "\n",
        encoding="utf-8",
    )
    _git(repo, "sparse-checkout", "init", "--no-cone")
    with pattern_file.open("rb") as handle:
        subprocess.run(
            ["git", "-C", str(repo), "sparse-checkout", "set", "--stdin"],
            check=True, stdin=handle, capture_output=True,
        )
    (data / "owned.json").write_text('{"ok": true}\n', encoding="utf-8")
    (outside / "new-outside.pdf").write_bytes(b"%PDF-new\n")
    started = time.monotonic()
    refused = stage_owned(repo, ["dashboard/data", ":(glob)**/out/**"])
    elapsed = time.monotonic() - started
    assert elapsed < 20, elapsed
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    assert staged == ["dashboard/data/owned.json"]
    assert "out/new-outside.pdf" in refused
    logged = capsys.readouterr().out
    assert "stage: diff of tracked paths" in logged
    assert "stage: listing untracked paths" in logged
    assert "stage: done staged=1 refused=1" in logged
