#!/usr/bin/env python3
"""Tests for the content-addressed dashboard deploy gate.

Runs in ci-bootstrap-smoke (drive-intake job) from a sparse checkout that has
this file, the gate script and three workflow files -- so no PyYAML and no
other repo files here. Git is used only in throwaway repositories.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
import workflow_run_deploy_gate as gate  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=gate-test", "-c", "user.email=gate@test.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


class DecideTests(unittest.TestCase):
    def test_push_and_dispatch_always_deploy(self) -> None:
        for event in ("push", "workflow_dispatch"):
            deploy, _ = gate.decide(event, synced=True, deferred_today=True, pruned_today=True)
            self.assertTrue(deploy, event)

    def test_upstream_run_with_unchanged_inputs_does_not_deploy(self) -> None:
        # A Power Zone / LS-algo run whose main job was skipped commits nothing,
        # so the fingerprint is one a previous deploy already synced.
        deploy, reason = gate.decide("workflow_run", synced=True, deferred_today=False, pruned_today=False)
        self.assertFalse(deploy)
        self.assertIn("unchanged", reason)

    def test_upstream_run_with_changed_inputs_deploys(self) -> None:
        deploy, _ = gate.decide("workflow_run", synced=False, deferred_today=False, pruned_today=False)
        self.assertTrue(deploy)

    def test_no_same_day_retry_after_a_d1_deferral(self) -> None:
        for event in ("workflow_run", "schedule"):
            deploy, reason = gate.decide(event, synced=False, deferred_today=True, pruned_today=False)
            self.assertFalse(deploy, event)
            self.assertIn("00:00 UTC", reason)

    def test_schedule_is_the_post_reset_recovery_path(self) -> None:
        # Yesterday's deferral left the inputs unsynced; today has no deferral yet.
        self.assertTrue(gate.decide("schedule", synced=False, deferred_today=False, pruned_today=True)[0])
        # Nothing changed, but today's retention has not run.
        self.assertTrue(gate.decide("schedule", synced=True, deferred_today=False, pruned_today=False)[0])
        # Nothing changed, nothing owed: cheap no-op.
        self.assertFalse(gate.decide("schedule", synced=True, deferred_today=False, pruned_today=True)[0])

    def test_unknown_events_fail_open(self) -> None:
        self.assertTrue(gate.decide("repository_dispatch", synced=True, deferred_today=False, pruned_today=True)[0])

    def cli(self, event: str, fingerprint: str, last: str | None) -> dict[str, str]:
        """Run ``decide`` as the workflow does; ``last`` is what the newest
        dashboard-deploy-last-v1- cache entry restored (None: nothing)."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.txt"
            last_file = Path(tmp) / ".deploy-gate-last" / "fingerprint"
            if last is not None:
                last_file.parent.mkdir()
                last_file.write_text(last, encoding="utf-8")
            self.assertEqual(gate.main([
                "decide", "--event", event, "--fingerprint", fingerprint,
                "--last-file", str(last_file), "--deferred-hit", "", "--pruned-hit", "",
                "--github-output", str(out),
            ]), 0)
            return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())

    def test_cli_compares_against_the_last_deployed_fingerprint(self) -> None:
        self.assertEqual(self.cli("workflow_run", "aaa", "aaa")["should_deploy"], "false")
        self.assertEqual(self.cli("workflow_run", "aaa", "bbb")["should_deploy"], "true")
        self.assertEqual(self.cli("workflow_run", "aaa", None)["should_deploy"], "true")
        self.assertEqual(self.cli("workflow_run", "aaa", "aaa\n")["last_deployed"], "aaa")

    def test_a_revert_to_earlier_content_redeploys(self) -> None:
        # Deploys shipped A, then B. main reverts to A. "A was synced once"
        # said skip, leaving the site and D1 on B; the last deploy was B.
        for event in ("workflow_run", "schedule"):
            self.assertEqual(self.cli(event, "fingerprint-A", "fingerprint-B")["should_deploy"], "true", event)

    def test_is_synced_needs_a_fingerprint(self) -> None:
        self.assertFalse(gate.is_synced("", ""))
        self.assertFalse(gate.is_synced("", None))
        self.assertTrue(gate.is_synced("abc", "abc"))


class FingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-q")
        for path in ("dashboard/index.html", "_system/scripts/export_dashboard_d1_seed.py", "notes/research.md"):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"v1 {path}\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "one")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def commit(self, path: str, text: str) -> None:
        (self.repo / path).write_text(text, encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", f"touch {path}")

    def test_unrelated_commit_keeps_the_fingerprint(self) -> None:
        before = gate.fingerprint(cwd=self.repo)
        self.commit("notes/research.md", "v2\n")
        self.assertEqual(gate.fingerprint(cwd=self.repo), before)

    def test_deploy_input_change_moves_the_fingerprint(self) -> None:
        before = gate.fingerprint(cwd=self.repo)
        self.commit("dashboard/index.html", "v2\n")
        after = gate.fingerprint(cwd=self.repo)
        self.assertNotEqual(after, before)
        self.commit("_system/scripts/export_dashboard_d1_seed.py", "v2\n")
        self.assertNotEqual(gate.fingerprint(cwd=self.repo), after)

    def test_fingerprint_is_the_content_not_the_commit(self) -> None:
        before = gate.fingerprint(cwd=self.repo)
        self.commit("dashboard/index.html", "v2\n")
        self.commit("dashboard/index.html", "v1 dashboard/index.html\n")
        self.assertEqual(gate.fingerprint(cwd=self.repo), before)

    def test_absent_inputs_are_stable(self) -> None:
        ids = gate.object_ids(cwd=self.repo)
        self.assertEqual(ids[".github/workflows/dashboard-pages.yml"], "absent")
        self.assertRegex(ids["dashboard"], r"^[0-9a-f]{40}$")


class WorkflowWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github" / "workflows" / "dashboard-pages.yml").read_text(encoding="utf-8")

    def job(self, name: str) -> str:
        match = re.search(rf"\n  {re.escape(name)}:\n(.*?)(?=\n  [a-z][a-z0-9-]*:\n|\Z)", self.workflow, re.S)
        self.assertIsNotNone(match, name)
        return match.group(1)

    @staticmethod
    def code(text: str) -> str:
        return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))

    def test_data_pipeline_persists_changed_warning_state(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "data-pipeline.yml").read_text(encoding="utf-8")
        drive_block = workflow.split("\n  drive:\n", 1)[1].split("\n  news:\n", 1)[0]
        intake_full_block = workflow.split("\n  intake-full:\n", 1)[1].split("\n  technicals:\n", 1)[0]
        self.assertIn("id: google_creds", drive_block)
        self.assertNotIn("id: google_creds", intake_full_block)
        self.assertIn("Commit updated intake report", workflow)
        self.assertIn("steps.import.outputs.report_changed == 'true'", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("::error::Drive Intake cannot run", workflow)
        self.assertIn("steps.rebuild.conclusion == 'success'", workflow)
        self.assertGreaterEqual(workflow.count("always() &&"), 3)

    def test_gate_covers_workflow_run_and_schedule(self) -> None:
        gate_job = self.job("deploy-gate")
        self.assertIn("github.event_name == 'workflow_run' || github.event_name == 'schedule'", gate_job)
        self.assertIn("workflow_run_deploy_gate.py fingerprint", gate_job)
        self.assertIn("workflow_run_deploy_gate.py decide", gate_job)
        self.assertIn("lookup-only: true", gate_job)
        self.assertIn("needs.deploy-gate.outputs.should_deploy == 'true'", self.job("build"))

    def test_gate_and_recheck_compare_against_the_last_deploy(self) -> None:
        # Restore the NEWEST last-deployed entry (prefix match), then compare.
        for name in ("deploy-gate", "build"):
            body = self.job(name)
            self.assertRegex(
                body,
                r"path: \.deploy-gate-last\n\s+key: dashboard-deploy-last-v1-\$\{\{ github\.run_id \}\}"
                r"-\$\{\{ github\.run_attempt \}\}\n\s+restore-keys: dashboard-deploy-last-v1-\n",
                name,
            )
            self.assertIn("--last-file .deploy-gate-last/fingerprint", body, name)
            self.assertNotIn("--synced-hit", body, name)
            self.assertNotIn("dashboard-deploy-synced-v1-", body, name)

    def test_darwin_is_not_a_trigger(self) -> None:
        # WS7 deleted the Darwin Portfolio Refresh workflow.
        self.assertNotIn("Darwin Portfolio Refresh", self.workflow)

    def test_cancelled_runs_do_not_deploy(self) -> None:
        for name in ("build", "oauth-proxy"):
            body = self.code(self.job(name))
            self.assertIn("!cancelled() &&", body, name)
            self.assertNotIn("always()", body, name)

    def test_deploys_serialize_without_killing_one_mid_flight(self) -> None:
        header = self.code(self.workflow.split("\njobs:\n", 1)[0])
        self.assertNotRegex(header, r"(?m)^concurrency:")
        build = self.job("build")
        self.assertRegex(build, r"concurrency:\n\s+group: dashboard-deploy\n\s+cancel-in-progress: false")

    def test_last_deploy_is_recorded_only_when_d1_was_not_deferred(self) -> None:
        build = self.job("build")
        saved = re.search(
            r"if: (.*)\n\s+uses: actions/cache/save@v4\n\s+with:\n\s+path: \.deploy-gate-last\n"
            r"\s+key: dashboard-deploy-last-v1-\$\{\{ github\.run_id \}\}-\$\{\{ github\.run_attempt \}\}\n",
            build)
        self.assertIsNotNone(saved)
        self.assertIn("steps.cloudflare.outputs.d1_deferred != 'true'", saved.group(1))
        # Every deploy that ships records it, pushes included (the re-check
        # restore is skipped for them, so the directory must be created).
        self.assertIn("mkdir -p .deploy-gate-marker .deploy-gate-last", build)
        self.assertIn('printf \'%s\' "$FINGERPRINT" > .deploy-gate-last/fingerprint', build)

    def test_deferral_fails_the_job_after_pages_and_alerts_slack(self) -> None:
        build = self.job("build")
        deploy_at = build.index("uses: ./.github/actions/deploy-cloudflare-dashboard")
        alert_at = build.index("d1_alert.py")
        self.assertLess(deploy_at, alert_at)
        tail = build[alert_at:]
        self.assertIn("SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}", build[deploy_at:])
        self.assertIn("exit 1", tail)

    def test_schedule_moved_off_the_quarter_hour(self) -> None:
        cron = re.search(r'cron: "([^"]+)"', self.workflow).group(1)
        minute, hour = cron.split()[:2]
        self.assertNotIn(int(minute), (0, 15, 30, 45))
        self.assertLessEqual(int(hour), 3)  # still soon after the 00:00 UTC reset

    def test_drive_intake_tests_are_wired_into_ci(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci-bootstrap-smoke.yml").read_text(encoding="utf-8")
        self.assertIn("drive-intake:", workflow)
        self.assertIn("_system.scripts.test_import_drive_intake", workflow)
        self.assertIn("_system.scripts.test_materialize_drive_credentials", workflow)
        self.assertIn("_system.scripts.test_workflow_run_deploy_gate", workflow)


if __name__ == "__main__":
    unittest.main()
