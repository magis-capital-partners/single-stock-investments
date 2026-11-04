"""Contract tests for .github/workflows/research-quality.yml.

The `changes` job's classifier is JavaScript run by actions/github-script. The
tests execute it in node with a stub `context`/`github`/`core`, so they check
what the job decides, not how the source looks.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "research-quality.yml"

HARNESS = r"""
const fs = require('fs');
const [scriptPath, eventName, filesJson, payloadJson] = process.argv.slice(2);
const files = JSON.parse(filesJson);
const outputs = {};
const summary = { addHeading() { return this; }, addTable() { return this; }, async write() {} };
const core = { setOutput: (key, value) => { outputs[key] = value; }, summary };
const payload = payloadJson
  ? JSON.parse(payloadJson)
  : (eventName === 'pull_request' ? { pull_request: { number: 1 } } : {});
const context = { eventName, payload, repo: { owner: 'o', repo: 'r' } };
const github = {
  paginate: async () => files.map(filename => ({ filename })),
  rest: { pulls: { listFiles: () => {} } },
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('github', 'context', 'core', fs.readFileSync(scriptPath, 'utf8'))(github, context, core)
  .then(() => console.log(JSON.stringify(outputs)))
  .catch(error => { console.error(error); process.exit(1); });
"""


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def triggers() -> dict:
    data = load()
    return data.get("on", data.get(True))  # PyYAML reads the bare `on:` key as True


def classify(tmp_path: Path, event: str, files: list[str], payload: dict | None = None) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    steps = load()["jobs"]["changes"]["steps"]
    script = next(step["with"]["script"] for step in steps if step.get("with", {}).get("script"))
    (tmp_path / "classify.js").write_text(script, encoding="utf-8")
    (tmp_path / "harness.js").write_text(HARNESS, encoding="utf-8")
    cmd = [node, str(tmp_path / "harness.js"), str(tmp_path / "classify.js"), event, json.dumps(files)]
    if payload is not None:
        cmd.append(json.dumps(payload))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_main_head_is_tested_on_a_schedule_off_the_hour():
    """Bot pushes use GITHUB_TOKEN and start no workflow: after 2026-09-23 22:46
    nothing tested main for a day."""
    schedule = triggers()["schedule"]
    assert schedule, "research-quality needs a schedule"
    for entry in schedule:
        minute = entry["cron"].split()[0]
        assert minute.isdigit() and minute != "0", entry["cron"]


def test_a_scheduled_run_checks_main_like_a_push(tmp_path):
    outputs = classify(tmp_path, "schedule", [])
    assert outputs["graph_invariants"] == "true"
    assert outputs["fact_currency"] == "true"
    assert outputs["ssi_pipeline"] == "true"
    # The PR-only jobs need a base ref and stay off.
    assert outputs["research_lint"] == "false"
    assert outputs["dashboard_integrity"] == "false"


def test_a_pr_touching_only_a_falsifier_draft_runs_graph_invariants(tmp_path):
    """The CEG / #988 failure: a draft-only PR skipped the job that runs the
    history check's promotion simulation."""
    for draft in (
        "CEG/research/falsifier_drafts/f8685f88d1aff5b6b56d0eba.json",
        "CEG/research/falsifier_drafts/archive/old.json",
        "CEG/research/falsifier_drafts/README.md",
    ):
        outputs = classify(tmp_path, "pull_request", [draft])
        assert outputs["graph_invariants"] == "true", draft


def test_a_push_touching_only_a_falsifier_draft_triggers_the_workflow():
    assert "**/research/falsifier_drafts/**" in triggers()["push"]["paths"]


def test_the_history_job_runs_the_promotion_gate_suite_when_present():
    steps = load()["jobs"]["graph-invariants"]["steps"]
    history = next(s for s in steps if "immutable history" in str(s.get("name", "")))
    run = history["run"]
    assert "[ -f _system/scripts/tests/test_falsifier_promotion_gate.py ]" in run
    assert 'PROMOTION_GATE="tests.test_falsifier_promotion_gate"' in run
    assert "test_resolve_falsifiers $PROMOTION_GATE" in run


def test_a_pr_touching_only_a_deep_dive_skips_graph_invariants(tmp_path):
    outputs = classify(tmp_path, "pull_request", ["ABC/research/deep_dive_2026-09-01.md"])
    assert outputs["graph_invariants"] == "false"
    assert outputs["research_lint"] == "true"


def test_dispatch_is_not_a_manual_run_button():
    """workflow_dispatch adds a Run button. Governance forbids that outside
    an allowlist, and it is how run 36651667022 failed on main."""
    on = triggers()
    assert "workflow_dispatch" not in on
    assert on["repository_dispatch"]["types"] == ["research-quality-pr"]
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "format('research-quality-pr {0} {1}'" in text


def test_a_dispatch_classifies_the_named_pr(tmp_path):
    sha = "a" * 40
    outputs = classify(
        tmp_path,
        "repository_dispatch",
        ["ABC/research/deep_dive_2026-09-01.md"],
        {"client_payload": {"pr": "1074", "sha": sha}},
    )
    assert outputs["research_lint"] == "true"
    assert outputs["graph_invariants"] == "false"


def test_every_job_tests_the_exact_commit():
    data = load()
    assert data["env"]["CHECKOUT_SHA"] == (
        "${{ github.event.pull_request.head.sha || github.event.client_payload.sha || github.sha }}"
    )
    for name, job in data["jobs"].items():
        for step in job.get("steps", []):
            run = str(step.get("run", ""))
            if "ci_checkout_workspace.sh" in run:
                assert '"$CHECKOUT_SHA"' in run, f"{name}: {run}"
                assert "pull/${{" not in run, f"{name}: {run}"
            uses = str(step.get("uses", ""))
            is_bootstrap = "ci_checkout_workspace.sh" in str(step.get("with", {}).get("sparse-checkout", ""))
            if uses.startswith("actions/checkout") and not is_bootstrap:
                # A real checkout (not the bootstrap that fetches the checkout
                # scripts) pins the commit too.
                assert step["with"]["ref"] == "${{ env.CHECKOUT_SHA }}", name


def test_warrant_problems_do_not_red_unrelated_research_prs():
    """9/11-9/18: "warrants.json reports structural contract errors" failed
    every research PR's dashboard-integrity job. The warrant lane enforces;
    the PR gate reports. Checkers that predate --warn-only keep the old run."""
    steps = load()["jobs"]["dashboard-integrity"]["steps"]
    run = next(s["run"] for s in steps if "check_warrant_universe.py" in str(s.get("run", "")))
    assert 'check_warrant_universe.py --help | grep -q -- "--warn-only"' in run
    assert "check_warrant_universe.py --warn-only" in run


def history_step() -> dict:
    steps = load()["jobs"]["graph-invariants"]["steps"]
    return next(s for s in steps if "immutable history" in str(s.get("name", "")))


def test_a_scheduled_run_judges_everything_since_the_previous_scheduled_run():
    """HISTORY_BASE="HEAD" compared HEAD with itself and checked nothing."""
    step = history_step()
    run = step["run"]
    assert 'HISTORY_BASE="HEAD"\n' not in run
    assert "actions/workflows/research-quality.yml/runs?event=schedule&status=completed" in run
    assert "select(.id != ${{ github.run_id }})" in run
    assert 'HISTORY_BASE="HEAD~1"' in run
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert load()["permissions"]["actions"] == "read"


def run_history_selection(tmp_path: Path, gh_says: str) -> tuple[str, dict[str, str]]:
    """Run the step's base-selection lines for a schedule event, with a fake gh."""
    bash = shutil.which("bash")
    git = shutil.which("git")
    if not bash or not git:
        pytest.skip("needs bash and git")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    shas = {}
    subprocess.run([git, "init", "-q", "-b", "main"], cwd=repo, env=env, check=True)
    for name in ("c1", "c2", "c3"):
        (repo / name).write_text(name, encoding="utf-8")
        subprocess.run([git, "add", "-A"], cwd=repo, env=env, check=True)
        subprocess.run([git, "commit", "-q", "-m", name], cwd=repo, env=env, check=True)
        shas[name] = subprocess.run([git, "rev-parse", "HEAD"], cwd=repo, env=env, check=True,
                                    capture_output=True, text=True).stdout.strip()
    lines = history_step()["run"].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('HISTORY_BASE="origin/main"'))
    end = next(i for i in range(start, len(lines)) if lines[i] == "fi")
    snippet = "\n".join(lines[start:end + 1]) + '\necho "BASE=$HISTORY_BASE"\n'
    for expr, value in (("${{ github.event_name }}", "schedule"),
                        ("${{ github.event.before }}", "0" * 40),
                        ("${{ github.repository }}", "o/r"),
                        ("${{ github.run_id }}", "999")):
        snippet = snippet.replace(expr, value)
    fake = tmp_path / "bin"
    fake.mkdir(parents=True)
    (fake / "gh").write_text(f"#!/usr/bin/env bash\necho '{shas.get(gh_says, gh_says)}'\n", encoding="utf-8",
                             newline="\n")
    (fake / "gh").chmod(0o755)
    (tmp_path / "snippet.sh").write_text(snippet, encoding="utf-8", newline="\n")
    env["PATH"] = str(fake) + os.pathsep + env["PATH"]
    proc = subprocess.run([bash, str(tmp_path / "snippet.sh")], cwd=repo, env=env,
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    base = next(line[5:] for line in proc.stdout.splitlines() if line.startswith("BASE="))
    return base, shas


def test_the_previous_scheduled_runs_sha_is_the_base(tmp_path):
    base, shas = run_history_selection(tmp_path, "c1")
    assert base == shas["c1"]


def test_no_usable_previous_run_falls_back_to_the_last_commit(tmp_path):
    base, _ = run_history_selection(tmp_path, "")
    assert base == "HEAD~1"
    base, _ = run_history_selection(tmp_path / "unknown", "f" * 40)
    assert base == "HEAD~1"


def checkout_run(job: str) -> str:
    steps = load()["jobs"][job]["steps"]
    return next(str(s["run"]) for s in steps if "ci_checkout_workspace.sh" in str(s.get("run", "")))


def test_scheduled_jobs_no_longer_check_out_the_full_tree():
    """The ~53 GiB tree timed out fact-ledger-currency after 45 minutes (run
    41710891780) and ran graph-invariants out of disk (run 41795979498)."""
    assert "ci_checkout_workspace.sh fact_currency " in checkout_run("fact-ledger-currency")
    assert "ci_checkout_workspace.sh graph_invariants " in checkout_run("graph-invariants")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ci_checkout_workspace.sh full" not in text
    for job in ("fact-ledger-currency", "graph-invariants"):
        step = next(s for s in load()["jobs"][job]["steps"] if "ci_checkout_workspace.sh" in str(s.get("run", "")))
        assert step.get("timeout-minutes"), job


def test_graph_invariants_keeps_the_lane_history_deepen():
    steps = load()["jobs"]["graph-invariants"]["steps"]
    names = [str(s.get("name", "")) for s in steps]
    checkout = next(i for i, n in enumerate(names) if n.startswith("Checkout workspace"))
    deepen = next(i for i, n in enumerate(names) if n.startswith("Deepen commit history"))
    assert checkout < deepen
    assert "--deepen=400" in steps[deepen]["run"]


def test_a_pr_changing_the_checkout_wiring_runs_both_checkout_jobs(tmp_path):
    for name in (
        ".github/workflows/research-quality.yml",
        "_system/scripts/ci_checkout_workspace.sh",
        "_system/scripts/ci_resolve_checkout_ref.sh",
        "_system/scripts/ci_sparse_checkout_paths.py",
    ):
        outputs = classify(tmp_path, "pull_request", [name])
        assert outputs["fact_currency"] == "true", name
        assert outputs["graph_invariants"] == "true", name
        assert name in triggers()["pull_request"]["paths"], name
        assert name in triggers()["push"]["paths"], name


CHECKOUT_SCRIPTS = (
    "ci_checkout_workspace.sh",
    "ci_resolve_checkout_ref.sh",
    "ci_sparse_checkout_paths.py",
)

# Stands in for graph_build in the fixture repo: every fact-ledger ref is a
# Source node, missing when it is not on disk, as in the real builder.
FAKE_GRAPH_BUILD = '''
import json
from pathlib import Path


class GraphBuilder:
    def __init__(self, root):
        self.root = Path(root)
        self.nodes = {}

    def build(self):
        for ledger in sorted(self.root.glob("*/research/valuation_fact_ledger.json")):
            for fact in json.loads(ledger.read_text(encoding="utf-8"))["facts"]:
                ref = fact["source"]["ref"]
                exists = (self.root / ref).exists()
                self.nodes["source:" + ref] = {"type": "Source", "path": ref,
                                               "status": "present" if exists else "missing"}
'''


def run_profile(tmp_path: Path, profile: str, files: dict[str, str]) -> set[str]:
    """Run ci_checkout_workspace.sh against a fixture origin; return the worktree files."""
    git = shutil.which("git")
    if not git or not shutil.which("bash"):
        pytest.skip("needs bash and git")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    for key in ("GITHUB_WORKSPACE", "GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_REF_NAME", "GITHUB_HEAD_REF"):
        env.pop(key, None)
    origin = tmp_path / "origin"
    files = dict(files)
    for name in CHECKOUT_SCRIPTS:
        files[f"_system/scripts/{name}"] = (ROOT / "_system" / "scripts" / name).read_text(encoding="utf-8")
    files["_system/scripts/graph_build.py"] = FAKE_GRAPH_BUILD
    for rel, content in files.items():
        path = origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run(cwd: Path, *args: str, stdin: str | None = None) -> str:
        proc = subprocess.run([git, *args], cwd=cwd, env=env, input=stdin,
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, (args, proc.stderr)
        return proc.stdout

    run(origin, "init", "-q", "-b", "main")
    run(origin, "config", "uploadpack.allowFilter", "true")
    run(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
    run(origin, "add", "-A")
    run(origin, "commit", "-q", "-m", "fixture")
    sha = run(origin, "rev-parse", "HEAD").strip()

    # The workflow's bootstrap: actions/checkout of the three checkout scripts.
    work = tmp_path / "work"
    work.mkdir()
    run(work, "init", "-q")
    run(work, "remote", "add", "origin", origin.as_uri())
    run(work, "sparse-checkout", "init", "--no-cone")
    run(work, "sparse-checkout", "set", "--stdin",
        stdin="".join(f"/_system/scripts/{name}\n" for name in CHECKOUT_SCRIPTS))
    run(work, "fetch", "-q", "--depth=1", "--filter=blob:none", "origin", sha)
    run(work, "checkout", "-q", "--detach", "FETCH_HEAD")

    proc = subprocess.run(["bash", "_system/scripts/ci_checkout_workspace.sh", profile, sha],
                          cwd=work, env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return {
        path.relative_to(work).as_posix()
        for path in work.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(work).parts
    }


def test_fact_currency_checks_out_what_the_scan_opens(tmp_path):
    present = run_profile(tmp_path, "fact_currency", {
        "AAA/research/valuation.json": "{}",
        "AAA/research/valuation_fact_ledger.json": "{}",
        "AAA/research/evidence/sec_companyfacts.json": "{}",
        "BBB/research/evidence/archive/old_sec_companyfacts.json": "{}",
        "AAA/research/thesis.md": "t",
        "AAA/research/evidence/filing_digest.md": "d",
        "AAA/investor-documents/sec-edgar/10-K.htm": "filing",
        "_system/scripts/scan_fact_ledger_currency.py": "",
        "_system/data/big.json": "{}",
        ".github/workflows/w.yml": "on: push",
    })
    for rel in (
        "AAA/research/valuation.json",
        "AAA/research/valuation_fact_ledger.json",
        "AAA/research/evidence/sec_companyfacts.json",
        # Any ref ending in sec_companyfacts.json is one the scanner resolves.
        "BBB/research/evidence/archive/old_sec_companyfacts.json",
        "_system/scripts/scan_fact_ledger_currency.py",
        ".github/workflows/w.yml",
    ):
        assert rel in present, rel
    for rel in (
        "AAA/research/thesis.md",
        "AAA/research/evidence/filing_digest.md",
        "AAA/investor-documents/sec-edgar/10-K.htm",
        "_system/data/big.json",
    ):
        assert rel not in present, rel


def test_graph_invariants_checks_out_its_trees_and_only_the_cited_filings(tmp_path):
    cited = "AAA/investor-documents/sec-edgar/10-K [2025] *final*.htm"
    ledger = {"facts": [
        {"locked": True, "source": {"ref": cited}},
        {"locked": True, "source": {"ref": "AAA/research/evidence/sec_companyfacts.json"}},
        {"locked": True, "source": {"ref": "AAA/investor-documents/never-committed.pdf"}},
    ]}
    sources = {"feeds": [{"path": "dashboard/data/insights/podcasts.json"}, {"path": "dashboard/data/tickers"}]}
    present = run_profile(tmp_path, "graph_invariants", {
        "README.md": "root doc",
        "AAA/README.md": "a",
        "AAA/research/valuation_fact_ledger.json": json.dumps(ledger),
        "AAA/research/evidence/sec_companyfacts.json": "{}",
        "AAA/research/evidence/_text/10-K.txt": "text",
        cited: "cited filing",
        "AAA/investor-documents/sec-edgar/10-Q.htm": "uncited filing",
        "AAA/third-party-analyses/report.pdf": "pdf",
        "AAA/official-reports/annual.pdf": "pdf",
        # A folder with no top-level file still has to be listed.
        "BBB/sub/only.txt": "only",
        "_system/scripts/x.py": "",
        "_system/memory/MEMORY.md": "beliefs",
        "_system/graph/graph_sources.json": json.dumps(sources),
        "_system/reference/activist-reports/AAA/report.pdf": "pdf",
        "_system/reference/investment-wisdom/INDEX.md": "wisdom",
        "dashboard/index.html": "html",
        "dashboard/data/insights/podcasts.json": "{}",
        "dashboard/data/tickers/AAA.json": "{}",
        "dashboard/data/aggregates/big.json": "{}",
        "docs/RETIRED.md": "retired",
        ".github/workflows/w.yml": "on: push",
    })
    for rel in (
        "README.md",
        "AAA/README.md",
        "AAA/research/valuation_fact_ledger.json",
        "AAA/research/evidence/_text/10-K.txt",
        cited,
        "BBB/sub/only.txt",
        "_system/scripts/x.py",
        "_system/memory/MEMORY.md",
        "_system/reference/investment-wisdom/INDEX.md",
        "dashboard/index.html",
        "dashboard/data/insights/podcasts.json",
        "dashboard/data/tickers/AAA.json",
        "docs/RETIRED.md",
        ".github/workflows/w.yml",
    ):
        assert rel in present, rel
    for rel in (
        "AAA/investor-documents/sec-edgar/10-Q.htm",
        "AAA/third-party-analyses/report.pdf",
        "AAA/official-reports/annual.pdf",
        "_system/reference/activist-reports/AAA/report.pdf",
        "dashboard/data/aggregates/big.json",
    ):
        assert rel not in present, rel
