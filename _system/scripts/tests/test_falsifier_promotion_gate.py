"""Approved falsifier drafts must never wedge the Epistemic Falsifier Loop.

On 2026-09-07 a CEG draft stamped spec_revision 1 while superseding a
revision-1 forecast was approved. The promoter appended it in the runner,
check_falsifier_history.py rejected the tree ("superseding revision must
increase"), and the lane died before its commit step on every run for more
than two weeks, holding the ALB, AMZN and AVGO approvals behind it. The PR
that approved it passed, because the history check read sidecars only.

Runs under unittest (the lane has no pytest) and pytest. No network.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import epistemic_loop_controller as controller  # noqa: E402
import promote_falsifier_drafts as promoter  # noqa: E402
from check_falsifier_history import promotion_errors  # noqa: E402
from test_epistemic_integrity import v3_spec  # noqa: E402

COMPONENT = {"component_id": "core", "method": "owner_earnings_reinvestment_dcf"}
FINGERPRINT = hashlib.sha256(json.dumps(
    COMPONENT, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
# The superseded forecast: legacy, revision 1, not calibration eligible (CEG's).
LEGACY = {"spec_id": "tst-legacy", "spec_revision": 1, "component_id": "core",
          "metric": "owner_earnings", "calibration_eligible": False}
BAD = "TST/research/falsifier_drafts/a-bad.json"
HISTORY = SCRIPTS / "check_falsifier_history.py"


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed(root: Path, ticker: str = "TST", specs: list | None = None) -> Path:
    """A ticker both the promoter and the work-queue controller accept."""
    target = root / "_system/research/metric_definitions.json"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / "_system/research/metric_definitions.json").read_bytes())
    research = root / ticker / "research"
    _write(research / "valuation_contract.json", {
        "status": "evidence_blocked",
        "economic_ownership_map": [COMPONENT],
        "evidence": {"blockers": ["prospective_falsifier_gate: core"]},
        "falsifier_coverage": {"prospective_gate": {"missing_components": ["core"]}},
    })
    _write(research / "valuation_route.json", {"profile_id": "quality_reinvestment"})
    _write(research / "evidence/sec_companyfacts.json", {"facts": {"us-gaap": {
        "NetCashProvidedByUsedInOperatingActivities": {},
        "PaymentsToAcquireProductiveAssets": {}}}})
    if specs is not None:
        _write(research / "falsifier_specs.json",
               {"schema_version": "3.0", "ticker": ticker, "specs": specs})
    return research


def _draft(research: Path, name: str, spec: dict, status: str = "approved") -> Path:
    path = research / "falsifier_drafts" / f"{name}.json"
    _write(path, {"schema_version": "1.0", "draft_id": name, "work_id": f"work-{name}",
                  "input_sha": "abcdef0", "component_fingerprint": FINGERPRINT,
                  "status": status, "spec": spec})
    return path


def _superseding(revision: int = 1, **overrides) -> dict:
    """CEG's shape: a new spec_id superseding a revision-1 forecast."""
    return v3_spec(spec_id="tst-core-v2", spec_revision=revision,
                   supersedes_spec_id="tst-legacy", component_fingerprint=FINGERPRINT,
                   **overrides)


def _spec_ids(root: Path, ticker: str) -> list[str]:
    path = root / ticker / "research/falsifier_specs.json"
    if not path.exists():
        return []
    return [row["spec_id"] for row in json.loads(path.read_text(encoding="utf-8"))["specs"]]


class PromoterGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_draft_that_would_break_history_is_held_back_alone(self):
        _draft(_seed(self.root, specs=[LEGACY]), "a-bad", _superseding())
        _draft(_seed(self.root, "OTH"), "b-good", v3_spec(
            spec_id="oth-core", component_fingerprint=FINGERPRINT))
        result = promoter.promote(self.root)
        self.assertEqual([row["draft"] for row in result["blocked"]], [BAD])
        self.assertIn("immutable history: superseding revision must increase",
                      result["blocked"][0]["reasons"][0])
        self.assertEqual([row["ticker"] for row in result["promoted"]], ["OTH"])
        self.assertEqual(_spec_ids(self.root, "TST"), ["tst-legacy"])
        self.assertEqual(_spec_ids(self.root, "OTH"), ["oth-core"])

    def test_a_held_back_draft_is_recorded_on_the_draft_and_in_the_work_queue(self):
        path = _draft(_seed(self.root, specs=[LEGACY]), "a-bad", _superseding())
        _write(self.root / "_system/research/falsifier_calibration.json",
               {"status": "insufficient_outcomes"})
        promoter.promote(self.root)
        draft = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(draft["status"], "approved")
        self.assertIn("superseding revision must increase",
                      draft["promotion_blockers"]["reasons"][0])
        queue = controller.build(self.root, date(2026, 9, 25), write=False)["queue"]
        item = next(item for item in queue["items"] if item["task_type"] == "publish_forecast")
        self.assertEqual(item["state"], "needs_semantic_review")

        # Idempotent: a draft held back for weeks costs one diff, not one per run.
        state = self.root / controller.STATE_REL
        ledger, text = state.read_text(encoding="utf-8"), path.read_text(encoding="utf-8")
        promoter.promote(self.root)
        self.assertEqual(state.read_text(encoding="utf-8"), ledger)
        self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_the_fixed_draft_promotes_and_closes_its_work_item(self):
        path = _draft(_seed(self.root, specs=[LEGACY]), "a-bad", _superseding())
        promoter.promote(self.root)
        draft = json.loads(path.read_text(encoding="utf-8"))
        draft["spec"]["spec_revision"] = 2  # the CEG fix, on the recorded draft
        _write(path, draft)
        result = promoter.promote(self.root)
        self.assertEqual(result["blocked"], [])
        self.assertEqual(_spec_ids(self.root, "TST"), ["tst-legacy", "tst-core-v2"])
        draft = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(draft["status"], "published")
        self.assertNotIn("promotion_blockers", draft)
        work_id = controller._work_id("publish_forecast", "TST", "a-bad")
        events = controller._state_projection(controller._jsonl(self.root / controller.STATE_REL))
        self.assertEqual(events[work_id]["state"], "succeeded")

    def test_a_supersession_of_a_same_pass_promotion_waits_one_run(self):
        # check_falsifier_history judges against origin/main, which cannot yet
        # hold a spec promoted earlier in the same run -- so neither may this.
        research = _seed(self.root, specs=[LEGACY])
        _draft(research, "a-first", _superseding(revision=2))
        _draft(research, "b-second", v3_spec(
            spec_id="tst-core-v3", spec_revision=3, supersedes_spec_id="tst-core-v2",
            component_fingerprint=FINGERPRINT))
        first = promoter.promote(self.root)
        self.assertEqual([row["spec_id"] for row in first["promoted"]], ["tst-core-v2"])
        self.assertIn("supersedes unknown forecast", first["blocked"][0]["reasons"][0])
        second = promoter.promote(self.root)
        self.assertEqual([row["spec_id"] for row in second["promoted"]], ["tst-core-v3"])

    def test_a_malformed_revision_holds_back_its_draft_without_crashing_the_lane(self):
        # The history check keys on int(spec_revision), so it may only ever see
        # drafts that already passed spec_errors; otherwise "v2" is a traceback
        # that kills the whole run, which the old promoter never allowed.
        for revision in ("v2", "2.0", [2]):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _draft(_seed(root, specs=[LEGACY]), "a-bad", _superseding(revision=revision))
                _draft(_seed(root, "OTH"), "b-good", v3_spec(
                    spec_id="oth-core", component_fingerprint=FINGERPRINT))
                result = promoter.promote(root)
                self.assertEqual([row["draft"] for row in result["blocked"]], [BAD])
                self.assertIn("spec_revision: positive integer required",
                              result["blocked"][0]["reasons"][0])
                self.assertEqual([row["ticker"] for row in result["promoted"]], ["OTH"])

    def test_a_problem_already_in_the_sidecar_blocks_no_new_draft(self):
        duplicated = {"specs": [LEGACY, dict(LEGACY)]}
        self.assertEqual(promotion_errors("TST", duplicated, duplicated,
                                          v3_spec(spec_id="tst-new")), [])

    def test_held_back_drafts_do_not_fail_the_lane(self):
        _draft(_seed(self.root, specs=[LEGACY]), "a-bad", _superseding())
        run = subprocess.run([sys.executable, str(SCRIPTS / "promote_falsifier_drafts.py"),
                              "--root", str(self.root), "--dry-run"],
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["blocked"], 1)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.com",
                    "-c", "user.name=t", "-c", "core.autocrlf=false", *args],
                   check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git"), "git required")
