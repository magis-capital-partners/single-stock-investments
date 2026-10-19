"""The Data Pipeline thirteen-f job checks out every dashboard file it reads.

Run 39310759840 failed in "Check 13F filings": build_overlap_holdings.py
reads dashboard/data/overlap_holders.json, and the minimal profile only
materializes _system, .github, and Makefile. The file is on main. A full
checkout would hide the miss and pull ticker trees this job never opens.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "data-pipeline.yml"
SHELL = ROOT / "_system" / "scripts" / "ci_checkout_workspace.sh"
PATHS = ROOT / "_system" / "scripts" / "ci_sparse_checkout_paths.py"
SCRIPTS = ROOT / "_system" / "scripts"

ASSIGNMENT = re.compile(r'ROOT\s*/\s*"dashboard"((?:\s*/\s*"[^"]+")+)')
SEGMENT = re.compile(r'"([^"]+)"')
IMPORT = re.compile(r"(?m)^(?:from|import) ([a-z_][a-z0-9_]*)")


def thirteen_f_job() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text.split("\n  thirteen-f:\n", 1)[1].split("\n  pipeline-summary:\n", 1)[0]


def sparse_entries() -> list[str]:
    """Same path list ci_checkout_workspace.sh writes for thirteen-f."""
    result = subprocess.run(
        [sys.executable, str(PATHS), "thirteen-f"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    extra = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    # apply_sparse_paths files-only echoes these two, then the script output.
    return ["_system", ".github", *extra]


def covers(path: str, entries: list[str]) -> bool:
    path = path.rstrip("/")
    for entry in entries:
        entry = entry.rstrip("/")
        if path == entry or path.startswith(entry + "/"):
            return True
    return False


def dashboard_paths(text: str) -> list[str]:
    found = []
    for match in ASSIGNMENT.finditer(text):
        found.append("/".join(["dashboard", *SEGMENT.findall(match.group(1))]))
    return found


def modules_the_job_imports() -> list[Path]:
    job = thirteen_f_job()
    entry = [
        ROOT / match
        for match in re.findall(r"python (_system/scripts/\S+\.py)", job)
    ]
    assert entry, "thirteen-f job does not run any _system/scripts python file"
    seen: set[Path] = set()
    ordered: list[Path] = []

    def walk(path: Path) -> None:
        if path in seen or not path.is_file():
            return
        seen.add(path)
        ordered.append(path)
        text = path.read_text(encoding="utf-8")
        for name in IMPORT.findall(text):
            walk(path.parent / f"{name}.py")

    for path in entry:
        walk(path)
    return ordered


def test_thirteen_f_job_uses_the_dedicated_sparse_profile():
    job = thirteen_f_job()
    assert "bash _system/scripts/ci_checkout_workspace.sh thirteen-f" in job
    assert "ci_checkout_workspace.sh minimal" not in job
    assert "ci_checkout_workspace.sh full" not in job
    assert "ci_checkout_workspace.sh pages" not in job


def test_thirteen_f_arm_asks_for_listed_files_not_the_dashboard_tree():
    shell = SHELL.read_text(encoding="utf-8")
    arm = re.search(r"(?ms)^  thirteen-f\)\n(.*?\n    ;;\n)", shell)
    assert arm, "ci_checkout_workspace.sh has no thirteen-f profile"
    body = arm.group(1)
    assert "apply_sparse_paths files-only" in body
    assert "git sparse-checkout set _system .github\n" in body
    assert "sparse-checkout disable" not in body
    assert re.search(r"sparse-checkout set[^\n]*\bdashboard\b", body) is None
    func = re.search(r"(?ms)^apply_sparse_paths\(\) \{\n(.*?)\n\}", shell)
    assert func
    source = func.group(1)
    assert 'echo "_system"' in source
    assert 'echo ".github"' in source
    assert '!= "files-only"' in source
    assert 'echo "dashboard"' in source
    # Other profiles still take the whole dashboard tree.
    assert re.search(r"(?m)^    apply_sparse_paths$", shell)


def test_sparse_paths_cover_every_dashboard_file_the_scripts_read_or_commit():
    entries = sparse_entries()
    assert "dashboard" not in entries
    assert "dashboard/data" not in entries
    assert covers("dashboard/data/overlap_holders.json", entries)

    missing = []
    for path in modules_the_job_imports():
        for rel in dashboard_paths(path.read_text(encoding="utf-8")):
            if not covers(rel, entries):
                missing.append(f"{path.relative_to(ROOT)} -> {rel}")
    job = thirteen_f_job()
    for rel in re.findall(r"(dashboard/\S+)", job):
        if not covers(rel, entries):
            missing.append(f"git_add -> {rel}")
    assert not missing, "thirteen-f checkout misses:\n  " + "\n  ".join(missing)

    # Ownership inputs live under _system, which the profile always includes.
    assert covers("_system/reference/market-data/ownership", entries)


def test_thirteen_f_patterns_materialize_those_files_and_nothing_else_in_dashboard(tmp_path):
    """Non-cone patterns from the path script, applied the way the shell does."""
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "_system/scripts/marker.py": "script",
        ".github/actions/commit-main/action.yml": "action",
        "dashboard/data/overlap_holders.json": "holders",
        "dashboard/data/overlap_holdings.json": "overlap",
        "dashboard/data/fund_holdings_summary.json": "summary",
        "dashboard/data/index_membership.json": "index",
        "dashboard/data/holdings/by_ticker/AAA.json": "ticker",
        "dashboard/data/holdings/by_manager/akre.json": "manager",
        "dashboard/data/holdings/feed.json": "feed",
        "dashboard/data/holdings/managers_index.json": "managers",
        "dashboard/data/should_not_appear.json": "decoy",
        "other/nope.txt": "nope",
    }
    for rel, body in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "config", "user.email", "t@example.com"], check=True)
    subprocess.run([*git, "config", "user.name", "t"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)

    paths_file = tmp_path / "sparse.txt"
    paths_file.write_text("\n".join(sparse_entries()) + "\n", encoding="utf-8")
    subprocess.run([*git, "sparse-checkout", "init", "--no-cone"], check=True)
    subprocess.run([*git, "sparse-checkout", "set", "--stdin"], stdin=paths_file.open(), check=True)

    def present(rel: str) -> bool:
        return (repo / rel).is_file()

    for rel in files:
        if rel in {"dashboard/data/should_not_appear.json", "other/nope.txt"}:
            assert not present(rel), rel
        else:
            assert present(rel), rel
