"""Contracts for the Mac Mini always-on media lane."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]  # workspace root
sys.path.insert(0, str(SCRIPTS))


class MediaLaneResourcesTests(unittest.TestCase):
    def test_default_threads_never_take_all_cores(self):
        import media_lane_resources as r

        with mock.patch.object(r, "cpu_count", return_value=8):
            self.assertEqual(r.default_whisper_threads(cap=4), 4)
        with mock.patch.object(r, "cpu_count", return_value=4):
            self.assertEqual(r.default_whisper_threads(cap=4), 2)
        with mock.patch.object(r, "cpu_count", return_value=2):
            self.assertEqual(r.default_whisper_threads(cap=4), 1)

    def test_file_lock_is_exclusive(self):
        import media_lane_resources as r

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lane.lock"
            a = r.FileLock(path)
            b = r.FileLock(path)
            self.assertTrue(a.acquire(blocking=False))
            self.assertFalse(b.acquire(blocking=False))
            a.release()
            self.assertTrue(b.acquire(blocking=False))
            b.release()

    def test_available_mb_returns_int_or_none(self):
        import media_lane_resources as r

        free = r.available_mb()
        self.assertTrue(free is None or (isinstance(free, int) and free >= 0))


class MediaLaneSupervisorTests(unittest.TestCase):
    def test_supervisor_sequences_whisper_before_analysis(self):
        text = (SCRIPTS / "media_lane_supervisor.py").read_text(encoding="utf-8")
        whisper_at = text.index("phase=whisper")
        youtube_at = text.index("phase=youtube")
        reader_at = text.index("phase=reader-summary")
        video_at = text.index("phase=video-analysis")
        podcast_at = text.index("phase=podcast-analysis")
        self.assertLess(whisper_at, youtube_at)
        self.assertLess(youtube_at, reader_at)
        self.assertLess(reader_at, video_at)
        self.assertLess(video_at, podcast_at)

    def test_whisper_reconciles_and_rotates_with_analysis(self):
        text = (SCRIPTS / "media_lane_supervisor.py").read_text(encoding="utf-8")
        self.assertIn("--reconcile-whisper-orphans", text)
        self.assertIn("whisper_turn", text)
        # Reconcile runs before the pending check in the cycle.
        self.assertLess(
            text.index("reconcile_whisper_orphans()"),
            text.index("pending = whisper_pending()"),
        )

    def test_no_second_media_supervisor(self):
        names = {p.name for p in SCRIPTS.glob("*media*supervisor*")}
        self.assertEqual(names, {"media_lane_supervisor.py", "test_media_lane_supervisor.py"})

    def test_install_script_and_plist_exist(self):
        install = SCRIPTS / "install_mac_media_lane.sh"
        plist = SCRIPTS / "deploy" / "mac" / "com.magis.ssi.media-lane.plist"
        self.assertTrue(install.exists())
        self.assertTrue(plist.exists())
        body = install.read_text(encoding="utf-8")
        self.assertIn("launchctl", body)
        self.assertIn("media_lane_supervisor.py", body)
        self.assertIn('uname -s)" != "Darwin"', body)
        # Soft resource posture is in the plist, not left to chance.
        plist_text = plist.read_text(encoding="utf-8")
        self.assertIn("SoftResourceLimits", plist_text)
        self.assertIn("<integer>15</integer>", plist_text)
        self.assertIn("WHISPER_THREADS", plist_text)
        self.assertIn("qwen-gpu", plist_text)
        self.assertIn("distil-large-v3", plist_text)

    def test_status_snapshot_shape(self):
        import media_lane_supervisor as mls

        with mock.patch.object(mls, "whisper_pending", return_value=3), \
             mock.patch.object(mls, "reader_summary_remaining", return_value=4), \
             mock.patch.object(mls, "analysis_remaining", side_effect=[1, 2]), \
             mock.patch.object(mls, "available_mb", return_value=4096):
            snap = mls.status_snapshot()
        self.assertEqual(snap["whisper_pending"], 3)
        self.assertEqual(snap["reader_summary_remaining"], 4)
        self.assertIn("defaults", snap)
        self.assertLessEqual(snap["defaults"]["whisper_threads"], 4)

    def test_llm_discover_parses_unix_cmdline(self):
        import llm_local

        found = llm_local._parse_llama_cmdline(
            "/path/llama-server --port 54321 --api-key secret-key --model x"
        )
        self.assertEqual(found, ("http://127.0.0.1:54321/v1", "secret-key"))
        self.assertIsNone(llm_local._parse_llama_cmdline("unrelated process"))

    def test_analysis_phase_does_not_wait_on_whisper(self):
        """Sequencing already guarantees Whisper is idle; do not double-gate."""
        text = (SCRIPTS / "media_lane_supervisor.py").read_text(encoding="utf-8")
        self.assertIn("--share-with-whisper", text)
        self.assertIn('--max-wait-minutes", "0"', text)


class PodcastAgentDocsMacLane(unittest.TestCase):
    def test_podcast_agent_mentions_mac_lane(self):
        doc = (ROOT / "_system" / "agents" / "PODCAST.md").read_text(encoding="utf-8")
        self.assertIn("Mac Mini", doc)
        self.assertIn("install_mac_media_lane.sh", doc)
        self.assertIn("media_lane_supervisor.py", doc)


if __name__ == "__main__":
    unittest.main()
