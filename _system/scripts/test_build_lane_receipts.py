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
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_lane_receipts as builder  # noqa: E402

REPO = "owner/repo"
NOW = datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc)


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

    def __init__(self, runs_by_workflow, annotations=None, annotation_errors=()):
        self.runs = runs_by_workflow
        self.annotations = annotations or {}
        self.annotation_errors = set(annotation_errors)
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
            # Behaves like the real endpoint: newest first, per_page / page,
            # and the created>= filter.
            workflow = path.split("/")[2]
            query = parse_qs(urlsplit(path).query)
            per_page = int(query.get("per_page", ["30"])[0])
            page = int(query.get("page", ["1"])[0])
            rows = sorted(self.runs.get(workflow, []), key=lambda r: r["id"], reverse=True)
            created = unquote(query.get("created", [""])[0])
            if created.startswith(">="):
                rows = [r for r in rows if r["created_at"] >= created[2:]]
            rows = rows[(page - 1) * per_page:page * per_page]
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
            job_id = int(path.split("/")[1])
            if job_id in self.annotation_errors:
                return None
            return self.annotations.get(job_id, [])
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

    def build(self, fake, now=NOW, api=None):
        with mock.patch.object(builder.subprocess, "run", fake):
            try:
                return builder.build(self.root, REPO, api=api, now=now)
            except TypeError:          # the schema-1 builder had no clock
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
        self.assertNotEqual(receipt["last_success_at"], "2026-09-24T19:10:58Z")
        self.assertIsNone(receipt["last_success_at"], "08-11 is outside the 2x54h lookback")
        self.assertTrue(receipt["history_complete"])
        self.assertEqual(receipt["latest"]["outcome"], "failure")

    def test_a_timed_out_job_is_a_failure_not_a_cancel(self):
        self.configure([{"name": "news", "workflow_file": "dp.yml", "job": "news",
                         "freshness_hours": 18}])
        fake = FakeGh({"dp.yml": [
            run(1, "2026-09-24T05:16:00Z",
                [job(11, "news", "success", "2026-09-24T05:55:00Z")]),
            run(2, "2026-09-24T17:26:29Z",
                [job(21, "news", "cancelled", "2026-09-24T18:33:48Z",
                     [("Ingest portfolio news", "cancelled")])], conclusion="cancelled"),
        ]}, annotations={21: [{"annotation_level": "failure",
                               "message": "The job has exceeded the maximum execution"
                                          " time of 45m0s"}]})
        self.build(fake)
        receipt = self.receipt("news")
        self.assertEqual(receipt["last_success_at"], "2026-09-24T05:55:00Z")
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

    def test_a_first_build_stops_at_the_newest_success(self):
        # 26 lanes x a 50-run listing, walked oldest-first, would spend the
        # token's whole hourly REST budget on the first supervisor run.
        self.configure([{"name": "backfill", "workflow_file": "b.yml", "job": "refill",
                         "freshness_hours": 24}])
        runs = [run(n, f"2026-09-24T{n:02d}:33:00Z",
                    [job(100 + n, "refill", "success", f"2026-09-24T{n:02d}:40:00Z")])
                for n in range(1, 11)]
        fake = FakeGh({"b.yml": runs})
        self.build(fake)
        jobs_calls = [c for c in fake.calls if c[:2] == ["gh", "api"] and "/jobs" in c[2]]
        self.assertEqual(len(jobs_calls), 1)
        self.assertEqual(self.receipt("backfill")["run_id"], 10)

    def test_the_job_call_budget_defers_the_rest_to_the_next_build(self):
        self.configure([{"name": "activist", "workflow_file": "dp.yml", "job": "activist",
                         "freshness_hours": 54}])
        runs = [run(n, f"2026-09-2{n}T11:03:54Z",
                    [job(100 + n, "activist", "failure", f"2026-09-2{n}T12:34:19Z",
                         [("Run activist scan", "failure")])], conclusion="failure")
                for n in range(1, 6)]
        fake = FakeGh({"dp.yml": runs})
        result = self.build(fake, api=builder.GhApi(REPO, max_job_calls=2))
        receipt = self.receipt("activist")
        self.assertEqual([f["run_id"] for f in receipt["failures"]], [5, 4])
        self.assertEqual((receipt["scanned_through"], receipt["scan_low"]), (5, 4))
        self.assertFalse(receipt["history_complete"], "not judged until the walk finishes")
        self.assertTrue(any("budget" in e for e in result["api_errors"]))
        fake.calls.clear()
        self.build(fake, api=builder.GhApi(REPO, max_job_calls=10))
        receipt = self.receipt("activist")
        self.assertEqual([f["run_id"] for f in receipt["failures"]], [5, 4, 3, 2, 1])
        self.assertTrue(receipt["history_complete"])
        jobs_calls = [c[2] for c in fake.calls if c[:2] == ["gh", "api"] and "/jobs" in c[2]]
        self.assertEqual(len(jobs_calls), 3, "the walk resumes below the cut, not from the top")

    def test_an_unreadable_annotation_leaves_the_cancel_unresolved(self):
        # A cancelled job whose annotations cannot be read might have been a
        # timeout. Recording it as a harmless cancel buried it for good.
        self.configure([{"name": "news", "workflow_file": "dp.yml", "job": "news",
                         "freshness_hours": 18}])
        runs = [run(1, "2026-09-24T05:10:00Z",
                    [job(11, "news", "success", "2026-09-24T05:50:00Z")]),
                run(2, "2026-09-24T17:26:29Z",
                    [job(21, "news", "cancelled", "2026-09-24T18:11:29Z",
                         [("Ingest portfolio news", "cancelled")])], conclusion="cancelled")]
        timeout = [{"message": "The job has exceeded the maximum execution time of 45m0s"}]
        self.build(FakeGh({"dp.yml": runs}, annotations={21: timeout}, annotation_errors={21}))
        receipt = self.receipt("news")
        self.assertFalse(receipt["history_complete"], "run 2 is unresolved: not judged yet")
        self.assertEqual(receipt["scan_low"], 3, "run 2 is rescanned on the next build")
        self.build(FakeGh({"dp.yml": runs}, annotations={21: timeout}))
        receipt = self.receipt("news")
        self.assertEqual(receipt["latest"]["outcome"], "timeout")
        self.assertEqual(receipt["last_success_at"], "2026-09-24T05:50:00Z")

    def test_a_weekly_job_in_a_busy_workflow_is_found_on_the_first_build(self):
        # 50 Data Pipeline runs are about three days; the weekly world-model
        # job's last success is six days back, so a 50-run listing read it as
        # stale on the very first run.
        self.configure([{"name": "world-model", "workflow_file": "dp.yml",
                         "job": "world-model", "freshness_hours": 342}])
        runs = [run(1, "2026-09-18T16:00:00Z",
                    [job(11, "world-model", "success", "2026-09-18T16:40:00Z")])]
        runs += [run(n, f"2026-09-{19 + (n - 2) // 25:02d}T{(n - 2) % 24:02d}:10:00Z",
                     [job(10 * n, "news", "success", "2026-09-24T00:00:00Z")])
                 for n in range(2, 142)]
        self.build(FakeGh({"dp.yml": runs}))
        receipt = self.receipt("world-model")
        self.assertEqual(receipt["last_success_at"], "2026-09-18T16:40:00Z")

    def test_a_cut_on_a_new_run_keeps_a_judged_lanes_verdict(self):
        # Verifier flap probe: one 502 on the jobs call for one new ls-algo run
        # reset the history walk, the supervisor announced "[RECOVERED] ls-algo:
        # work-done success at None", then "[STALE]" again on the next build.
        self.configure([{"name": "ls-algo", "workflow_file": "ls.yml", "job": "intake",
                         "freshness_hours": 54}])
        old = [run(n, f"2026-09-24T0{n}:00:00Z",
                   [job(10 * n, "intake", "failure", f"2026-09-24T0{n}:30:00Z",
                        [("Identity, onboard", "failure")])], conclusion="failure")
               for n in range(1, 4)]
        self.build(FakeGh({"ls.yml": old}))
        judged = self.receipt("ls-algo")
        self.assertTrue(judged["history_complete"])
        newer = run(4, "2026-09-24T12:00:00Z",
                    [job(40, "intake", "failure", "2026-09-24T12:30:00Z",
                         [("Identity, onboard", "failure")])], conclusion="failure")
        fake = FakeGh({"ls.yml": [newer] + old})
        fake.respond_original = fake.respond
        fake.respond = lambda cmd: None if (cmd[:2] == ["gh", "api"] and "/runs/4/jobs" in cmd[2]) \
            else fake.respond_original(cmd)
        self.build(fake)
        receipt = self.receipt("ls-algo")
        self.assertTrue(receipt["history_complete"], "a cut new run must not un-judge the lane")
        self.assertEqual(receipt["scanned_through"], 3, "run 4 is rescanned next build")
        self.build(FakeGh({"ls.yml": [newer] + old}))
        self.assertEqual(self.receipt("ls-algo")["latest"]["run_id"], 4)

    def test_an_in_flight_run_is_rescanned_when_a_newer_run_is_cut(self):
        # Verifier pending probe: run 100 in flight, 101 and 102 done, the jobs
        # call for 102 fails. The watermark used to jump to 101, past 100, so
        # run 100's eventual success was never seen.
        self.configure([{"name": "act", "workflow_file": "dp.yml", "job": "activist",
                         "freshness_hours": 54}])
        base = [run(90, "2026-09-24T05:00:00Z",
                    [job(900, "activist", "success", "2026-09-24T06:00:00Z")])]
        self.build(FakeGh({"dp.yml": base}))
        pending = run(100, "2026-09-24T09:00:00Z", [], status="in_progress", conclusion=None)
        later = [run(101, "2026-09-24T09:30:00Z", [job(1010, "news", "success",
                                                        "2026-09-24T09:50:00Z")]),
                 run(102, "2026-09-24T10:00:00Z", [job(1020, "news", "success",
                                                        "2026-09-24T10:20:00Z")])]
        fake = FakeGh({"dp.yml": [pending] + later + base})
        fake.respond_original = fake.respond
        fake.respond = lambda cmd: None if (cmd[:2] == ["gh", "api"] and "/runs/102/jobs" in cmd[2]) \
            else fake.respond_original(cmd)
        self.build(fake)
        self.assertLess(self.receipt("act")["scanned_through"], 100)
        done = run(100, "2026-09-24T09:00:00Z",
                   [job(1000, "activist", "success", "2026-09-24T10:30:00Z")])
        self.build(FakeGh({"dp.yml": [done] + later + base}))
        self.assertEqual(self.receipt("act")["last_success_at"], "2026-09-24T10:30:00Z")

    def test_a_partial_listing_is_no_listing(self):
        # Verifier partial-listing probe: page 2 of a paged listing failing
        # used to leave page 1 looking complete, so a weekly lane whose success
        # was on page 2 was judged "never succeeded".
        self.configure([{"name": "world-model", "workflow_file": "dp.yml",
                         "job": "world-model", "freshness_hours": 342}])
        runs = [run(1, "2026-09-18T16:00:00Z",
                    [job(11, "world-model", "success", "2026-09-18T16:40:00Z")])]
        runs += [run(n, f"2026-09-{19 + (n - 2) // 25:02d}T{(n - 2) % 24:02d}:10:00Z",
                     [job(10 * n, "news", "success", "2026-09-24T00:00:00Z")])
                 for n in range(2, 142)]
        fake = FakeGh({"dp.yml": runs})
        fake.respond_original = fake.respond
        fake.respond = lambda cmd: None if (cmd[:2] == ["gh", "api"] and "/runs?" in cmd[2]
                                            and "page=2" in cmd[2]) \
            else fake.respond_original(cmd)
        result = self.build(fake)
        self.assertIn("world-model", result["unavailable"])
        self.assertFalse((self.root / "_system/data/lane_receipts/world-model.json").exists(),
                         "no receipt is better than one judged on half a listing")

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
