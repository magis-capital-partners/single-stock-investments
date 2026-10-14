#!/usr/bin/env python3
"""Tests for SEC fundamental series extraction."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_fundamental_series import extract_metric_series, series_for_tag  # noqa: E402


class TagSelectionTests(unittest.TestCase):
    def test_picks_latest_tag_not_first_stale_tag(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2020-07-31",
                                    "start": "2020-05-01",
                                    "val": 500.0,
                                    "form": "10-Q",
                                    "filed": "2020-09-01",
                                }
                            ]
                        }
                    },
                    "RevenueFromContractWithCustomerIncludingAssessedTax": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2026-04-30",
                                    "start": "2026-02-01",
                                    "val": 1200.0,
                                    "form": "10-Q",
                                    "filed": "2026-05-29",
                                }
                            ]
                        }
                    },
                }
            }
        }
        series = extract_metric_series(facts, "revenues")
        self.assertEqual(series[-1]["period"], "2026-04-30")
        self.assertEqual(series[-1]["value"], 1200.0)


def _fact(start: str, end: str, val: float, form: str = "10-Q", filed: str = "2026-01-01") -> dict:
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed}


class DerivedQuarterTests(unittest.TestCase):
    """Cash flow is filed year to date, so Q2 to Q4 exist only as differences."""

    def test_ytd_cash_flow_becomes_four_quarters(self) -> None:
        facts = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            _fact("2025-01-01", "2025-03-31", 10.0, filed="2025-05-01"),
            _fact("2025-01-01", "2025-06-30", 25.0, filed="2025-08-01"),
            _fact("2025-01-01", "2025-09-30", 45.0, filed="2025-11-01"),
            _fact("2025-01-01", "2025-12-31", 70.0, form="10-K", filed="2026-02-20"),
        ]}}}}}
        series = extract_metric_series(facts, "cfo")
        self.assertEqual([p["period"] for p in series], ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"])
        self.assertEqual([p["value"] for p in series], [10.0, 15.0, 20.0, 25.0])
        self.assertNotIn("derived", series[0])
        self.assertEqual(series[1]["derived"], "ytd_difference")
        self.assertEqual(series[3]["from_periods"], ["2025-09-30", "2025-12-31"])
        self.assertEqual(series[3]["form"], "10-K")

    def test_reported_quarter_beats_a_derived_one(self) -> None:
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            _fact("2025-01-01", "2025-03-31", 100.0),
            _fact("2025-04-01", "2025-06-30", 130.0),
            _fact("2025-01-01", "2025-06-30", 999.0),
        ]}}}}}
        series = series_for_tag(facts["facts"]["us-gaap"], "Revenues", is_flow=True)
        self.assertEqual(series["2025-06-30"]["value"], 130.0)
        self.assertNotIn("derived", series["2025-06-30"])

    def test_annual_without_a_nine_month_fact_stays_undefined(self) -> None:
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            _fact("2025-01-01", "2025-03-31", 100.0),
            _fact("2025-01-01", "2025-12-31", 500.0, form="10-K"),
        ]}}}}}
        series = series_for_tag(facts["facts"]["us-gaap"], "Revenues", is_flow=True)
        self.assertEqual(sorted(series), ["2025-03-31"])

    def test_per_share_figures_are_never_derived(self) -> None:
        facts = {"facts": {"us-gaap": {"EarningsPerShareBasic": {"units": {"USD/shares": [
            _fact("2025-01-01", "2025-03-31", 1.0),
            _fact("2025-01-01", "2025-06-30", 2.5),
        ]}}}}}
        series = extract_metric_series(facts, "eps_basic")
        self.assertEqual([p["period"] for p in series], ["2025-03-31"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
