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
