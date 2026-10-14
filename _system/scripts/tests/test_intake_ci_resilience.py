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
        partial = next(step for step in steps if step.get("name") == "Commit partial progress")
        self.assertIn("dashboard_written != 'true'", partial["if"])
        self.assertIn("failed_source", partial["with"]["message"])
        loud = next(step for step in steps if step.get("name") == "Report intake-full failure")
        self.assertIn("::error::", loud["run"])
        self.assertIn("exit 1", loud["run"])
        self.assertIn("failed_source", loud["run"])
        success = next(step for step in steps if step.get("name") == "Commit artifacts")
        self.assertIn("intake_rebuild.outcome == 'success'", success["if"])


if __name__ == "__main__":
    unittest.main()
