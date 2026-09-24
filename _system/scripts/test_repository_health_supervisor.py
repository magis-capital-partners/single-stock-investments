from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import supervise_repository_health as supervisor

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 24, 20, 41, tzinfo=timezone.utc)
MORNING = datetime(2026, 9, 24, 8, 41, tzinfo=timezone.utc)   # before the 13:00 UTC digest
FALSIFIER_ERROR = ("ERROR: superseding revision must increase: ('CEG',"
                   " 'ceg-operating-owner-earnings-2026q3-v2', 1)")


class FakeGitHub:
    repository = "owner/repo"

    def __init__(self, annotations=None, logs=None):
        self.annotations = annotations or {}
        self.logs = logs or {}
        self.issues: dict[int, dict] = {}
        self.events: list[str] = []
        self.workflow_runs: list[tuple] = []
        self.comments: list[tuple] = []
        self.assignees: dict[int, list] = {}
        self.labels: list[str] = []
        self.fail: set[str] = set()      # method names that fail, to test retries
        self._next = 1100

    def job_annotations(self, job_id):
        return self.annotations.get(job_id, [])

    def job_log(self, job_id):
        return self.logs.get(job_id)

    def open_issues(self, label):
        return [{"number": n, "title": i["title"]} for n, i in self.issues.items()
                if i["state"] == "open" and label in i["labels"]]

    def ensure_label(self, name, color, description):
        self.labels.append(name)
        return True

    def create_issue(self, title, body, labels):
        if "create_issue" in self.fail:
            return None
        number = self._next
        self._next += 1
        self.issues[number] = {"title": title, "body": body, "labels": labels, "state": "open"}
        return number

    def assign(self, number, assignees):
        if "assign" in self.fail:
            return False
        self.assignees[number] = assignees
        return True

    def update_issue(self, number, **fields):
        if "update_issue" in self.fail:
            return False
        self.issues[number].update(fields)
        return True

    def comment(self, number, body):
        if "comment" in self.fail:
            return False
        self.comments.append((number, body))
        return True

    def dispatch_event(self, event_type):
        self.events.append(event_type)
        return True

    def dispatch_workflow(self, workflow, fields):
        self.workflow_runs.append((workflow, fields))
        return True


class FakeSlack:
    configured = True

    def __init__(self, ok=True):
        self.ok = ok
        self.messages: list[str] = []

    def send(self, text):
        self.messages.append(text)
        return self.ok


class FakeD1:
    def __init__(self, usage=None, error=None):
        self.usage = usage or {"rows_read": 0, "rows_written": 0}
        self.error = error

    def fetch(self, day):
        if self.error:
            raise supervisor.D1Unavailable(self.error)
        return self.usage


def lane(name, job="work", workflow="w.yml", hours=54):
    return {"name": name, "workflow_file": workflow, "job": job, "freshness_hours": hours}


class SupervisorFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.github = FakeGitHub()
        self.slack = FakeSlack()

    def tearDown(self):
        self._tmp.cleanup()

    def configure(self, lanes, feeds=None):
        path = self.root / "_system/graph/graph_sources.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"lanes": lanes, "data_feeds": feeds or {}}), encoding="utf-8")

    def receipt(self, name, last_success_at, latest=None, failures=(), job="work",
                workflow="w.yml", in_flight=False):
        path = self.root / f"_system/data/lane_receipts/{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": "2.0", "lane": name, "workflow_file": workflow, "job": job,
            "work_step": None, "last_success_at": last_success_at, "latest": latest,
            "failures": list(failures), "in_flight": in_flight,
            "workflow_state": "active"}), encoding="utf-8")

    def run_plan(self, now, **kwargs):
        with mock.patch.object(supervisor, "_head", return_value="abc"):
            return supervisor.plan(self.root, now=now, github=kwargs.get("github", self.github),
                                   slack=kwargs.get("slack", self.slack),
                                   d1=kwargs.get("d1"), act=kwargs.get("act", True))

    def state(self):
        return json.loads((self.root / supervisor.STATE_REL).read_text(encoding="utf-8"))


def failure(run_id, at, job_id, step="Validate the post-resolution tree", outcome="failure"):
    return {"run_id": run_id, "at": at, "outcome": outcome, "job_id": job_id,
            "failed_step": step, "url": f"https://github.com/owner/repo/actions/runs/{run_id}"}


