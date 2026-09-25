#!/usr/bin/env python3
"""Activist scan phases: budgets, rotation, weekly discovery, coverage check.

The one-command scan hit the 90-minute job limit on every run from 2026-08-03
(reported "cancelled"; last "activist scan sync" commit 2026-08-02). No test
here touches the network: the fetchers are replaced.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_activist_freshness  # noqa: E402
import scan_activist_sources as scan  # noqa: E402


class RotationTests(unittest.TestCase):
    def test_never_scanned_first_then_stalest(self) -> None:
        last = {"A": "2026-09-20T00:00:00Z", "B": "2026-09-10T00:00:00Z"}
        self.assertEqual(scan.rotation_order(["A", "B", "C", "D"], last), ["C", "D", "B", "A"])


class SecPhaseBudgetTests(unittest.TestCase):
    TICKERS = ["A", "B", "C", "D"]

    def _state(self) -> dict:
        return {"sec": {"last_scanned": {"A": "2026-09-20T00:00:00Z", "B": "2026-09-10T00:00:00Z"}}}

    def _run(self, state: dict, fake, *, minutes: float | None = 2.0, checkpoint=None):
        clock = {"t": 0.0}

        def timed(ticker, **kwargs):
            clock["t"] += 60.0  # one "minute" per ticker
            return fake(ticker, **kwargs)

        budget = scan.Budget(minutes, clock=lambda: clock["t"])
        with mock.patch.object(scan, "scan_ticker_sec", side_effect=timed), \
                redirect_stdout(io.StringIO()) as out:
            hits = scan.run_sec_phase(self.TICKERS, state, budget, checkpoint=checkpoint)
        return hits, out.getvalue()

    def test_budget_stops_the_phase_and_the_next_run_resumes(self) -> None:
        seen: list[str] = []

        def fake(ticker, **_kwargs):
            seen.append(ticker)
            return [{"form": "SC 13D"}]

        state = self._state()
        hits, out = self._run(state, fake)
        self.assertEqual(seen, ["C", "D"])  # never-scanned first
        self.assertEqual([hit["ticker"] for hit in hits], ["C", "D"])
        run = state["sec"]["last_run"]
        self.assertTrue(run["budget_hit"])
        self.assertEqual((run["scanned"], run["remaining"]), (2, 2))
        self.assertIn("[activist:sec] 2/4 done", out)
        self._run(state, fake)  # the next run picks up the names this one did not reach
        self.assertEqual(seen, ["C", "D", "B", "A"])

    def test_one_failing_ticker_does_not_stall_the_rotation(self) -> None:
        seen: list[str] = []

        def fake(ticker, **_kwargs):
            seen.append(ticker)
            if ticker == "C":
                raise ValueError("unparseable submissions")
            return []

        state = self._state()
        self._run(state, fake, minutes=None)
        self.assertEqual(seen, ["C", "D", "B", "A"])  # C failed, the phase went on
        sec = state["sec"]
        self.assertNotIn("C", sec["last_scanned"])
        self.assertEqual(sec["failures"]["C"]["count"], 1)
        self.assertEqual(sec["last_run"]["failed"], 1)

    def test_a_ticker_that_just_failed_waits_its_turn(self) -> None:
        # C failed on the last run (attempted, never scanned); D has not been
        # tried this cycle. Ordering by last success alone put C first on
        # every run, so a permanently failing ticker ate the budget forever.
        seen: list[str] = []
        state = {
            "sec": {
                "last_scanned": {"A": "2026-09-20T00:00:00Z", "B": "2026-09-10T00:00:00Z"},
                "last_attempted": {"C": "2026-09-24T06:00:00Z"},
            }
        }
        self._run(state, lambda ticker, **_k: seen.append(ticker) or [], minutes=1.0)
        self.assertEqual(seen, ["D"])

    def test_a_failed_fetch_is_not_recorded_as_scanned(self) -> None:
        import sec_activist_scan

        forbidden = urllib.error.HTTPError("https://data.sec.gov/x", 403, "Forbidden", None, None)
        state: dict = {}
        with mock.patch.object(sec_activist_scan, "ticker_meta", return_value={"cik": "1"}), \
                mock.patch.object(sec_activist_scan, "fetch_submissions", side_effect=forbidden), \
                mock.patch.object(sec_activist_scan, "append_scan_log") as scan_log, \
                redirect_stdout(io.StringIO()):
            scan.run_sec_phase(["AAA"], state, scan.Budget(None))
        self.assertEqual(state["sec"]["last_scanned"], {})
        self.assertIn("HTTPError", state["sec"]["failures"]["AAA"]["error"])
        scan_log.assert_called_once()  # still logged, as before

    def test_state_is_checkpointed_after_every_ticker(self) -> None:
        checkpoint = mock.Mock()
        self._run(self._state(), lambda ticker, **_k: [], minutes=None, checkpoint=checkpoint)
        self.assertGreaterEqual(checkpoint.call_count, len(self.TICKERS))


class MainPhaseStateTests(unittest.TestCase):
    def _main(self, state_path: Path, fake) -> int:
        with mock.patch.object(scan, "scan_ticker_sec", side_effect=fake), \
                mock.patch.object(scan, "save_global_scan") as global_scan, \
                mock.patch.object(scan.signal, "signal"), \
                redirect_stdout(io.StringIO()):
            try:
                return scan.main(
                    ["--phase", "sec", "--ticker", "AAA", "--ticker", "BBB", "--ticker", "CCC",
                     "--state", str(state_path)]
                )
            finally:
                global_scan.assert_not_called()  # a fetch phase does not finalize

    def test_main_runs_one_phase_and_saves_its_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            code = self._main(state_path, lambda ticker, **_k: [])
            state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(state["sec"]["last_scanned"]), ["AAA", "BBB", "CCC"])
        self.assertFalse(state["sec"]["last_run"]["budget_hit"])

    def test_progress_survives_a_sigterm(self) -> None:
        # `timeout` sends SIGTERM; the handler turns it into SystemExit(143).
        def fake(ticker, **_kwargs):
            if ticker == "CCC":
                raise SystemExit(143)
            return []

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with self.assertRaises(SystemExit):
                self._main(state_path, fake)
            state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(state["sec"]["last_scanned"]), ["AAA", "BBB"])


class DiscoveryIntervalTests(unittest.TestCase):
    def test_discovery_runs_weekly(self) -> None:
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = {"discovery": {"last_completed_at": recent}}
        with mock.patch.object(scan, "discover_filers") as discover, redirect_stdout(io.StringIO()):
            ran = scan.run_discovery_phase(
                state, scan.Budget(None), scan_date="2026-09-24", min_interval_days=6.5
            )
        self.assertFalse(ran)
        discover.assert_not_called()

    def test_discovery_runs_when_due(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = {"discovery": {"last_completed_at": stale}}
        found = {"row_count": 3, "resolved_firm_count": 1, "firm_count": 2, "off_book_count": 1}
        with mock.patch.object(scan, "discover_filers", return_value=found), \
                redirect_stdout(io.StringIO()):
            ran = scan.run_discovery_phase(
                state, scan.Budget(None), scan_date="2026-09-24", dry_run=True, min_interval_days=6.5
            )
        self.assertTrue(ran)
        self.assertNotEqual(state["discovery"]["last_completed_at"], stale)


class ScanCoverageCheckTests(unittest.TestCase):
    NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

    def _stamp(self, days: float) -> str:
        return (self.NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_holdings_the_rotation_has_not_reached_are_a_problem(self) -> None:
        state = {
            "created_at": self._stamp(10),
            "sec": {"last_scanned": {"T1": self._stamp(2), "T2": self._stamp(9)}},
        }
        problems = check_activist_freshness.scan_coverage_problems(
            state, ["T1", "T2", "T3"], now=self.NOW
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("2 of 3 holdings", problems[0])

    def test_first_rotation_is_not_judged(self) -> None:
        state = {"created_at": self._stamp(3), "sec": {"last_scanned": {}}}
        self.assertEqual(
            check_activist_freshness.scan_coverage_problems(state, ["T1"], now=self.NOW), []
        )

    def test_check_reads_the_state_file_when_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "feed.json"
            feed.write_text(
                json.dumps(
                    {
                        "generated_at": self._stamp(0.5),
                        "feed": [{"row": i} for i in range(150)],
                        "summary": {"activist_row_count": 150},
                    }
                ),
                encoding="utf-8",
            )
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps({"created_at": self._stamp(30), "sec": {"last_scanned": {}}}),
                encoding="utf-8",
            )
            ok, problems = check_activist_freshness.check(
                now=self.NOW, feed_path=feed, state_path=state_path, tickers=["T1"]
            )
        self.assertFalse(ok)
        self.assertIn("no SEC activist scan", problems[0])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
