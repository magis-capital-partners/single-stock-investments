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


if __name__ == "__main__":
    unittest.main()