class HealerTests(SupervisorFixture):
    def falsifier_failing(self):
        self.configure([lane("falsifier", job="resolve-and-validate",
                             workflow="falsifier-resolution.yml")])
        failures = [failure(3, "2026-09-24T20:14:40Z", 33), failure(2, "2026-09-24T13:58:00Z", 22)]
        self.receipt("falsifier", "2026-09-06T23:45:28Z", latest=failures[0], failures=failures,
                     job="resolve-and-validate", workflow="falsifier-resolution.yml")
        for job_id in (22, 33):
            self.github.annotations[job_id] = [
                {"annotation_level": "failure", "message": "Process completed with exit code 1."}]
            self.github.logs[job_id] = "\n".join([
                "2026-09-24T20:14:40.4744735Z ##[group]Run set -euo pipefail",
                "2026-09-24T20:14:40.4749134Z   PYTHON: 3.12",
                "2026-09-24T20:14:40.4749134Z ##[endgroup]",
                "2026-09-24T20:14:40.5607896Z falsifier lint: 0 violation(s)",
                f"2026-09-24T20:14:40.8133150Z {FALSIFIER_ERROR}",
                "2026-09-24T20:14:40.8137115Z falsifier history: 1 violation(s)",
                "2026-09-24T20:14:40.8220599Z ##[error]Process completed with exit code 1."])

    def test_the_same_failure_twice_stops_dispatch_and_opens_one_issue(self):
        # v1 re-dispatched this lane 84 times against one deterministic error.
        self.falsifier_failing()
        result = self.run_plan(T0)
        self.assertEqual(self.github.events, [], "a persistent failure must not be retried")
        self.assertEqual(len(self.github.issues), 1)
        number, issue = next(iter(self.github.issues.items()))
        self.assertIn("lane-failure", issue["labels"])
        self.assertIn("superseding revision must increase", issue["title"])
        self.assertIn(FALSIFIER_ERROR, issue["body"])
        self.assertIn("runs/3", issue["body"])
        self.assertEqual(self.github.assignees[number], ["GoldmanDrew"])
        self.assertIn("falsifier", result["persistent_lanes"])
        self.assertTrue(any("[NEW FAILURE ISSUE]" in m for m in self.slack.messages))
        self.assertEqual(self.github.comments, [], "a new issue gets no 'now stale' comment")
        # Next supervisor run: same state, so no second issue, no repeat alert,
        # and still no dispatch.
        self.slack.messages.clear()
        self.run_plan(T0 + timedelta(hours=2))
        self.assertEqual(len(self.github.issues), 1)
        self.assertEqual(self.github.events, [])
        self.assertFalse(any("[NEW FAILURE ISSUE]" in m for m in self.slack.messages))

    def test_a_new_failure_is_retried_with_backoff_and_a_daily_cap(self):
        self.configure([lane("memory-digest", job="triage", workflow="memory-digest.yml")])
        # Stale with no fingerprintable failure: the healer's case.
        self.receipt("memory-digest", "2026-09-21T15:00:00Z", job="triage",
                     workflow="memory-digest.yml")
        start = datetime(2026, 9, 25, 0, 41, tzinfo=timezone.utc)
        for offset in (0, 1, 2, 3, 6, 8, 12, 16, 20):
            self.run_plan(start + timedelta(hours=offset))
        self.assertEqual(self.github.events, ["memory-triage-run"] * 3)
        state = self.state()
        self.assertEqual(state["dispatch_log"]["memory-digest"]["count"], 3)
        self.assertIn("daily cap", state["lanes"]["memory-digest"]["held"])
        # A new UTC day restores the budget.
        self.run_plan(datetime(2026, 9, 26, 0, 41, tzinfo=timezone.utc))
        self.assertEqual(len(self.github.events), 4)

    def recover_falsifier(self, at="2026-09-26T10:00:00Z"):
        fixed = failure(9, at, 99)
        fixed["outcome"] = "success"
        self.receipt("falsifier", at, latest=fixed, failures=[],
                     job="resolve-and-validate", workflow="falsifier-resolution.yml")

    def test_a_failed_close_records_nothing_and_is_retried(self):
        self.falsifier_failing()
        self.run_plan(T0)
        number = next(iter(self.github.issues))
        self.recover_falsifier()
        self.github.fail = {"update_issue"}
        self.slack.messages.clear()
        self.run_plan(datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(self.github.issues[number]["state"], "open")
        issue = next(iter(self.state()["issues"].values()))
        self.assertEqual(issue["state"], "open", "a failed close must not be recorded as closed")
        self.assertFalse(any("[RECOVERED] issue" in m for m in self.slack.messages))
        self.github.fail = set()
        self.run_plan(datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc))
        self.assertEqual(self.github.issues[number]["state"], "closed")
        self.assertTrue(any("[RECOVERED] issue" in m for m in self.slack.messages))
        recovered = [body for n, body in self.github.comments if "Recovered" in body]
        self.assertEqual(len(recovered), 1, "the closing comment is not repeated on the retry")

    def test_a_failed_reopen_records_nothing_and_is_retried(self):
        self.falsifier_failing()
        self.run_plan(T0)
        number = next(iter(self.github.issues))
        self.recover_falsifier()
        self.run_plan(datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(self.github.issues[number]["state"], "closed")
        again = [failure(12, "2026-09-28T13:58:00Z", 122), failure(11, "2026-09-27T13:58:00Z", 112)]
        for job_id in (112, 122):
            self.github.annotations[job_id] = self.github.annotations[33]
            self.github.logs[job_id] = self.github.logs[33]
        self.receipt("falsifier", "2026-09-26T10:00:00Z", latest=again[0], failures=again,
                     job="resolve-and-validate", workflow="falsifier-resolution.yml")
        self.github.fail = {"update_issue"}
        self.slack.messages.clear()
        self.run_plan(datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc))
        self.assertEqual(self.github.issues[number]["state"], "closed")
        self.assertEqual(next(iter(self.state()["issues"].values()))["state"], "closed")
        self.assertFalse(any("[FAILING AGAIN]" in m for m in self.slack.messages))
        self.github.fail = set()
        self.run_plan(datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(self.github.issues[number]["state"], "open")
        self.assertEqual(len(self.github.issues), 1, "the same issue is reopened, not a new one")
        self.assertTrue(any(f"[FAILING AGAIN] #{number}" in m for m in self.slack.messages))

    def test_an_issue_alert_lost_to_a_failed_send_is_sent_once_later(self):
        self.falsifier_failing()
        self.run_plan(T0, slack=FakeSlack(ok=False))
        self.assertEqual(len(self.github.issues), 1)
        self.run_plan(T0 + timedelta(hours=2))
        self.run_plan(T0 + timedelta(hours=4))
        announced = [m for m in self.slack.messages if "[NEW FAILURE ISSUE]" in m]
        self.assertEqual(len(announced), 1)
        self.assertEqual(len(self.github.issues), 1)

    def test_one_issue_for_the_same_error_on_several_lanes(self):
        # drive, intake-full and world-model failing on one check_warrant_universe
        # error are one defect, so one issue that lists all three.
        names = ("data-pipeline-drive", "data-pipeline-intake-full", "data-pipeline-world-model")
        self.configure([lane(n, job=n.split("data-pipeline-")[1], workflow="data-pipeline.yml")
                        for n in names])
        error = ("check_warrant_universe.py: health.status unhealthy: 3 active warrants without"
                 " a mark for 6 days")
        for index, name in enumerate(names):
            base = 300 + 10 * index
            fails = [failure(base + 2, "2026-09-24T18:00:00Z", base + 2, step="Validate"),
                     failure(base + 1, "2026-09-23T18:00:00Z", base + 1, step="Validate")]
            self.receipt(name, "2026-09-10T00:00:00Z", latest=fails[0], failures=fails,
                         job=name.split("data-pipeline-")[1], workflow="data-pipeline.yml")
            for job_id in (base + 1, base + 2):
                self.github.annotations[job_id] = [{"annotation_level": "failure",
                                                    "message": error}]
        self.run_plan(T0)
        self.assertEqual(len(self.github.issues), 1)
        issue = next(iter(self.github.issues.values()))
        for name in names:
            self.assertIn(f"`{name}`", issue["body"])
        self.assertIn("+2", issue["title"])

    def test_an_unreadable_failure_is_retried_never_filed(self):
        # Two failures whose logs cannot be read must not collapse into one
        # "no error line" fingerprint and open an issue about an API outage.
        self.falsifier_failing()
        self.github.logs.clear()
        self.run_plan(T0)
        self.assertEqual(self.github.issues, {})
        self.assertEqual(self.github.events, ["falsifier-resolution-run"])

    def test_no_dispatch_while_a_run_is_in_flight(self):
        self.configure([lane("memory-digest", job="triage", workflow="memory-digest.yml")])
        self.receipt("memory-digest", "2026-09-21T15:00:00Z", job="triage",
                     workflow="memory-digest.yml", in_flight=True)
        self.run_plan(T0)
        self.assertEqual(self.github.events, [])

    def test_recovery_closes_the_issue_and_says_so(self):
        self.falsifier_failing()
        self.run_plan(T0)
        number = next(iter(self.github.issues))
        fixed = failure(9, "2026-09-26T10:00:00Z", 99)
        fixed["outcome"] = "success"
        self.receipt("falsifier", "2026-09-26T10:00:00Z", latest=fixed, failures=[],
                     job="resolve-and-validate", workflow="falsifier-resolution.yml")
        self.slack.messages.clear()
        self.run_plan(datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(self.github.issues[number]["state"], "closed")
        self.assertTrue(any(n == number and "Recovered" in body for n, body in self.github.comments))
        self.assertTrue(any("[RECOVERED]" in m for m in self.slack.messages))

    def test_timeouts_fingerprint_on_the_step_that_was_running(self):
        self.configure([lane("data-pipeline-activist", job="activist", workflow="data-pipeline.yml")])
        timeouts = [failure(n, f"2026-09-2{n}T12:34:19Z", 100 + n, step="Run activist scan",
                            outcome="timeout") for n in (4, 3)]
        self.receipt("data-pipeline-activist", None, latest=timeouts[0], failures=timeouts,
                     job="activist", workflow="data-pipeline.yml")
        for job_id in (103, 104):
            self.github.annotations[job_id] = [
                {"annotation_level": "failure",
                 "message": "The job has exceeded the maximum execution time of 1h30m0s"}]
        self.run_plan(T0)
        issue = next(iter(self.github.issues.values()))
        self.assertIn("timeout while running step 'Run activist scan'", issue["title"])

    def test_p6_feed_healer_obeys_its_lanes_persistent_stop(self):
        # heal-warrants ran 51 times against one "strict health remains degraded".
        feeds = {"warrant_monitor": {"path": "dashboard/data/warrants.json",
                                     "stamp_field": "generated_at", "max_age_hours": 100,
                                     "healer": "refresh warrants"}}
        self.configure([lane("data-pipeline-warrant-discover", job="warrant-discover",
                             workflow="data-pipeline.yml", hours=342)], feeds)
        feed = self.root / "dashboard/data/warrants.json"
        feed.parent.mkdir(parents=True, exist_ok=True)
        feed.write_text(json.dumps({"generated_at": "2026-09-10T00:00:00Z"}), encoding="utf-8")
        fails = [failure(n, f"2026-09-2{n}T23:11:00Z", 200 + n, step="Keep unresolved source"
                         " failures loud after preserving progress") for n in (2, 1)]
        self.receipt("data-pipeline-warrant-discover", "2026-09-14T15:00:00Z", latest=fails[0],
                     failures=fails, job="warrant-discover", workflow="data-pipeline.yml")
        for job_id in (201, 202):
            self.github.annotations[job_id] = [
                {"annotation_level": "failure",
                 "message": "Warrant snapshot was preserved, but strict health remains degraded."}]
        self.run_plan(T0)
        self.assertNotIn("heal-warrants", self.github.events)
        self.assertEqual(len(self.github.issues), 1)

    def test_plan_only_mode_writes_nothing_and_sends_nothing(self):
        self.configure([lane("memory-digest", job="triage", workflow="memory-digest.yml")])
        self.receipt("memory-digest", "2026-09-20T15:00:00Z", job="triage",
                     workflow="memory-digest.yml")
        with mock.patch.object(supervisor, "_head", return_value="abc"):
            result = supervisor.plan(self.root, now=T0)
        self.assertFalse((self.root / supervisor.STATE_REL).exists())
        self.assertEqual([d["event_type"] for d in result["dispatches"]], ["memory-triage-run"])
        self.assertFalse(result["dispatches"][0]["sent"])

    def test_issue_847_is_never_written(self):
        self.falsifier_failing()
        for hours in (0, 2, 4, 6):
            result = self.run_plan(T0 + timedelta(hours=hours))
        self.assertNotIn("escalate", result)
        self.assertFalse(any(n == 847 for n, _ in self.github.comments))
        self.assertFalse(any("self-healer escalation" in i["title"]
                             for i in self.github.issues.values()))
        workflow = (ROOT / ".github/workflows/repository-health-supervisor.yml").read_text(
            encoding="utf-8")
        self.assertNotIn("Repository self-healer escalation", workflow)


class AlertTests(SupervisorFixture):
    def test_stale_and_recovered_are_each_announced_once(self):
        self.configure([lane("ls-algo", job="intake", workflow="ls-algo-universe.yml")])
        self.receipt("ls-algo", "2026-08-11T04:14:38Z", job="intake", workflow="ls-algo-universe.yml")
        self.run_plan(T0)
        self.assertTrue(any("[STALE] `ls-algo`" in m for m in self.slack.messages))
        self.slack.messages.clear()
        self.run_plan(T0 + timedelta(hours=2))
        self.assertEqual(self.slack.messages, [])
        self.receipt("ls-algo", "2026-09-24T22:00:00Z", job="intake", workflow="ls-algo-universe.yml")
        self.run_plan(T0 + timedelta(hours=4))
        self.assertTrue(any("[RECOVERED] `ls-algo`" in m for m in self.slack.messages))
        self.slack.messages.clear()
        self.run_plan(T0 + timedelta(hours=6))
        self.assertEqual(self.slack.messages, [])

    def test_an_unfinished_scan_is_not_judged_stale_until_a_window_passes(self):
        # A receipt whose history walk was cut by the API budget knows
        # nothing yet; calling the lane stale would be a false alarm on the
        # first run after the job-level receipts land.
        self.configure([lane("world-model", job="world-model", workflow="data-pipeline.yml",
                             hours=342)])
        path = self.root / "_system/data/lane_receipts/world-model.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": "2.0", "lane": "world-model", "workflow_file": "data-pipeline.yml",
            "job": "world-model", "work_step": None, "last_success_at": None,
            "history_complete": False, "failures": [], "latest": None}), encoding="utf-8")
        result = self.run_plan(MORNING)
        self.assertEqual(result["stale_lanes"], [])
        self.assertFalse(any("[STALE]" in m for m in self.slack.messages))
        result = self.run_plan(MORNING + timedelta(hours=343))
        self.assertEqual(result["stale_lanes"], ["world-model"])
        self.assertTrue(any("no complete job-level receipt for 343h" in m
                            for m in self.slack.messages))

    def test_a_failed_send_is_retried_on_the_next_run(self):
        self.configure([lane("ls-algo", job="intake", workflow="ls-algo-universe.yml")])
        self.receipt("ls-algo", None, job="intake", workflow="ls-algo-universe.yml")
        down = FakeSlack(ok=False)
        self.run_plan(MORNING, slack=down)
        self.assertEqual(len(down.messages), 1)
        self.assertIn("[STALE] `ls-algo`", down.messages[0])
        self.run_plan(MORNING + timedelta(hours=2))
        self.assertTrue(any("[STALE] `ls-algo`" in m for m in self.slack.messages))

    def test_d1_thresholds_alert_once_per_day(self):
        self.configure([])
        self.run_plan(T0, d1=FakeD1({"rows_read": 3_100_000, "rows_written": 10}))
        self.assertTrue(any("[D1 60%]" in m and "rows read" in m for m in self.slack.messages))
        self.slack.messages.clear()
        self.run_plan(T0 + timedelta(minutes=30), d1=FakeD1({"rows_read": 3_300_000,
                                                             "rows_written": 10}))
        self.assertEqual(self.slack.messages, [])
        self.run_plan(T0 + timedelta(hours=1), d1=FakeD1({"rows_read": 4_100_000,
                                                          "rows_written": 10}))
        self.assertTrue(any("[D1 80%]" in m for m in self.slack.messages))
        self.slack.messages.clear()
        # A first reading already past 80% says 80% once, not 60% and 80%.
        self.run_plan(T0 + timedelta(days=1), d1=FakeD1({"rows_read": 10, "rows_written": 85_000}))
        joined = "\n".join(self.slack.messages)
        self.assertIn("[D1 80%] D1 rows written", joined)
        self.assertNotIn("[D1 60%]", joined)

    def test_d1_unauthorized_degrades_quietly(self):
        self.configure([])
        result = self.run_plan(MORNING,
                               d1=FakeD1(error="HTTP 403 (token may lack Account Analytics read)"))
        self.assertTrue(result["d1"]["status"].startswith("unavailable"))
        self.assertEqual(self.slack.messages, [])
        self.assertTrue(self.state()["d1"]["status"].startswith("unavailable"))

    def test_a_supervisor_gap_is_announced_once(self):
        self.configure([])
        self.run_plan(T0)
        self.slack.messages.clear()
        self.run_plan(T0 + timedelta(hours=10))
        self.assertTrue(any("[GAP]" in m and "10.0h" in m for m in self.slack.messages))
        self.slack.messages.clear()
        self.run_plan(T0 + timedelta(hours=12))
        self.assertFalse(any("[GAP]" in m for m in self.slack.messages))

    def test_one_digest_per_day_after_1300_utc(self):
        self.configure([lane("ls-algo", job="intake", workflow="ls-algo-universe.yml")])
        self.receipt("ls-algo", None, job="intake", workflow="ls-algo-universe.yml")
        day = datetime(2026, 9, 25, tzinfo=timezone.utc)
        self.run_plan(day.replace(hour=11))
        self.assertFalse(any("digest" in m for m in self.slack.messages))
        self.run_plan(day.replace(hour=13, minute=41))
        self.run_plan(day.replace(hour=15, minute=41))
        digests = [m for m in self.slack.messages if "Repository health digest" in m]
        self.assertEqual(len(digests), 1)
        self.assertIn("`ls-algo`", digests[0])
        self.run_plan(day.replace(day=26, hour=13, minute=41))
        digests = [m for m in self.slack.messages if "Repository health digest" in m]
        self.assertEqual(len(digests), 2)