class PullRequestSimulationTests(unittest.TestCase):
    """check_falsifier_history.py, as the PR gate and the lane run it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def _commit(self) -> None:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "base")

    def _check(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HISTORY), "--root", str(self.root),
                               "--base-ref", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_approving_a_draft_that_cannot_promote_fails_the_pr(self):
        research = _seed(self.root, specs=[LEGACY])
        _draft(research, "a-bad", _superseding(), status="awaiting_review")
        self._commit()
        _draft(research, "a-bad", _superseding())  # the PR approves it
        run = self._check()
        self.assertEqual(run.returncode, 1, run.stdout)
        self.assertIn(f"approved draft {BAD} would not promote: "
                      "superseding revision must increase", run.stdout)
        _draft(research, "a-bad", _superseding(revision=2))  # the fix
        self.assertEqual(self._check().returncode, 0)

    def test_approving_a_malformed_draft_is_reported_not_a_traceback(self):
        research = _seed(self.root, specs=[LEGACY])
        self._commit()
        _draft(research, "a-bad", _superseding(revision="v2"))
        run = self._check()
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn(f"approved draft {BAD} would not promote: "
                      "specs[0].spec_revision: positive integer required", run.stdout)
        self.assertNotIn("Traceback", run.stderr)

    def test_a_pr_that_adds_an_unparseable_draft_fails(self):
        # The promoter holds an unparseable draft back, so the lane survives
        # it; the PR that introduces one must not pass in silence.
        research = _seed(self.root, specs=[LEGACY])
        self._commit()
        broken = research / "falsifier_drafts/c-broken.json"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text('{"status": "approved", "spec": {', encoding="utf-8")
        run = self._check()
        self.assertEqual(run.returncode, 1, run.stdout)
        self.assertIn("draft TST/research/falsifier_drafts/c-broken.json is not valid JSON",
                      run.stdout)
        self._commit()  # already broken on the base: an unrelated PR stays green
        self.assertEqual(self._check().returncode, 0)

    def test_a_draft_already_approved_on_the_base_reddens_no_unrelated_pr(self):
        # ...nor the lane's own post-promotion check, once the promoter has
        # held it back and recorded why on the draft.
        path = _draft(_seed(self.root, specs=[LEGACY]), "a-bad", _superseding())
        self._commit()
        promoter.promote(self.root)
        self.assertIn("promotion_blockers", json.loads(path.read_text(encoding="utf-8")))
        run = self._check()
        self.assertEqual(run.returncode, 0, run.stdout)

    def test_the_lane_validates_after_promoting_past_a_bad_draft(self):
        _draft(_seed(self.root, specs=[LEGACY]), "a-bad", _superseding())
        _draft(_seed(self.root, "OTH"), "b-good", v3_spec(
            spec_id="oth-core", component_fingerprint=FINGERPRINT))
        self._commit()
        promoter.promote(self.root)
        run = self._check()
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertEqual(_spec_ids(self.root, "OTH"), ["oth-core"])


class LaneWorkflowTests(unittest.TestCase):
    WORKFLOW = REPO / ".github/workflows/falsifier-resolution.yml"

    def _validate_block(self) -> list[str]:
        lines = self.WORKFLOW.read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(lines)
                     if "name: Validate the post-resolution tree" in line)
        end = next(i for i in range(start + 1, len(lines)) if "- name:" in lines[i])
        return lines[start:end]

    def test_the_lane_runs_the_promotion_gate_tests(self):
        self.assertTrue(any("test_falsifier_promotion_gate" in line
                            for line in self._validate_block()))

    @unittest.skipUnless(shutil.which("bash"), "bash required")
    def test_a_crashed_invariant_run_cannot_pass_on_the_checked_out_report(self):
        # graph_invariants.py exits 1 for other lanes' violations, so the lane
        # tolerates its exit code; that tolerance must not extend to a crash
        # that leaves the report committed with the checkout in place.
        snippet = [line.strip() for line in self._validate_block()
                   if "invariant" in line and not line.strip().startswith("#")]
        self.assertTrue(any("validate_invariant_subset.py" in line for line in snippet))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "_system/scripts"
            scripts.mkdir(parents=True)
            shutil.copy2(SCRIPTS / "validate_invariant_subset.py", scripts)
            (scripts / "graph_invariants.py").write_text(
                "raise SystemExit('graph build crashed')\n", encoding="utf-8")
            _write(root / "_system/graph/invariants.json", {"invariants": [
                {"id": ident, "severity": "hard", "count": 0}
                for ident in ("E2", "E3", "E4", "E5", "E7", "E8", "E9")]})
            run = subprocess.run(["bash", "-c", "set -euo pipefail\n" + "\n".join(snippet)],
                                 cwd=root, capture_output=True, text=True,
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertNotEqual(run.returncode, 0, run.stdout)


if __name__ == "__main__":
    unittest.main()
