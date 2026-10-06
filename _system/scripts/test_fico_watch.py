#!/usr/bin/env python3
"""Offline tests for the FICO dashboard watch. No SEC calls."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_fico_watch import (  # noqa: E402
    FACTS_PATH,
    build_payload,
    latest_duration,
    latest_periodic,
    ledger_from_payload,
    span_days,
)
from lint_kpi_ledger import lint_ledger  # noqa: E402


def _usd(val, *, start=None, end, form="10-Q", filed="2026-07-29"):
    row = {"val": val, "end": end, "form": form, "filed": filed, "accn": "0000814547-26-000030"}
    if start:
        row["start"] = start
    return row


def _gaap():
    return {
        "LongTermDebtNoncurrent": {"units": {"USD": [_usd(5_282_389_000, end="2026-06-30")]}},
        "LongTermDebtCurrent": {"units": {"USD": [_usd(300_000_000, end="2026-06-30")]}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [_usd(248_444_000, end="2026-06-30")]}},
        "OperatingIncomeLoss": {"units": {"USD": [
            _usd(362_628_000, start="2026-04-01", end="2026-06-30"),
            _usd(999_142_000, start="2025-10-01", end="2026-06-30"),
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _usd(674_188_000, start="2026-04-01", end="2026-06-30"),
            _usd(1_877_824_000, start="2025-10-01", end="2026-06-30"),
        ]}},
        "InterestExpense": {"units": {"USD": [
            _usd(146_000_000, start="2025-10-01", end="2026-06-30"),
        ]}},
    }


def _submissions(form="10-Q", accession="0000814547-26-000030", filed="2026-07-29"):
    return {
        "filings": {
            "recent": {
                "form": ["8-K", form],
                "accessionNumber": ["0000814547-26-000001", accession],
                "filingDate": ["2026-08-01", filed],
                "reportDate": ["2026-06-30", "2026-06-30"],
            }
        }
    }


class SpanTests(unittest.TestCase):
    def test_quarter_and_year_to_date_are_not_confused(self):
        rows = _gaap()["OperatingIncomeLoss"]["units"]["USD"]
        self.assertEqual(span_days(rows[0]), 90)
        self.assertEqual(span_days(rows[1]), 272)
        quarter = latest_duration(rows, min_days=80, max_days=100)
        ytd = latest_duration(rows, min_days=170, max_days=380)
        self.assertEqual(quarter["val"], 362_628_000)
        self.assertEqual(ytd["val"], 999_142_000)

    def test_latest_periodic_ignores_current_reports(self):
        latest = latest_periodic(_submissions())
        self.assertEqual(latest["form"], "10-Q")
        self.assertEqual(latest["accession"], "0000814547-26-000030")


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
        self.today = date(2026, 10, 6)

    def _payload(self, **kwargs):
        kwargs.setdefault("today", self.today)
        kwargs.setdefault("generated_at", "2026-10-06T14:00:00Z")
        return build_payload(self.facts, kwargs.pop("submissions", _submissions()), kwargs.pop("gaap", _gaap()), **kwargs)

    def test_current_filing_breaks_the_three_lines_that_matter(self):
        payload = self._payload()
        self.assertEqual(payload["freshness"]["state"], "current")
        by_id = {gate["kpi_id"]: gate for gate in payload["gates"]}
        self.assertEqual(by_id["mortgage_exclusivity"]["status"], "fail")
        self.assertIn("One grid", by_id["mortgage_exclusivity"]["display"])
        self.assertEqual(by_id["software_growth_pct"]["status"], "fail")
        self.assertEqual(by_id["net_debt_to_annualized_operating_income"]["status"], "fail")
        self.assertGreater(by_id["net_debt_to_annualized_operating_income"]["actual"], 3)
        self.assertEqual(by_id["preferred_lender_count"]["status"], "pass")
        self.assertEqual(by_id["bureau_revenue_share_pct"]["status"], "pass")
        self.assertEqual(by_id["scores_operating_margin_pct"]["status"], "pass")
        self.assertEqual(by_id["mortgage_unit_price"]["status"], "unchecked")
        self.assertIn("Mortgage exclusivity is gone", payload["banner"]["text"])
        self.assertIn("Software is not an offset", payload["banner"]["text"])
        self.assertIn("Debt is above 3× operating income", payload["banner"]["text"])
        self.assertTrue(all(gate.get("in_base_irr") is not True for gate in payload["gates"]))

    def test_leverage_uses_year_to_date_not_the_quarter(self):
        payload = self._payload()
        gate = next(g for g in payload["gates"] if g["kpi_id"] == "net_debt_to_annualized_operating_income")
        net = 5_282_389_000 + 300_000_000 - 248_444_000
        annualized = 999_142_000 * (365 / 272)
        self.assertAlmostEqual(gate["actual"], round(net / annualized, 2))
        revenue = next(row for row in payload["groups"][1]["rows"] if row["id"] == "revenue_quarter")
        self.assertEqual(revenue["display"], "$674.2 million")

    def test_newer_filing_marks_segment_gates_unread_and_keeps_sec_math(self):
        payload = self._payload(submissions=_submissions(
            form="10-K", accession="0000814547-26-000099", filed="2026-11-12",
        ))
        self.assertEqual(payload["freshness"]["state"], "unread_filing")
        by_id = {gate["kpi_id"]: gate for gate in payload["gates"]}
        self.assertEqual(by_id["software_growth_pct"]["status"], "stale")
        self.assertEqual(by_id["bureau_revenue_share_pct"]["status"], "stale")
        self.assertEqual(by_id["mortgage_exclusivity"]["status"], "fail")
        self.assertEqual(by_id["net_debt_to_annualized_operating_income"]["status"], "fail")
        self.assertIn("Newer filing unread", payload["banner"]["text"])
        scores = next(row for row in payload["groups"][2]["rows"] if row["id"] == "scores_quarter")
        self.assertEqual(scores["pill"], "Unread")

    def test_old_policy_date_does_not_keep_a_confident_fail(self):
        payload = self._payload(today=date(2026, 11, 1))
        gate = next(g for g in payload["gates"] if g["kpi_id"] == "mortgage_exclusivity")
        self.assertEqual(gate["status"], "stale")
        self.assertNotIn("Mortgage exclusivity is gone", payload["banner"]["text"])

    def test_sec_outage_reuses_the_last_automatic_multiple(self):
        good = self._payload()
        payload = build_payload(
            self.facts,
            None,
            None,
            today=self.today,
            sec_error="URLError: down",
            previous=good,
            generated_at="2026-10-07T14:00:00Z",
        )
        self.assertEqual(payload["freshness"]["state"], "sec_unchecked")
        self.assertEqual(payload["auto"]["leverage"], good["auto"]["leverage"])
        self.assertEqual(payload["auto"]["checked_at"], good["auto"]["checked_at"])
        self.assertTrue(payload["freshness"]["reused_auto"])

    def test_ledger_passes_the_weekly_lint(self):
        payload = self._payload()
        ledger = ledger_from_payload(payload, self.today)
        self.assertLessEqual(len(ledger["kpis"]), 15)
        self.assertTrue(all(kpi["in_base_irr"] is False for kpi in ledger["kpis"]))
        self.assertEqual(lint_ledger("FICO", ledger), [])


if __name__ == "__main__":
    unittest.main()
