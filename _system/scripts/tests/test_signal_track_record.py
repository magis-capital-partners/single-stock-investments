"""Signal track record: log-as-published, first write wins, graded on maturity."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_signal_track_record", SCRIPTS / "build_signal_track_record.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def history(n: int, start: date, growth: float) -> list[list]:
    out, close = [], 100.0
    for i in range(n):
        out.append([(start + timedelta(days=i)).isoformat(), round(close, 6)])
        close *= 1.0 + growth
    return out


def signals_payload(n: int, as_of_index: int, *, state="panic", stale_ticker=False) -> dict:
    start = date(2026, 1, 1)
    spy = history(n, start, 0.001)
    stock = history(n, start, 0.002)
    as_of = stock[as_of_index][0]
    snap = {
        "as_of": as_of, "benchmark": "SPY", "model_version": "technical-fear-v3", "history": stock,
        "capitulation": {"state": state, "scores": {"panic": 81.0, "pressure": 70.0, "exhaustion": 20.0}},
        "setup": {"phase": "company_selloff"}, "context": {"selloff_type": "company_specific"},
        "outlook": {"risk": {"p_drop15_63d": 0.3, "expected_vol_21d_pct": 40.0}, "rebound": {"score": 87.0}},
    }
    if stale_ticker:
        snap["fetch_status"] = "preserved_after_fetch_failure"
    return {
        "model_version": "technical-fear-v3",
        "market_context": {"internal": {"as_of": spy[as_of_index][0], "state": "normal", "scores": {"panic": 40.0}, "breadth_panic": 0.05}},
        "by_ticker": {
            "AAA": snap,
            "SPY": {"as_of": spy[as_of_index][0], "benchmark": "SPY", "history": spy,
                    "capitulation": {"state": "normal", "scores": {"panic": 40.0}}, "setup": {"phase": "trend_intact"}},
        },
    }


class TrackRecordTests(unittest.TestCase):
    def test_open_us_session_is_not_logged(self):
        payload = signals_payload(101, 100)  # as_of 2026-04-11
        self.write(payload)
        # 2026-04-11 15:00 UTC = 11:00 New York: the session is still open
        result = MODULE.run(**self.paths, now=datetime(2026, 4, 11, 15, tzinfo=timezone.utc))
        self.assertEqual(result["added"], 0)
        # after the close the same snapshot logs
        result = MODULE.run(**self.paths, now=datetime(2026, 4, 11, 21, tzinfo=timezone.utc))
        self.assertEqual(result["added"], 3)  # AAA, SPY and the market row


    def test_long_stale_snapshots_are_not_logged(self):
        self.write(signals_payload(101, 100))
        result = MODULE.run(**self.paths, now=datetime(2026, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(result["added"], 0)  # as_of 2026-04-11 is > 30 days before the run


    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = {"signals_path": root / "technical_signals.json", "capitulation_path": root / "capitulation_daily.json",
                      "ledger_dir": root / "ledger", "summary_path": root / "signal_track_record.json",
                      "expectations_path": SCRIPTS / "technical_signal_expectations.json"}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, payload, capitulation=None):
        self.paths["signals_path"].write_text(json.dumps(payload), encoding="utf-8")
        if capitulation is not None:
            self.paths["capitulation_path"].write_text(json.dumps(capitulation), encoding="utf-8")

    def test_logs_once_and_grades_when_mature(self):
        # day 1: signal published on history index 100 (history ends there)
        self.write(signals_payload(101, 100), {"model_version": "capitulation-daily-v1", "market": {
            "symbol": "SPY", "as_of": "2026-04-11", "state": "stress", "raw_state": "stress", "panic": 72.0,
            "exhaustion_meaningful": False, "drawdown_pct": -6.0}})
        first = MODULE.run(**self.paths, now=datetime(2026, 4, 12, tzinfo=timezone.utc))
        self.assertEqual(first["added"], 4)  # AAA, SPY stock row, market row, ladder row
        self.assertEqual(first["graded"], 0)
        # same session re-run with different published values: first write wins
        again = signals_payload(101, 100, state="normal")
        self.write(again)
        second = MODULE.run(**self.paths, now=datetime(2026, 4, 12, 1, tzinfo=timezone.utc))
        self.assertEqual(second["added"], 0)
        ledger = MODULE.load_ledger(self.paths["ledger_dir"])
        row = ledger[(signals_payload(101, 100)["by_ticker"]["AAA"]["as_of"], "stock", "AAA")]
        self.assertEqual(row["state"], "panic")
        # 70 sessions later: history now covers the 5/21/63 horizons of the logged row
        later = signals_payload(171, 170)
        self.write(later)
        third = MODULE.run(**self.paths, now=datetime(2026, 6, 20, tzinfo=timezone.utc))
        self.assertGreaterEqual(third["graded"], 2)
        ledger = MODULE.load_ledger(self.paths["ledger_dir"])
        row = ledger[(row["as_of"], "stock", "AAA")]
        # next-close entry: closes grow 0.2% a day -> 21-session return = 1.002**21 - 1
        self.assertAlmostEqual(float(row["r21"]), 1.002 ** 21 - 1, places=4)
        self.assertAlmostEqual(float(row["b21"]), 1.001 ** 21 - 1, places=4)
        self.assertAlmostEqual(float(row["mae63"]), 0.002, places=3)  # never below the signal close
        summary = json.loads(self.paths["summary_path"].read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], 1)
        self.assertIn("panic", summary["live"]["stock_state"])
        self.assertEqual(summary["live"]["stock_state"]["panic"]["h21"]["graded"], 1)
        self.assertGreater(summary["live"]["stock_state"]["panic"]["h21"]["mean_excess"], 0)
        self.assertIn("company_selloff", summary["live"]["stock_phase"])
        self.assertIn("full_1990_2026", summary["backtest"])

    def test_stale_snapshots_are_logged_but_never_graded(self):
        self.write(signals_payload(101, 100, stale_ticker=True))
        MODULE.run(**self.paths, now=datetime(2026, 4, 12, tzinfo=timezone.utc))
        self.write(signals_payload(171, 170, stale_ticker=True))
        MODULE.run(**self.paths, now=datetime(2026, 6, 20, tzinfo=timezone.utc))
        ledger = MODULE.load_ledger(self.paths["ledger_dir"])
        stale = [r for k, r in ledger.items() if k[2] == "AAA"]
        self.assertTrue(stale)
        self.assertTrue(all(r["fresh"] == "0" and not r["r21"] for r in stale))

    def test_ledger_files_are_sorted_monthly_csv(self):
        self.write(signals_payload(101, 100))
        MODULE.run(**self.paths, now=datetime(2026, 4, 12, tzinfo=timezone.utc))
        files = sorted(self.paths["ledger_dir"].glob("*.csv"))
        self.assertTrue(files)
        header = files[0].read_text(encoding="utf-8").splitlines()[0].split(",")
        self.assertEqual(header, MODULE.FIELDS)


if __name__ == "__main__":
    unittest.main()
