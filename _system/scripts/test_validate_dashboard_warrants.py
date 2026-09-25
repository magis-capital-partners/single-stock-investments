#!/usr/bin/env python3
"""validate_dashboard_data: warrant registry problems warn, publishing faults fail.

From 2026-09-10 to 09-22 one expired warrant row (BKSY.W still "active")
made warrants.json carry health.structural_errors, and this validator turned
that into a hard error in every lane that runs it: the technicals job and 21
dashboard deploys failed on "warrants.json reports structural contract
errors". The warrant lane owns that registry and enforces it strictly.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_dashboard_data as vdd  # noqa: E402


def _warrants(**overrides) -> dict:
    payload = {
        "rows": [
            {
                "warrant_ticker": "TESTW",
                "lifecycle": "active",
                "gates": {"identity": {"pass": True}, "survival": {"pass": False}},
                "diagnostics": {"opportunity_score": None},
            }
        ],
        "summary": {"active_series": 1},
        "health": {"status": "healthy", "structural_errors": []},
    }
    payload.update(overrides)
    return payload


class WarrantMonitorIssuesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "warrants.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _issues(self, payload: dict) -> tuple[list[str], list[str]]:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return vdd.warrant_monitor_issues(self.path)

    def test_structural_registry_errors_are_a_warning_not_an_error(self) -> None:
        errors, warnings = self._issues(
            _warrants(
                health={
                    "status": "unhealthy",
                    "structural_errors": ["row 4: active security is past contractual expiry"],
                }
            )
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("past contractual expiry", warnings[0])

    def test_score_before_gates_is_still_an_error(self) -> None:
        payload = _warrants()
        payload["rows"][0]["diagnostics"]["opportunity_score"] = 71
        errors, _warnings = self._issues(payload)
        self.assertTrue(any("score emitted before all gates pass" in e for e in errors))

    def test_summary_mismatch_and_missing_file_are_errors(self) -> None:
        errors, _ = self._issues(_warrants(summary={"active_series": 3}))
        self.assertTrue(any("active_series does not match" in e for e in errors))
        self.path.unlink()
        errors, _ = vdd.warrant_monitor_issues(self.path)
        self.assertEqual(errors, ["missing dashboard/data/warrants.json"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
