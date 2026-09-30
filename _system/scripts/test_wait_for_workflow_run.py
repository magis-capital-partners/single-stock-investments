#!/usr/bin/env python3
"""Unit tests for wait_for_workflow_run (no live GitHub calls)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import wait_for_workflow_run as wait


class EvaluateRunsTests(unittest.TestCase):
    def test_absent_when_empty(self):
        self.assertEqual(wait.evaluate_runs([], allow_skipped=False), "absent")

    def test_pending_while_in_progress(self):
        runs = [{"status": "in_progress", "conclusion": None}]
        self.assertEqual(wait.evaluate_runs(runs, allow_skipped=False), "pending")

    def test_success(self):
        runs = [{"status": "completed", "conclusion": "success"}]
        self.assertEqual(wait.evaluate_runs(runs, allow_skipped=False), "success")

    def test_failure(self):
        runs = [{"status": "completed", "conclusion": "failure", "html_url": "u"}]
        self.assertEqual(wait.evaluate_runs(runs, allow_skipped=False), "failure")

    def test_skipped_only_ok_when_allowed(self):
        runs = [{"status": "completed", "conclusion": "skipped"}]
        self.assertEqual(wait.evaluate_runs(runs, allow_skipped=False), "failure")
        self.assertEqual(wait.evaluate_runs(runs, allow_skipped=True), "success")


class WaitLoopTests(unittest.TestCase):
    def test_waits_through_absent_then_succeeds(self):
        states = [
            [],
            [{"status": "queued", "conclusion": None}],
            [{"status": "completed", "conclusion": "success", "html_url": "u"}],
        ]

        def list_fn(*_a, **_k):
            return states.pop(0)

        sleeps: list[int] = []
        clock = {"t": 0.0}

        def now():
            return clock["t"]

        def sleep(seconds):
            sleeps.append(seconds)
            clock["t"] += seconds

        rc = wait.wait_for_workflow(
            repo="o/r",
            workflow="Research quality (PR)",
            sha="abc123456789",
            token="t",
            timeout_seconds=60,
            poll_seconds=5,
            allow_skipped=False,
            sleep_fn=sleep,
            now_fn=now,
            list_fn=list_fn,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(sleeps, [5, 5])

    def test_fails_on_workflow_failure(self):
        runs = [[{"status": "completed", "conclusion": "failure", "html_url": "u"}]]

        rc = wait.wait_for_workflow(
            repo="o/r",
            workflow="Research quality (PR)",
            sha="abc123456789",
            token="t",
            timeout_seconds=60,
            poll_seconds=5,
            allow_skipped=False,
            sleep_fn=lambda _s: None,
            now_fn=lambda: 0.0,
            list_fn=lambda *_a, **_k: runs[0],
        )
        self.assertEqual(rc, 1)

    def test_timeout_while_absent(self):
        clock = {"t": 0.0}

        def now():
            return clock["t"]

        def sleep(seconds):
            clock["t"] += seconds

        with patch("builtins.print"):
            rc = wait.wait_for_workflow(
                repo="o/r",
                workflow="Research quality (PR)",
                sha="abc123456789",
                token="t",
                timeout_seconds=10,
                poll_seconds=5,
                allow_skipped=False,
                sleep_fn=sleep,
                now_fn=now,
                list_fn=lambda *_a, **_k: [],
            )
        self.assertEqual(rc, 1)


class DispatchTitleTests(unittest.TestCase):
    def test_a_run_stored_on_main_is_found_when_its_title_names_the_sha(self):
        sha = "a" * 40
        titled = {
            "name": "Research quality",
            "display_title": f"research-quality-pr 1074 {sha}",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "b" * 40,
        }

        def fake(args, *, token):
            path = args[0]
            if "head_sha=" in path:
                return {"workflow_runs": []}
            return {"workflow_runs": [titled, {"name": "Python tests", "display_title": titled["display_title"]}]}

        with patch.object(wait, "_gh_json", fake):
            runs = wait.list_workflow_runs("o/r", "Research quality", sha, "t")
        self.assertEqual(runs, [titled])

    def test_a_title_for_a_different_commit_does_not_match(self):
        run = {"display_title": "research-quality-pr 1074 " + ("b" * 40)}
        self.assertFalse(wait.run_titles_sha(run, "a" * 40))
        self.assertFalse(wait.run_titles_sha({"display_title": "fixed " + ("a" * 40)}, "a" * 40))


if __name__ == "__main__":
    unittest.main()
