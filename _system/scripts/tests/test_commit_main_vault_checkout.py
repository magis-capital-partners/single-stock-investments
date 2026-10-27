"""Jobs that publish through commit-main must already have the private vault.

preserve-private-dashboard runs migrate_dashboard_sources.py, which refuses
to redact public files unless a research-vault checkout exists. After the
fund-letter reader landed, Epistemic Falsifier, Committee Outcome, Canonical
Memory Triage, and Data Pipeline thirteen-f all died in that step: they call
commit-main and never clone the vault. Letter Backfill's publish job is the
pattern that already works.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
PRESERVE = ROOT / ".github" / "actions" / "preserve-private-dashboard" / "action.yml"
MIGRATE = ROOT / "_system" / "scripts" / "migrate_dashboard_sources.py"
COMMIT = "commit-main"
VAULT = "checkout-vault"


def load_workflows() -> dict[str, dict]:
    return {path.name: yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(WORKFLOWS.glob("*.yml"))}


def merged_env(doc: dict, job: dict) -> dict:
    env = dict(doc.get("env") or {})
    env.update(job.get("env") or {})
    return env


def uses_name(step: dict) -> str:
    return str(step.get("uses") or "")


def vault_ready(doc: dict, job: dict, commit_at: int) -> bool:
    """A checkout-vault step, or rebuild-data after the clone token is in env."""
    token = str(merged_env(doc, job).get("RESEARCH_VAULT_CLONE_TOKEN") or "")
    for step in (job.get("steps") or [])[:commit_at]:
        uses = uses_name(step)
        if uses.endswith(VAULT):
            return True
        if uses.endswith("rebuild-data") and "secrets.RESEARCH_VAULT_CLONE_TOKEN" in token:
            return True
    return False


def test_every_commit_main_job_checks_out_the_vault_first():
    missing = []
    seen = 0
    for name, doc in load_workflows().items():
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps") or []
            commits = [i for i, step in enumerate(steps) if uses_name(step).endswith(COMMIT)]
            if not commits:
                continue
            seen += 1
            token = str(merged_env(doc, job).get("RESEARCH_VAULT_CLONE_TOKEN") or "")
            if "secrets.RESEARCH_VAULT_CLONE_TOKEN" not in token or not vault_ready(doc, job, commits[0]):
                missing.append(f"{name}:{job_name}")
            # The action files have to be on disk before the step runs. Jobs that
            # list commit-main in a narrow sparse-checkout do not get siblings.
            for step in steps:
                sparse = str((step.get("with") or {}).get("sparse-checkout") or "")
                if ".github/actions/commit-main" not in sparse:
                    continue
                if "preserve-private-dashboard" not in sparse or "checkout-vault" not in sparse:
                    missing.append(f"{name}:{job_name} sparse-checkout")
    assert seen >= 20, seen
    assert not missing, "commit-main without a prior research-vault checkout:\n  " + "\n  ".join(missing)


def test_the_publication_guard_still_refuses_a_missing_vault():
    text = MIGRATE.read_text(encoding="utf-8")
    assert 'raise RuntimeError("A configured private research-vault checkout is required; public files were not changed.")' in text
    action = PRESERVE.read_text(encoding="utf-8")
    assert "python _system/scripts/migrate_dashboard_sources.py" in action
    assert "ci_push_vault.sh" in action
    assert "dashboard/private-assets.json" in action
    assert "git sparse-checkout add --skip-checks" in action
    assert '"add", "--sparse"' in action


def _bootstrap_script() -> str:
    text = PRESERVE.read_text(encoding="utf-8")
    start = text.index('if [ ! -f dashboard/private-assets.json ]')
    end = text.index('test -f .gitattributes', start)
    return text[start:end] + "test -f .gitattributes\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_sparse_checkout_materializes_the_committed_manifest_before_redaction(tmp_path):
    """Without this, a thirteen-f checkout would rewrite private-assets.json
    from the few files it has on disk."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "dashboard").mkdir()
    (repo / "dashboard" / "private-assets.json").write_text('{"assets":{"keep":true}}\n', encoding="utf-8")
    (repo / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
    (repo / "README").write_text("visible\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    (repo / "notes").mkdir()
    (repo / "notes" / "readme.txt").write_text("visible\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "notes")
    # Cone mode accepts directories only. Non-cone is what thirteen-f uses.
    modes = (("nocon", ["sparse-checkout", "init", "--no-cone"], ["sparse-checkout", "set", "README"]),
             ("cone", ["sparse-checkout", "init", "--cone"], ["sparse-checkout", "set", "notes"]))
    for name, init, narrow in modes:
        work = tmp_path / name
        _git(repo, "clone", "-q", str(repo), str(work))
        _git(work, "config", "user.email", "t@example.com")
        _git(work, "config", "user.name", "t")
        _git(work, *init)
        _git(work, *narrow)
        assert not (work / "dashboard" / "private-assets.json").is_file()
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", _bootstrap_script()], cwd=work, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert (work / "dashboard" / "private-assets.json").read_text(encoding="utf-8") == '{"assets":{"keep":true}}\n'
        assert (work / ".gitattributes").read_text(encoding="utf-8") == "* text=auto\n"


def _stage_script() -> str:
    text = PRESERVE.read_text(encoding="utf-8")
    start = text.rfind("\n", 0, text.index("import subprocess\n")) + 1
    end = text.index("\n        PY\n", start)
    return textwrap.dedent(text[start:end])


def test_migration_staging_leaves_the_jobs_other_edits_unstaged(tmp_path):
    """A narrow git_add must still receive the redacted files, and must not
    gain every other path the job has already edited."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "kept.txt").write_text("before\n", encoding="utf-8")
    (repo / "redacted.txt").write_text("full\n", encoding="utf-8")
    (repo / "secret.txt").write_text("nope\n", encoding="utf-8")
    (repo / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    _git(repo, "add", "kept.txt", "redacted.txt", ".gitignore")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "kept.txt").write_text("job edit\n", encoding="utf-8")
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.write_text(subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain=v1", "-uall"], text=True), encoding="utf-8")
    (repo / "redacted.txt").write_text("placeholder\n", encoding="utf-8")
    (repo / "secret.txt").write_text("still secret\n", encoding="utf-8")
    after.write_text(subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain=v1", "-uall"], text=True), encoding="utf-8")
    proc = subprocess.run(["python3", "-", str(before), str(after)], input=_stage_script(), cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    staged = subprocess.check_output(["git", "-C", str(repo), "diff", "--cached", "--name-only"], text=True).split()
    assert staged == ["redacted.txt"]
