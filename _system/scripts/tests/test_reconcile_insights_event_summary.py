"""Publishing metadata repair must preserve retained events and source evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
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


def _publishable(retained: int, generated_at: str = "2026-10-20T09:30:36Z") -> dict:
    return {
        "generated_at": generated_at,
        "event_count": retained,
        "letter_count": 12865,
        "source_health": {
            "filing_facts": {"status": "ok"},
            "superinvestor_letters": {"items": 12865},
            "videos": {"items": 1, "generated_at": "old-video"},
        },
        "provenance": {
            "event_triage_summary": {
                "retained_event_count": retained,
                "raw_event_count": 800,
                "signal": retained,
                "context": 0,
                "noise": 0,
            }
        },
        "shards": {"events": "data/insights/events.json", "podcast_episodes": "data/insights/podcast_episodes/"},
    }


class MediaPublishAndRebase(unittest.TestCase):
    def test_media_patch_keeps_corpus_and_derives_count_from_destination_events(self):
        stale = _publishable(1539, "2026-10-15T09:13:13Z")
        stale["source_health"]["podcasts"] = {"items": 999, "generated_at": "2026-10-20T11:07:59Z"}
        stale["source_health"]["videos"] = {"items": 98, "generated_at": "lane-video"}
        stale["shards"]["podcasts"] = "data/insights/podcasts.json"
        destination = _publishable(10)
        events = [
            {"observed_at": "2026-01-01", "tier": "signal", "feed_eligible": True},
            {"observed_at": "2026-01-02", "tier": "context", "feed_eligible": True},
        ]
        merged = module.apply_media_fields(destination, stale, videos=False, podcasts=True)
        result = module.reconciled_manifest(merged, events)
        summary = result["provenance"]["event_triage_summary"]
        self.assertEqual(summary["retained_event_count"], 2)
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["letter_count"], 12865)
        self.assertEqual(result["source_health"]["podcasts"]["items"], 999)
        self.assertEqual(result["source_health"]["videos"]["generated_at"], "old-video")
        self.assertEqual(result["generated_at"], "2026-10-20T09:30:36Z")
        self.assertEqual(summary["raw_event_count"], 800)
        self.assertIn("podcast_episodes", result["shards"])

    def test_prepare_refuses_a_stub_and_does_not_trust_a_stale_count(self):
        with self.assertRaises(ValueError):
            module.prepare_published_manifest(
                {"generated_at": "2026-10-19T16:50:44Z", "shards": {}},
                [{"observed_at": "2026-01-01"}],
                lambda manifest: manifest.update(video_count=1),
            )
        result = module.prepare_published_manifest(
            _publishable(1539),
            [{"observed_at": "2026-01-01", "tier": "noise", "feed_eligible": False}],
            lambda manifest: manifest.update(video_count=98),
        )
        self.assertEqual(result["provenance"]["event_triage_summary"]["retained_event_count"], 1)
        self.assertEqual(result["video_count"], 98)
        self.assertEqual(result["letter_count"], 12865)

    def test_richer_manifest_prefers_corpus_over_the_download_stub(self):
        stub = {"generated_at": "2026-10-19T16:50:44Z", "shards": {"videos": "data/insights/videos.json"}}
        rich = _publishable(1530)
        self.assertEqual(module.richer_manifest(stub, rich)["letter_count"], 12865)
        self.assertFalse(module.is_publishable_manifest(stub))

    def test_rebase_keeps_rows_and_derives_the_retained_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
                subprocess.run(["git", "config", key, value], cwd=repo, check=True)
            insight = repo / "dashboard" / "data" / "insights"
            insight.mkdir(parents=True)

            def write(name: str, doc: dict) -> None:
                (insight / name).write_text(json.dumps(doc), encoding="utf-8")

            def commit(message: str) -> None:
                subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)

            events = {"events": [
                {"observed_at": "2026-01-01", "tier": "signal", "feed_eligible": True},
                {"observed_at": "2026-01-02", "tier": "context", "feed_eligible": True},
            ]}
            podcasts = {"podcast_index": [{"id": "a"}, {"id": "b"}], "podcast_by_show": {"show": [{}]}}
            write("manifest.json", _publishable(1539, "2026-10-15T09:13:13Z"))
            write("events.json", events)
            write("podcasts.json", podcasts)
            commit("base")
            write("manifest.json", {"generated_at": "2026-10-19T16:50:44Z", "shards": {"videos": "data/insights/videos.json"}})
            write("podcasts.json", {"podcast_index": None, "podcast_by_show": None, "generated_at": "2026-10-19T16:50:44Z"})
            commit("download stub")
            subprocess.run(["git", "checkout", "-qb", "main-moved", "HEAD~1"], cwd=repo, check=True)
            moved = _publishable(1530, "2026-10-20T09:30:36Z")
            moved["source_health"]["podcasts"] = {"items": 4670}
            write("manifest.json", moved)
            write("podcasts.json", {"podcast_index": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "podcast_by_show": {"show": [{}]}})
            commit("intake")
            subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
            rebase = subprocess.run(["git", "rebase", "main-moved"], cwd=repo, capture_output=True, text=True)
            self.assertNotEqual(rebase.returncode, 0, rebase.stderr)
            self.assertEqual(module.resolve_rebase_conflicts(repo), 2)
            manifest = json.loads((insight / "manifest.json").read_text(encoding="utf-8"))
            repaired = json.loads((insight / "podcasts.json").read_text(encoding="utf-8"))
            summary = manifest["provenance"]["event_triage_summary"]
            self.assertEqual(summary["retained_event_count"], 2)
            self.assertEqual(manifest["event_count"], 2)
            self.assertEqual(manifest["letter_count"], 12865)
            self.assertEqual(len(repaired["podcast_index"]), 3)
            self.assertIn("filing_facts", manifest["source_health"])
            unmerged = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=repo, capture_output=True, text=True, check=True,
            )
            self.assertEqual(unmerged.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
