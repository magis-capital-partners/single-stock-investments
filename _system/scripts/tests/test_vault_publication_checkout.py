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
PUBLICATION_CALLERS = set(LOOPS) | {
    "vault-publication-checkout.yml",
    "research-quality.yml",
    # Data Pipeline jobs that do not read the letter corpus. Drive adds
    # vic-research and the insight indexes through extra-paths. The company
    # source lane adds only its archive the same way.
    "data-pipeline.yml",
    "company-source-backfill.yml",
    # The hub validation job reads the immutable published snapshot objects.
    "python-tests.yml",
}


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


def test_default_archive_reader_keeps_corpora_and_omits_historical_parts(tmp_path):
    from vault_source_archive_sparse import part_patterns
    action=_action()
    patterns=_patterns("publication-only != 'true'")
    exclusion='!/dashboard-private/company-source-backfill-v2/*'
    assert exclusion in patterns
    step=next(s for s in action['runs']['steps'] if s.get('name')=='Materialize current source archive parts')
    assert "inputs.include-source-archive == 'true'" in step['if']
    assert 'manifest.json' in step['run'] and 'sparse-checkout add' in step['run']
    vault=tmp_path/'vault';vault.mkdir()
    _git(vault,'init','-q','-b','main')
    _git(vault,'config','user.email','fixture@example.invalid')
    _git(vault,'config','user.name','Fixture')
    prefix='dashboard-private/company-source-backfill-v2'
    folder=vault/prefix;folder.mkdir(parents=True)
    current='a'*64+'.zip'; historical='b'*64+'.zip'
    (folder/current).write_bytes(b'current immutable input')
    (folder/historical).write_bytes(b'historical immutable input')
    manifest={'parts':[{'file':current,'sha256':'a'*64}]}
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    (vault/'superinvestor-letters').mkdir()
    (vault/'superinvestor-letters/letter.md').write_text('Keep the full corpus')
    _git(vault,'add','-A');_git(vault,'commit','-q','-m','fixture')
    _git(vault,'sparse-checkout','set','--no-cone','--stdin',input_text='/*\n'+exclusion+'\n')
    assert not (folder/current).exists() and not (folder/historical).exists()
    selected=['/'+prefix+'/manifest.json',*part_patterns(manifest)]
    _git(vault,'sparse-checkout','add','--stdin',input_text='\n'.join(selected)+'\n')
    assert (folder/current).read_bytes()==b'current immutable input'
    assert not (folder/historical).exists()
    assert (vault/'superinvestor-letters/letter.md').read_text()=='Keep the full corpus'
    assert _git(vault,'ls-files','-v',prefix+'/'+historical).startswith('S ')
    _git(vault,'add','--sparse','--force','--','dashboard-private')
    assert not _git(vault,'diff','--cached','--name-status').strip()


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

    opted = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                uses = str(step.get("uses") or "")
                chosen = (step.get("with") or {}).get("publication-only")
                if uses.endswith("checkout-vault") and str(chosen).lower() == "true":
                    opted.add(path.name)
                if uses.endswith("commit-main"):
                    cache = (step.get("with") or {}).get("preserve-company-cache")
                    if path.name in LOOPS and job_name == LOOPS[path.name]:
                        assert str(cache).lower() == "false", path.name
                    elif cache is not None:
                        raise AssertionError(f"{path.name}:{job_name} sets preserve-company-cache")
    assert opted == PUBLICATION_CALLERS
    python = yaml.safe_load((WORKFLOWS / "python-tests.yml").read_text(encoding="utf-8"))
    python_readers = [
        name for name, job in python["jobs"].items()
        for step in job.get("steps", [])
        if str((step.get("with") or {}).get("publication-only")).lower() == "true"
    ]
    assert python_readers == ["hub-payloads"]
    quality = yaml.safe_load((WORKFLOWS / "research-quality.yml").read_text(encoding="utf-8"))
    # Only validation of already published data may use the scoped snapshot.
    # Keep research-producing jobs on their existing evidence boundary.
    quality_readers = [
        name for name, job in quality["jobs"].items()
        for step in job.get("steps", [])
        if str((step.get("with") or {}).get("publication-only")).lower() == "true"
    ]
    assert quality_readers == ["dashboard-integrity"]
    for name, job_name in LOOPS.items():
        document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
        step = next(step for step in document["jobs"][job_name]["steps"] if str(step.get("uses") or "").endswith("checkout-vault"))
        assert str(step["with"]["publication-only"]).lower() == "true"


