#!/usr/bin/env python3
"""Structural guards for the data-feed workflows (data-pipeline, forced-flow).

Each test encodes a failure that shipped:

* Forced Flow Daily ran build_capitulation_daily.py without numpy for 13 runs
  (2026-09-04..22). Any job that runs a criticality consumer must install a
  requirements file carrying numpy and scipy first.
"""
from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
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

    def test_run_start_is_recorded_before_any_builder_can_fail(self) -> None:
        steps = load_workflow("data-pipeline.yml")["jobs"]["technicals"]["steps"]
        build = steps[step_index(steps, lambda s: "build_capitulation_daily.py --workers" in step_text(s))]
        commands = [
            line.strip() for line in step_text(build).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertIn("capitulation_started_at", commands[0])

    def test_technicals_job_fails_loud_when_capitulation_was_not_rebuilt(self) -> None:
        steps = load_workflow("data-pipeline.yml")["jobs"]["technicals"]["steps"]
        check = step_index(steps, lambda s: s.get("id") == "capitulation_rebuilt")
        self.assertGreaterEqual(check, 0)
        self.assertTrue(steps[check].get("continue-on-error"))
        loud = steps[-1]
        self.assertIn("steps.capitulation_rebuilt.outcome == 'failure'", str(loud.get("if")))
        self.assertIn("exit 1", step_text(loud))


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@unittest.skipIf(yaml is None, "PyYAML not installed")
class DriveImportCommitTests(unittest.TestCase):
    """A failed rebuild lost the day's Drive imports (6 -> 61 re-imported, 2026-09-10..22)."""

    def _steps(self) -> list[dict]:
        return load_workflow("data-pipeline.yml")["jobs"]["drive"]["steps"]

    def _fallback(self) -> dict:
        steps = self._steps()
        index = step_index(
            steps, lambda s: "steps.rebuild.conclusion != 'success'" in str(s.get("if") or "")
        )
        self.assertGreaterEqual(index, 0, "no commit step for a failed rebuild")
        return steps[index]

    def test_import_is_committed_when_the_rebuild_fails(self) -> None:
        step = self._fallback()
        condition = str(step.get("if"))
        self.assertIn("always()", condition)
        self.assertIn("steps.import.outputs.imported != '0'", condition)
        # A skipped import (e.g. after a failed checkout) reports '' -- never commit then.
        self.assertIn("steps.import.outputs.imported != ''", condition)
        run = step_text(step)
        self.assertIn("ci_push_main.sh", run)
        self.assertNotRegex(run, r"git add\s+(--sparse\s+)?-A\b", "must not stage derived artifacts")
        self.assertNotIn("--modified", run, "--modified also lists deletions")
        self.assertNotIn("uses", step)

    def test_success_path_still_commits_everything_after_a_good_rebuild(self) -> None:
        steps = self._steps()
        index = step_index(steps, lambda s: s.get("name") == "Commit imported documents")
        self.assertIn("steps.rebuild.conclusion == 'success'", str(steps[index].get("if")))

    def _import_paths(self) -> list[str]:
        run = step_text(self._fallback())
        block = run[run.index("IMPORT_PATHS=(") + len("IMPORT_PATHS=("):]
        return shlex.split(block[:block.index(")\n")])

    def test_fallback_stages_only_new_or_modified_import_outputs(self) -> None:
        paths = self._import_paths()
        run = step_text(self._fallback())
        self.assertIn('git ls-files -z --others --exclude-standard -- "${IMPORT_PATHS[@]}"', run)
        self.assertIn('git diff -z --name-only --diff-filter=M -- "${IMPORT_PATHS[@]}"', run)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "-q")
            _git(repo, "config", "user.email", "ci@example.test")
            _git(repo, "config", "user.name", "CI")
            files = {
                ".gitignore": "*.pdf\n",
                "_system/data/drive_intake_manifest.json": "{}",
                "_system/reference/document-store/drive_intake_latest.json": "{}",
                "dashboard/data/research_memory.json": '{"claims": 12000}',
                "AAPL/third-party-analyses/vic/old.source.json": "{}",
                "AAPL/third-party-analyses/vic/kept.source.json": "{}",
            }
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text, encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "base")
            changed = {
                "_system/data/drive_intake_manifest.json": '{"files": 1}',
                "dashboard/data/research_memory.json": '{"claims": 1116}',  # half-rebuilt
                "MSFT/third-party-analyses/vic/new.source.json": "{}",
                "MSFT/third-party-analyses/vic/new.pdf": "%PDF",  # gitignored
                "MSFT/investor-documents/drive-intake/deck.source.json": "{}",
            }
            for rel, text in changed.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text, encoding="utf-8")
            (repo / "AAPL/third-party-analyses/vic/old.source.json").unlink()  # not checked out
            new = _git(repo, "ls-files", "-z", "--others", "--exclude-standard", "--", *paths)
            modified = _git(repo, "diff", "-z", "--name-only", "--diff-filter=M", "--", *paths)
            staged = sorted(path for path in (new + modified).split("\0") if path)
            self.assertEqual(
                staged,
                [
                    "MSFT/investor-documents/drive-intake/deck.source.json",
                    "MSFT/third-party-analyses/vic/new.source.json",
                    "_system/data/drive_intake_manifest.json",
                ],
            )


