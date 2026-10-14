"""The ``separation_register`` falsifier adapter reads the append-only register.

Two typed metrics: ``separation_completed`` (did the register say completed by
the target date) and ``separation_flow_window_elapsed`` (is today past the
latest flow row's window_end). Both read ``_system/data/separations/*.jsonl``
through ``separation_common`` and never estimate anything.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import falsifier_evidence_adapters as adapters  # noqa: E402

REPO_DEFINITIONS = SCRIPTS.parent / "research" / "metric_definitions.json"
SID = "sep:test-parent-spin-2026"


def _registry_row(version: int, status: str, recorded_at: str, settlement: str | None) -> dict:
    return {
        "separation_id": SID, "version": version, "recorded_at": recorded_at, "kind": "split_off",
        "market": "US", "parent_ticker": "PRNT", "parent_cik": "0000000001", "spinco_ticker": "SPIN",
        "spinco_cik": None, "spinco_name": "SpinCo Inc.", "status": status, "lifecycle": "active",
        "dates": {"expiration": "2026-11-20", "settlement": settlement},
        "terms": {"exchange": {"discount_pct": 7.0, "upper_limit_ratio": 8.0}},
        "sources": [{"form": "SC TO-I", "accession": "0001-26-000001", "filed": "2026-10-20"}],
        "notes": "",
    }


def _flow_row(flow_id: str, run_date: str, side: str, window_end: str | None) -> dict:
    return {
        "flow_id": flow_id, "separation_id": SID, "run_date": run_date, "model_version": "separation-flow-v1",
        "side": side, "ticker": "SPIN" if side == "spinco" else "PRNT", "status": "ok", "reason": None,
        "window_start": "2026-11-23", "window_end": window_end, "legs": [],
        "research_only": True, "in_base_irr": False, "authority": "none",
    }


def _spec(metric_id: str, *, measurement_end: str = "2026-12-31", side: str | None = None,
          separation_id: str | None = SID, unit: str = "indicator") -> dict:
    plan = {
        "metric_definition_id": metric_id, "metric_definition_version": "1.0",
        "source_adapter": "separation_register", "fiscal_period": "EVENT",
        "observation_type": "instant", "duration_basis": "event",
        "canonical_unit": "indicator", "expected_publication_date": measurement_end,
        "accepted_forms": ["SC TO-I", "8-K"], "maximum_source_lag_days": 30,
        "historical_replay": {"status": "passed", "evidence_ref": "fixture:separation-register"},
    }
    if side:
        plan["side"] = side
    spec = {
        "spec_schema_version": "3.0", "spec_id": f"{metric_id}-test", "unit": unit,
        "measurement_period_end": measurement_end, "observable_after": measurement_end,
        "resolution_deadline": "2027-03-31", "observation_plan": plan,
    }
    if separation_id:
        spec["separation_id"] = separation_id
    return spec


class SeparationRegisterAdapterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        target = self.root / "_system/research/metric_definitions.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(REPO_DEFINITIONS.read_bytes())
        (self.root / "_system/data/separations").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def write_jsonl(self, name: str, rows: list[dict]) -> None:
        path = self.root / "_system/data/separations" / name
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    # ---------------------------------------------------- definitions
    def test_repo_definitions_register_both_metrics_on_the_adapter(self):
        definitions = adapters.metric_definitions(self.root)
        for metric_id in ("separation_completed", "separation_flow_window_elapsed"):
            with self.subTest(metric=metric_id):
                definition = definitions[metric_id]
                self.assertEqual(definition["source_adapters"], ["separation_register"])
                self.assertEqual(definition["canonical_unit"], "indicator")
                self.assertEqual(definition["version"], "1.0")
        self.assertIn("separation_register", adapters.BASE_SUPPORTED_ADAPTERS)

    def test_preflight_accepts_the_frozen_plan(self):
        check = adapters.preflight_spec("PRNT", _spec("separation_completed"), self.root)
        self.assertTrue(check["ok"], check)
        self.assertEqual(check["adapter"], "separation_register")

    # ------------------------------------------------ separation_completed
    def test_completed_by_target_date_resolves_to_one_with_register_provenance(self):
        self.write_jsonl("separation_registry.jsonl", [_registry_row(1, "offer_open", "2026-10-20T00:00:00Z", None)])
        self.write_jsonl("separation_amendments.jsonl", [_registry_row(2, "completed", "2026-11-25T00:00:00Z", "2026-11-24")])
        result = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2026, 11, 26))
        self.assertIsNone(result["blocker_reason"], result)
        self.assertEqual(result["value"], 1)
        self.assertEqual(result["as_of"], "2026-11-24")
        self.assertEqual(result["unit"], "indicator")
        self.assertTrue(result["evidence_ref"].endswith(f"separation_registry.jsonl#{SID}@v2"))
        self.assertEqual(result["raw_observation"]["version"], 2)

    def test_not_completed_once_target_date_passed_resolves_to_zero(self):
        self.write_jsonl("separation_registry.jsonl", [_registry_row(1, "offer_open", "2026-10-20T00:00:00Z", None)])
        result = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2027, 1, 5))
        self.assertIsNone(result["blocker_reason"], result)
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["as_of"], "2026-12-31")

    def test_not_completed_before_target_date_blocks_instead_of_guessing(self):
        self.write_jsonl("separation_registry.jsonl", [_registry_row(1, "offer_open", "2026-10-20T00:00:00Z", None)])
        result = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2026, 11, 1))
        self.assertEqual(result["blocker_reason"], "target_date_not_reached")
        self.assertIsNone(result["value"])

    def test_completion_after_target_date_counts_as_zero(self):
        self.write_jsonl("separation_registry.jsonl", [_registry_row(1, "offer_open", "2026-10-20T00:00:00Z", None)])
        self.write_jsonl("separation_amendments.jsonl", [_registry_row(2, "completed", "2027-01-10T00:00:00Z", "2027-01-09")])
        result = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2027, 1, 12))
        self.assertEqual(result["value"], 0)

    def test_register_versions_recorded_after_as_of_are_invisible(self):
        # The point-in-time rule: a later amendment cannot leak into an earlier read.
        self.write_jsonl("separation_registry.jsonl", [_registry_row(1, "offer_open", "2026-10-20T00:00:00Z", None)])
        self.write_jsonl("separation_amendments.jsonl", [_registry_row(2, "completed", "2026-11-25T00:00:00Z", "2026-11-24")])
        result = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2026, 11, 20))
        self.assertEqual(result["blocker_reason"], "target_date_not_reached")
        self.assertEqual(result["details"]["status"], "offer_open")
        only_later = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2026, 10, 1))
        self.assertEqual(only_later["blocker_reason"], "register_version_recorded_after_as_of")

    def test_unknown_separation_and_missing_id_are_typed_blockers(self):
        self.write_jsonl("separation_registry.jsonl", [_registry_row(1, "offer_open", "2026-10-20T00:00:00Z", None)])
        missing = adapters.resolve_spec("PRNT", _spec("separation_completed", separation_id="sep:nobody"), self.root, date(2027, 1, 5))
        self.assertEqual(missing["blocker_reason"], "separation_not_in_register")
        no_id = adapters.resolve_spec("PRNT", _spec("separation_completed", separation_id=None), self.root, date(2027, 1, 5))
        self.assertEqual(no_id["blocker_reason"], "separation_id_missing")
        self.assertEqual(no_id["adapter"], "separation_register")

    def test_empty_register_directory_blocks_rather_than_raising(self):
        result = adapters.resolve_spec("PRNT", _spec("separation_completed"), self.root, date(2027, 1, 5))
        self.assertEqual(result["blocker_reason"], "separation_not_in_register")

    # --------------------------------------- separation_flow_window_elapsed
    def test_window_elapsed_reads_the_latest_run_only(self):
        self.write_jsonl("separation_flows.jsonl", [
            _flow_row("sepflow:a", "2026-11-01", "spinco", "2026-12-05"),
            _flow_row("sepflow:b", "2026-11-15", "spinco", "2026-12-20"),  # latest run extends the window
        ])
        spec = _spec("separation_flow_window_elapsed", side="spinco")
        before = adapters.resolve_spec("SPIN", spec, self.root, date(2026, 12, 10))
        self.assertIsNone(before["blocker_reason"], before)
        self.assertEqual(before["value"], 0)
        self.assertTrue(before["evidence_ref"].endswith("separation_flows.jsonl#sepflow:b"))
        on_the_day = adapters.resolve_spec("SPIN", spec, self.root, date(2026, 12, 20))
        self.assertEqual(on_the_day["value"], 0)
        after = adapters.resolve_spec("SPIN", spec, self.root, date(2026, 12, 21))
        self.assertEqual(after["value"], 1)
        self.assertEqual(after["as_of"], "2026-12-21")

    def test_side_filter_and_future_runs_are_respected(self):
        self.write_jsonl("separation_flows.jsonl", [
            _flow_row("sepflow:parent", "2026-11-01", "parent", "2026-11-30"),
            _flow_row("sepflow:spin", "2026-11-01", "spinco", "2026-12-20"),
            _flow_row("sepflow:future", "2027-01-01", "spinco", "2027-02-01"),  # run_date after as_of
        ])
        parent = adapters.resolve_spec("PRNT", _spec("separation_flow_window_elapsed", side="parent"), self.root, date(2026, 12, 10))
        self.assertEqual(parent["value"], 1)
        spin = adapters.resolve_spec("SPIN", _spec("separation_flow_window_elapsed", side="spinco"), self.root, date(2026, 12, 10))
        self.assertEqual(spin["value"], 0)
        self.assertEqual(spin["raw_observation"]["flow_id"], "sepflow:spin")

    def test_missing_flows_and_missing_window_end_are_typed_blockers(self):
        none = adapters.resolve_spec("SPIN", _spec("separation_flow_window_elapsed"), self.root, date(2026, 12, 10))
        self.assertEqual(none["blocker_reason"], "flow_rows_absent")
        self.write_jsonl("separation_flows.jsonl", [_flow_row("sepflow:na", "2026-11-01", "spinco", None)])
        na = adapters.resolve_spec("SPIN", _spec("separation_flow_window_elapsed"), self.root, date(2026, 12, 10))
        self.assertEqual(na["blocker_reason"], "window_end_missing")
        self.assertEqual(na["details"]["flow_id"], "sepflow:na")

    # -------------------------------------------------------- guard rails
    def test_adapter_refuses_a_metric_it_does_not_define(self):
        definitions = json.loads((self.root / "_system/research/metric_definitions.json").read_text(encoding="utf-8"))
        definitions["definitions"]["some_other_metric"] = {
            "version": "1.0", "canonical_unit": "indicator", "source_adapters": ["separation_register"],
        }
        (self.root / "_system/research/metric_definitions.json").write_text(json.dumps(definitions), encoding="utf-8")
        result = adapters.resolve_spec("PRNT", _spec("some_other_metric"), self.root, date(2027, 1, 5))
        self.assertEqual(result["blocker_reason"], "metric_not_supported_by_adapter:some_other_metric")

    def test_unit_mismatch_is_caught_in_preflight(self):
        result = adapters.resolve_spec("PRNT", _spec("separation_completed", unit="percent"), self.root, date(2027, 1, 5))
        self.assertEqual(result["blocker_reason"], "unit_mismatch")


if __name__ == "__main__":
    unittest.main()
