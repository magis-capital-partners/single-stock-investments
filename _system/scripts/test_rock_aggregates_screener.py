#!/usr/bin/env python3
"""Unit tests for the rock / aggregates screener (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_rock_aggregates_screener as mod


def _facts(tag: str, entries: list[dict], namespace: str = "us-gaap") -> dict:
    return {"facts": {namespace: {tag: {"units": {"USD": entries}}}}}


class SeedTests(unittest.TestCase):
    def test_load_seed_uppercases_and_dedupes(self):
        csv_text = (
            "ticker,company,market,cap_tier,rock_type,notes\n"
            "vmc,Vulcan Materials,US,large,aggregates_pure,note a\n"
            "VMC,Dup,US,large,aggregates_pure,dup\n"
            "USLM,US Lime,US,small,lime,high margin\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.csv"
            path.write_text(csv_text, encoding="utf-8")
            with mock.patch.object(mod, "SEED_PATH", path):
                rows = mod.load_seed_rows()
        self.assertEqual([r["ticker"] for r in rows], ["VMC", "USLM"])
        self.assertEqual(rows[0]["rock_type"], "aggregates_pure")
        self.assertEqual(rows[0]["rock_type_label"], "Aggregates (pure)")
        self.assertEqual(rows[1]["rock_type_label"], "Lime")


class AnnualDurationTests(unittest.TestCase):
    """A 10-K carries its own Q4 alongside the full year, both tagged fp=FY."""

    def test_quarter_inside_a_10k_is_not_annual(self):
        q4 = {"start": "2025-10-01", "end": "2025-12-31", "form": "10-K", "fp": "FY", "val": 1}
        self.assertFalse(mod._is_annual_entry(q4))

    def test_full_year_is_annual(self):
        fy = {"start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "fp": "FY", "val": 1}
        self.assertTrue(mod._is_annual_entry(fy))

    def test_ytd_in_a_10q_is_not_annual(self):
        ytd = {"start": "2025-01-01", "end": "2025-09-30", "form": "10-Q", "fp": "FY", "val": 1}
        self.assertFalse(mod._is_annual_entry(ytd))

    def test_duration_fact_without_start_is_rejected(self):
        self.assertFalse(mod._is_annual_entry({"end": "2025-12-31", "form": "10-K", "val": 1}))

    def test_annual_picker_takes_the_year_not_the_quarter(self):
        """Regression: MLM reported a $1.53B Q4 and a $6.15B FY both ending 2025-12-31."""
        facts = _facts(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            [
                {"start": "2025-10-01", "end": "2025-12-31", "form": "10-K", "fp": "FY", "val": 1_534_000_000},
                {"start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "fp": "FY", "val": 6_150_000_000},
            ],
        )
        val, end = mod.latest_annual_usd_fact(facts, mod.REVENUE_TAGS)
        self.assertEqual(val, 6_150_000_000)
        self.assertEqual(end, "2025-12-31")

    def test_annual_picker_ignores_quarter_order(self):
        """Same facts, reversed order: the answer must not depend on JSON ordering."""
        facts = _facts(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            [
                {"start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "fp": "FY", "val": 6_150_000_000},
                {"start": "2025-10-01", "end": "2025-12-31", "form": "10-K", "fp": "FY", "val": 1_534_000_000},
            ],
        )
        val, _ = mod.latest_annual_usd_fact(facts, mod.REVENUE_TAGS)
        self.assertEqual(val, 6_150_000_000)


class TagSelectionTests(unittest.TestCase):
    def test_latest_period_wins_across_tags(self):
        """Regression: Knife River retired one revenue tag in FY2024 and kept filing
        under another; first-tag-wins froze the row two years in the past."""
        facts = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [
                            {"start": "2023-01-01", "end": "2023-12-31", "form": "10-K", "val": 2_830_350_000},
                        ]}
                    },
                    "Revenues": {
                        "units": {"USD": [
                            {"start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "val": 3_146_012_000},
                        ]}
                    },
                }
            }
        }
        val, end = mod.latest_annual_usd_fact(facts, mod.REVENUE_TAGS)
        self.assertEqual(val, 3_146_012_000)
        self.assertEqual(end, "2025-12-31")

    def test_preferred_tag_wins_an_exact_tie(self):
        facts = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [
                            {"start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "val": 100},
                        ]}
                    },
                    "Revenues": {
                        "units": {"USD": [
                            {"start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "val": 999},
                        ]}
                    },
                }
            }
        }
        val, _ = mod.latest_annual_usd_fact(facts, mod.REVENUE_TAGS)
        self.assertEqual(val, 100)

    def test_balance_sheet_picker_accepts_a_quarter(self):
        facts = _facts("StockholdersEquity", [
            {"end": "2025-12-31", "form": "10-K", "val": 500},
            {"end": "2026-03-31", "form": "10-Q", "val": 550},
        ])
        val, end = mod.latest_usd_fact(facts, mod.EQUITY_TAGS)
        self.assertEqual(val, 550)
        self.assertEqual(end, "2026-03-31")


class MetricsTests(unittest.TestCase):
    def _sec(self, **over):
        base = {
            "revenue_usd": 1_000.0,
            "operating_income_usd": 200.0,
            "dda_usd": 100.0,
            "cfo_usd": 250.0,
            "capex_usd": 90.0,
            "equity_usd": 800.0,
            "cash_usd": 50.0,
            "long_term_debt_usd": 500.0,
            "short_term_debt_usd": 50.0,
            "goodwill_usd": 300.0,
            "intangibles_usd": 100.0,
        }
        base.update(over)
        return base

    def test_core_math(self):
        m = mod.compute_rock_metrics(self._sec(), price=10.0, mcap=2_000.0)
        self.assertEqual(m["ebitda_usd"], 300.0)                # 200 + 100
        self.assertEqual(m["ebitda_margin_pct"], 30.0)          # 300 / 1000
        self.assertEqual(m["fcf_usd"], 160.0)                   # 250 - 90
        self.assertEqual(m["fcf_conversion_pct"], 53.3)         # 160 / 300
        self.assertEqual(m["capex_pct_revenue"], 9.0)           # 90 / 1000
        self.assertEqual(m["total_debt_usd"], 550.0)
        self.assertEqual(m["net_debt_usd"], 500.0)              # 550 - 50
        self.assertEqual(m["net_debt_ebitda"], 1.67)            # 500 / 300
        self.assertEqual(m["enterprise_value_usd"], 2_500.0)    # 2000 + 500
        self.assertEqual(m["ev_ebitda"], 8.3)                   # 2500 / 300
        self.assertEqual(m["fcf_yield_pct"], 8.0)               # 160 / 2000
        self.assertEqual(m["goodwill_equity_pct"], 50.0)        # 400 / 800

    def test_roic_uses_invested_capital_not_equity(self):
        # NOPAT 200 * 0.79 = 158; invested = 800 + 550 - 50 = 1300 -> 12.2%
        m = mod.compute_rock_metrics(self._sec(), price=10.0, mcap=2_000.0)
        self.assertEqual(m["roic_pct"], 12.2)

    def test_net_cash_reads_as_negative_leverage(self):
        m = mod.compute_rock_metrics(
            self._sec(long_term_debt_usd=0.0, short_term_debt_usd=0.0, cash_usd=600.0),
            price=10.0,
            mcap=2_000.0,
        )
        self.assertEqual(m["net_debt_usd"], -600.0)
        self.assertEqual(m["net_debt_ebitda"], -2.0)
        self.assertEqual(m["enterprise_value_usd"], 1_400.0)

    def test_missing_inputs_yield_none_not_zero(self):
        m = mod.compute_rock_metrics({"revenue_usd": 1_000.0}, price=None, mcap=None)
        for key in ("ebitda_usd", "ebitda_margin_pct", "fcf_usd", "net_debt_usd",
                    "roic_pct", "ev_ebitda", "fcf_yield_pct"):
            self.assertIsNone(m[key], f"{key} should be None when inputs are missing")

    def test_zero_ebitda_does_not_divide(self):
        m = mod.compute_rock_metrics(
            self._sec(operating_income_usd=-100.0, dda_usd=100.0), price=10.0, mcap=2_000.0
        )
        self.assertEqual(m["ebitda_usd"], 0.0)
        self.assertIsNone(m["ev_ebitda"])
        self.assertIsNone(m["net_debt_ebitda"])
        self.assertIsNone(m["fcf_conversion_pct"])


class ScreenTickerTests(unittest.TestCase):
    def test_ifrs_filer_is_labelled_not_silently_blank(self):
        ifrs = {"entityName": "CEMEX SAB DE CV", "facts": {"dei": {}, "ifrs-full": {"Revenue": {}}}}
        with mock.patch.object(mod, "fetch_json", return_value=ifrs):
            out = mod.screen_ticker("0001076378")
        self.assertIn("IFRS filer", out["sec_error"])
        self.assertIn("ifrs-full", out["sec_error"])
        self.assertIsNone(out.get("revenue_usd"))

    def test_unreachable_companyfacts_is_labelled(self):
        with mock.patch.object(mod, "fetch_json", return_value=None):
            out = mod.screen_ticker("0000000001")
        self.assertEqual(out["sec_error"], "companyfacts unavailable")


class SortAndPayloadTests(unittest.TestCase):
    def test_sort_puts_rock_first_then_cheapest(self):
        rows = [
            {"ticker": "CEMENT", "rock_type": "cement", "ev_ebitda": 5.0, "roic_pct": 20},
            {"ticker": "PRICEY", "rock_type": "aggregates_pure", "ev_ebitda": 18.0, "roic_pct": 10},
            {"ticker": "CHEAP", "rock_type": "aggregates_vertical", "ev_ebitda": 9.0, "roic_pct": 8},
            {"ticker": "NODATA", "rock_type": "aggregates_pure", "ev_ebitda": None, "roic_pct": None},
        ]
        rows.sort(key=mod.sort_key)
        self.assertEqual([r["ticker"] for r in rows], ["CHEAP", "PRICEY", "NODATA", "CEMENT"])

    def test_holdings_are_not_demoted(self):
        """Deliberate difference from the banks screen: the holdings are the benchmark."""
        rows = [
            {"ticker": "NEW", "rock_type": "aggregates_pure", "ev_ebitda": 20.0, "in_holdings": False},
            {"ticker": "VMC", "rock_type": "aggregates_pure", "ev_ebitda": 16.0, "in_holdings": True},
        ]
        rows.sort(key=mod.sort_key)
        self.assertEqual([r["ticker"] for r in rows], ["VMC", "NEW"])

    def test_payload_envelope_keys(self):
        fake_rows = [
            {"ticker": "VMC", "company": "Vulcan Materials", "market": "US",
             "rock_type": "aggregates_pure", "is_pure_rock": True,
             "in_holdings": True, "in_watchlist": False},
            {"ticker": "EXP", "company": "Eagle Materials", "market": "US",
             "rock_type": "cement", "is_pure_rock": False,
             "in_holdings": False, "in_watchlist": False},
        ]
        payload = mod.build_payload(fake_rows)
        for key in ("built_at", "criteria", "seed_path", "row_count", "pure_rock_count", "rows"):
            self.assertIn(key, payload)
        self.assertEqual(payload["row_count"], 2)
        self.assertEqual(payload["pure_rock_count"], 1)

    def test_criteria_states_the_flow_basis(self):
        payload = mod.build_payload([])
        self.assertIn("FULL-YEAR", payload["criteria"])


class FormatTests(unittest.TestCase):
    def test_usd_scales_and_signs(self):
        self.assertEqual(mod.fmt_usd(7_940_000_000), "$7.94B")
        self.assertEqual(mod.fmt_usd(373_000_000), "$373M")
        self.assertEqual(mod.fmt_usd(-600_000_000), "-$600M")
        self.assertIsNone(mod.fmt_usd(None))

    def test_pct_and_multiple(self):
        self.assertEqual(mod.fmt_pct(29.8), "29.8%")
        self.assertEqual(mod.fmt_multiple(-2.1), "-2.1x")
        self.assertIsNone(mod.fmt_pct(None))
        self.assertIsNone(mod.fmt_multiple(None))


if __name__ == "__main__":
    unittest.main()