class HeldWorkTests(SupervisorFixture):
    def queue(self, items):
        path = self.root / supervisor.WORK_QUEUE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"items": items}), encoding="utf-8")

    def test_a_held_back_draft_is_announced_once_and_listed_in_the_digest(self):
        # The promoter now parks a draft it cannot promote in
        # needs_semantic_review instead of failing the lane, so the lane stays
        # green and nothing else would ever mention the draft.
        self.configure([])
        self.queue([
            {"work_id": "w1", "ticker": "CRM", "task_type": "author_falsifier",
             "state": "needs_semantic_review",
             "promotion_blockers": ["metric_definition_id missing from the registry"]},
            {"work_id": "w2", "ticker": "SPGI", "task_type": "resolve_falsifier",
             "state": "needs_semantic_review", "reason": "ttm_period_inputs_missing"},
            {"work_id": "w3", "ticker": "ASML", "state": "queued"}])
        result = self.run_plan(MORNING)
        joined = "\n".join(self.slack.messages)
        self.assertIn("[HELD DRAFT] CRM", joined)
        self.assertIn("metric_definition_id missing", joined)
        self.assertNotIn("SPGI", joined, "only promoter drafts page; the rest go to the digest")
        self.assertEqual(result["held_for_review"], {"items": 2, "drafts": 1})
        self.slack.messages.clear()
        self.run_plan(MORNING.replace(hour=14))
        joined = "\n".join(self.slack.messages)
        self.assertNotIn("[HELD DRAFT]", joined)
        self.assertIn("Held for semantic review: 2 work item(s), 1 draft(s)", joined)
        self.assertIn("SPGI", joined)


