"""Buyback radar: split adjustment, pace, grade, filing events, and the feed envelope."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_buyback_radar as radar  # noqa: E402
import build_special_situations as book  # noqa: E402


def _year(fy: int, shares: float) -> dict:
    return {"fy": fy, "end": f"{fy}-01-31", "filed": f"{fy}-03-15", "shares": shares, "split_factor": 1.0}


class SplitTests(unittest.TestCase):
    def test_forward_splits_compound_onto_older_counts(self):
        points = [_year(2020, 100), _year(2021, 200), _year(2022, 400)]
        out = radar._adjust_splits(points)
        self.assertEqual([row["shares"] for row in out], [400, 400, 400])

    def test_a_fifty_for_one_jump_is_a_forward_split(self):
        points = [_year(2023, 28_000_000), _year(2024, 1_400_000_000)]
        out = radar._adjust_splits(points)
        self.assertEqual(out[0]["shares"], 1_400_000_000)
        self.assertFalse(out[-1].get("split_review"))

    def test_a_one_year_spike_is_dropped(self):
        points = [_year(2020, 100), _year(2021, 100_000), _year(2022, 110), _year(2023, 105)]
        out = radar._adjust_splits(points)
        self.assertEqual([row["fy"] for row in out], [2020, 2022, 2023])
        self.assertTrue(out[-1]["share_review"])

    def test_seven_for_one_with_a_same_year_buyback_still_adjusts(self):
        points = [_year(2013, 900), _year(2014, 5860), _year(2015, 5570)]
        out = radar._adjust_splits(points)
        self.assertEqual(round(out[0]["shares"]), 6300)

    def test_a_halving_is_not_treated_as_a_reverse_split(self):
        points = [_year(2020, 200), _year(2021, 100)]
        out = radar._adjust_splits(points)
        self.assertEqual([row["shares"] for row in out], [200, 100])
        self.assertFalse(out[-1].get("split_review"))

    def test_a_separation_sized_drop_is_flagged(self):
        points = [_year(2010, 1000), _year(2011, 146)]
        out = radar._adjust_splits(points)
        self.assertEqual(out[1]["shares"], 146)
        self.assertTrue(out[-1]["split_review"])


class PaceTests(unittest.TestCase):
    def test_four_pace_states(self):
        self.assertEqual(radar.pace_signal(-30, 9.7, 5), "issuing_again")
        self.assertEqual(radar.pace_signal(-37, 0.4, 5), "stopped")
        self.assertEqual(radar.pace_signal(-20, -17, 5), "accelerating")
        self.assertEqual(radar.pace_signal(-20, -4, 5), "steady")
        self.assertIsNone(radar.pace_signal(5, -1, 5))


class GradeTests(unittest.TestCase):
    def test_letter_thresholds(self):
        self.assertEqual(radar._letter(6, never_a=False, partial=False), "A")
        self.assertEqual(radar._letter(6, never_a=True, partial=False), "B")
        self.assertEqual(radar._letter(4, never_a=False, partial=True), "B")
        self.assertNotEqual(radar._letter(4, never_a=False, partial=True), "A")

    def test_full_window_can_be_an_a(self):
        rows = []
        for i in range(10):
            rows.append(
                {
                    "shares": 100 - i * 5,
                    "shares_repurchased": 5,
                    "repurchase_usd": 50 if i < 7 else 30,
                    "cfo": 200,
                    "capex": 20,
                    "debt_issued": 0,
                    "debt_repaid": 0,
                }
            )
        graded = radar.grade_window(rows)
        self.assertEqual(graded["grade"], "A")
        self.assertFalse(graded["grade_partial"])

    def test_weak_stickiness_cannot_be_an_a(self):
        rows = []
        for i in range(10):
            rows.append(
                {
                    "shares": 100 - i * 0.2,
                    "shares_repurchased": 20,
                    "repurchase_usd": 100,
                    "cfo": 400,
                    "capex": 10,
                    "debt_issued": 0,
                    "debt_repaid": 10,
                }
            )
        graded = radar.grade_window(rows)
        self.assertEqual(graded["stickiness_points"], 0)
        self.assertNotEqual(graded["grade"], "A")

    def test_missing_price_paid_is_partial_and_not_an_a(self):
        rows = []
        for i in range(10):
            rows.append(
                {
                    "shares": 100 - i * 5,
                    "repurchase_usd": 40,
                    "cfo": 200,
                    "capex": 10,
                    "debt_issued": 0,
                    "debt_repaid": 0,
                }
            )
        graded = radar.grade_window(rows)
        self.assertTrue(graded["grade_partial"])
        self.assertNotEqual(graded["grade"], "A")


class EventTests(unittest.TestCase):
    def test_tender_reads_dutch_range_and_odd_lot(self):
        text = (
            "Issuer tender offer. The company is commencing a Dutch auction offer to purchase "
            "shares at $20.00 and $23.50 per share. Odd-lot holders may tender. "
            "The offer expires on December 15, 2026."
        )
        parsed = radar.parse_tender(text)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["dutch_auction"])
        self.assertTrue(parsed["odd_lot"])
        self.assertEqual(parsed["price_low"], 20.0)
        self.assertEqual(parsed["price_high"], 23.5)
        self.assertEqual(parsed["ends"], "2026-12-15")

    def test_asr_reads_the_dollar_amount_and_skips_a_completion_notice(self):
        announced = "The company entered into an accelerated share repurchase agreement for $500 million of common stock."
        parsed = radar.parse_asr(announced)
        self.assertEqual(parsed["usd"], 500_000_000)
        completed = "The company completed the final settlement of its accelerated share repurchase."
        self.assertIsNone(radar.parse_asr(completed))

    def test_earnings_repurchase_is_not_a_new_program(self):
        text = "During the quarter the company repurchased $400 million of common stock under its existing repurchase program."
        self.assertIsNone(radar.parse_program(text))

    def test_program_size_decides_row_versus_mention(self):
        parsed = radar.parse_program(
            "The board of directors authorized a new share repurchase program of up to $1.2 billion."
        )
        big = radar.classify_program(parsed, 8_000_000_000)
        self.assertTrue(big["row"])
        self.assertIn("15.0%", big["one_number"])
        small = radar.classify_program(dict(parsed), 40_000_000_000)
        self.assertFalse(small["row"])
        self.assertIn("Not a situation row", small["mention"])

    def test_discover_keeps_the_row_and_the_mention_apart(self):
        texts = [
            {
                "kind": "program",
                "ticker": "SMALL",
                "cik": "0000000001",
                "adsh": "0001-26-000001",
                "url": "https://www.sec.gov/Archives/edgar/data/1/a.htm",
                "display": "SMALL CO (SMALL) (CIK 0000000001)",
                "filed": "2026-10-01",
                "text": "The board of directors authorized a new repurchase program of up to $200 million.",
            },
            {
                "kind": "program",
                "ticker": "BIG",
                "cik": "0000000002",
                "adsh": "0002-26-000001",
                "url": "https://www.sec.gov/Archives/edgar/data/2/b.htm",
                "display": "BIG CO (BIG)",
                "filed": "2026-10-02",
                "text": "The board of directors approved an increase of the repurchase program of up to $1 billion.",
            },
        ]

        def mv(ticker: str):
            return {"SMALL": 1_000_000_000, "BIG": 50_000_000_000}.get(ticker)

        rows, mentions, _stats = radar.discover_events(date(2026, 10, 18), mv, offline_texts=texts)
        self.assertEqual([row["ticker"] for row in rows], ["SMALL"])
        self.assertTrue(rows[0]["research_only"])
        self.assertEqual([row["ticker"] for row in mentions], ["BIG"])


def _share_doc(points: list[tuple[int, float]], usd: dict[str, list[dict]] | None = None) -> dict:
    dei = []
    for fy, shares in points:
        dei.append(
            {
                "form": "10-K",
                "fp": "FY",
                "fy": fy,
                "end": f"{fy}-01-31",
                "filed": f"{fy}-03-15",
                "val": shares,
                "accn": f"000{fy}",
            }
        )
    us = {tag: {"units": {"USD": rows}} for tag, rows in (usd or {}).items()}
    return {
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": dei}}},
            "us-gaap": us,
        }
    }


def _usd(fy: int, val: float, tag_end: str | None = None) -> dict:
    return {
        "form": "10-K",
        "fp": "FY",
        "fy": fy,
        "start": f"{fy - 1}-02-01",
        "end": tag_end or f"{fy}-01-31",
        "filed": f"{fy}-03-20",
        "val": val,
        "accn": f"usd{fy}",
    }


class InstrumentTests(unittest.TestCase):
    def test_funds_and_typed_instruments_are_not_operating_companies(self):
        self.assertEqual(radar.is_non_operating_instrument("SPDR® GOLD TRUST", None)[0], True)
        self.assertEqual(radar.is_non_operating_instrument("United States Oil Fund, LP", None)[0], True)
        self.assertEqual(radar.is_non_operating_instrument("iShares Ethereum Trust ETF", None)[0], True)
        self.assertEqual(radar.is_non_operating_instrument("Home Depot", "closed_end_fund")[0], True)
        self.assertEqual(radar.is_non_operating_instrument("Home Depot", "etf")[0], True)
        self.assertEqual(radar.is_non_operating_instrument("Home Depot", "listed_investment_co")[0], True)
        self.assertEqual(radar.is_non_operating_instrument("NORTHERN TRUST CORP", None)[0], False)
        self.assertEqual(radar.is_non_operating_instrument("CAMDEN PROPERTY TRUST", None)[0], False)
        self.assertEqual(radar.is_non_operating_instrument("Berkshire", "holding_company")[0], False)
        self.assertEqual(radar.is_non_operating_instrument("Berkshire", "operating_company")[0], False)
        trust = {"facts": {"us-gaap": {"SaleOfTrustAssetsToPayExpenses": {}}}}
        self.assertEqual(radar.is_non_operating_instrument("VS Trust", None, trust)[0], True)
        self.assertEqual(radar.is_non_operating_instrument("Cipher Digital Inc.", None, trust)[0], False)

    def test_a_fund_gets_no_pace_grade_or_issuance_flag(self):
        # Shrink for five years, then issue. That is issuing_again for an operating company.
        points = [(2019, 100), (2020, 100), (2021, 90), (2022, 80), (2023, 70), (2024, 60), (2025, 70)]
        doc = _share_doc(points)
        fund, _, reason = radar.build_company_row(
            ticker="GLD",
            company="SPDR® GOLD TRUST",
            cik="0001222333",
            in_registry=True,
            doc=doc,
            price=100,
            price_as_of="2026-10-16",
        )
        self.assertIsNone(reason)
        self.assertTrue(fund["non_operating"])
        self.assertIsNone(fund["pace"])
        self.assertIsNone(fund["grade"])
        self.assertEqual(fund["grade_reason"], "creation_units_not_dilution")
        operating, _, _ = radar.build_company_row(
            ticker="NRG",
            company="NRG Energy, Inc",
            cik="0000000001",
            in_registry=True,
            doc=doc,
            price=100,
            price_as_of="2026-10-16",
            instrument_type="operating_company",
        )
        self.assertEqual(operating["pace"], "issuing_again")
        self.assertFalse(operating["non_operating"])
        typed, _, _ = radar.build_company_row(
            ticker="NAN",
            company="Nuveen",
            cik="0000000002",
            in_registry=True,
            doc=doc,
            price=10,
            price_as_of="2026-10-16",
            instrument_type="closed_end_fund",
        )
        self.assertIsNone(typed["pace"])
        self.assertIsNone(typed["grade"])
        signals = radar.issuance_signals([fund, operating, typed])
        self.assertEqual([row["ticker"] for row in signals], ["NRG"])

    def test_zero_common_stock_repurchase_falls_back_and_marks_the_tag(self):
        points = [(2024, 100), (2025, 90)]
        doc = _share_doc(
            points,
            {
                "PaymentsForRepurchaseOfCommonStock": [_usd(2024, 80), _usd(2025, 0)],
                "PaymentsForRepurchaseOfEquity": [_usd(2025, 250)],
                "TreasuryStockValueAcquiredCostMethod": [_usd(2025, 999)],
            },
        )
        row, _, reason = radar.build_company_row(
            ticker="HD",
            company="HOME DEPOT, INC.",
            cik="0000354950",
            in_registry=True,
            doc=doc,
            price=10,
            price_as_of="2026-10-16",
        )
        self.assertIsNone(reason)
        self.assertEqual(row["repurchase_tag"], "PaymentsForRepurchaseOfEquity")
        self.assertEqual(row["repurchase_fy_usd"], 250)
        self.assertEqual(row["repurchase_fy"], 2025)
        # 250 / (10 * 90) = 27.777... -> 27.78
        self.assertEqual(row["buyback_yield_pct"], 27.78)
        self.assertIn("PaymentsForRepurchaseOfEquity", radar.shard_buyback(row)["note"])

    def test_a_missing_primary_tag_uses_treasury_stock_acquired(self):
        doc = _share_doc(
            [(2024, 50), (2025, 40)],
            {"TreasuryStockValueAcquiredCostMethod": [_usd(2025, 40)]},
        )
        row, _, _ = radar.build_company_row(
            ticker="EX",
            company="Example Co",
            cik="1",
            in_registry=True,
            doc=doc,
            price=10,
            price_as_of="2026-10-16",
        )
        self.assertEqual(row["repurchase_tag"], "TreasuryStockValueAcquiredCostMethod")
        self.assertEqual(row["repurchase_fy_usd"], 40)
        self.assertEqual(row["buyback_yield_pct"], 10.0)

    def test_an_explicit_zero_stays_zero_after_the_other_tags_are_empty(self):
        doc = _share_doc(
            [(2024, 100), (2025, 100)],
            {
                "PaymentsForRepurchaseOfCommonStock": [_usd(2025, 0)],
                "TreasuryStockValueAcquiredCostMethod": [_usd(2025, 0)],
            },
        )
        row, _, _ = radar.build_company_row(
            ticker="HD",
            company="HOME DEPOT, INC.",
            cik="1",
            in_registry=True,
            doc=doc,
            price=20,
            price_as_of="2026-10-16",
        )
        self.assertEqual(row["repurchase_tag"], "PaymentsForRepurchaseOfCommonStock")
        self.assertEqual(row["repurchase_fy_usd"], 0)
        self.assertEqual(row["buyback_yield_pct"], 0.0)

    def test_a_positive_primary_tag_is_not_replaced(self):
        doc = _share_doc(
            [(2024, 100), (2025, 80)],
            {
                "PaymentsForRepurchaseOfCommonStock": [_usd(2025, 160)],
                "StockRepurchasedDuringPeriodValue": [_usd(2025, 500)],
            },
        )
        row, _, _ = radar.build_company_row(
            ticker="LOW",
            company="LOWES COMPANIES INC",
            cik="1",
            in_registry=True,
            doc=doc,
            price=10,
            price_as_of="2026-10-16",
        )
        self.assertEqual(row["repurchase_tag"], "PaymentsForRepurchaseOfCommonStock")
        self.assertEqual(row["repurchase_fy_usd"], 160)
        self.assertEqual(row["buyback_yield_pct"], 20.0)


class FeedTests(unittest.TestCase):
    def test_envelope_and_budget(self):
        company = {
            "ticker": "HD",
            "company": "Home Depot",
            "retired_since_peak_pct": 41.2,
            "change_5y_pct": -12.0,
            "change_1y_pct": -1.0,
            "buyback_yield_pct": 3.4,
            "pace": "steady",
            "grade": "B",
        }
        l0, companies = radar.assemble_feeds(
            companies=[company],
            events=[],
            mentions=[],
            gaps=[],
            stats={"attempted": 1, "fetch_failures": 0},
            generated_at="2026-10-18T00:00:00Z",
        )
        self.assertEqual(l0["_envelope"]["schema_version"], "magis.feed.v2")
        self.assertEqual(l0["_envelope"]["health"]["status"], "healthy")
        self.assertIn("methodology", l0)
        self.assertLess(len(json.dumps(l0).encode("utf-8")), radar.L0_BUDGET_BYTES)
        self.assertEqual(companies["companies"][0]["ticker"], "HD")
        self.assertEqual(companies["issuance_signals"], [])
        self.assertTrue(l0["research_only"])
        self.assertFalse(l0["in_base_irr"])

    def test_situation_lane_ranks_the_event_and_skips_the_mention(self):
        payload = book.build_book(
            buyback={
                "events": [
                    {
                        "ticker": "TNDR",
                        "company": "Tender Co",
                        "event_type": "issuer_tender",
                        "what": "Issuer tender (Dutch auction): $20.00–$23.50.",
                        "ends": "2026-12-15",
                        "ends_label": "Expires 2026-12-15",
                        "url": "https://www.sec.gov/Archives/edgar/data/1/t.htm",
                        "accession": "0001-26-000009",
                        "filed": "2026-10-01",
                        "one_number": "$20.00–$23.50",
                        "book": "ranked",
                        "research_only": True,
                    }
                ],
                "program_mentions": [{"ticker": "AAPL", "line": "Program $10.0 billion, 0.3% of market value."}],
            },
            generated_at="2026-10-18T00:00:00Z",
        )
        self.assertIn("buyback_events", [lane["id"] for lane in payload["lanes"]])
        ranked = [row for row in payload["rows"] if row["lane"] == "buyback_events"]
        self.assertEqual([row["ticker"] for row in ranked], ["TNDR"])
        self.assertTrue(ranked[0]["research_only"])
        self.assertEqual(ranked[0]["one_number"], "$20.00–$23.50")
        self.assertEqual(ranked[0]["accession"], "0001-26-000009")
        self.assertEqual(payload["buyback_mentions"][0]["ticker"], "AAPL")
        self.assertNotIn("AAPL", [row["ticker"] for row in payload["rows"]])

    def test_dashboard_renders_the_buyback_lane_and_the_ticker_cell(self):
        script = r"""
