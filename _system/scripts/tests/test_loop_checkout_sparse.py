"""The epistemic loops check out a narrow tree and still publish without deleting omitted files."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import loop_checkout_sparse as loop

WORKFLOWS = ROOT / ".github" / "workflows"
LOOPS = {
    "memory-digest.yml": ("triage", 1),
    "falsifier-resolution.yml": ("resolve-and-validate", 0),
    "committee-outcomes.yml": ("observe", 1),
}
MATERIALIZE = "Materialize cited sources and registered feeds"
PUSH_FILES = (
    "_system/scripts/ci_push_main.sh",
    "_system/scripts/audit_fund_letter_exposure.py",
    "_system/scripts/compact_dated_artifacts.py",
    "_system/scripts/atomic_io.py",
)


def _git(repo: Path, *args: str, input_text: str | None = None, env: dict | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text, capture_output=True, text=True, check=False, env=env,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def _steps(name: str) -> list[dict]:
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    job = LOOPS[name][0] if name in LOOPS else "measure"
    return document["jobs"][job]["steps"]


def _main_checkout(steps: list[dict]) -> dict:
    return next(step for step in steps if str(step.get("uses", "")).startswith("actions/checkout"))


def _index(steps: list[dict], predicate) -> int:
    return next(i for i, step in enumerate(steps) if predicate(step))


def test_each_loop_checks_out_the_shared_patterns_blobless():
    for name, (_, depth) in {**LOOPS, "loop-checkout-size.yml": (None, None)}.items():
        checkout = _main_checkout(_steps(name))["with"]
        assert checkout["filter"] == "blob:none", name
        assert str(checkout["sparse-checkout-cone-mode"]).lower() == "false", name
        lines = [line for line in checkout["sparse-checkout"].splitlines() if line.strip()]
        assert tuple(lines) == loop.CHECKOUT_PATTERNS, name
        if depth is not None:
            assert checkout["fetch-depth"] == depth, name


def test_extra_inputs_land_before_hydration_and_before_any_loop_script():
    for name in (*LOOPS, "loop-checkout-size.yml"):
        steps = _steps(name)
        checkout = _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/checkout"))
        materialize = _index(steps, lambda s: s.get("name") == MATERIALIZE)
        run = steps[materialize]["run"]
        assert "set -euo pipefail" in run, name
        assert "python3 _system/scripts/loop_checkout_sparse.py >" in run, name
        assert "git sparse-checkout add --skip-checks --stdin <" in run, name
        assert checkout < materialize, name
        later = [s for s in steps[:materialize] if "_system/scripts/" in str(s.get("run", ""))]
        assert not later, name
        if name in LOOPS:
            vault = _index(steps, lambda s: str(s.get("uses", "")).endswith("checkout-vault"))
            commit = _index(steps, lambda s: str(s.get("uses", "")).endswith("commit-main"))
            assert materialize < vault < commit, name


def test_derived_artifacts_live_under_research():
    config = json.loads((ROOT / "_system/graph/graph_sources.json").read_text(encoding="utf-8"))
    for name, entry in config["derived_artifacts"].items():
        if name.startswith("_"):
            continue
        for key in ("source", "derived"):
            assert str(entry[key]).startswith("research/"), (name, key)


def test_escape_keeps_a_cited_name_literal():
    assert loop.escape("A/b c.pdf") == "/A/b c.pdf"
    assert loop.escape("A/x*[1]?.htm") == "/A/x\\*\\[1]\\?.htm"
    assert loop.escape("A/back\\slash") == "/A/back\\\\slash"
    assert loop.escape("A/trailing ") == "/A/trailing\\ "


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _publish_paths() -> set[str]:
    paths = set()
    for name in LOOPS:
        for step in _steps(name):
            if str(step.get("uses", "")).endswith("commit-main"):
                paths.update(str(step["with"]["git_add"]).split())
    paths.discard("-A")
    return paths


SEED = {
    "README.md": "readme\n",
    ".gitattributes": "* text=auto\n",
    "AAA/README.md": "aaa\n",
    "AAA/research/valuation.json": "{}\n",
    "AAA/research/valuation_fact_ledger.json": "{\"facts\": []}\n",
    "AAA/research/falsifier_specs.json": "{\"specs\": []}\n",
    "AAA/research/evidence/sec_companyfacts.json": "{}\n",
    "AAA/investor-documents/sec-edgar/20-F_20260301_rpt.htm": "<p>cover</p>\n",
    "AAA/investor-documents/sec-edgar/10-K_20260301_rpt.htm": "<p>annual</p>\n",
    "BBB/research/valuation.json": "{}\n",
    "BBB/investor-documents/cited.htm": "<p>cited</p>\n",
    "BBB/investor-documents/large.pdf": "PDF-1\n",
    "CCC/official-reports/report.pdf": "PDF\n",
    "_system/memory/MEMORY.md": (
        "## Approved beliefs \u2014 Charlie Munger\n\n"
        "- A cited claim. \u2014 `BBB/investor-documents/cited.htm` `[active 2026-08-09 \u00b7 agent]`\n"
    ),
    "_system/graph/graph_sources.json": json.dumps({
        "data_feeds": {"_doc": "x", "feed": {"path": "dashboard/data/feed.json", "max_age_hours": 48}},
        "live_feeds": {"log": {"evidence_path": "~/monitor.log"}},
    }) + "\n",
    "_system/data/other.json": "{}\n",
    "_system/reference/market-data/fx_rates.json": "{}\n",
    "_system/reference/activist-reports/firm/report.pdf": "PDF\n",
    "_system/reference/investment-wisdom/munger/talk.pdf": "PDF\n",
    "dashboard/data/core.json": "{\"private_snapshot\":true}\n",
    "dashboard/data/feed.json": "{\"generated_at\": \"2026-10-31\"}\n",
    "dashboard/index.html": "<html></html>\n",
    "dashboard/private-assets.json": "",
}
OMITTED = (
    "AAA/investor-documents/sec-edgar/10-K_20260301_rpt.htm",
    "BBB/investor-documents/large.pdf",
    "CCC/official-reports/report.pdf",
    "_system/reference/activist-reports/firm/report.pdf",
    "_system/reference/investment-wisdom/munger/talk.pdf",
    "dashboard/data/core.json",
    "dashboard/index.html",
)


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "config", "user.email", "t@example.com")
    _git(seed, "config", "user.name", "t")
    core = SEED["dashboard/data/core.json"].encode("utf-8")
    manifest = {"assets": {"data/core.json": {
        "private_sha256": "a" * 64, "public_sha256": hashlib.sha256(core).hexdigest()}}}
    files = dict(SEED, **{"dashboard/private-assets.json": json.dumps(manifest) + "\n"})
    for relative in sorted(_publish_paths()):
        files.setdefault(relative if Path(relative).suffix else relative + "/run.json", "{}\n")
    for relative, content in files.items():
        _write(seed, relative, content)
    for relative in PUSH_FILES:
        (seed / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, seed / relative)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _write(seed, "_system/data/other.json", "{\"day\": 2}\n")
    _git(seed, "commit", "-q", "-am", "second")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)], check=True)
    _git(origin, "config", "uploadpack.allowFilter", "true")
    _git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
    return seed, origin


def _loop_clone(origin: Path, work: Path, depth: int) -> None:
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "remote", "add", "origin", origin.as_uri())
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    depth_args = [f"--depth={depth}"] if depth else []
    _git(work, "fetch", "-q", "--no-tags", *depth_args, "--filter=blob:none", "origin",
         "+refs/heads/main:refs/remotes/origin/main")
    _git(work, "config", "remote.origin.promisor", "true")
    _git(work, "config", "remote.origin.partialclonefilter", "blob:none")
    _git(work, "sparse-checkout", "set", "--no-cone", "--stdin",
         input_text="\n".join(loop.CHECKOUT_PATTERNS) + "\n")
    _git(work, "checkout", "-q", "-B", "main", "refs/remotes/origin/main")


def test_static_patterns_hold_every_publish_and_push_input(tmp_path):
    _, origin = _seed(tmp_path)
    work = tmp_path / "work"
    _loop_clone(origin, work, 1)
    needed = set(_publish_paths()) | set(PUSH_FILES) | {
        "dashboard/private-assets.json", ".gitattributes",
        "_system/reference/market-data/fx_rates.json", "_system/graph/graph_sources.json",
        "_system/memory/MEMORY.md", "AAA/research/evidence/sec_companyfacts.json",
    }
    for relative in sorted(needed):
        assert (work / relative).exists(), relative
    for relative in OMITTED + ("BBB/investor-documents/cited.htm", "dashboard/data/feed.json",
                               "AAA/investor-documents/sec-edgar/20-F_20260301_rpt.htm"):
        assert not (work / relative).exists(), relative


def test_extra_patterns_materialize_citations_feeds_and_cover_filings(tmp_path):
    _, origin = _seed(tmp_path)
    work = tmp_path / "work"
    _loop_clone(origin, work, 1)
    patterns = loop.extra_patterns(work)
    assert "/BBB/investor-documents/cited.htm" in patterns
    assert "/dashboard/data/feed.json" in patterns
    assert "/AAA/investor-documents/sec-edgar/20-F_*.htm*" in patterns
    assert not any("monitor.log" in pattern for pattern in patterns)
    _git(work, "sparse-checkout", "add", "--skip-checks", "--stdin", input_text="\n".join(patterns) + "\n")
    assert (work / "BBB/investor-documents/cited.htm").read_text(encoding="utf-8") == "<p>cited</p>\n"
    assert (work / "dashboard/data/feed.json").is_file()
    assert (work / "AAA/investor-documents/sec-edgar/20-F_20260301_rpt.htm").is_file()
    for relative in OMITTED:
        assert not (work / relative).exists(), relative


def test_narrow_checkout_add_all_commit_and_shallow_rebase_keep_omitted_files(tmp_path):
    """The falsifier stages with -A. Main moves while the loop runs; the push rebases onto it."""
    for depth in (1, 0):
        lane = tmp_path / f"depth-{depth}"
        lane.mkdir()
        _, origin = _seed(lane)
        work = lane / "work"
        _loop_clone(origin, work, depth)
        patterns = loop.extra_patterns(work)
        _git(work, "sparse-checkout", "add", "--skip-checks", "--stdin", input_text="\n".join(patterns) + "\n")

        # Another lane lands on main: one omitted file and one in-cone file change.
        upstream = lane / "upstream"
        subprocess.run(["git", "clone", "-q", str(origin), str(upstream)], check=True)
        _git(upstream, "config", "user.email", "u@example.com")
        _git(upstream, "config", "user.name", "u")
        _write(upstream, "BBB/investor-documents/large.pdf", f"PDF-{depth + 2}\n")
        _write(upstream, "_system/data/other.json", f"{{\"day\": {depth + 3}}}\n")
        _git(upstream, "commit", "-q", "-am", "other lane")
        _git(upstream, "push", "-q", "origin", "HEAD:main")
        moved = _git(upstream, "rev-parse", "HEAD").strip()

        _write(work, "AAA/research/valuation_fact_ledger.json", f"{{\"facts\": [{depth}]}}\n")
        _write(work, "AAA/research/falsifier_drafts/new.json", "{}\n")
        _write(work, "_system/graph/INVARIANTS.md", "report\n")
        _git(work, "add", "--sparse", "-A")
        staged = _git(work, "diff", "--cached", "--name-status").splitlines()
        assert sorted(staged) == sorted([
            "M\tAAA/research/valuation_fact_ledger.json",
            "A\tAAA/research/falsifier_drafts/new.json",
            "A\t_system/graph/INVARIANTS.md",
        ]), staged

        env = dict(os.environ, PYTHON=sys.executable, CI_PUSH_SKIP_SELF_REFRESH="1",
                   GIT_AUTHOR_NAME="bot", GIT_AUTHOR_EMAIL="bot@example.com")
        env.pop("GITHUB_ACTIONS", None)
        push = subprocess.run(["bash", "_system/scripts/ci_push_main.sh", "loop commit"],
                              cwd=work, env=env, capture_output=True, text=True, check=False)
        assert push.returncode == 0, push.stdout + push.stderr
        assert "Pushed to main" in push.stdout

        head = _git(origin, "rev-parse", "main").strip()
        assert _git(origin, "rev-parse", f"{head}^").strip() == moved
        changes = _git(origin, "diff", "--name-status", moved, head).splitlines()
        assert sorted(changes) == sorted(staged), changes
        tree = set(_git(origin, "ls-tree", "-r", "--name-only", head).splitlines())
        for relative in OMITTED:
            assert relative in tree, relative
        assert _git(origin, "show", f"{head}:BBB/investor-documents/large.pdf") == f"PDF-{depth + 2}\n"
        assert _git(origin, "show", f"{head}:_system/data/other.json") == f"{{\"day\": {depth + 3}}}\n"