class ExtractionTests(unittest.TestCase):
    def test_specific_annotation_beats_the_generic_exit_code(self):
        kind, line = supervisor.extract_error([
            {"annotation_level": "failure", "message": "Process completed with exit code 1."},
            {"annotation_level": "warning", "message": "Node.js 20 is deprecated."},
            {"annotation_level": "failure",
             "message": "Warrant snapshot was preserved, but strict health remains degraded."}],
            None)
        self.assertEqual((kind, line), ("error", "Warrant snapshot was preserved, but strict"
                                                  " health remains degraded."))

    def test_log_fallbacks(self):
        traceback = "\n".join([
            "2026-09-22T23:53:10.1Z Traceback (most recent call last):",
            '2026-09-22T23:53:10.1Z   File "build_capitulation_daily.py", line 121, in <module>',
            "2026-09-22T23:53:10.1Z ModuleNotFoundError: No module named 'numpy'",
            "2026-09-22T23:53:10.2Z ##[error]Process completed with exit code 1."])
        self.assertEqual(supervisor.extract_error([], traceback)[1],
                         "ModuleNotFoundError: No module named 'numpy'")
        clobber = "\n".join([
            "2026-09-24T18:00:01Z [4/6] pricing: 12 priced (1 configs seeded)",
            "2026-09-24T18:00:01Z       ! AXTI: KeyError: 'scenarios'",
            "2026-09-24T18:00:02Z Refusing to write dashboard_data.json: sparse/empty ticker"
            " checkout would clobber infra stats over 843 tickers -- readme 840->0",
            "2026-09-24T18:00:02Z ##[error]Process completed with exit code 1."])
        self.assertTrue(supervisor.extract_error([], clobber)[1].startswith(
            "Refusing to write dashboard_data.json"))

    def test_normalization_makes_recurrences_match(self):
        a = supervisor.normalize_error("2026-09-20T23:01:57.7Z activist feed is 28 days old"
                                       " (generated 2026-08-26T19:49:54Z, limit 3d)")
        b = supervisor.normalize_error("2026-09-24T12:34:17.1Z activist feed is 29 days old"
                                       " (generated 2026-08-26T19:49:54Z, limit 3d)")
        self.assertEqual(a, b)
        c = supervisor.normalize_error("tmp /home/runner/work/_temp/757bd676-f5f4-47e8-9d0f-"
                                       "7dc80be7bcc3/x failed at 36052344370")
        self.assertNotIn("757bd676", c)
        self.assertNotIn("36052344370", c)