def shell_timeout_minutes(run: str) -> float | None:
    """Minutes from a coreutils `timeout [opts] <N>[smh] cmd` prefix, if any."""
    match = re.search(r"\btimeout\s+(?:--?\S+\s+)*(\d+(?:\.\d+)?)([smh]?)\s", run)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2) or "s"
    return value * {"s": 1 / 60, "m": 1, "h": 60}[unit]


@unittest.skipIf(yaml is None, "PyYAML not installed")
class NewsBudgetTests(unittest.TestCase):
    """58 of 65 news runs (2026-09-08..24) ended as a job-timeout "cancelled"."""

    def test_news_overrun_is_a_failure_not_a_cancel(self) -> None:
        job = load_workflow("data-pipeline.yml")["jobs"]["news"]
        steps = job["steps"]
        ingest = steps[step_index(steps, lambda s: "ingest_portfolio_news.py" in step_text(s))]
        step_minutes = shell_timeout_minutes(step_text(ingest))
        self.assertIsNotNone(step_minutes, "wrap the ingester in `timeout`")
        deadline_minutes = float(job["env"]["PORTFOLIO_NEWS_DEADLINE_SEC"]) / 60
        job_minutes = float(job["timeout-minutes"])
        # in-process deadline < shell timeout < job timeout, with room for the commit
        self.assertLess(deadline_minutes, step_minutes)
        self.assertLessEqual(step_minutes + 5, job_minutes)
        self.assertGreaterEqual(int(job["env"]["PORTFOLIO_NEWS_GOOGLE_WORKERS"]), 2)

    def test_a_mostly_failed_run_commits_its_partial_feed_and_goes_red(self) -> None:
        steps = load_workflow("data-pipeline.yml")["jobs"]["news"]["steps"]
        ingest = step_index(steps, lambda s: s.get("id") == "ingest")
        self.assertGreaterEqual(ingest, 0)
        self.assertTrue(steps[ingest].get("continue-on-error"))
        commit = step_index(steps, lambda s: "chore: refresh portfolio news" in step_text(s))
        self.assertGreater(commit, ingest)
        loud = steps[-1]
        self.assertIn("steps.ingest.outcome == 'failure'", str(loud.get("if")))
        self.assertIn("exit 1", step_text(loud))


