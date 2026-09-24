#!/usr/bin/env python3
"""Structural guards for the data-feed workflows (data-pipeline, forced-flow).

Each test encodes a failure that shipped:

* Forced Flow Daily ran build_capitulation_daily.py without numpy for 13 runs
  (2026-09-04..22). Any job that runs a criticality consumer must install a
  requirements file carrying numpy and scipy first.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is present on dev boxes and runners
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
MODEL_PACKAGES = {"numpy", "scipy"}


def load_workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def all_workflows() -> dict[str, dict]:
    return {path.name: load_workflow(path.name) for path in sorted(WORKFLOWS.glob("*.yml"))}


def step_text(step: dict) -> str:
    return str(step.get("run") or "")


def criticality_consumers() -> set[str]:
    """Scripts in _system/scripts that import criticality, directly or via another script."""
    imports: dict[str, set[str]] = {}
    for path in SCRIPTS.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        imports[path.stem] = set(re.findall(r"(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", text))
    consumers = {name for name, found in imports.items() if "criticality" in found}
    changed = True
    while changed:
        changed = False
        for name, found in imports.items():
            if name not in consumers and found & consumers:
                consumers.add(name)
                changed = True
    return {f"{name}.py" for name in consumers}


def installed_packages(run: str) -> set[str]:
    """Package names a `pip install -r <file>` line brings in (from the file)."""
    packages: set[str] = set()
    for req in re.findall(r"-r\s+(\S+\.txt)", run):
        path = ROOT / req
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
            if match and not line.lstrip().startswith("#"):
                packages.add(match.group(1).lower())
    for pkg in re.findall(r"pip install\s+(?!-r)([^\n]+)", run):
        packages.update(token.split("=")[0].split(">")[0].lower() for token in pkg.split())
    return packages


@unittest.skipIf(yaml is None, "PyYAML not installed")
class CriticalityDependencyTests(unittest.TestCase):
    def test_consumers_are_discovered(self) -> None:
        consumers = criticality_consumers()
        self.assertIn("build_capitulation_daily.py", consumers)
        self.assertIn("build_criticality_signals.py", consumers)

    def test_every_job_running_a_consumer_installs_the_model_first(self) -> None:
        consumers = criticality_consumers()
        checked = 0
        for name, workflow in all_workflows().items():
            for job_name, job in (workflow.get("jobs") or {}).items():
                installed: set[str] = set()
                for step in job.get("steps") or []:
                    run = step_text(step)
                    installed |= installed_packages(run)
                    used = [script for script in consumers if re.search(rf"\b{re.escape(script)}\b", run)]
                    if not used:
                        continue
                    checked += 1
                    missing = MODEL_PACKAGES - installed
                    self.assertFalse(
                        missing,
                        f"{name}:{job_name} runs {', '.join(sorted(used))} before installing "
                        f"{', '.join(sorted(missing))} (pip install -r "
                        "_system/scripts/requirements-criticality.txt)",
                    )
        self.assertGreater(checked, 0, "no criticality consumer found in any workflow")


def step_index(steps: list[dict], predicate) -> int:
    for index, step in enumerate(steps):
        if predicate(step):
            return index
    return -1


@unittest.skipIf(yaml is None, "PyYAML not installed")
class CapitulationRebuiltGateTests(unittest.TestCase):
    """The builder exits 0 even when it writes nothing; the jobs must judge the artifact."""

    def test_forced_flow_checks_the_snapshot_before_committing(self) -> None:
        steps = load_workflow("forced-flow-daily.yml")["jobs"]["refresh"]["steps"]
        build = step_index(steps, lambda s: "build_capitulation_daily.py --workers" in step_text(s))
        check = step_index(steps, lambda s: "--check-rebuilt-since" in step_text(s))
        commit = step_index(steps, lambda s: str(s.get("uses", "")).endswith("commit-main"))
        self.assertTrue(0 <= build < check < commit, (build, check, commit))
        self.assertIn("capitulation_started_at", step_text(steps[build]))

    def test_technicals_job_fails_loud_when_capitulation_was_not_rebuilt(self) -> None:
        steps = load_workflow("data-pipeline.yml")["jobs"]["technicals"]["steps"]
        check = step_index(steps, lambda s: s.get("id") == "capitulation_rebuilt")
        self.assertGreaterEqual(check, 0)
        self.assertTrue(steps[check].get("continue-on-error"))
        loud = steps[-1]
        self.assertIn("steps.capitulation_rebuilt.outcome == 'failure'", str(loud.get("if")))
        self.assertIn("exit 1", step_text(loud))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
