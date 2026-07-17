import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import investment_committee_pipeline as icp
from darwin import run_ls_algo_valuation_pipeline as pipeline


class LsAlgoValuationPipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = pipeline.ROOT
        self._old_icp_root = icp.ROOT
        pipeline.ROOT = Path(self._tmp.name)
        icp.ROOT = Path(self._tmp.name)

    def tearDown(self):
        pipeline.ROOT = self._old_root
        icp.ROOT = self._old_icp_root
        self._tmp.cleanup()

    def _write(self, relative: str, payload: dict) -> None:
        path = pipeline.ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_price_gate_fires_at_or_below_15pct_entry(self):
        self._write(
            "AAA/research/pricing_analysis.json",
            {"price": 50.0, "primary_entry_price_15pct_base": 55.0},
        )
        triggers = pipeline.gate_triggers("AAA", set())
        self.assertEqual(len(triggers), 1)
        self.assertIn("15% hurdle entry", triggers[0])

    def test_price_gate_silent_above_entry(self):
        self._write(
            "AAA/research/pricing_analysis.json",
            {"price": 60.0, "primary_entry_price_15pct_base": 55.0},
        )
        self.assertEqual(pipeline.gate_triggers("AAA", set()), [])

    def test_live_position_and_flag_triggers(self):
        self._write(
            "BBB/research/committee_trigger.json",
            {"status": "open", "reason": "guidance withdrawn"},
        )
        triggers = pipeline.gate_triggers("BBB", {"BBB"})
        self.assertEqual(len(triggers), 2)
        self.assertTrue(any("live ls-algo book position" in t for t in triggers))
        self.assertTrue(any("guidance withdrawn" in t for t in triggers))

    def test_closed_flag_does_not_trigger(self):
        self._write("CCC/research/committee_trigger.json", {"status": "resolved"})
        self.assertEqual(pipeline.gate_triggers("CCC", set()), [])

    def test_gates_never_initialize_evidence_blocked_names(self):
        self._write(
            "DDD/research/valuation_workbench.json",
            {"decision": {"status": "evidence_blocked"}, "committee": {"status": "not_started"}},
        )
        self._write(
            "DDD/research/pricing_analysis.json",
            {"price": 10.0, "primary_entry_price_15pct_base": 20.0},
        )
        gates = pipeline.stage_gates(["DDD"], "2026-07-17", dry_run=True)
        self.assertEqual(gates["initiated"], [])
        self.assertEqual(len(gates["evidence_blocked_with_trigger"]), 1)
        self.assertEqual(gates["evidence_blocked_with_trigger"][0]["ticker"], "DDD")

    def test_gates_skip_busy_committee(self):
        self._write(
            "EEE/research/valuation_workbench.json",
            {
                "decision": {"status": "decision_grade"},
                "committee": {"status": "owner_decision_pending"},
            },
        )
        self._write(
            "EEE/research/pricing_analysis.json",
            {"price": 10.0, "primary_entry_price_15pct_base": 20.0},
        )
        gates = pipeline.stage_gates(["EEE"], "2026-07-17", dry_run=True)
        self.assertEqual(gates["initiated"], [])
        self.assertEqual(len(gates["blocked"]), 1)
        self.assertIn("owner_decision_pending", gates["blocked"][0]["reason"])

    def test_decision_grade_without_trigger_rests(self):
        self._write(
            "FFF/research/valuation_workbench.json",
            {"decision": {"status": "decision_grade"}, "committee": {"status": "not_started"}},
        )
        gates = pipeline.stage_gates(["FFF"], "2026-07-17", dry_run=True)
        self.assertEqual(gates["initiated"], [])
        self.assertEqual(gates["decision_grade_resting"], ["FFF"])

    def test_dry_run_gate_pass_reports_without_freezing(self):
        self._write(
            "GGG/research/valuation_workbench.json",
            {"decision": {"status": "decision_grade"}, "committee": {"status": "not_started"}},
        )
        self._write(
            "GGG/research/pricing_analysis.json",
            {"price": 10.0, "primary_entry_price_15pct_base": 20.0},
        )
        gates = pipeline.stage_gates(["GGG"], "2026-07-17", dry_run=True)
        self.assertEqual(len(gates["initiated"]), 1)
        self.assertIn("dry run", gates["initiated"][0]["note"])
        self.assertFalse((pipeline.ROOT / "GGG" / "research" / "committee_work").exists())

    def test_live_gate_pass_freezes_packet_with_route_personas(self):
        research = pipeline.ROOT / "HHH" / "research"
        research.mkdir(parents=True)
        (research / "valuation.json").write_text(
            json.dumps(
                {
                    "valuation_method_route": {
                        "primary_personas": ["hk", "stahl"],
                        "cross_check_personas": ["klarman_asset_value", "marks_credit_cycle"],
                        "silent_personas": [
                            "hohn",
                            "pabrai",
                            "buffett_weschler",
                            "greenblatt",
                            "marathon_capital_cycle",
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        (research / "thesis.md").write_text("thesis", encoding="utf-8")
        (research / "deep_dive_2026-07-01.md").write_text("dive", encoding="utf-8")
        self._write(
            "HHH/research/valuation_workbench.json",
            {"decision": {"status": "decision_grade"}, "committee": {"status": "not_started"}},
        )
        self._write(
            "HHH/research/pricing_analysis.json",
            {"price": 10.0, "primary_entry_price_15pct_base": 20.0},
        )
        gates = pipeline.stage_gates(["HHH"], "2026-07-17", dry_run=False)
        self.assertEqual(len(gates["initiated"]), 1)
        manifest = json.loads(
            (research / "committee_work" / "2026-07-17" / "manifest.json").read_text(encoding="utf-8")
        )
        personas = [row["persona"] for row in manifest["selected_raters"]]
        self.assertEqual(personas, ["hk", "klarman_asset_value", "marks_credit_cycle"])
        self.assertEqual(manifest["stage"], "round_one_open")

    def test_live_gate_pass_without_evidence_is_blocked_not_fatal(self):
        research = pipeline.ROOT / "III" / "research"
        research.mkdir(parents=True)
        (research / "valuation.json").write_text("{}", encoding="utf-8")
        self._write(
            "III/research/valuation_workbench.json",
            {"decision": {"status": "decision_grade"}, "committee": {"status": "not_started"}},
        )
        self._write(
            "III/research/pricing_analysis.json",
            {"price": 10.0, "primary_entry_price_15pct_base": 20.0},
        )
        gates = pipeline.stage_gates(["III"], "2026-07-17", dry_run=False)
        self.assertEqual(gates["initiated"], [])
        self.assertEqual(len(gates["blocked"]), 1)
        self.assertIn("evidence artifacts", gates["blocked"][0]["reason"])

    def test_queue_review_written_only_when_actionable(self):
        empty = {
            "live_underlyings": 0,
            "initiated": [],
            "blocked": [],
            "evidence_blocked_with_trigger": [],
            "decision_grade_resting": ["FFF"],
        }
        self.assertIsNone(pipeline.write_ic_queue_review("2026-07-17", empty, dry_run=False))
        actionable = {
            "live_underlyings": 3,
            "initiated": [
                {
                    "ticker": "GGG",
                    "triggers": ["material live ls-algo book position"],
                    "note": "packet frozen; round one open",
                }
            ],
            "blocked": [],
            "evidence_blocked_with_trigger": [],
            "decision_grade_resting": [],
        }
        path = pipeline.write_ic_queue_review("2026-07-17", actionable, dry_run=False)
        self.assertIsNotNone(path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("GGG", text)
        self.assertIn("owner_decision_pending", text)


if __name__ == "__main__":
    unittest.main()
