#!/usr/bin/env python3
"""Unit tests for warrant gate ordering and immutable registry checks."""
from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from warrant_common import gate_state, load_jsonl, quote_age_days, validate_registry
from resolve_warrant_outcomes import corporate_action_terminal


def record() -> dict:
    return {
        "warrant_id": "0000000001:test:public",
        "version": 1,
        "issuer": "Test Issuer",
        "cik": "0000000001",
        "common_ticker": "TEST",
        "warrant_ticker": "TESTW",
        "lane": "chapter_11",
        "lifecycle": "active",
        "terms_complete": True,
        "terms": {
            "strike": 10.0,
            "currency": "USD",
            "share_ratio": 1.0,
            "issue_date": "2026-01-01",
            "expiry": "2030-01-01",
        },
        "survival": {"status": "pass", "missing_inputs": []},
        "source": {"url": "https://www.sec.gov/Archives/test"},
    }


class WarrantPipelineTests(unittest.TestCase):
    def test_all_gates_required_for_review_ready(self) -> None:
        gates = gate_state(
            record(),
            {"close": 3.0, "bid": 2.9, "ask": 3.1},
            {"close": 12.0},
        )
        self.assertEqual(gates["status"], "review_ready")
        self.assertTrue(all(gates[name]["pass"] for name in ("identity", "survival", "market")))

    def test_missing_two_sided_quote_blocks_execution(self) -> None:
        gates = gate_state(record(), {"close": 3.0}, {"close": 12.0})
        self.assertEqual(gates["status"], "market_blocked")
        self.assertIn("warrant bid", gates["market"]["missing"])
        self.assertIn("warrant ask", gates["market"]["missing"])

    def test_terms_precede_survival_and_market(self) -> None:
        candidate = record()
        candidate["terms_complete"] = False
        candidate["terms"]["strike"] = None
        candidate["survival"] = {"status": "review_required", "missing_inputs": ["debt"]}
        gates = gate_state(candidate, {}, {})
        self.assertEqual(gates["status"], "terms_blocked")

    def test_survival_precedes_market(self) -> None:
        candidate = record()
        candidate["survival"] = {"status": "review_required", "missing_inputs": ["liquidity"]}
        gates = gate_state(candidate, {}, {})
        self.assertEqual(gates["status"], "survival_blocked")

    def test_registry_rejects_duplicate_versions(self) -> None:
        first = record()
        second = copy.deepcopy(first)
        errors = validate_registry([first, second])
        self.assertTrue(any("duplicate warrant_id/version" in error for error in errors))

    def test_past_expiry_is_checked_on_the_latest_version_only(self) -> None:
        older = record()
        older["terms"]["expiry"] = "2020-01-01"
        expired = copy.deepcopy(older)
        expired["version"] = 2
        expired["lifecycle"] = "expired"
        self.assertFalse(any("past contractual expiry" in error for error in validate_registry([older, expired])))
        still_active = copy.deepcopy(expired)
        still_active["lifecycle"] = "active"
        errors = validate_registry([older, still_active])
        self.assertEqual(sum("past contractual expiry" in error for error in errors), 1)

    def test_registry_rejects_incomplete_verified_terms(self) -> None:
        candidate = record()
        candidate["terms"].pop("expiry")
        errors = validate_registry([candidate])
        self.assertTrue(any("terms_complete but expiry missing" in error for error in errors))

    def test_redemption_cash_resolves_delisted_cohort(self) -> None:
        candidate = record()
        candidate["lifecycle"] = "redeemed"
        candidate["corporate_action"] = {
            "effective_at": "2026-06-01",
            "cash_per_warrant": 0.01,
        }
        terminal = corporate_action_terminal(candidate, date(2026, 7, 1))
        self.assertEqual(terminal["close"], 0.01)
        self.assertEqual(terminal["outcome_kind"], "redeemed")

    def test_quote_age_uses_fetch_stamp_not_last_trade(self) -> None:
        old_print = (date.today() - timedelta(days=12)).isoformat()
        fresh_fetch = date.today().isoformat() + "T20:51:54Z"
        age = quote_age_days({"quote_date": old_print, "fetched_at": fresh_fetch, "close": 0.002})
        self.assertEqual(age, 0)


class WarrantExpirySweepTests(unittest.TestCase):
    """BKSY.W expired 2026-09-09 and stayed "active" until a human amended it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.registry = base / "warrant_registry.jsonl"
        self.amendments = base / "warrant_registry_amendments.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def _sweep(self, as_of: date) -> list[dict]:
        import sweep_warrant_expiry

        return sweep_warrant_expiry.sweep(
            as_of=as_of, registry_path=self.registry, amendments_path=self.amendments
        )

    def _all_rows(self) -> list[dict]:
        return load_jsonl(self.registry) + load_jsonl(self.amendments)

    def test_sweep_retires_a_series_past_its_expiry(self) -> None:
        bksy = record()
        bksy["terms"]["expiry"] = "2026-09-09"
        self._write(self.registry, [bksy])
        self.assertTrue(any("past contractual expiry" in e for e in validate_registry(self._all_rows())))

        added = self._sweep(date(2026, 9, 10))

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["version"], 2)
        self.assertEqual(added[0]["supersedes_version"], 1)
        self.assertEqual(added[0]["lifecycle"], "expired")
        self.assertEqual(added[0]["terms"], bksy["terms"])  # contract terms untouched
        self.assertEqual(validate_registry(self._all_rows()), [])
        self.assertEqual(self._sweep(date(2026, 9, 11)), [])  # idempotent

    def test_sweep_honours_a_recorded_extension(self) -> None:
        original = record()
        original["terms"]["expiry"] = "2026-09-09"
        extended = copy.deepcopy(original)
        extended["version"] = 2
        extended["terms"]["expiry"] = "2027-09-09"
        self._write(self.registry, [original])
        self._write(self.amendments, [extended])
        self.assertEqual(self._sweep(date(2026, 9, 10)), [])

    def test_sweep_leaves_live_and_terminal_series_alone(self) -> None:
        live = record()  # expiry 2030
        on_the_day = record()
        on_the_day["warrant_id"] = "0000000002:test:public"
        on_the_day["terms"]["expiry"] = "2026-09-10"
        redeemed = record()
        redeemed["warrant_id"] = "0000000003:test:public"
        redeemed["lifecycle"] = "redeemed"
        redeemed["terms"]["expiry"] = "2022-01-21"
        self._write(self.registry, [live, on_the_day, redeemed])
        self.assertEqual(self._sweep(date(2026, 9, 10)), [])
        self.assertFalse(self.amendments.exists())


class WarrantCheckWarnOnlyTests(unittest.TestCase):
    ISSUES = (["row 4: active security is past contractual expiry"], [])

    def test_warn_only_reports_and_exits_zero(self) -> None:
        import check_warrant_universe

        with mock.patch.object(check_warrant_universe, "check", return_value=self.ISSUES), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check_warrant_universe.main(["--warn-only"]), 0)
        self.assertIn("::warning", out.getvalue())
        self.assertIn("past contractual expiry", out.getvalue())

    def test_default_mode_still_fails(self) -> None:
        import check_warrant_universe

        with mock.patch.object(check_warrant_universe, "check", return_value=self.ISSUES), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(check_warrant_universe.main([]), 1)


if __name__ == "__main__":
    unittest.main()