const fs = require('fs');
global.window = global;
eval(fs.readFileSync('dashboard/special-situations-viz.js', 'utf8'));
eval(fs.readFileSync('dashboard/buyback-viz.js', 'utf8'));
const desk = SpecialSituationsViz.render({
  generated_at: '2026-10-18T00:00:00Z',
  definition: 'Ends.',
  lanes: [{id: 'buyback_events', label: 'Buyback events'}],
  counts: {ranked: {buyback_events: 1}},
  rows: [{
    id: 'ss:1', lane: 'buyback_events', lanes: ['buyback_events'], book: 'ranked',
    ticker: 'TNDR', company: 'Tender Co', what: 'Issuer tender.',
    ends: '2026-12-15', ends_label: 'Expires 2026-12-15',
    one_number: '$20.00–$23.50', research_only: true,
    evidence_url: 'https://www.sec.gov/Archives/edgar/data/1/t.htm', evidence_label: 'SEC filing',
    next: 'Read the filing.'
  }],
  discovery: [], history: [],
  buyback_mentions: [{ticker: 'AAPL', line: 'Program $10.0 billion, 0.3% of market value.'}]
}, {lane: 'buyback_events'});
const cell = BuybackViz.renderHoldingsCell({
  buyback: {grade: 'B', retired_since_peak_pct: 41.2, buyback_yield_pct: 3.4, pace: 'steady'}
}, (v) => String(v));
const detail = BuybackViz.renderDetail({
  buyback: {grade: 'B', retired_since_peak_pct: 41.2, buyback_yield_pct: 3.4, pace: 'issuing_again', change_5y_pct: -30, change_1y_pct: 9.7, as_of: '2026-02-01', repurchase_tag: 'PaymentsForRepurchaseOfEquity'}
}, (v) => String(v));
const fundCell = BuybackViz.renderHoldingsCell({
  buyback: {non_operating: true, retired_since_peak_pct: 18.3, pace: null, grade: null}
}, (v) => String(v));
const fundDetail = BuybackViz.renderDetail({
  buyback: {non_operating: true, retired_since_peak_pct: 18.3, pace: null, grade: null, as_of: '2026-09-30'}
}, (v) => String(v));
const short = {buyback_issuance_signals: [{ticker: 'ISS', company: 'Issuer', change_1y_pct: 9.7, change_5y_pct: -30, grade: 'C'}]};
process.stdout.write(JSON.stringify({desk, cell, detail, fundCell, fundDetail, hasIssuing: true, signals: short.buyback_issuance_signals.length}));
"""
        proc = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertIn("Buyback events · 1", out["desk"])
        self.assertIn("Ordinary programs", out["desk"])
        self.assertIn("AAPL", out["desk"])
        self.assertIn("$20.00–$23.50", out["desk"])
        self.assertIn("Research only", out["desk"])
        self.assertIn("41% retired", out["cell"])
        self.assertIn("steady", out["cell"])
        self.assertIn("3.4% yield", out["cell"])
        self.assertIn("issuing again", out["detail"])
        self.assertIn("not a return per year", out["detail"])
        self.assertIn("PaymentsForRepurchaseOfEquity", out["detail"])
        self.assertIn("not dilution", out["fundCell"])
        self.assertIn("Creation and redemption", out["fundDetail"])
        self.assertNotIn("issuing again", out["fundDetail"])


class WorkflowTests(unittest.TestCase):
    def test_monday_job_is_wired(self):
        text = (ROOT / ".github/workflows/data-pipeline.yml").read_text(encoding="utf-8")
        self.assertIn("buyback-radar:", text)
        self.assertIn("needs.decide.outputs.buyback_radar == 'true'", text)
        self.assertIn("python -u _system/scripts/build_buyback_radar.py", text)
        self.assertIn("buyback-radar, world-model", text)


if __name__ == "__main__":
    unittest.main()
