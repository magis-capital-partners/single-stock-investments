"""Job-level, work-done lane receipts (build_lane_receipts.py).

The fake below stands in for the ``gh`` CLI itself -- both the ``gh run list``
call the schema-1 builder made and the ``gh api`` calls the job-level builder
makes -- so these tests exercise either implementation through the same
boundary. Each scenario is one that the whole-run receipts got wrong.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_lane_receipts as builder  # noqa: E402

REPO = "owner/repo"


def run(run_id, created, jobs, conclusion="success", event="schedule", status="completed"):
    return {"id": run_id, "created_at": created, "updated_at": created,
            "run_started_at": created, "status": status, "conclusion": conclusion,
            "event": event, "head_branch": "main", "head_sha": f"sha{run_id}",
            "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}", "_jobs": jobs}


def job(job_id, name, conclusion, completed, steps=()):
    return {"id": job_id, "name": name, "conclusion": conclusion, "status": "completed",
            "started_at": completed, "completed_at": completed,
            "steps": [{"name": n, "conclusion": c, "number": i + 1}
                      for i, (n, c) in enumerate(steps)]}


class FakeGh:
    """Answers the gh invocations both receipt builders make."""

    def __init__(self, runs_by_workflow, annotations=None):
        self.runs = runs_by_workflow
        self.annotations = annotations or {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append(list(cmd))
        out = self.respond(cmd)
        return subprocess.CompletedProcess(cmd, 0 if out is not None else 1,
                                           stdout=json.dumps(out) if out is not None else "",
                                           stderr="" if out is not None else "not found")

    def respond(self, cmd):
        if cmd[:3] == ["gh", "run", "list"]:          # the schema-1 builder
            workflow = cmd[cmd.index("--workflow") + 1]
            rows = [r for r in self.runs.get(workflow, [])
                    if r["status"] == "completed" and r["conclusion"] == "success"]
            rows.sort(key=lambda r: r["id"], reverse=True)
            return [{"databaseId": r["id"], "createdAt": r["created_at"],
                     "updatedAt": r["updated_at"], "headSha": r["head_sha"],
                     "url": r["html_url"], "conclusion": r["conclusion"]} for r in rows[:20]]
        if cmd[:2] != ["gh", "api"]:
            return None
        path = cmd[2]
        prefix = f"repos/{REPO}/"
        if not path.startswith(prefix):
            return None
        path = path[len(prefix):]
        if path.startswith("actions/workflows/") and "/runs" in path:
            workflow = path.split("/")[2]
            rows = sorted(self.runs.get(workflow, []), key=lambda r: r["id"], reverse=True)
            return {"workflow_runs": [{k: v for k, v in r.items() if k != "_jobs"}
                                      for r in rows]}
        if path.startswith("actions/workflows/"):
            return {"state": "active"}
        if path.startswith("actions/runs/") and "/jobs" in path:
            run_id = int(path.split("/")[2])
            for rows in self.runs.values():
                for r in rows:
                    if r["id"] == run_id:
                        return {"jobs": r["_jobs"]}
            return None
        if path.startswith("check-runs/") and path.endswith("/annotations"):
            return self.annotations.get(int(path.split("/")[1]), [])
        return None


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def configure(self, lanes):
        path = self.root / "_system/graph/graph_sources.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")

    def build(self, fake):
        with mock.patch.object(builder.subprocess, "run", fake):
            return builder.build(self.root, REPO)

    def receipt(self, lane):
        path = self.root / f"_system/data/lane_receipts/{lane}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_a_gate_only_run_never_refreshes_the_receipt(self):
        # ls-algo 2026-09-24: every scheduled intake failed, while workflow_run
        # triggers whose intake job was skipped kept the receipt "fresh".
        self.configure([{"name": "ls-algo", "workflow_file": "ls.yml", "job": "intake",
                         "freshness_hours": 54}])
        fake = FakeGh({"ls.yml": [
            run(1, "2026-08-11T04:00:00Z",
                [job(11, "intake", "success", "2026-08-11T04:14:38Z")]),
            run(2, "2026-09-24T07:49:04Z",
                [job(21, "intake", "failure", "2026-09-24T08:30:00Z",
                     [("Identity, onboard", "failure")])], conclusion="failure"),
            run(3, "2026-09-24T19:10:49Z",
                [job(31, "gate", "success", "2026-09-24T19:10:58Z"),
                 job(32, "intake", "skipped", "2026-09-24T19:10:58Z")]),
        ]})
        self.build(fake)
        receipt = self.receipt("ls-algo")
        self.assertEqual(receipt["last_success_at"], "2026-08-11T04:14:38Z")
        self.assertEqual(receipt["latest"]["outcome"], "failure")

    def test_a_timed_out_job_is_a_failure_not_a_cancel(self):
        self.configure([{"name": "news", "workflow_file": "dp.yml", "job": "news",
                         "freshness_hours": 18}])
        fake = FakeGh({"dp.yml": [
            run(1, "2026-09-21T22:06:43Z",
                [job(11, "news", "success", "2026-09-21T22:45:33Z")]),
            run(2, "2026-09-24T17:26:29Z",
                [job(21, "news", "cancelled", "2026-09-24T18:33:48Z",
                     [("Ingest portfolio news", "cancelled")])], conclusion="cancelled"),
        ]}, annotations={21: [{"annotation_level": "failure",
                               "message": "The job has exceeded the maximum execution"
                                          " time of 45m0s"}]})
        self.build(fake)
        receipt = self.receipt("news")
        self.assertEqual(receipt["last_success_at"], "2026-09-21T22:45:33Z")
        self.assertEqual(receipt["latest"]["outcome"], "timeout")
        self.assertEqual(receipt["failures"][0]["failed_step"], "Ingest portfolio news")

    def test_each_pipeline_job_is_its_own_lane(self):
        # The Data Pipeline's drive job kept "data-pipeline" green while the
        # activist job had not succeeded in 30 runs.
        self.configure([
            {"name": "drive", "workflow_file": "dp.yml", "job": "drive", "freshness_hours": 54},
            {"name": "activist", "workflow_file": "dp.yml", "job": "activist",
             "freshness_hours": 54}])
        fake = FakeGh({"dp.yml": [
            run(1, "2026-09-24T11:03:54Z",
                [job(11, "activist", "cancelled", "2026-09-24T12:34:19Z",
                     [("Run activist scan", "cancelled")])], conclusion="cancelled"),
            run(2, "2026-09-24T18:00:40Z",
                [job(21, "drive", "success", "2026-09-24T18:36:00Z")]),
        ]}, annotations={11: [{"message": "The job has exceeded the maximum execution time"
                                          " of 1h30m0s"}]})
        self.build(fake)
        self.assertEqual(self.receipt("drive")["last_success_at"], "2026-09-24T18:36:00Z")
        activist = self.receipt("activist")
        self.assertIsNone(activist["last_success_at"])
        self.assertEqual(activist["latest"]["outcome"], "timeout")

    def test_a_skipped_work_step_is_a_noop(self):
        self.configure([{"name": "drive", "workflow_file": "dp.yml", "job": "drive",
                         "work_step": "Import Drive intake PDFs", "freshness_hours": 54}])
        fake = FakeGh({"dp.yml": [
            run(1, "2026-09-20T14:00:00Z",
                [job(11, "drive", "success", "2026-09-20T14:30:00Z",
                     [("Import Drive intake PDFs", "success")])]),
            run(2, "2026-09-24T14:00:00Z",
                [job(21, "drive", "success", "2026-09-24T14:05:00Z",
                     [("Import Drive intake PDFs", "skipped"), ("Skip note", "success")])]),
        ]})
        self.build(fake)
        self.assertEqual(self.receipt("drive")["last_success_at"], "2026-09-20T14:30:00Z")

    def test_a_schema_one_receipt_is_not_trusted(self):
        # "Never rewind" must not preserve a timestamp that came from a no-op run.
        self.configure([{"name": "ls-algo", "workflow_file": "ls.yml", "job": "intake",
                         "freshness_hours": 54}])
        stale = self.root / "_system/data/lane_receipts/ls-algo.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text(json.dumps({"schema_version": "1.0", "lane": "ls-algo",
                                     "workflow_file": "ls.yml",
                                     "last_success_at": "2026-09-24T19:10:58Z"}),
                         encoding="utf-8")
        fake = FakeGh({"ls.yml": [
            run(3, "2026-09-24T19:10:49Z",
                [job(31, "gate", "success", "2026-09-24T19:10:58Z"),
                 job(32, "intake", "skipped", "2026-09-24T19:10:58Z")]),
        ]})
        self.build(fake)
        self.assertIsNone(self.receipt("ls-algo")["last_success_at"])

    def test_a_lane_with_no_success_does_not_fail_the_build(self):
        # The schema-1 builder returned 1 here, which fails the supervisor job
        # before it can report the very lane that has never succeeded.
        self.configure([{"name": "two-phase", "workflow_file": "tp.yml", "job": "watch",
                         "freshness_hours": 342}])
        fake = FakeGh({"tp.yml": [
            run(1, "2026-09-20T19:17:21Z",
                [job(11, "watch", "failure", "2026-09-20T19:20:00Z",
                     [("Compile two-phase watch", "failure")])], conclusion="failure")]})
        with mock.patch.object(builder.subprocess, "run", fake), \
                mock.patch.object(sys, "argv", ["build_lane_receipts.py", "--root",
                                                str(self.root), "--repository", REPO]), \
                mock.patch("builtins.print"):
            self.assertEqual(builder.main(), 0)

    def test_scans_are_incremental_and_never_rewind(self):
        self.configure([{"name": "memory", "workflow_file": "m.yml", "job": "triage",
                         "freshness_hours": 54}])
        runs = [run(1, "2026-09-23T15:02:00Z",
                    [job(11, "triage", "success", "2026-09-23T15:20:00Z")]),
                run(2, "2026-09-24T15:08:00Z",
                    [job(21, "triage", "success", "2026-09-24T15:22:22Z")])]
        fake = FakeGh({"m.yml": runs})
        self.build(fake)
        first = self.receipt("memory")
        self.assertEqual(first["last_success_at"], "2026-09-24T15:22:22Z")
        self.assertEqual(first["scanned_through"], 2)
        fake.calls.clear()
        self.build(fake)
        jobs_calls = [c for c in fake.calls if c[:2] == ["gh", "api"] and "/jobs" in c[2]]
        self.assertEqual(jobs_calls, [], "completed runs below the watermark are not refetched")
        self.assertEqual(self.receipt("memory")["last_success_at"], "2026-09-24T15:22:22Z")

    def test_an_in_flight_run_holds_the_watermark(self):
        self.configure([{"name": "memory", "workflow_file": "m.yml", "job": "triage",
                         "freshness_hours": 54}])
        runs = [run(1, "2026-09-23T15:02:00Z",
                    [job(11, "triage", "success", "2026-09-23T15:20:00Z")]),
                run(2, "2026-09-24T15:08:00Z", [], status="in_progress", conclusion=None),
                run(3, "2026-09-24T17:08:00Z",
                    [job(31, "triage", "success", "2026-09-24T17:22:00Z")])]
        self.build(FakeGh({"m.yml": runs}))
        receipt = self.receipt("memory")
        self.assertEqual(receipt["scanned_through"], 1)
        self.assertTrue(receipt["in_flight"])
        self.assertEqual(receipt["last_success_at"], "2026-09-24T17:22:00Z")


if __name__ == "__main__":
    unittest.main()