class ClientTests(unittest.TestCase):
    def test_webhook_first_then_bot_token(self):
        calls = []

        def fake_post(url, payload, headers=None, timeout=20):
            calls.append((url, payload, headers))
            if "hooks.slack.com" in url:
                raise supervisor.urllib.error.URLError("webhook down")
            return 200, json.dumps({"ok": True})

        with mock.patch.object(supervisor, "_post_json", fake_post):
            client = supervisor.SlackClient("https://hooks.slack.com/services/x", "xoxb-1", "C1")
            self.assertTrue(client.send("hello"))
        self.assertEqual(calls[0][0], "https://hooks.slack.com/services/x")
        self.assertEqual(calls[1][0], "https://slack.com/api/chat.postMessage")
        self.assertEqual(calls[1][1]["channel"], "C1")
        self.assertEqual(calls[1][2]["Authorization"], "Bearer xoxb-1")

    def test_d1_graphql_sums_databases_and_reports_errors(self):
        payload = {"data": {"viewer": {"accounts": [{"d1AnalyticsAdaptiveGroups": [
            {"sum": {"rowsRead": 100, "rowsWritten": 5}},
            {"sum": {"rowsRead": 50, "rowsWritten": 1}}]}]}}}
        self.assertEqual(supervisor.parse_d1_usage(payload),
                         {"rows_read": 150, "rows_written": 6})
        with self.assertRaises(supervisor.D1Unavailable):
            supervisor.parse_d1_usage({"errors": [{"message": "not authorized for that account"}],
                                       "data": None})