def test_sparse_vault_add_keeps_objects_that_were_not_checked_out(tmp_path):
    """Buyback run 41433311840 refreshed private shards, then commit-main
    refused to stage the new object hashes. --sparse stages those files and
    leaves the hashes that were not checked out in the index."""
    action = (ROOT / ".github/actions/preserve-private-dashboard/action.yml").read_text(encoding="utf-8")
    assert 'git -C "$vault" add --sparse --force -- dashboard-private' in action

    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.email", "t@example.com")
    _git(origin, "config", "user.name", "t")
    kept = origin / "dashboard-private/objects/bbb"
    kept.parent.mkdir(parents=True)
    kept.write_text("kept", encoding="utf-8")
    (origin / "dashboard-private/objects/aaa").write_text("old", encoding="utf-8")
    (origin / "dashboard-private/manifest.json").write_text("{}\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "fixture")
    work = tmp_path / "work"
    _git(origin, "clone", "-q", "--sparse", str(origin), str(work))
    _git(work, "sparse-checkout", "init", "--no-cone")
    _git(
        work,
        "sparse-checkout",
        "set",
        "--no-cone",
        "--stdin",
        input_text="/dashboard-private/manifest.json\n/dashboard-private/objects/aaa\n",
    )
    (work / "dashboard-private/objects/ccc").write_text("new", encoding="utf-8")
    (work / "dashboard-private/manifest.json").write_text('{"ok":1}\n', encoding="utf-8")
    _git(work, "add", "--sparse", "--force", "--", "dashboard-private")
    staged = _git(work, "diff", "--cached", "--name-status")
    assert "A\tdashboard-private/objects/ccc" in staged
    assert "M\tdashboard-private/manifest.json" in staged
    assert "dashboard-private/objects/bbb" not in staged
    assert _git(work, "ls-files", "-v", "dashboard-private/objects/bbb").startswith("S ")


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

def test_snapshot_scope_matches_existing_hydration_input_selection(tmp_path):
    from vault_publication_sparse import publication_entries
    selected=tmp_path/'dashboard/data/core.json';selected.parent.mkdir(parents=True);selected.write_text('{"private_snapshot":true}')
    model=tmp_path/'_system/data/model.json';model.parent.mkdir(parents=True);model.write_text('{"private_snapshot":true}')
    manifest={'assets':{'data/core.json':{'private_sha256':'a'*64},'data/tickers/OTHER.json':{'private_sha256':'b'*64}},'repository_assets':{'_system/data/model.json':{'private_sha256':'c'*64},'_system/data/unselected.json':{'private_sha256':'d'*64}}}
    assert object_patterns(manifest,tmp_path)==['/dashboard-private/objects/'+'a'*64,'/dashboard-private/objects/'+'c'*64]
    assert len(object_patterns(manifest))==4
    assert {r[1] for r in publication_entries(manifest,tmp_path)}=={'data/core.json','_system/data/model.json'}

def test_scoped_manifest_still_rejects_bad_receipts_and_escaped_paths(tmp_path):
    import pytest
    for name,identity in [('data/not-selected.json','bad'),('../escape.json','a'*64)]:
        with pytest.raises(ValueError):object_patterns({'assets':{name:{'private_sha256':identity}}},tmp_path)

def test_snapshot_validation_is_read_only_and_opt_in_for_hub():
    action=_action();assert action['inputs']['snapshot-validation-only']['default']=='false'
    step=next(s for s in action['runs']['steps'] if s.get('name')=='Materialize the verified private catalog view')
    assert '--snapshot-validation-only' in step['run'] and 'test "$PUBLICATION_ONLY" = "true"' in step['run']
    objects=next(s for s in action['runs']['steps'] if s.get('name')=='Materialize publication objects')
    assert '--workspace "$GITHUB_WORKSPACE"' in objects['run'] and 'publication_entries(manifest, workspace)' in objects['run']
    workflow=yaml.safe_load((WORKFLOWS/'python-tests.yml').read_text(encoding='utf-8'))
    selected=[name for name,job in workflow['jobs'].items() for s in job.get('steps',[]) if (s.get('with') or {}).get('snapshot-validation-only')=='true']
    assert selected==['hub-payloads']


def test_full_manifest_validation_does_not_use_workspace_scope():
    objects=next(s for s in _action()["runs"]["steps"] if s.get("name")=="Materialize publication objects")
    assert objects["env"]["HYDRATE_PUBLICATION"]=="${{ inputs.hydrate }}"
    assert 'if [ "$HYDRATE_PUBLICATION" = "true" ]; then' in objects["run"]
    assert 'if os.environ["HYDRATE_PUBLICATION"] == "true" else None' in objects["run"]
    workflow=yaml.safe_load((WORKFLOWS/"vault-publication-checkout.yml").read_text(encoding="utf-8"))
    checkout=next(s for s in workflow["jobs"]["publication-objects"]["steps"] if s.get("uses")=="./.github/actions/checkout-vault")
    assert checkout["with"]["hydrate"]=="false"
