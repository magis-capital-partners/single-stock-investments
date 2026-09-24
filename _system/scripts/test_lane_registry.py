"""Lane contract, cron spans and job-level run classification (lane_registry)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_registry as lr  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


SCHEDULED = """name: Nightly
on:
  schedule:
    - cron: "7 3 * * *"
  repository_dispatch:
    types: [nightly-run]
jobs:
  work:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - name: Do the work
        if: env.READY == 'true'
        run: echo work
  pretty:
    name: Pretty Name
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo hi
  analyze:
    name: analyze-${{ matrix.language }}
    runs-on: ubuntu-latest
    timeout-minutes: 5
    strategy:
      matrix:
        language: [python, actions]
    steps:
      - run: echo scan
  research:
    needs: work
    uses: ./.github/workflows/called.yml
"""

CALLED = """name: Called
on:
  workflow_call:
jobs:
  select:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Pick
        run: echo pick
"""

PUSH_ONLY = """name: Push only
on: push
jobs:
  q:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo q
"""


class ContractFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write(self.root / ".github/workflows/nightly.yml", SCHEDULED)
        write(self.root / ".github/workflows/called.yml", CALLED)
        write(self.root / ".github/workflows/push.yml", PUSH_ONLY)

    def tearDown(self):
        self._tmp.cleanup()

    def contract(self, lanes, exempt=None):
        config = {"lanes": lanes}
        if exempt is not None:
            config["unmonitored_workflows"] = exempt
        return lr.lane_contract(self.root, config)

    def lane(self, **extra):
        base = {"name": "nightly", "workflow_file": "nightly.yml", "job": "work",
                "freshness_hours": 54}
        base.update(extra)
        return base

    def test_a_wired_lane_passes(self):
        violations, warnings = self.contract([self.lane(work_step="Do the work")])
        self.assertEqual(violations, [])
        self.assertEqual(warnings, [])

    def test_missing_workflow_job_and_step_are_violations(self):
        for lane, needle in (
                (self.lane(workflow_file="gone.yml"), "does not exist"),
                (self.lane(job="nope"), "no job named 'nope'"),
                (self.lane(work_step="Not a step"), "no step named 'Not a step'"),
                (self.lane(job=None), "declares no job"),
                (self.lane(freshness_hours=None), "freshness_hours")):
            violations, _ = self.contract([lane], exempt={})
            self.assertTrue(any(needle in v for v in violations), (lane, violations))

    def test_job_must_be_named_as_the_api_reports_it(self):
        # The Actions API reports "Pretty Name", never the id, so a lane naming
        # the id could never advance its receipt.
        violations, _ = self.contract([self.lane(job="pretty")])
        self.assertTrue(any("no job named 'pretty'" in v for v in violations), violations)
        violations, _ = self.contract([self.lane(job="Pretty Name")])
        self.assertEqual(violations, [])

    def test_matrix_and_reusable_jobs_resolve(self):
        violations, _ = self.contract([self.lane(job="analyze-*")])
        self.assertEqual(violations, [])
        violations, _ = self.contract([self.lane(job="research / select", work_step="Pick")])
        self.assertEqual(violations, [])
        violations, _ = self.contract([self.lane(job="research / nope")])
        self.assertTrue(any("has no job 'nope'" in v for v in violations), violations)

    def test_scheduled_workflow_must_be_a_lane_or_exempt(self):
        violations, _ = self.contract([])
        self.assertEqual(violations, ["nightly.yml: scheduled workflow is not declared as a"
                                      " lane (or listed in unmonitored_workflows with a"
                                      " reason)"])
        violations, _ = self.contract([], exempt={"nightly.yml": "retired on purpose"})
        self.assertEqual(violations, [])
        violations, _ = self.contract([], exempt={"nightly.yml": ""})
        self.assertTrue(any("needs a reason" in v for v in violations), violations)

    def test_a_scheduled_yaml_workflow_is_seen_too(self):
        write(self.root / ".github/workflows/weekly.yaml",
              SCHEDULED.replace('"7 3 * * *"', '"9 4 * * 1"'))
        violations, _ = self.contract([self.lane()])
        self.assertTrue(any(v.startswith("weekly.yaml: scheduled workflow is not declared")
                            for v in violations), violations)

    def test_exemption_for_a_deleted_workflow_is_only_a_warning(self):
        # So the lane registry and a PR deleting the workflow can land in either order.
        violations, warnings = self.contract([self.lane()], exempt={"deleted.yml": "retired"})
        self.assertEqual(violations, [])
        self.assertEqual(len(warnings), 1)

    def test_duplicate_lane_names_are_violations(self):
        violations, _ = self.contract([self.lane(), self.lane()])
        self.assertTrue(any("declared twice" in v for v in violations), violations)


class RealRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = lr.load_config(REPO_ROOT)
        cls.lanes = lr.declared_lanes(cls.config)

    def test_the_registry_satisfies_its_own_contract(self):
        violations, _ = lr.lane_contract(REPO_ROOT, self.config)
        self.assertEqual(violations, [])

    def test_every_window_covers_one_skipped_cycle_plus_jitter(self):
        for lane in self.lanes:
            crons = lane.get("cadence_cron")
            self.assertTrue(crons, f"{lane['name']}: declare cadence_cron")
            floor = lr.one_skip_span_hours(crons) + lr.JITTER_HOURS
            self.assertGreaterEqual(lane["freshness_hours"], floor, lane["name"])
            # ...and is not so loose that a dead lane hides for weeks.
            self.assertLessEqual(lane["freshness_hours"], max(2 * floor, 24), lane["name"])

    def test_every_lane_is_job_anchored(self):
        for lane in self.lanes:
            self.assertTrue(lane.get("workflow_file") and lane.get("job"), lane["name"])

    def test_required_lanes_are_declared(self):
        names = {lane["name"] for lane in self.lanes}
        for required in ("supervisor", "forced-flow", "two-phase-watch", "ls-algo",
                         "valuation", "data-pipeline-news", "data-pipeline-activist",
                         "data-pipeline-technicals", "data-pipeline-intake-full",
                         "data-pipeline-drive", "data-pipeline-warrant-discover",
                         "data-pipeline-world-model", "data-pipeline-cvr-discover",
                         "research-watchdog", "falsifier", "memory-digest"):
            self.assertIn(required, names)
        workflows = {lane["workflow_file"] for lane in self.lanes}
        for retired in ("vicki-ir-harvest.yml", "youtube-refresh.yml", "darwin-refresh.yml",
                        "deploy-oauth-proxy.yml", "filing-sentinel-gold.yml"):
            self.assertNotIn(retired, workflows)

    def test_memory_digest_is_watched_daily_not_weekly(self):
        lane = next(l for l in self.lanes if l["name"] == "memory-digest")
        self.assertLessEqual(lane["freshness_hours"], 54)

    def test_supervisor_lane_is_about_twelve_hours(self):
        lane = next(l for l in self.lanes if l["name"] == "supervisor")
        self.assertEqual(lane["freshness_hours"], 12)

    def test_parser_matches_pyyaml_on_every_workflow(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed; the parser exists so CI does not need it")
        for path in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            mine = lr.parse_workflow(text)
            ref = yaml.safe_load(text)
            on = ref.get(True, ref.get("on"))
            triggers = {on} if isinstance(on, str) else set(on or [])
            self.assertEqual(mine["triggers"], triggers, path.name)
            crons = [row["cron"] for row in (on.get("schedule") or [])] \
                if isinstance(on, dict) else []
            self.assertEqual(mine["crons"], crons, path.name)
            for job_id, job in (ref.get("jobs") or {}).items():
                got = mine["jobs"][job_id]
                self.assertEqual(got["name"], job.get("name"), (path.name, job_id))
                self.assertEqual(got["uses"], job.get("uses"), (path.name, job_id))
                self.assertEqual([s["name"] for s in got["steps"]],
                                 [s.get("name") for s in job.get("steps") or []],
                                 (path.name, job_id))


class Cron(unittest.TestCase):
    def test_one_skip_spans(self):
        cases = {
            ("0 3 * * *",): 48, ("15 2 * * 1-5",): 96, ("0 15 * * 1",): 336,
            ("30 */6 * * *",): 12, ("0 12 * * 1,2,4,5,6", "0 10 * * 0,3"): 50,
            ("13 16 * * 0", "11 15 * * 3"): 168, ("41 */2 * * *",): 4,
        }
        for crons, hours in cases.items():
            self.assertAlmostEqual(lr.one_skip_span_hours(list(crons)), hours, places=3,
                                   msg=str(crons))


def job(name, conclusion, steps=(), job_id=1, completed="2026-09-24T10:00:00Z"):
    return {"id": job_id, "name": name, "conclusion": conclusion,
            "started_at": "2026-09-24T09:00:00Z", "completed_at": completed,
            "steps": [{"name": n, "conclusion": c} for n, c in steps]}


class Classify(unittest.TestCase):
    lane = {"name": "x", "workflow_file": "w.yml", "job": "news"}

    def classify(self, jobs, lane=None, timeout=False):
        return lr.classify_lane_run(jobs, lane or self.lane, lambda _job: timeout)

    def test_absent_job_is_not_this_lanes_run(self):
        self.assertIsNone(self.classify([job("activist", "success")]))

    def test_success_skip_failure(self):
        self.assertEqual(self.classify([job("news", "success")])["outcome"], lr.SUCCESS)
        self.assertEqual(self.classify([job("news", "skipped")])["outcome"], lr.SKIPPED)
        failed = self.classify([job("news", "failure", [("Checkout", "success"),
                                                         ("Ingest", "failure")])])
        self.assertEqual((failed["outcome"], failed["failed_step"]), (lr.FAILURE, "Ingest"))

    def test_timeout_is_a_failure_and_plain_cancel_is_neutral(self):
        jobs = [job("news", "cancelled", [("Ingest", "cancelled")])]
        timed_out = self.classify(jobs, timeout=True)
        self.assertEqual((timed_out["outcome"], timed_out["failed_step"]),
                         (lr.TIMEOUT, "Ingest"))
        self.assertIn(lr.TIMEOUT, lr.FAILING_OUTCOMES)
        self.assertEqual(self.classify(jobs, timeout=False)["outcome"], lr.CANCELLED)
        # Unknown (annotations unreadable) is neither: the run stays unresolved.
        self.assertEqual(self.classify(jobs, timeout=None)["outcome"], lr.UNRESOLVED)

    def test_skipped_work_step_is_a_noop_not_a_success(self):
        lane = {"name": "drive", "workflow_file": "w.yml", "job": "drive",
                "work_step": "Import Drive intake PDFs"}
        noop = self.classify([job("drive", "success", [("Import Drive intake PDFs", "skipped"),
                                                        ("Skip note", "success")])], lane)
        self.assertEqual(noop["outcome"], lr.NOOP)
        done = self.classify([job("drive", "success", [("Import Drive intake PDFs", "success")])],
                             lane)
        self.assertEqual(done["outcome"], lr.SUCCESS)

    def test_matrix_lane_fails_if_any_leg_fails(self):
        lane = {"name": "scan", "workflow_file": "w.yml", "job": "analyze-*"}
        jobs = [job("analyze-python", "success", job_id=1),
                job("analyze-actions", "failure", job_id=2)]
        self.assertEqual(self.classify(jobs, lane)["outcome"], lr.FAILURE)
        jobs[1]["conclusion"] = "success"
        self.assertEqual(self.classify(jobs, lane)["outcome"], lr.SUCCESS)


class ReceiptCurrency(unittest.TestCase):
    def test_schema_one_receipt_proves_nothing_for_a_job_lane(self):
        lane = {"name": "ls-algo", "workflow_file": "ls-algo-universe.yml", "job": "intake"}
        old = {"schema_version": "1.0", "last_success_at": "2026-09-24T19:10:58Z",
               "workflow_file": "ls-algo-universe.yml"}
        self.assertFalse(lr.receipt_is_current(old, lane))
        new = dict(old, schema_version=lr.RECEIPT_SCHEMA, job="intake", work_step=None)
        self.assertTrue(lr.receipt_is_current(new, lane))
        self.assertFalse(lr.receipt_is_current(dict(new, job="gate"), lane))


if __name__ == "__main__":
    unittest.main()
