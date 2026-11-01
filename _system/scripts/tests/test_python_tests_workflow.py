"""Contract tests for .github/workflows/python-tests.yml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "python-tests.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def triggers() -> dict:
    data = load()
    return data.get("on", data.get(True))


def covered(path: str, filters: list[str]) -> bool:
    """Is a sparse-checkout entry covered by an `on.<event>.paths` filter?

    Only the two filter shapes this workflow uses: an exact file, or `dir/**`.
    """
    for pattern in filters:
        if pattern.endswith("/**") and (path + "/").startswith(pattern[:-2]):
            return True
        if pattern == path:
            return True
    return False


def sparse_entries() -> list[str]:
    job = load()["jobs"]["unit-tests"]
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    entries = []
    for line in checkout["with"]["sparse-checkout"].splitlines():
        line = line.strip()
        if line and not line.startswith("!"):
            entries.append(line.strip("/"))
    return entries


def test_every_file_the_suites_read_triggers_the_workflow():
    """dashboard/data/criticality_summary.json was read but not a trigger."""
    for event in ("pull_request", "push"):
        filters = triggers()[event]["paths"]
        missing = [entry for entry in sparse_entries() if not covered(entry, filters)]
        assert not missing, f"{event} paths miss {missing}"


def test_investor_identity_references_survive_the_reference_corpus_exclusion(tmp_path):
    """The broad _system entry alone does not override the reference exclusion."""
    import subprocess

    required = (
        "_system/reference/investors/public_roster.json",
        "_system/reference/investors/manager_aliases.json",
        "_system/reference/investors/historical_filers.json",
    )
    excluded = "_system/reference/unrelated-corpus/large.json"
    for relative in (*required, excluded):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    def git(*args, **kwargs):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                              capture_output=True, **kwargs)

    git("init")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "fixture")
    checkout = next(s for s in load()["jobs"]["unit-tests"]["steps"]
                    if str(s.get("uses", "")).startswith("actions/checkout"))
    git("sparse-checkout", "set", "--no-cone", "--stdin",
        input=checkout["with"]["sparse-checkout"].encode())
    assert all((tmp_path / relative).is_file() for relative in required)
    assert not (tmp_path / excluded).exists()


# test_unified_data_architecture.py reads these committed files. The unit-tests
# job is a non-cone sparse checkout, so a path that is not listed is absent on
# CI even when it exists on main. The FTS5 query is kind=ticker and is filled
# from dashboard/data/agent_shards/, which is why the directory is required.
UNIFIED_ARCHITECTURE_READS = (
    "dashboard/data/portfolio_summary.json",
    "dashboard/data/research_manifest.json",
    "dashboard/data/kpi_summary.json",
    "dashboard/data/document_catalog_summary.json",
    "dashboard/data/agent_shards/TPL.json",
    "dashboard/data/agent_shards/GOOGL.json",
    "TPL/research/evidence/thematic_context.md",
    "TPL/research/evidence/insider_signal.md",
    "TPL/research/evidence/filing_digest.md",
    "TPL/third-party-analyses/source_inventory.json",
    "GOOGL/research/evidence/thematic_context.md",
    "GOOGL/research/evidence/insider_signal.md",
    "GOOGL/research/evidence/filing_digest.md",
    "GOOGL/third-party-analyses/source_inventory.json",
)


def _sparse_has(path: str, entries: list[str]) -> bool:
    for entry in entries:
        if entry == path or path.startswith(entry.rstrip("/") + "/"):
            return True
    return False


def test_unified_architecture_reads_are_in_the_unit_test_checkout():
    """L0 summaries, agent shards, and TPL/GOOGL evidence were omitted."""
    entries = sparse_entries()
    missing = [path for path in UNIFIED_ARCHITECTURE_READS if not _sparse_has(path, entries)]
    assert not missing, f"unit-tests sparse-checkout misses {missing}"


# test_agent_data_architecture.py rebuilds claims from every thesis card and
# picks its 10 golden tickers from thesis cards plus latest.json. get_valuation
# reads GOOGL/research/valuation.json. None of those are under /_system/.
AGENT_DATA_SPARSE = (
    "*/research/thesis_card.json",
    "*/research/latest.json",
    "GOOGL/research/valuation.json",
)


def test_agent_data_reads_are_in_the_unit_test_checkout():
    """Claim rebuild and the golden eval saw an empty sparse tree."""
    entries = sparse_entries()
    missing = [path for path in AGENT_DATA_SPARSE if path not in entries]
    assert not missing, f"unit-tests sparse-checkout misses {missing}"


def test_a_known_failure_that_starts_passing_is_reported_even_beside_one_that_still_fails(tmp_path):
    """Run together, the still-failing test made pytest exit 1 and hid the
    fixed one (main fixed test_deploy_defers_... while test_hot_routes_... still
    fails)."""
    import os
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if not bash:
        import pytest

        pytest.skip("needs bash")
    job = load()["jobs"]["unit-tests"]
    step = next(s for s in job["steps"] if str(s.get("name", "")).startswith("Known failures"))
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "python").write_text('#!/usr/bin/env bash\ncase "$*" in *fixed*) exit 0 ;; *) exit 1 ;; esac\n',
                                 encoding="utf-8", newline="\n")
    (fake / "python").chmod(0o755)
    (tmp_path / "step.sh").write_text(step["run"], encoding="utf-8", newline="\n")
    env = {**os.environ, "PATH": str(fake) + os.pathsep + os.environ["PATH"],
           "RUNNER_TEMP": str(tmp_path), "KNOWN_FAILURES": "tests/a.py::still_broken tests/b.py::fixed"}
    proc = subprocess.run([bash, "-e", str(tmp_path / "step.sh")], env=env, capture_output=True, text=True,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    assert "::warning title=Known failure now passes::tests/b.py::fixed passes" in proc.stdout
    assert "still failing: tests/a.py::still_broken" in proc.stdout
    assert "1 known failure(s) still fail" in proc.stdout


def test_there_is_no_undefined_name_allowance():
    """two_phase_watch.py's F821s are fixed on main; the baseline is zero."""
    job = load()["jobs"]["undefined-names"]
    assert "env" not in job or not any("KNOWN" in key for key in job["env"])
    run = next(s["run"] for s in job["steps"] if "run" in s)
    assert "check_undefined_names.py _system/scripts _system/trading" in run
    assert "--exit-zero" not in run