@unittest.skipIf(yaml is None, "PyYAML not installed")
class DecideMatchesTriggersTests(unittest.TestCase):
    """decide case-matches exact cron strings and hard-errors on anything else."""

    def test_every_cron_and_dispatch_type_has_a_case(self) -> None:
        workflow = load_workflow("data-pipeline.yml")
        triggers = workflow.get("on") or workflow.get(True)  # PyYAML reads `on:` as True
        crons = {entry["cron"] for entry in triggers["schedule"]}
        dispatch = {f"dispatch:{kind}" for kind in triggers["repository_dispatch"]["types"]}
        run = step_text(workflow["jobs"]["decide"]["steps"][0])
        cases = set(re.findall(r'(?m)^\s*"([^"]+)"\)', run))
        self.assertEqual(cases, crons | dispatch)


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ActivistPhaseTests(unittest.TestCase):
    """The activist job hit its 90-minute limit on every run from 2026-08-03,
    and a job timeout is reported as "cancelled", which hid it for 53 days."""

    PHASES = ("phase_sec", "phase_sites", "phase_wires", "phase_discovery", "phase_finalize")

    def _job(self) -> dict:
        return load_workflow("data-pipeline.yml")["jobs"]["activist"]

    def test_every_phase_is_bounded_and_keeps_going(self) -> None:
        steps = {step.get("id"): step for step in self._job()["steps"] if step.get("id")}
        for phase in self.PHASES:
            self.assertIn(phase, steps)
            step = steps[phase]
            self.assertTrue(step.get("continue-on-error"), phase)
            for line in (l for l in step_text(step).splitlines() if "python" in l):
                self.assertIsNotNone(shell_timeout_minutes(line), f"{phase}: {line}")
        self.assertIn("--budget-min", step_text(steps["phase_sec"]))
        self.assertIn("--min-interval-days", step_text(steps["phase_discovery"]))

    def test_every_step_has_a_limit_and_they_fit_inside_the_job_limit(self) -> None:
        # Not vacuous: a step with no limit of its own fails this test, so the
        # sum below is a real upper bound on the steps, and the job limit sits
        # above it -- a job timeout (reported "cancelled") cannot be what ends
        # the run. Runner overhead outside the steps gets 10 minutes.
        job = self._job()
        total = 0.0
        for step in job["steps"]:
            label = step.get("id") or step.get("name") or step.get("uses")
            limit = step.get("timeout-minutes")
            self.assertIsNotNone(limit, f"activist step without timeout-minutes: {label}")
            total += float(limit)
            # inner `timeout`s (plus their 1-minute kill grace) fire before the step limit
            inner = [shell_timeout_minutes(line) for line in step_text(step).splitlines()]
            inner_total = sum(minutes + 1 for minutes in inner if minutes is not None)
            self.assertLessEqual(inner_total, float(limit), label)
        self.assertLessEqual(total + 10, float(job["timeout-minutes"]))
        self.assertLessEqual(float(job["timeout-minutes"]), 300)  # governance cap

    def test_coverage_guards_are_bounded(self) -> None:
        steps = self._job()["steps"]
        guards = steps[step_index(steps, lambda s: s.get("name") == "Activist coverage guards")]
        self.assertLessEqual(float(guards["timeout-minutes"]), 10)

    def test_progress_is_committed_and_failures_stay_red(self) -> None:
        steps = self._job()["steps"]
        sec = step_index(steps, lambda s: s.get("id") == "phase_sec")
        commit = step_index(
            steps,
            lambda s: str(s.get("uses", "")).endswith("commit-main")
            and "always()" in str(s.get("if"))
            and "steps.checkout_full.outcome == 'success'" in str(s.get("if")),
        )
        self.assertGreater(commit, sec, "commit the SEC phase's progress right after it")
        fresh = steps[step_index(steps, lambda s: "check_activist_freshness.py" in step_text(s))]
        self.assertEqual(fresh.get("if"), "always()")
        loud = steps[-1]
        self.assertIn("exit 1", step_text(loud))
        for phase in self.PHASES:
            self.assertIn(f"steps.{phase}.outcome == 'failure'", str(loud.get("if")))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
