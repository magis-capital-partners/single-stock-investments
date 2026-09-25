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


def test_there_is_no_undefined_name_allowance():
    """two_phase_watch.py's F821s are fixed on main; the baseline is zero."""
    job = load()["jobs"]["undefined-names"]
    assert "env" not in job or not any("KNOWN" in key for key in job["env"])
    run = next(s["run"] for s in job["steps"] if "run" in s)
    assert "check_undefined_names.py _system/scripts _system/trading" in run
    assert "--exit-zero" not in run
