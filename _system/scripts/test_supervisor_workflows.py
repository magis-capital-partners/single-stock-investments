"""Workflow-level contracts for the monitoring plane (WS6, 2026-09-24).

The supervisor, the ops-watchdog deploy, the retired CI-autofix lane, the
cron minutes and the memory-digest invariant step are all YAML; these tests pin
the properties that matter so a later edit cannot quietly undo them.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_registry as lr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class SupervisorWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("repository-health-supervisor.yml")

    def test_runs_every_two_hours_off_the_quarter_hour(self):
        self.assertEqual(lr.parse_workflow(self.text)["crons"], ["41 */2 * * *"])

    def test_has_an_on_demand_trigger_but_no_manual_button(self):
        self.assertRegex(self.text, r"types: \[[^\]]*\bsupervisor-run\b")
        self.assertNotRegex(self.text, r"(?m)^\s{2}workflow_dispatch:\s*$")

    def test_permissions_cover_issues_annotations_and_dispatch(self):
        block = self.text.split("permissions:", 1)[1].split("\n\n", 1)[0]
        for grant in ("actions: write", "checks: read", "contents: write", "issues: write"):
            self.assertIn(grant, block)

    def test_secrets_reach_the_supervisor(self):
        for secret in ("SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID",
                       "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
            self.assertIn(f"{secret}: ${{{{ secrets.{secret} }}}}", self.text)
        self.assertIn("supervise_repository_health.py --act", self.text)

    def test_the_847_escalation_and_bash_dispatch_loop_are_gone(self):
        self.assertNotIn("Repository self-healer escalation", self.text)
        self.assertNotIn("gh issue comment", self.text)
        self.assertNotIn("dispatches.jsonl", self.text)

    def sparse_patterns(self) -> list[str]:
        block = self.text.split("sparse-checkout: |", 1)[1].split("sparse-checkout-cone-mode", 1)[0]
        return [line.strip() for line in block.splitlines() if line.strip()]

    def test_the_checkout_carries_everything_the_supervisor_reads(self):
        # A feed outside the sparse checkout reads "file missing" forever, and
        # its healer is then dispatched three times a day against nothing
        # (capitulation_daily.json, caught by the verifier).
        import json
        import supervise_repository_health as supervisor
        patterns = self.sparse_patterns()

        def covered(path: str) -> bool:
            return any(path == p or path.startswith(p.rstrip("/") + "/") for p in patterns)

        config = json.loads((ROOT / "_system/graph/graph_sources.json").read_text(encoding="utf-8"))
        feeds = [feed["path"] for name, feed in config["data_feeds"].items()
                 if not name.startswith("_") and isinstance(feed, dict)]
        self.assertGreaterEqual(len(feeds), 8)
        reads = [Path(p).as_posix() for p in (
            lr.CONFIG_REL, lr.RECEIPTS_REL, lr.WORKFLOWS_REL, supervisor.STATE_REL,
            supervisor.WORK_QUEUE_REL)]
        reads += ["_system/scripts/supervise_repository_health.py",
                  "_system/scripts/build_lane_receipts.py", ".github/actions/commit-main"]
        for path in feeds + reads:
            self.assertTrue(covered(path), f"{path} is not in the supervisor's sparse checkout")


class RetiredAutofix(unittest.TestCase):
    def test_ci_autofix_workflow_and_config_stay_removed(self):
        self.assertFalse((WORKFLOWS / "ci-autofix.yml").exists())
        self.assertFalse((ROOT / ".github" / "ci-autofix.yml").exists())
        for path in WORKFLOWS.glob("*.yml"):
            self.assertNotIn("Auto - CI Repair", path.read_text(encoding="utf-8"), path.name)


class CronMinutes(unittest.TestCase):
    OWNED = ("committee-outcomes.yml", "memory-digest.yml", "research-watchdog.yml",
             "market-risk-components.yml", "podcast-refresh.yml", "letter-backfill.yml",
             "security-weekly.yml", "investment-committee.yml", "contract-backfill-continue.yml",
             "repository-health-supervisor.yml")

    def test_owned_crons_avoid_the_quarter_hours(self):
        for name in self.OWNED:
            for cron in lr.parse_workflow(read(name))["crons"]:
                self.assertNotIn(cron.split()[0], ("0", "00", "15", "30", "45"),
                                 f"{name}: {cron}")

    def test_every_lane_window_covers_its_workflows_real_schedule(self):
        # Other workstreams move their own crons; what must hold is that a
        # lane's window still tolerates one skipped run of the schedule its
        # workflow actually has, whatever minute it fires at.
        config = lr.load_config(ROOT)
        for lane in lr.declared_lanes(config):
            if lane["workflow_file"] == "data-pipeline.yml" \
                    or lane["name"] in ("valuation", "daily-sync"):
                continue   # per-job crons, or driven by the downloads job's runs
            crons = lr.parse_workflow(read(lane["workflow_file"]))["crons"]
            if not crons:
                continue
            floor = lr.one_skip_span_hours(crons) + lr.JITTER_HOURS
            self.assertGreaterEqual(lane["freshness_hours"], floor, lane["name"])


class MemoryDigestInvariantStep(unittest.TestCase):
    def test_a_crashed_invariant_run_cannot_pass_on_a_stale_report(self):
        text = read("memory-digest.yml")
        code = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertNotIn("graph_invariants.py || true", code)
        remove = text.index("rm -f _system/graph/invariants.json")
        run = text.index("python _system/scripts/graph_invariants.py"
                         " || test -s _system/graph/invariants.json")
        subset = text.index("validate_invariant_subset.py E4 E5 E7")
        self.assertLess(remove, run)
        self.assertLess(run, subset)


class OpsWatchdogDeploy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("deploy-ops-watchdog.yml")

    def test_deploys_only_on_a_push_to_its_own_tree(self):
        spec = lr.parse_workflow(self.text)
        self.assertEqual(spec["triggers"], {"push"})
        self.assertIn('      - "ops-watchdog/**"', self.text)
        self.assertNotRegex(self.text, r"(?m)^\s{2}workflow_dispatch:\s*$")

    def test_tests_gate_the_deploy_and_secrets_become_worker_secrets(self):
        self.assertIn("node --test", self.text)
        self.assertIn("needs: test", self.text)
        self.assertIn("cloudflare/wrangler-action@v3", self.text)
        secrets_block = self.text.split("secrets: |", 1)[1]
        for name in ("SLACK_WEBHOOK_URL", "CF_API_TOKEN", "CF_ACCOUNT_ID"):
            self.assertIn(name, secrets_block)

    def test_the_worker_has_no_d1_binding(self):
        config = (ROOT / "ops-watchdog" / "wrangler.toml").read_text(encoding="utf-8")
        self.assertNotRegex(config, r"(?m)^\s*\[\[d1_databases\]\]")
        self.assertIn('crons = ["*/30 * * * *"]', config)


class CapitulationFeed(unittest.TestCase):
    """dashboard/data/capitulation_daily.json is a registered P6 feed (WS4)."""

    def violations(self, payload):
        import json
        import shutil
        import tempfile
        from datetime import datetime, timezone
        import graph_invariants
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_system/graph").mkdir(parents=True)
            shutil.copy(ROOT / "_system/graph/graph_sources.json",
                        root / "_system/graph/graph_sources.json")
            feed = root / "dashboard/data/capitulation_daily.json"
            feed.parent.mkdir(parents=True)
            feed.write_text(json.dumps(payload), encoding="utf-8")
            now = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)
            result = graph_invariants.inv_p6(None, root, now)
            return [v for v in result.violations if v.startswith("capitulation_daily")]

    def test_fresh_ready_and_lagging_pass(self):
        for state in ("ready", "limited", "lagging"):
            self.assertEqual(self.violations({"generated_at": "2026-09-24T07:47:33Z",
                                              "quality_state": state}), [], state)

    def test_unavailable_stale_and_old_fail(self):
        for state in ("unavailable", "stale"):
            found = self.violations({"generated_at": "2026-09-24T07:47:33Z",
                                     "quality_state": state})
            self.assertEqual(len(found), 1, state)
        old = self.violations({"generated_at": "2026-09-19T07:47:33Z", "quality_state": "ready"})
        self.assertTrue(any("stale (window 100h)" in v for v in old), old)

    def test_its_healer_is_the_technicals_lane(self):
        import supervise_repository_health as supervisor
        self.assertEqual(supervisor.P6_FEED_LANES["capitulation_daily"], "data-pipeline-technicals")


class YamlValidity(unittest.TestCase):
    def test_every_workflow_parses(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for path in sorted(WORKFLOWS.glob("*.yml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIsInstance(doc, dict, path.name)
            self.assertIn("jobs", doc, path.name)
            self.assertTrue(doc.get(True) or doc.get("on"), path.name)


if __name__ == "__main__":
    unittest.main()