def test_private_architecture_inputs_are_restored_before_the_suite():
    job = load()["jobs"]["unit-tests"]
    steps = job["steps"]
    restore = next(i for i, s in enumerate(steps) if s.get("uses") == "./.github/actions/checkout-vault")
    suite = next(i for i, s in enumerate(steps) if s.get("name") == "Trading and script test suites")
    assert restore < suite
    assert "dashboard/private-assets.json" in sparse_entries()
    assert job["env"]["RESEARCH_VAULT_CLONE_TOKEN"] == "${{ secrets.RESEARCH_VAULT_CLONE_TOKEN }}"


def test_fixture_checkout_omits_batch_archives_and_deploy_can_select_history(tmp_path):
    import re
    import subprocess

    action = yaml.safe_load((ROOT / ".github/actions/checkout-vault/action.yml").read_text(encoding="utf-8"))
    assert action["inputs"]["include-source-archive"]["default"] == "true"
    assert action["inputs"]["include-investor-history"]["default"] == "false"
    checkout = next(s for s in action["runs"]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert "blob:none" in checkout["with"]["filter"]
    patterns = re.findall(r"&& '([^']+)'", checkout["with"]["sparse-checkout"])
    assert patterns
    for name in ("hub-payloads", "unit-tests"):
        restore = next(s for s in load()["jobs"][name]["steps"] if s.get("uses") == "./.github/actions/checkout-vault")
        assert restore["with"]["include-source-archive"] == "false"

    preserved = ["dashboard-private/objects/snapshot", "dashboard-private/originals/filing.pdf", "dashboard-private/commodity-inputs/source.json", "superinvestor-letters/fund/letter.md"]
    archived = "dashboard-private/company-source-backfill-v2/part.zip"
    history = "dashboard-private/investor-history/objects/part.gz"
    for relative in [*preserved, archived, history]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")

    def git(*args, **kwargs):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, **kwargs)

    git("init")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")
    git("sparse-checkout", "set", "--no-cone", "--stdin", input=("\n".join(patterns) + "\n").encode())
    assert all((tmp_path / path).is_file() for path in preserved)
    assert not (tmp_path / archived).exists()
    assert not (tmp_path / history).exists()
    git("sparse-checkout", "add", "/dashboard-private/investor-history/")
    assert (tmp_path / history).is_file()
    assert all((tmp_path / path).is_file() for path in preserved)
    assert not (tmp_path / archived).exists()

    refresh = yaml.safe_load((ROOT / ".github/workflows/investor-history.yml").read_text(encoding="utf-8"))
    restore = next(s for s in refresh["jobs"]["refresh"]["steps"] if s.get("uses") == "./.github/actions/checkout-vault")
    assert restore["with"]["include-investor-history"] == "true"
