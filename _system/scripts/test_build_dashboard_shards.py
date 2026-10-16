from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_dashboard_shards as bds  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = ROOT / "dashboard" / "index.html"


def _cv() -> dict:
    """A component_valuation shaped like the real payload."""
    return {
        "status": "provisional",
        "total_equity_value_per_share": {"low": 1, "base": 2, "high": 3},
        "upside_downside_pct": {"base": 0.25},
        "market_price_per_share": 1.75,
        "material_component_count": 2,
        # the detail-pane schedule -- the expensive half
        "economic_value": {"segments": [{"name": "x", "value": 1}] * 20},
        "components": [{"id": "a", "method": "net_asset_value"}] * 12,
        "decision_rule": "a long prose decision rule " * 8,
        "review_status": "committee_open",
        "review_open_count": 3,
    }


class PublicationGuardTests(unittest.TestCase):
    def test_direct_shard_writer_rejects_sparse_collapse_before_any_write(self):
        rows = [
            {
                "ticker": f"T{i}", "pdf_count": 10, "readme": True,
                "research_dir": True, "sec_filings": 20,
                "dossier": {"status": "reviewed"},
                "valuation_decision": {"status": "decision_grade"},
            }
            for i in range(60)
        ]
        healthy = {"tickers": rows, "summary": {"ticker_count": 60, "total_pdfs": 600}}
        for field in ("infra", "research", "valuation"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                data_dir = Path(folder)
                bds.write_shards(healthy, None, data_dir)
                before = {p.relative_to(data_dir): p.read_bytes() for p in data_dir.rglob("*.json")}
                thinned = copy.deepcopy(healthy)
                if field == "infra":
                    for row in thinned["tickers"]:
                        row.update(pdf_count=0, readme=False, sec_filings=0)
                    thinned["summary"]["total_pdfs"] = 7
                elif field == "research":
                    for row in thinned["tickers"]:
                        row["dossier"] = None
                else:
                    for row in thinned["tickers"]:
                        row["valuation_decision"] = {"status": "missing"}
                # An ignored monolith may already contain the new, broken build.
                (data_dir / "dashboard_data.json").write_text(json.dumps(thinned), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    bds.write_shards(thinned, {"record_count": 0}, data_dir)
                after = {p.relative_to(data_dir): p.read_bytes() for p in data_dir.rglob("*.json")
                         if p.name != "dashboard_data.json"}
                self.assertEqual(before, after)


class SlimComponentValuationTests(unittest.TestCase):
    def test_detail_only_schedule_is_dropped(self):
        slim = bds._slim_component_valuation(_cv())
        for field in ("economic_value", "components", "decision_rule",
                      "review_status", "review_open_count"):
            self.assertNotIn(field, slim, f"{field} still ships in core.json")

    def test_table_keys_survive(self):
        """These four are what the holdings table reads before any ticker is
        opened. Dropping one renders the value-gap column blank."""
        slim = bds._slim_component_valuation(_cv())
        for field in ("status", "total_equity_value_per_share",
                      "upside_downside_pct", "market_price_per_share"):
            self.assertIn(field, slim, f"{field} is boot-critical and was dropped")

    def test_slim_actually_shrinks_the_row(self):
        full = _cv()
        slim = bds._slim_component_valuation(full)
        self.assertLess(len(json.dumps(slim)), len(json.dumps(full)) / 2)

    def test_every_component_valuation_sort_key_survives_the_slim(self):
        """The binding constraint, asserted against the SPA itself.

        index.html sorts the holdings table on `component_valuation.<field>`
        paths. Sorting happens before any shard loads, so a sort key whose field
        this function drops silently sorts every row as equal. Adding such a
        sort key must fail here rather than in the browser.
        """
        if not INDEX_HTML.exists():                      # pragma: no cover
            self.skipTest("dashboard/index.html not present")
        html = INDEX_HTML.read_text(encoding="utf-8", errors="ignore")
        referenced = set(re.findall(r"component_valuation\.([A-Za-z0-9_]+)", html))
        self.assertTrue(referenced, "expected index.html to sort on component_valuation")
        dropped = referenced & set(bds._COMPONENT_VALUATION_DETAIL_ONLY)
        self.assertEqual(
            dropped, set(),
            f"index.html sorts on component_valuation.{sorted(dropped)}"
            " but the core slim drops it -- the column would sort every row as equal",
        )


class SlimTickerRowTests(unittest.TestCase):
    def test_row_slim_applies_component_valuation(self):
        row = {"ticker": "T", "component_valuation": _cv()}
        slim = bds.slim_ticker_row(row)
        self.assertIn("component_valuation", slim)
        self.assertNotIn("economic_value", slim["component_valuation"])
        self.assertIn("upside_downside_pct", slim["component_valuation"])

    def test_row_without_component_valuation_is_untouched(self):
        slim = bds.slim_ticker_row({"ticker": "T"})
        self.assertNotIn("component_valuation", slim)

    def test_valuation_governance_detail_is_lazy_loaded(self):
        tier = {
            "tier": 1,
            "tier_id": "tier_1",
            "label": "Active underwriting",
            "assignment_reasons": [{"code": "paper_position"}] * 8,
            "promotion_gates": ["long policy text"] * 4,
        }
        decision = {
            "status": "decision_grade",
            "model_level": "stock_specific",
            "return_publishable": True,
            "value_per_share": {"low": 90, "base": 110, "high": 130},
            "margin_of_safety_pct": {"base": 9.1},
            "forward_return_at_price_pct": {"base": 12.0},
            "decision_eligibility": {"reason": "full detail only"},
            "legacy_audit": {"reason": "audit only"},
            "forward_cashflow_schedule": [{"date": "2030-12-31", "amount": 130}],
            "universe_tier": tier,
        }
        slim = bds.slim_ticker_row({
            "ticker": "T",
            "valuation_decision": decision,
            "valuation_tier": tier,
        })
        self.assertEqual(slim["valuation_tier"], {
            "tier": 1, "tier_id": "tier_1", "label": "Active underwriting",
        })
        self.assertEqual(slim["valuation_decision"]["forward_return_at_price_pct"], {"base": 12.0})
        self.assertNotIn("decision_eligibility", slim["valuation_decision"])
        self.assertNotIn("legacy_audit", slim["valuation_decision"])
        self.assertNotIn("forward_cashflow_schedule", slim["valuation_decision"])
        self.assertNotIn("assignment_reasons", slim["valuation_decision"]["universe_tier"])

    def test_every_valuation_decision_sort_key_survives_the_slim(self):
        if not INDEX_HTML.exists():  # pragma: no cover
            self.skipTest("dashboard/index.html not present")
        html = INDEX_HTML.read_text(encoding="utf-8", errors="ignore")
        referenced = set(re.findall(r"valuation_decision\??\.([A-Za-z0-9_]+)", html))
        self.assertTrue(referenced, "expected index.html valuation decision fields")
        self.assertEqual(
            referenced - set(bds._VALUATION_DECISION_CORE_FIELDS),
            {"annualized_return_at_price_pct", "proof_complete_pct", "unvalued_component_count"},
            "A new boot-time decision field was added without updating the core slim contract",
        )

    def test_next_calendar_event_stays_off_the_core_row(self):
        slim = bds.slim_ticker_row({
            "ticker": "T",
            "index_membership": {
                "status": "in",
                "next_calendar_event": {"date": "2026-11-01", "name": "rebalance"},
            },
        })
        self.assertEqual(slim["index_membership"]["status"], "in")
        self.assertNotIn("next_calendar_event", slim["index_membership"])

    def test_release_standalone_embeds_drops_the_monolith_blobs(self):
        payload = {
            "document_catalog": {"generated_at": "t", "documents": [{}, {}]},
            "kpi_trends": {"generated_at": "t", "inflection_count": 3},
            "activist_feed": {"generated_at": "t"},
            "tickers": [],
        }
        removed = bds.release_standalone_embeds(payload)
        self.assertIn("document_catalog", removed)
        self.assertNotIn("document_catalog", payload)
        self.assertNotIn("kpi_trends", payload)
        self.assertNotIn("activist_feed", payload)
        self.assertEqual(payload["document_catalog_ref"]["document_count"], 2)
        self.assertEqual(payload["kpi_trends_ref"]["inflection_count"], 3)

    def test_two_phase_watch_stays_off_core_rows(self):
        row = {"ticker": "INV", "two_phase_watch": {"as_of": "2026-08-26", "hits": [{}] * 8}}
        slim = bds.slim_ticker_row(row)
        self.assertNotIn("two_phase_watch", slim)
        self.assertIn("two_phase_watch", bds.DETAIL_ONLY_FIELDS)

    def test_index_html_has_two_phase_section(self):
        if not INDEX_HTML.exists():  # pragma: no cover
            self.skipTest("dashboard/index.html not present")
        html = INDEX_HTML.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("renderTwoPhaseWatch", html)
        self.assertIn("Two-phase cooling watch", html)
        self.assertIn('id="two-phase-watch"', html)


if __name__ == "__main__":
    unittest.main()
