"""TCI contract semantics, point-in-time ingestion and alert replay tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from buy_zones import build_buy_zones, load_config
from tci_return_bridge import build_bridge, incremental_roic, irr_attribution
from tci_return_bridge import contract_schedule_patch
from refresh_core_compounders import publish_brief, refresh, transitions
from operating_kpis import model
from operating_kpis.cme import parse_prnewswire_release, parse_rpc
from operating_kpis.filings import parse_filing
from operating_kpis.ice import parse_ice_xlsx
from operating_kpis.mirror import normalize
from marketdata.valuation_history import archive_valuation_on_write

CONFIG = load_config()
MODEL = {"ticker": "CME", "as_of": "2026-06-03", "method": "full",
         "inputs": {"price": 252.65, "fcf_per_share": 11.4, "price_source": "Stooq 2026-06-03", "fcf_source": "Existing FY2025 normalized estimate"},
         "scenarios": {"bear": {"growth_y1_5": .03, "growth_y6_10": .02, "exit_pfcf_y10": 18},
                       "base": {"growth_y1_5": .07, "growth_y6_10": .05, "exit_pfcf_y10": 22},
                       "bull": {"growth_y1_5": .09, "growth_y6_10": .06, "exit_pfcf_y10": 26}}}


def put(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class ReturnMathTests(unittest.TestCase):
    def test_cme_exact_reconciliation_and_ten_year_sensitivity(self):
        bridge = build_bridge(MODEL)
        base = bridge["scenarios"]["base"]
        self.assertAlmostEqual(base["exact_irr_pct"], 11.194752469, places=7)
        self.assertAlmostEqual(base["approximate_return_pct"] + base["reconciliation_gap_pp"], base["exact_irr_pct"])
        self.assertAlmostEqual(bridge["sensitivity_10yr"]["base"]["exact_irr_pct"], 10.831718167, places=7)
        self.assertEqual(set(bridge["forward_cashflow_schedule"]), {"low", "base", "high"})
        self.assertIsNone(base["growth_components"]["buyback_accretion_pct"])

    def test_stub_nav_and_missing_cash_do_not_receive_a_return(self):
        for method in ["price_stub", "yield_curve", "owner_earnings_reinvestment_dcf"]:
            value = deepcopy(MODEL)
            value["method"] = method
            self.assertEqual(build_bridge(value)["scenarios"], {})
        value = deepcopy(MODEL)
        value["inputs"]["fcf_per_share"] = None
        self.assertEqual(build_bridge(value)["status"], "gap")

    def test_attribution_telescopes(self):
        changed = deepcopy(MODEL)
        changed["inputs"].update(price=305.71, fcf_per_share=12)
        changed["scenarios"]["base"].update(growth_y1_5=.08, exit_pfcf_y10=21)
        result = irr_attribution(MODEL, changed)
        expected = build_bridge(changed)["scenarios"]["base"]["exact_irr_pct"] - build_bridge(MODEL)["scenarios"]["base"]["exact_irr_pct"]
        self.assertAlmostEqual(result["total_delta_pp"], expected)
        self.assertAlmostEqual(result["residual_pp"], 0)

    def test_incremental_roic_withholds_nonpositive_capital(self):
        self.assertEqual(incremental_roic(10, 15, 100, 120), 25)
        self.assertIsNone(incremental_roic(10, 15, 100, 90))

    def test_schedule_generator_retains_evidence_gates(self):
        from test_generalized_valuation_system import component_fixture
        from marvin_valuation import compute_valuation
        fixture = component_fixture()
        fixture.update(ticker="CME", method="full", scenarios=deepcopy(MODEL["scenarios"]))
        fixture["inputs"].update(MODEL["inputs"])
        component = fixture["component_valuation"]["components"][0]["valuation"]
        component["method"] = "dated_forward_cashflow_schedule_per_share"
        component["calculation_proof"]["method_id"] = "dated_forward_cashflow_schedule_per_share"
        component["calculation_proof"]["output_basis"] = "forward_cashflow_schedule"
        fixture["valuation_methodology"] = {**contract_schedule_patch(build_bridge(fixture)), "required_return_pct": 12}
        result = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(result["valuation"]["output_basis"], "forward_cashflow_schedule")
        self.assertEqual(result["status"], "evidence_blocked")
        self.assertTrue(any("moat-impairment" in gap for gap in result["evidence"]["blockers"]))


class ZoneTests(unittest.TestCase):
    def pricing(self):
        return {"authority": "valuation_contract", "proof_status": "decision_grade", "model_level": "stock_specific",
                "output_basis": "forward_cashflow_schedule", "entry_price_status": "available", "price": 176.41,
                "entry_prices_by_hurdle_and_case": {"base": {"12pct": 241.71, "15pct": 205.83, "18pct": 176.41}, "low": {"8pct": 210.48}}}

    def test_hurdles_boundaries_and_bear_constraint(self):
        pricing = self.pricing()
        zones = build_buy_zones(pricing)
        self.assertEqual([z["price"] for z in zones["zones"]], [241.71, 205.83, 176.41])
        self.assertEqual(zones["deepest_active_zone"], "zone_3")
        pricing["entry_prices_by_hurdle_and_case"]["low"]["8pct"] = 150
        self.assertEqual(build_buy_zones(pricing)["zones"][2]["price"], 150)

    def test_present_values_legacy_and_blocked_models_publish_no_zones(self):
        for field, value in [("output_basis", "present_value_today"), ("authority", None), ("model_level", "screening_grade"), ("proof_status", "evidence_blocked")]:
            pricing = self.pricing()
            pricing[field] = value
            self.assertEqual(build_buy_zones(pricing)["zones"], [])

    def test_royalty_is_only_corroborating(self):
        zones = build_buy_zones(self.pricing(), royalty_signal={"active": False, "as_of": "2026-10-23", "source": "mirror"}, as_of="2026-10-23")
        self.assertEqual(zones["royalty_corroboration"]["status"], "disagreement")
        self.assertEqual(zones["zones"][2]["price"], 176.41)


class ObservationTests(unittest.TestCase):
    def point(self, period, value, kpi="adv_total"):
        return model.make_point(ticker="CME", kpi=kpi, period=period, value=value, unit="contracts_per_day",
                                source_url="https://issuer.test/release", doc="test", fetched_at="2026-10-23")

    def test_quarterly_annual_yoy_and_guidance(self):
        rows = [self.point("2025Q2", 10), self.point("2026Q2", 12),
                self.point("2025", 10, "geo_guidance_low"), self.point("2026", 12, "geo_guidance_low")]
        result = model.attach_yoy(rows)
        self.assertEqual(next(p for p in result if p["period"] == "2026Q2")["yoy"], .2)
        self.assertTrue(all(p["yoy"] is None for p in result if "guidance" in p["kpi"]))
        self.assertEqual(model.period_end("2026Q2").isoformat(), "2026-06-30")

    def test_monthly_and_quarterly_points_never_form_one_trend(self):
        from operating_kpis.trends import metric_from_points
        rows = [self.point("2026-07", 10), self.point("2026-08", 11), self.point("2026-09", 12), self.point("2026Q3", 11)]
        metric = metric_from_points(rows, evidence_ref="test")
        self.assertEqual(metric["latest_period"], "2026-09")
        self.assertEqual(metric["cadence"], "monthly")
        self.assertEqual(len(metric["points"]), 3)

    def test_partial_refresh_keeps_history_and_revisions(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(model, "STORE_DIR", Path(temp)):
            model.write_ticker_store("CME", [self.point("2026-08", 10)], sources=[], fetched_at="2026-09-01")
            model.write_ticker_store("CME", [self.point("2026-09", 12)], sources=[], fetched_at="2026-10-01")
            model.write_ticker_store("CME", [self.point("2026-09", 13)], sources=[], fetched_at="2026-10-23")
            data = model.load_ticker_store("CME")
            self.assertEqual(len(data["points"]), 2)
            self.assertEqual(len(data["revisions"]), 1)
            with self.assertRaises(model.LayoutError):
                model.write_ticker_store("CME", [self.point("2026-10", float("nan"))], sources=[], fetched_at="now")

    def test_mirror_alias_and_share_units(self):
        row = {"ticker": "MIAX", "kpi": "options_rpc3m", "value": .098, "unit": "usd_per_contract", "period": "2026-09", "source_url": "https://issuer.test", "fetched_at": "2026-10-20"}
        point = normalize(row, mirror_as_of="2026-10-23", source_hash="abc")
        self.assertEqual(point["kpi"], "options_rpc")
        self.assertEqual(point["claim_type"], "inference")
        row.update(kpi="options_share", value=.167, unit="share", yoy=-.009)
        point = normalize(row, mirror_as_of="2026-10-23", source_hash="abc")
        self.assertAlmostEqual(point["value"], 16.7)
        self.assertAlmostEqual(point["yoy"], -.9)

    def test_cme_monthly_quarterly_disambiguation_and_rpc(self):
        # Synthetic layout fixture using values in the dated source mirror.
        html = '''<meta name='date' content="2026-10-02"><section class="release-body">today reported September with 31.8 million contracts, up 22% year-over-year. September 2026 monthly highlights across asset classes Interest Rate ADV increased 22% to 16.2 million contracts Q3 2026 quarterly highlights Interest Rate ADV increased 99% to 99 million contracts</section>'''
        points = parse_prnewswire_release(html, source_url="https://issuer.test/monthly", fetched_at="2026-10-23")
        self.assertEqual(next(p for p in points if p["kpi"] == "adv_total")["value"], 31_800_000)
        self.assertEqual(next(p for p in points if p["kpi"] == "adv_interest_rate")["value"], 16_200_000)
        points = parse_rpc("third-quarter 2026 total average rate per contract was $0.679.", source_url="https://issuer.test/q3", filing={}, fetched_at="2026-10-23")
        self.assertEqual(points[0]["period"], "2026Q3")

    def test_filing_guidance_keeps_annual_period(self):
        text = "Financial Highlights - Q2 2026 132,405 GEOs sold, +18% 122,205 Net GEOs sold, +20% Guidance 2026 guidance 510,000 to 570,000 GEOs"
        points = parse_filing("FNV", text, filing={"accessionNumber": "test", "filingDate": "2026-08-01"}, source_url="https://issuer.test", fetched_at="2026-10-23")
        self.assertEqual(next(p for p in points if p["kpi"] == "geos_sold")["period"], "2026Q2")
        self.assertEqual(next(p for p in points if p["kpi"] == "geo_guidance_low")["period"], "2026")

    def test_ice_workbook_sections_units_and_required_rows(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("operating_fixture_helpers", Path(__file__).parent / "tests/test_operating_kpis.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = module._xlsx([
            ["", "", "July 2026", "August 2026", "September 2026"],
            ["Monthly ADV"], ["TOTAL ENERGY", "", "5000", "5100", "5469"],
            ["TOTAL FUTURES & OPTIONS", "", "11000", "12000", "12785"],
            ["Rate per Contract"], ["Energy", "", "1.2", "1.3", "1.4"],
            ["TOTAL FINANCIALS", "", ".5", ".6", ".7"],
        ], sheet_name="Derivs 2026")
        points = parse_ice_xlsx(raw, source_url="https://issuer.test/stats.xlsx", doc="stats", fetched_at="2026-10-23")
        latest = {(p["kpi"], p["period"]): p for p in points}
        self.assertEqual(latest[("adv_energy", "2026-09")]["value"], 5_469_000)
        self.assertEqual(latest[("rpc3m_energy", "2026-09")]["value"], 1.4)


class MonitoringTests(unittest.TestCase):
    def test_unknown_quote_never_clears_zone_and_changes_deduplicate(self):
        old = {"conditions": {"buy_zone:zone_1": True}, "model": {}, "base_irr_pct": None}
        events, state = transitions("CME", old, {"conditions": {"buy_zone:zone_1": None}, "model": {}, "base_irr_pct": None}, threshold=2, as_of="2026-10-23")
        self.assertFalse(events)
        self.assertTrue(state["conditions"]["buy_zone:zone_1"])
        current = {"conditions": {"buy_zone:zone_1": False}, "model": {}, "base_irr_pct": None}
        events, state = transitions("CME", state, current, threshold=2, as_of="2026-10-23")
        self.assertEqual(len(events), 1)
        self.assertFalse(transitions("CME", state, current, threshold=2, as_of="2026-10-23")[0])

    def test_brief_overflow_and_crash_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events = [{"event_id": str(i).zfill(8), "ticker": "CME", "lane": "model_stale", "condition": "model_stale", "before": False, "after": True, "as_of": "2026-10-23"} for i in range(15)]
            state = {"pending_events": deepcopy(events)}
            publish_brief(root, state, "2026-10-23")
            self.assertEqual(len(state["pending_events"]), 3)
            # Replay the state from before acknowledgement: no duplicate brief.
            state = {"pending_events": deepcopy(events)}
            publish_brief(root, state, "2026-10-23")
            self.assertEqual(len(state["pending_events"]), 3)
            brief = json.loads((root / "_system/data/desk_briefs/fundamentals/2026-10-23.json").read_text())
            from jsonschema import Draft202012Validator
            schema = json.loads((Path(__file__).resolve().parents[1] / "data/desk_briefs/schema.json").read_text())
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(brief)

    def test_refresh_stages_proposals_without_mutating_underwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            put(root, "_system/reference/core_compounders.json", CONFIG)
            put(root, "_system/portfolio/registry.json", {"holdings": {"CME": {"classification": {}}}})
            put(root, "CME/research/valuation.json", MODEL)
            put(root, "CME/research/valuation_contract.json", {"status": "evidence_blocked"})
            before = (root / "CME/research/valuation.json").read_bytes()
            state = refresh(root=root, as_of="2026-10-23", write=True, propose=True, tickers=["CME"])
            self.assertFalse(state["events_this_run"])
            self.assertEqual((root / "CME/research/valuation.json").read_bytes(), before)
            refresh(root=root, as_of="2026-10-23", write=True, propose=True, tickers=["CME"])
            self.assertEqual(len((root / "_system/data/agent_proposals/inbox.jsonl").read_text().splitlines()), 1)

    def test_same_day_history_is_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            ticker_dir = Path(temp)
            first = archive_valuation_on_write(ticker_dir, MODEL)
            changed = deepcopy(MODEL)
            changed["inputs"]["price"] = 300
            second = archive_valuation_on_write(ticker_dir, changed)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text())["inputs"]["price"], 252.65)


if __name__ == "__main__":
    unittest.main()
