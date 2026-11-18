"""Intake-full names the failing source, and a cancelled check is not a pass.

The 2026-10-08 nightly died on a Drive read timeout and committed nothing.
The 2026-10-09..11 nightlies finished the rebuild and then failed validation,
so the commit step never ran and the next night failed the same way.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_dashboard_shards as shards  # noqa: E402
import ci_rebuild_profile as ci  # noqa: E402
import validate_dashboard_data as validate  # noqa: E402


class StepPolicyTests(unittest.TestCase):
    def test_external_sources_retry_and_local_builders_do_not(self):
        attempts, timeout = ci.step_policy("_system/scripts/sync_pdf_store_google_drive.py")
        self.assertGreater(attempts, 1)
        self.assertLessEqual(timeout, 20 * 60)
        attempts, timeout = ci.step_policy("_system/scripts/fetch_respiratory_panel.py")
        self.assertEqual(attempts, 3)
        self.assertEqual(timeout, 5 * 60)
        attempts, _timeout = ci.step_policy("_system/scripts/build_dashboard_data.py")
        self.assertEqual(attempts, 1)
        self.assertEqual(_timeout, ci.DEFAULT_STEP_TIMEOUT_SEC)

    def test_a_timeout_retries_with_backoff_and_names_the_source(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        sleeps = []
        with patch.object(ci.subprocess, "run", fake_run):
            with self.assertRaises(ci.SourceFailure) as caught:
                ci.run_step(
                    ["_system/scripts/fetch_respiratory_panel.py"],
                    {},
                    sleep_fn=lambda delay: sleeps.append(delay),
                )
        self.assertEqual(calls, [5 * 60, 5 * 60, 5 * 60])
        self.assertEqual(sleeps, [2, 4])
        self.assertEqual(caught.exception.source, "fetch_respiratory_panel.py")
        self.assertIn("after 3 attempt(s)", str(caught.exception))
        self.assertIn("timed out after 300s", str(caught.exception))

    def test_a_local_builder_failure_is_not_retried(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            raise subprocess.CalledProcessError(1, cmd)

        with patch.object(ci.subprocess, "run", fake_run):
            with self.assertRaises(ci.SourceFailure) as caught:
                ci.run_step(
                    ["_system/scripts/build_kpi_trends.py"],
                    {},
                    sleep_fn=lambda _delay: self.fail("a local builder must not retry"),
                )
        self.assertEqual(len(calls), 1)
        self.assertEqual(caught.exception.source, "build_kpi_trends.py")
        self.assertIn("exit 1", str(caught.exception))

    def test_the_rebuild_deadline_caps_a_step_and_names_it(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        env = {ci.DEADLINE_ENV: "10900"}
        with patch.object(ci.subprocess, "run", fake_run):
            with self.assertRaises(ci.SourceFailure) as caught:
                ci.run_step(
                    ["_system/scripts/sync_pdf_store_google_drive.py"],
                    env,
                    sleep_fn=lambda _delay: self.fail("no retry once the budget is spent"),
                    clock=lambda: 10000.0,
                )
        self.assertEqual(calls, [900])
        self.assertEqual(caught.exception.source, "sync_pdf_store_google_drive.py")
        self.assertIn("rebuild budget exhausted", str(caught.exception))

    def test_no_step_starts_inside_the_last_minute_of_the_budget(self):
        with patch.object(ci.subprocess, "run", lambda *_a, **_k: self.fail("must not start")):
            with self.assertRaises(ci.SourceFailure) as caught:
                ci.run_step(
                    ["_system/scripts/build_superinvestor_insights.py"],
                    {ci.DEADLINE_ENV: "10030"},
                    clock=lambda: 10000.0,
                )
        self.assertEqual(caught.exception.source, "build_superinvestor_insights.py")
        self.assertIn("after 0 attempt(s): rebuild budget exhausted (30s left)", str(caught.exception))

    def test_a_distant_deadline_keeps_the_step_policy(self):
        calls = []
        with patch.object(ci.subprocess, "run", lambda cmd, **kw: calls.append(kw["timeout"])):
            ci.run_step(
                ["_system/scripts/build_superinvestor_insights.py"],
                {ci.DEADLINE_ENV: str(10000 + 4 * 3600)},
                clock=lambda: 10000.0,
            )
        self.assertEqual(calls, [ci.DEFAULT_STEP_TIMEOUT_SEC])


class PartialCommitFlagTests(unittest.TestCase):
    def test_a_failure_before_dashboard_assembly_is_safe_to_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "github_output"

            def boom(_step, _env, sleep_fn=None):
                raise ci.SourceFailure("sync_pdf_store_google_drive.py", "timed out")

            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                with patch.object(ci, "run_step", boom):
                    rc = ci.run_profile("minimal")
            text = out.read_text(encoding="utf-8")
            self.assertEqual(rc, 1)
            self.assertIn("failed_source=sync_pdf_store_google_drive.py", text)
            self.assertTrue(text.strip().endswith("dashboard_written=false"))

    def test_a_failure_during_dashboard_assembly_is_not_a_partial_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "github_output"

            def run_step(step, _env, sleep_fn=None):
                if step[0] == ci.DASHBOARD_STEP:
                    raise ci.SourceFailure("build_dashboard_data.py", "exit 1")

            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                with patch.object(ci, "run_step", run_step):
                    rc = ci.run_profile("minimal")
            text = out.read_text(encoding="utf-8")
            self.assertEqual(rc, 1)
            self.assertIn("failed_source=build_dashboard_data.py", text)
            self.assertTrue(text.strip().endswith("dashboard_written=true"))


class MonolithSizeTests(unittest.TestCase):
    def test_standalone_blobs_are_rejected_if_they_are_embedded_again(self):
        self.assertEqual(validate.standalone_embed_errors({"tickers": []}), [])
        errors = validate.standalone_embed_errors({"kpi_trends": {"rows": [1]}})
        self.assertEqual(len(errors), 1)
        self.assertIn("kpi_trends", errors[0])

    def test_core_rows_drop_the_calendar_blob(self):
        slim = shards.slim_ticker_row({
            "ticker": "T",
            "index_membership": {"status": "in", "next_calendar_event": {"date": "2026-11-01"}},
        })
        self.assertNotIn("next_calendar_event", slim["index_membership"])


class IntakeWorkflowTests(unittest.TestCase):
    def test_a_failed_rebuild_still_fails_the_job_and_names_the_source(self):
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "data-pipeline.yml").read_text(encoding="utf-8")
        )
        steps = workflow["jobs"]["intake-full"]["steps"]
        rebuild = next(step for step in steps if step.get("id") == "intake_rebuild")
        self.assertTrue(rebuild.get("continue-on-error"))
        commit = next(step for step in steps if step.get("name") == "Commit artifacts")
        self.assertIn("intake_rebuild.outcome == 'success' ||", commit["if"])
        self.assertIn(
            "(steps.intake_rebuild.outcome == 'failure' && steps.intake_rebuild.outputs.dashboard_written != 'true')",
            commit["if"],
        )
        self.assertIn("failed_source", commit["with"]["message"])
        self.assertIn("'chore: nightly intake-full $(date -u +%Y-%m-%d)'", commit["with"]["message"])
        loud = next(step for step in steps if step.get("name") == "Report intake-full failure")
        self.assertIn("::error::", loud["run"])
        self.assertIn("exit 1", loud["run"])
        self.assertIn("failed_source", loud["run"])

    def _intake(self) -> dict:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "data-pipeline.yml").read_text(encoding="utf-8")
        )
        return workflow["jobs"]["intake-full"]

    def test_step_budgets_fit_inside_the_job_limit(self):
        # 2026-11-18: the 180-minute job cap cancelled the partial-progress
        # commit mid-push because no step had a budget of its own.
        # Same rule as the activist job: a step without a limit fails here, so
        # the sum is a real bound, and runner overhead gets 10 minutes.
        job = self._intake()
        total = 0
        for step in job["steps"]:
            self.assertIn("timeout-minutes", step, step.get("name") or step.get("uses"))
            total += step["timeout-minutes"]
        self.assertLessEqual(total + 10, job["timeout-minutes"])
        self.assertLessEqual(job["timeout-minutes"], 300)
        commits = [s for s in job["steps"] if s.get("uses") == "./.github/actions/commit-main"]
        self.assertEqual(len(commits), 1)

    def test_profile_deadline_leaves_validation_time_inside_the_rebuild_step(self):
        steps = self._intake()["steps"]
        names = [s.get("name") for s in steps]
        deadline = steps[names.index("Set rebuild deadline")]
        rebuild = steps[names.index("Nightly intake-full rebuild")]
        self.assertEqual(names.index("Set rebuild deadline") + 1, names.index("Nightly intake-full rebuild"))
        self.assertIn(ci.DEADLINE_ENV, deadline["run"])
        minutes = int(deadline["run"].split("+ ", 1)[1].split(" * 60", 1)[0])
        self.assertGreaterEqual(rebuild["timeout-minutes"] - minutes, 5)

    def test_intake_full_skips_the_source_archive_it_never_reads(self):
        steps = self._intake()["steps"]
        rebuild = next(step for step in steps if step.get("id") == "intake_rebuild")
        self.assertEqual(rebuild["with"]["vault-include-source-archive"], "false")
        for script in ci.expand_steps(ci.PROFILES[ci.resolve_profile("full")]):
            source = (ROOT / script[0]).read_text(encoding="utf-8")
            self.assertNotIn("company-source-backfill", source, script[0])

    def test_rebuild_data_forwards_the_source_archive_choice(self):
        action = yaml.safe_load(
            (ROOT / ".github" / "actions" / "rebuild-data" / "action.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(action["inputs"]["vault-include-source-archive"]["default"], "true")
        vault = action["runs"]["steps"][0]
        self.assertEqual(vault["uses"], "./.github/actions/checkout-vault")
        self.assertEqual(
            vault["with"]["include-source-archive"], "${{ inputs.vault-include-source-archive }}"
        )


if __name__ == "__main__":
    unittest.main()
