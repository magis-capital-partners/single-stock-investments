import json
import re
import unittest
from pathlib import Path

from summarize_llm_ledger import summarize


ROOT = Path(__file__).resolve().parents[2]


class WorkflowGovernanceTests(unittest.TestCase):
    def test_actions_surface_has_no_manual_run_choices(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\s{2}workflow_dispatch:\s*$", path.name)

    def test_every_runner_job_has_a_hard_timeout(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            jobs = text.split("\njobs:\n", 1)
            if len(jobs) != 2:
                continue
            blocks = re.split(r"(?m)(?=^  [A-Za-z0-9_-]+:\s*$)", jobs[1])
            for block in blocks:
                if re.search(r"(?m)^    runs-on:", block):
                    self.assertRegex(block, r"(?m)^    timeout-minutes: [1-9][0-9]*$", path.name)
                    timeout = int(re.search(r"(?m)^    timeout-minutes: ([0-9]+)$", block).group(1))
                    self.assertLessEqual(timeout, 300, path.name)

    def test_agent_parallelism_and_artifact_retention_are_bounded(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            for value in re.findall(r"(?m)^\s+max-parallel:\s+([0-9]+)\s*$", text):
                self.assertLessEqual(int(value), 3, path.name)
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if "actions/upload-artifact@" in line:
                    window = "\n".join(lines[index:index + 12])
                    self.assertRegex(window, r"(?m)^\s+retention-days:\s+[1-7]\s*$", path.name)

    def test_deprecated_wrapper_workflows_stay_removed(self):
        retired = {
            "activist-scan-sync.yml",
            "drive-intake-sync.yml",
            "portfolio-news.yml",
            "batch-onboard-pdfs.yml",
            "ci-autofix-reusable.yml",
        }
        active = {path.name for path in (ROOT / ".github" / "workflows").glob("*.yml")}
        self.assertTrue(retired.isdisjoint(active))
        self.assertLessEqual(len(active), 19)

    def test_only_dispatcher_invokes_marvin_action(self):
        callers = []
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            if "uses: ./.github/actions/marvin-agent" in path.read_text(encoding="utf-8"):
                callers.append(path.name)
        self.assertEqual(callers, ["research-agent-dispatch.yml"])

    def test_active_workflows_use_pinned_install_and_shared_gate(self):
        active = [
            ROOT / ".github" / "actions" / "marvin-agent" / "action.yml",
            ROOT / ".github" / "actions" / "vicki-agent" / "action.yml",
            ROOT / ".github" / "workflows" / "investment-committee.yml",
        ]
        for path in active:
            text = path.read_text(encoding="utf-8")
            self.assertIn("actions/llm-gate", text, path.name)
            self.assertIn("npm ci", text, path.name)
            self.assertNotIn("npm install --no-save", text, path.name)
        local_runner = (ROOT / "_system" / "scripts" / "run_deep_dive.py").read_text(encoding="utf-8")
        self.assertNotIn("npm install --no-save", local_runner)
        self.assertIn("npm\", \"ci", local_runner)

    def test_committee_does_not_duplicate_open_pr_tasks(self):
        workflow = (ROOT / ".github" / "workflows" / "investment-committee.yml").read_text(encoding="utf-8")
        self.assertIn("Exclude committee tasks with an open PR", workflow)
        self.assertIn('row["task_key"] not in open_titles', workflow)
        self.assertIn('action = "waiting"', workflow)

    def test_agent_pr_merge_continues_after_draft_promotion(self):
        workflow = (ROOT / ".github" / "workflows" / "marvin-pr-automerge.yml").read_text(encoding="utf-8")
        self.assertIn('echo "eligible=true"', workflow)
        self.assertIn("if: steps.meta.outputs.eligible == 'true'", workflow)
        self.assertNotIn("Stop after promoting draft", workflow)

    def test_power_zone_writer_uses_shared_lock_and_retry_push(self):
        workflow = (ROOT / ".github" / "workflows" / "power-zone-universe.yml").read_text(encoding="utf-8")
        self.assertIn("group: data-commit-main", workflow)
        self.assertIn('bash _system/scripts/ci_push_main.sh "chore(valuation): process Power Zone universe"', workflow)
        self.assertNotIn('git push origin "HEAD:${GITHUB_REF_NAME}"', workflow)

    def test_research_quality_checks_use_persistent_pr_head_ref(self):
        workflow = (ROOT / ".github" / "workflows" / "research-quality.yml").read_text(encoding="utf-8")
        persistent_ref = '"pull/${{ github.event.pull_request.number }}/head"'
        self.assertEqual(workflow.count(persistent_ref), 3)

    def test_policy_encodes_expected_call_budgets(self):
        policy = json.loads((ROOT / "_system" / "config" / "llm_usage_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["consumers"]["marvin_research"]["daily_repo_limit"], 4)
        self.assertEqual(policy["consumers"]["investment_committee"]["baseline_calls_per_ticker"], 5)
        self.assertEqual(policy["consumers"]["investment_committee"]["maximum_calls_per_ticker"], 9)
        self.assertEqual(policy["consumers"]["ci_autofix"]["minimum_repeat_count"], 2)

    def test_legacy_static_rollout_fails_closed(self):
        rollout = (ROOT / "_system" / "ci_autofix" / "apply_rollout.sh").read_text(encoding="utf-8")
        self.assertIn("deprecated", rollout.lower())
        self.assertIn("exit 2", rollout)

    def test_ci_rollout_uses_current_repeat_and_signature_controls(self):
        installer = (ROOT / "_system" / "ci_autofix" / "install_org_repos.ps1").read_text(encoding="utf-8")
        self.assertIn("minimum_repeat_count: 2", installer)
        self.assertIn("maximum_failed_jobs: 2", installer)
        self.assertIn("default_action: notify_only", installer)
        implementation = (ROOT / "_system" / "ci_autofix" / "ci_autofix.mjs").read_text(encoding="utf-8")
        self.assertIn("CI-Autofix-Agent-Signature", implementation)

    def test_audit_summary_counts_calls_and_suppressions(self):
        result = summarize([
            {"consumer": "marvin_research", "status": "reserved"},
            {"consumer": "marvin_research", "status": "completed"},
            {"consumer": "vicki_ir", "status": "suppressed", "reason": "duplicate_evidence"},
        ])
        self.assertEqual(result["by_consumer"]["marvin_research"]["completed"], 1)
        self.assertEqual(result["suppression_reasons"]["duplicate_evidence"], 1)


if __name__ == "__main__":
    unittest.main()
