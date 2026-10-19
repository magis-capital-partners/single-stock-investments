"""Publishing metadata repair must preserve retained events and source evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("reconcile_summary", ROOT / "_system/scripts/reconcile_insights_event_summary.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReconcileEventSummary(unittest.TestCase):
    def test_counts_follow_current_events_while_unrelated_provenance_stays_intact(self):
        manifest = {"event_count": 99, "generated_at": "old", "source_health": {"videos": "unchanged"},
                    "provenance": {"other": "keep", "event_triage_summary": {"retained_event_count": 99, "raw_event_count": 800}}}
        original = copy.deepcopy(manifest)
        events = [{"observed_at": "2026-01-01", "tier": "signal", "feed_eligible": True},
                  {"observed_at": "2026-01-03", "tier": "context", "feed_eligible": True, "evidence_status": "missing"},
                  {"observed_at": "2026-01-02", "tier": "signal", "feed_eligible": False, "triage_verdict": "human_review"}]
        result = module.reconciled_manifest(manifest, events)
        summary = result["provenance"]["event_triage_summary"]
        self.assertEqual((summary["signal"], summary["context"], summary["noise"]), (1, 1, 1))
        self.assertEqual(summary["retained_event_count"], 3)
        self.assertEqual(summary["history_end"], "2026-01-03")
        self.assertEqual(summary["raw_event_count"], 800)
        self.assertEqual(result["source_health"], manifest["source_health"])
        self.assertEqual(manifest, original)

    def test_file_repair_is_idempotent_and_does_not_rewrite_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / "insights"; folder.mkdir()
            manifest = folder / "manifest.json"; events = folder / "events.json"
            manifest.write_text('{"event_count":99}', encoding="utf-8")
            events.write_text('{"events":[]}', encoding="utf-8")
            before = events.read_bytes()
            self.assertTrue(module.reconcile(root))
            result = manifest.read_bytes()
            self.assertFalse(module.reconcile(root))
            self.assertEqual(manifest.read_bytes(), result)
            self.assertEqual(events.read_bytes(), before)

    def test_missing_or_malformed_events_fail_without_replacing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / "insights"; folder.mkdir()
            manifest = folder / "manifest.json"; events = folder / "events.json"
            manifest.write_text('{"event_count":99}', encoding="utf-8")
            before = manifest.read_bytes()
            for payload in ({}, {"events": [None]}):
                events.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    module.reconcile(root)
                self.assertEqual(manifest.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
