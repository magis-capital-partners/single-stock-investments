"""ci_push_main.sh must bring its own happy-path files into a sparse checkout.

Market Risk Components keeps a partial clone at $RUNNER_TEMP/ssi-source and
widens it to the push helper only. The helper now runs
audit_fund_letter_exposure.py before every commit, so that file has to be
in the checkout or the publish step dies with Errno 2 and the fallback JSON
never lands. The same file list is the contract for every other workflow
that names ci_push_main.sh inside a sparse-checkout pattern.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUSH = ROOT / "_system" / "scripts" / "ci_push_main.sh"
WORKFLOWS = ROOT / ".github" / "workflows"

EXPECTED = (
    "_system/scripts/audit_fund_letter_exposure.py",
    "_system/scripts/compact_dated_artifacts.py",
    "_system/scripts/atomic_io.py",
    "dashboard/private-assets.json",
)


def dependency_paths() -> list[str]:
    text = PUSH.read_text(encoding="utf-8")
    match = re.search(r"PUSH_DEPENDENCY_PATHS=\((.*?)\)", text, re.S)
    assert match, "PUSH_DEPENDENCY_PATHS is missing from ci_push_main.sh"
    return re.findall(r"[A-Za-z0-9_./-]+\.(?:py|json)", match.group(1))


def sparse_blocks_that_name_the_helper(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not re.match(r"^[ \t]*sparse-checkout:[ \t]*\|[ \t]*$", line.rstrip("\n")):
            continue
        key_indent = len(line) - len(line.lstrip(" "))
        body_lines: list[str] = []
        for nxt in lines[index + 1 :]:
            if nxt.strip() == "":
                body_lines.append(nxt)
                continue
            content_indent = len(nxt) - len(nxt.lstrip(" "))
            if content_indent <= key_indent:
                break
            body_lines.append(nxt)
        body = "".join(body_lines)
        if "ci_push_main.sh" in body:
            blocks.append(body)
    for match in re.finditer(
        r"sparse-checkout (?:add|set)(?: \\\n| [^\n]*\\\n)((?:[ \t]+.+\\\n)*[ \t]+[^\n]+)",
        text,
    ):
        body = match.group(0)
        if "ci_push_main.sh" in body:
            blocks.append(body)
    return blocks


def test_dependency_list_covers_the_audit_and_what_it_reads():
    assert dependency_paths() == list(EXPECTED)
    text = PUSH.read_text(encoding="utf-8")
    body = text.split("ci_push_main()", 1)[1]
    assert body.index("materialize_push_dependencies") < body.index(
        "audit_fund_letter_exposure.py --staged --strict"
    )


def test_narrow_sparse_checkouts_list_every_push_dependency():
    named = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        blocks = sparse_blocks_that_name_the_helper(path.read_text(encoding="utf-8"))
        for block in blocks:
            named.append(path.name)
            normalized = block.replace("\\", " ")
            for dep in EXPECTED:
                assert dep in normalized or f"/{dep}" in normalized, f"{path.name} omits {dep}"
    assert named == ["contract-backfill-continue.yml", "market-risk-components.yml"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    for relative in EXPECTED:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative + "\n", encoding="utf-8")
    (repo / "README").write_text("readme\n", encoding="utf-8")
    (repo / "notes").mkdir()
    (repo / "notes" / "a.txt").write_text("note\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")


def _materialize(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail\n"
            'cd "$1"\n'
            "CI_PUSH_SOURCING=1 source \"$2\"\n"
            "materialize_push_dependencies\n",
            "bash",
            str(repo),
            str(PUSH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_materialize_restores_dependencies_in_cone_and_non_cone(tmp_path: Path):
    for mode, init, narrow in (
        ("nocon", ["sparse-checkout", "init", "--no-cone"], ["sparse-checkout", "set", "README"]),
        ("cone", ["sparse-checkout", "init", "--cone"], ["sparse-checkout", "set", "notes"]),
    ):
        repo = tmp_path / mode
        _init_repo(repo)
        _git(repo, *init)
        _git(repo, *narrow)
        assert not (repo / EXPECTED[0]).exists()
        result = _materialize(repo)
        assert result.returncode == 0, result.stderr
        for relative in EXPECTED:
            assert (repo / relative).read_text(encoding="utf-8") == relative + "\n"
        assert (repo / "README").is_file() or (repo / "notes" / "a.txt").is_file()


def test_materialize_is_a_no_op_when_the_checkout_is_not_sparse(tmp_path: Path):
    repo = tmp_path / "full"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README").write_text("readme\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "seed")
    result = _materialize(repo)
    assert result.returncode == 0, result.stderr
    assert not (repo / EXPECTED[0]).exists()
