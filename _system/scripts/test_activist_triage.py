#!/usr/bin/env python3
"""Unit tests for activist auto-triage rules."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_triage import load_passive_patterns, load_rules, triage_report  # noqa: E402
from activist_common import ticker_meta  # noqa: E402

GOLDEN = ROOT / "_system" / "scripts" / "fixtures" / "activist_triage_golden.jsonl"


class ActivistTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_rules()
        cls.passive = load_passive_patterns()

    def _triage(self, case: dict) -> str:
        ticker = case["ticker"]
        report = {k: v for k, v in case.items() if k != "expected_verdict"}
        meta = ticker_meta(ticker)
        result = triage_report(
            report,
            ticker=ticker,
            meta=meta,
            all_reports=[report],
            rules=self.rules,
            passive_patterns=self.passive,
            today=date(2026, 7, 5),
        )
        return result["triage_verdict"]

    def test_golden_cases(self) -> None:
        if not GOLDEN.exists():
            self.skipTest("golden fixture missing")
        for line in GOLDEN.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            expected = case["expected_verdict"]
            got = self._triage(case)
            self.assertEqual(
                got,
                expected,
                msg=f"{case['ticker']}/{case.get('firm_id')}: expected {expected}, got {got}",
            )

    def test_passive_blocklist_excludes_berkshire(self) -> None:
        report = {
            "firm_id": "sec_filer:berkshire_hathaway_inc",
            "firm_name": "BERKSHIRE HATHAWAY INC",
            "filing_class": "activist_13d",
            "report_date": "2024-02-16",
            "stake_percent": 2.0,
            "side": "long",
            "confidence": 0.85,
        }
        result = triage_report(
            report,
            ticker="BKRB",
            meta=ticker_meta("BKRB"),
            all_reports=[report],
            rules=self.rules,
            passive_patterns=self.passive,
            today=date(2026, 7, 5),
        )
        self.assertEqual(result["triage_verdict"], "auto_passive")
        self.assertFalse(result["include_in_feed"])

    def test_registry_proxy_promotes_frmi(self) -> None:
        report = {
            "firm_id": "vicksburg",
            "firm_name": "Vicksburg Investments Management",
            "filing_class": "activist_proxy",
            "form": "DFAN14A",
            "report_date": "2026-07-01",
            "side": "long",
            "confidence": 0.95,
        }
        result = triage_report(
            report,
            ticker="FRMI",
            meta=ticker_meta("FRMI"),
            all_reports=[report],
            rules=self.rules,
            passive_patterns=self.passive,
            today=date(2026, 7, 5),
        )
        self.assertEqual(result["triage_verdict"], "auto_signal")
        self.assertGreaterEqual(result.get("materiality_floor") or 0, 60)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
