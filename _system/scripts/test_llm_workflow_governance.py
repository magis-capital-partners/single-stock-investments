import json
import unittest
from pathlib import Path

from summarize_llm_ledger import summarize


ROOT = Path(__file__).resolve().parents[2]


class WorkflowGovernanceTests(unittest.TestCase):
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

    def test_policy_encodes_expected_call_budgets(self):
        policy = json.loads((ROOT / "_system" / "config" / "llm_usage_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["consumers"]["marvin_research"]["daily_repo_limit"], 1)
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