class CompatibilityTests(unittest.TestCase):
    def test_receipt_and_feed_health_are_evaluated_without_graph_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "lanes": [{"name": "daily", "freshness_hours": 48}],
                "data_feeds": {
                    "sample": {"path": "dashboard/data/sample.json",
                               "stamp_field": "generated_at", "max_age_hours": 24,
                               "healer": "refresh sample"},
                },
            }
            graph = root / "_system/graph/graph_sources.json"
            graph.parent.mkdir(parents=True)
            graph.write_text(json.dumps(config), encoding="utf-8")
            receipt = root / "_system/data/lane_receipts/daily.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({"last_success_at": "2026-08-17T10:00:00Z"}),
                               encoding="utf-8")
            feed = root / "dashboard/data/sample.json"
            feed.parent.mkdir(parents=True)
            feed.write_text(json.dumps({"generated_at": "2026-08-17T09:00:00Z"}),
                            encoding="utf-8")
            failures = supervisor.operational_failures(
                root, datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
            self.assertEqual(failures, [])
            receipt.unlink()
            feed.write_text(json.dumps({"generated_at": "2026-08-15T09:00:00Z"}),
                            encoding="utf-8")
            failures = supervisor.operational_failures(
                root, datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
            self.assertTrue(any(row.startswith("P3|") for row in failures))
            self.assertTrue(any(row.startswith("P6|") for row in failures))

    def test_stale_operational_lanes_plan_their_registered_healers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = root / "_system/graph/graph_sources.json"
            graph.parent.mkdir(parents=True)
            graph.write_text(json.dumps({
                "lanes": [
                    {"name": "memory-digest", "freshness_hours": 24},
                    {"name": "market-risk", "freshness_hours": 24},
                    {"name": "research-watchdog", "freshness_hours": 24},
                ],
                "data_feeds": {},
            }), encoding="utf-8")
            with mock.patch.object(supervisor, "_head", return_value="abc"):
                result = supervisor.plan(root)
            self.assertEqual([d.get("event_type") for d in result["dispatches"]],
                             ["memory-triage-run", "heal-market-risk", "research-watchdog-run"])

    def test_lane_workflows_install_and_order_their_recovery_dependencies(self):
        memory = (ROOT / ".github/workflows/memory-digest.yml").read_text(encoding="utf-8")
        self.assertLess(memory.index("pip install"), memory.index("python -m pytest"))
        self.assertIn("types: [memory-triage-run]", memory)

        falsifier = (ROOT / ".github/workflows/falsifier-resolution.yml").read_text(encoding="utf-8")
        self.assertIn("types: [falsifier-resolution-run]", falsifier)

        market = (ROOT / ".github/workflows/market-risk-components.yml").read_text(encoding="utf-8")
        self.assertLess(
            market.index("Commit daily dashboard fallback snapshot"),
            market.index("Publish signed component snapshot"),
        )
        publish_block = market.split("name: Publish signed component snapshot", 1)[1]
        self.assertIn("continue-on-error: true", publish_block)

    # Healers whose trigger another workstream is adding to the lane's workflow.
    # Until it lands, healer_wired() holds their dispatch (tested below).
    AWAITING_WIRING = {"two-phase-watch"}

    def test_every_healer_event_is_one_its_workflow_listens_for(self):
        # A repository_dispatch type nobody listens to burns the lane's budget.
        import lane_registry as lr
        config = lr.load_config(ROOT)
        by_lane = {l["name"]: l for l in lr.declared_lanes(config)}
        for name, healer in supervisor.P3_LANE_HEALERS.items():
            self.assertIn(name, by_lane, name)
            wired, why = supervisor.healer_wired(ROOT, by_lane[name], healer)
            if name in self.AWAITING_WIRING and not wired:
                continue
            self.assertTrue(wired, f"{name}: {why}")
        for feed, lane_name in supervisor.P6_FEED_LANES.items():
            self.assertIn(lane_name, by_lane, feed)

    def test_an_unwired_healer_is_held_not_dispatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_system/graph").mkdir(parents=True)
            (root / "_system/graph/graph_sources.json").write_text(json.dumps({
                "lanes": [lane("two-phase-watch", job="watch", workflow="two-phase-watch.yml",
                               hours=342)], "data_feeds": {}}), encoding="utf-8")
            stale = root / "_system/data/lane_receipts/two-phase-watch.json"
            stale.parent.mkdir(parents=True)
            stale.write_text(json.dumps({
                "schema_version": "2.0", "workflow_file": "two-phase-watch.yml", "job": "watch",
                "work_step": None, "last_success_at": None, "history_complete": True}),
                encoding="utf-8")
            flow = root / ".github/workflows/two-phase-watch.yml"
            flow.parent.mkdir(parents=True)
            flow.write_text("on:\n  schedule:\n    - cron: \"0 17 * * 0\"\njobs:\n  watch:\n",
                            encoding="utf-8")
            github = FakeGitHub()
            with mock.patch.object(supervisor, "_head", return_value="abc"):
                result = supervisor.plan(root, now=T0, github=github, slack=FakeSlack(), act=True)
            self.assertEqual(github.events, [])
            self.assertIn("does not listen for repository_dispatch two-phase-watch-run",
                          result["held"]["two-phase-watch"])
            flow.write_text("on:\n  schedule:\n    - cron: \"0 17 * * 0\"\n  repository_dispatch:\n"
                            "    types: [two-phase-watch-run]\njobs:\n  watch:\n", encoding="utf-8")
            with mock.patch.object(supervisor, "_head", return_value="abc"):
                supervisor.plan(root, now=T0 + timedelta(hours=3), github=github,
                                slack=FakeSlack(), act=True)
            self.assertEqual(github.events, ["two-phase-watch-run"])


if __name__ == "__main__":
    unittest.main()
