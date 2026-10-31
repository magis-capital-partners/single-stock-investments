"""Publication-only vault checkout stays closed and does not delete omitted trees."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_publication_sparse import object_patterns  # noqa: E402

ACTION = ROOT / ".github" / "actions" / "checkout-vault" / "action.yml"
COMMIT = ROOT / ".github" / "actions" / "commit-main" / "action.yml"
WORKFLOWS = ROOT / ".github" / "workflows"
LOOPS = {
    "memory-digest.yml": "triage",
    "falsifier-resolution.yml": "resolve-and-validate",
    "committee-outcomes.yml": "observe",
}
PUBLICATION_CALLERS = set(LOOPS) | {"vault-publication-checkout.yml"}


def _git(repo: Path, *args: str, input_text: str | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _checkout_step() -> dict:
    action = _action()
    return next(step for step in action["runs"]["steps"] if str(step.get("uses", "")).startswith("actions/checkout"))


def _patterns(marker: str) -> list[str]:
    import re

    found = []
    for line in _checkout_step()["with"]["sparse-checkout"].splitlines():
        if marker in line:
            found.extend(re.findall(r"&& '([^']+)'", line))
    return found


def test_object_patterns_follow_the_manifest_and_reject_a_bad_id():
    manifest = {
        "assets": {
            "data/core.json": {"private_sha256": "a" * 64, "public_sha256": "b" * 64},
            "data/tickers/AAA.json": {"private_sha256": "c" * 64, "public_sha256": "d" * 64},
        },
        "repository_assets": {
            "_system/data/chunks.jsonl": {"private_sha256": "a" * 64, "public_sha256": "e" * 64},
        },
    }
    assert object_patterns(manifest) == [
        "/dashboard-private/objects/" + ("a" * 64),
        "/dashboard-private/objects/" + ("c" * 64),
    ]
    manifest["assets"]["data/core.json"]["private_sha256"] = "not-a-sha"
    try:
        object_patterns(manifest)
    except ValueError as exc:
        assert "data/core.json" in str(exc)
    else:
        raise AssertionError("bad object id was accepted")


def test_publication_only_is_opt_in_and_the_three_loops_use_it():
    action = _action()
    assert action["inputs"]["publication-only"]["default"] == "false"
    assert action["inputs"]["include-source-archive"]["default"] == "true"
    checkout = _checkout_step()
    assert "blob:none" in checkout["with"]["filter"]
    assert _patterns("publication-only == 'true'") == [
        "/dashboard-private/migration-journal.jsonl",
        "/dashboard-private/manifest.json",
        "/dashboard-private/.gitattributes",
    ]
    assert "/*" in _patterns("publication-only != 'true'")
    assert "!/dashboard-private/company-source-backfill-v2/" in _patterns("publication-only != 'true'")
    commit = yaml.safe_load(COMMIT.read_text(encoding="utf-8"))
    assert commit["inputs"]["preserve-company-cache"]["default"] == "true"
    preserve = next(step for step in commit["runs"]["steps"] if str(step.get("uses", "")).endswith("preserve-private-dashboard"))
    assert preserve["with"]["preserve-company-cache"] == "${{ inputs.preserve-company-cache }}"

    opted = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                uses = str(step.get("uses") or "")
                chosen = (step.get("with") or {}).get("publication-only")
                if uses.endswith("checkout-vault") and str(chosen).lower() == "true":
                    opted.append(path.name)
                if uses.endswith("commit-main"):
                    cache = (step.get("with") or {}).get("preserve-company-cache")
                    if path.name in LOOPS and job_name == LOOPS[path.name]:
                        assert str(cache).lower() == "false", path.name
                    elif cache is not None:
                        raise AssertionError(f"{path.name}:{job_name} sets preserve-company-cache")
    assert opted == sorted(PUBLICATION_CALLERS)
    for name, job_name in LOOPS.items():
        document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
        step = next(step for step in document["jobs"][job_name]["steps"] if str(step.get("uses") or "").endswith("checkout-vault"))
        assert str(step["with"]["publication-only"]).lower() == "true"


def test_publication_checkout_materializes_named_objects_and_leaves_the_archive(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.email", "t@example.com")
    _git(origin, "config", "user.name", "t")
    named = "a" * 64
    orphan = "b" * 64
    files = {
        f"dashboard-private/objects/{named}": "snapshot",
        f"dashboard-private/objects/{orphan}": "old",
        "dashboard-private/migration-journal.jsonl": "{}\n",
        "dashboard-private/manifest.json": "{}\n",
        "dashboard-private/.gitattributes": "objects/* -text\n",
        "dashboard-private/company-source-backfill-v2/part.zip": "ARCHIVE",
        "dashboard-private/investor-history/objects/part.gz": "HIST",
        "dashboard-private/company-research-cache/git/x": "cache",
        "superinvestor-letters/fund/letter.md": "letter",
        "podcasts/ep.txt": "pod",
        "videos/clip.txt": "vid",
    }
    for relative, content in files.items():
        path = origin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "fixture")

    work = tmp_path / "work"
    _git(origin, "clone", "-q", "--filter=blob:none", "--sparse", str(origin), str(work))
    _git(work, "sparse-checkout", "init", "--no-cone")
    _git(work, "sparse-checkout", "set", "--no-cone", "--stdin", input_text="\n".join(_patterns("publication-only == 'true'")) + "\n")
    for relative in (
        "dashboard-private/company-source-backfill-v2/part.zip",
        "dashboard-private/investor-history/objects/part.gz",
        "dashboard-private/company-research-cache/git/x",
        "superinvestor-letters/fund/letter.md",
        "podcasts/ep.txt",
        "videos/clip.txt",
        f"dashboard-private/objects/{named}",
        f"dashboard-private/objects/{orphan}",
    ):
        assert not (work / relative).exists(), relative
    assert (work / "dashboard-private/manifest.json").is_file()
    assert (work / "dashboard-private/migration-journal.jsonl").is_file()

    manifest = {"assets": {"data/core.json": {"private_sha256": named, "public_sha256": "c" * 64}}}
    patterns = "\n".join(object_patterns(manifest)) + "\n"
    _git(work, "sparse-checkout", "add", "--skip-checks", "--stdin", input_text=patterns)
    assert (work / f"dashboard-private/objects/{named}").read_text(encoding="utf-8") == "snapshot"
    assert not (work / f"dashboard-private/objects/{orphan}").exists()
    assert not (work / "dashboard-private/company-source-backfill-v2/part.zip").exists()

    (work / "dashboard-private/manifest.json").write_text(json.dumps({"ok": 1}) + "\n", encoding="utf-8")
    _git(work, "add", "--force", "--", "dashboard-private")
    staged = _git(work, "diff", "--cached", "--name-status")
    assert staged.strip() == "M\tdashboard-private/manifest.json"
