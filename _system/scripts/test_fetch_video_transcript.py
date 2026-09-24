#!/usr/bin/env python3
"""Unit tests for the caption fetch lane: no audio path, quota discipline, gates."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import youtube_api  # noqa: E402
import fetch_video_transcript as fvt  # noqa: E402

FETCHER_SRC = (SCRIPTS / "fetch_video_transcript.py").read_text(encoding="utf-8")
API_SRC = (SCRIPTS / "youtube_api.py").read_text(encoding="utf-8")


class NoAudioPathTests(unittest.TestCase):
    """The video lane fetches captions and nothing else.

    yt-dlp is installed on this host. The guard against audio download is that
    no call site may exist -- same shape as the reqGlobalCancel ban in the
    trading code, where the test IS the enforcement mechanism.
    """

    FORBIDDEN = [
        "yt_dlp", "yt-dlp", "youtube_dl", "bestaudio", "--extract-audio",
        "ffmpeg", "WhisperModel", "faster_whisper", "whisper_transcribe",
    ]

    def test_fetcher_has_no_audio_download_call_site(self):
        for token in self.FORBIDDEN:
            # The docstring names yt-dlp to explain the ban; code must not.
            code = "\n".join(
                line for line in FETCHER_SRC.splitlines()
                if not line.strip().startswith("#")
            )
            body = code.split('"""', 2)[-1] if code.count('"""') >= 2 else code
            self.assertNotIn(token, body, "audio path leaked into the fetcher: " + token)

    def test_no_audio_url_field_is_persisted(self):
        self.assertNotIn("audio_url", FETCHER_SRC)


class QuotaDisciplineTests(unittest.TestCase):
    def test_search_endpoint_is_refused(self):
        # 100 units per call would burn the free tier in 100 iterations.
        with self.assertRaises(youtube_api.YouTubeAPIError) as ctx:
            youtube_api.call("search", {"q": "value investing"})
        self.assertIn("search.list", str(ctx.exception))

    def test_unknown_endpoint_is_refused_rather_than_guessed(self):
        with self.assertRaises(youtube_api.YouTubeAPIError):
            youtube_api.call("subscriptions", {})

    def test_documented_costs_are_one_unit(self):
        for endpoint in ("videos", "playlistItems", "channels"):
            self.assertEqual(youtube_api.UNIT_COST[endpoint], 1)

    def test_free_tier_constant_matches_google(self):
        self.assertEqual(youtube_api.FREE_TIER_DAILY_UNITS, 10_000)

    def test_budget_leaves_headroom_under_free_tier(self):
        self.assertLess(youtube_api.DEFAULT_BUDGET, youtube_api.FREE_TIER_DAILY_UNITS)

    def test_api_source_contains_no_search_call(self):
        self.assertNotIn('call("search"', API_SRC)


class DurationParsingTests(unittest.TestCase):
    def test_parses_minutes_and_seconds(self):
        self.assertEqual(youtube_api.parse_duration("PT10M12S"), 612)

    def test_parses_hours(self):
        self.assertEqual(youtube_api.parse_duration("PT1H30M5S"), 5405)

    def test_parses_seconds_only(self):
        self.assertEqual(youtube_api.parse_duration("PT45S"), 45)

    def test_missing_duration_is_none_not_zero(self):
        # None must not be confused with a zero-length video by the gate.
        self.assertIsNone(youtube_api.parse_duration(None))
        self.assertIsNone(youtube_api.parse_duration("garbage"))


class QualityGateTests(unittest.TestCase):
    def test_a_real_sohn_pitch_passes(self):
        # Measured 2026-09-01: 10,359 chars over 612s. The podcast 25,000-byte
        # floor would have rejected this; that is why it does not transfer.
        self.assertEqual(fvt.quality_gate("x" * 10359, 612), [])

    def test_short_clip_is_rejected_on_duration(self):
        reasons = fvt.quality_gate("x" * 9000, 200)
        self.assertTrue(any(r.startswith("too_short_duration") for r in reasons))

    def test_thin_transcript_is_rejected_on_length(self):
        reasons = fvt.quality_gate("x" * 500, 3600)
        self.assertTrue(any(r.startswith("transcript_too_short") for r in reasons))

    def test_partial_caption_track_is_caught_by_coverage(self):
        # 7,000 chars across a 60-minute video is ~117 cpm: the track exists and
        # does not cover the video. Length alone would have passed it.
        reasons = fvt.quality_gate("x" * 7000, 3600)
        self.assertTrue(any(r.startswith("caption_coverage") for r in reasons))
        self.assertFalse(any(r.startswith("transcript_too_short") for r in reasons))

    def test_normal_speech_density_passes_coverage(self):
        # 45 minutes at ~800 chars/min.
        self.assertEqual(fvt.quality_gate("x" * 36000, 2700), [])

    def test_unknown_duration_still_checks_length(self):
        self.assertEqual(fvt.quality_gate("x" * 30000, None), [])
        self.assertTrue(fvt.quality_gate("x" * 100, None))


class PathAndSlugTests(unittest.TestCase):
    def test_slug_is_filesystem_safe(self):
        slug = fvt.slugify("Mohnish Pabrai's Interview: Value & Risk / 2026")
        self.assertRegex(slug, r"^[a-z0-9-]+$")

    def test_slug_survives_a_title_that_is_all_punctuation(self):
        self.assertEqual(fvt.slugify("!!!???"), "video")

    def test_unicode_title_does_not_crash_the_slug(self):
        # The U+2060 class of failure, at the filename layer this time.
        self.assertRegex(fvt.slugify("Chris Voss on “No”⁠-Oriented"), r"^[a-z0-9-]+$")


class GateProgressionTests(unittest.TestCase):
    def test_fetched_meta_is_not_yet_relevance_judged(self):
        # Phase 2 ends at transcript_fetched; admission is Phase 3's decision.
        self.assertIn('"gate": "transcript_fetched"', FETCHER_SRC)
        self.assertIn('"relevance": None', FETCHER_SRC)


class CorpusShapeTests(unittest.TestCase):
    """Read whatever this lane has actually written, if anything."""

    def setUp(self) -> None:
        from vault_paths import videos_root
        self.lib = videos_root() / "library"
        if not self.lib.is_dir():
            self.skipTest("no video corpus on this host yet")
        self.metas = list(self.lib.rglob("*.meta.json"))
        if not self.metas:
            self.skipTest("no video meta files yet")

    def test_every_transcript_has_a_meta(self):
        # One direction only. Meta is written first, so a meta without a
        # transcript is an interrupted run that the next pass retries; a
        # transcript without a meta would be a corpus we cannot describe.
        metas = {p.with_suffix("").with_suffix("") for p in self.metas}
        for txt in self.lib.rglob("*.txt"):
            self.assertIn(txt.with_suffix(""), metas, "orphan transcript: " + txt.name)

    def test_no_meta_records_an_audio_source(self):
        for m in self.metas:
            doc = json.loads(m.read_text(encoding="utf-8"))
            self.assertEqual(doc.get("transcript_source"), "youtube_captions")
            self.assertNotIn("audio_url", doc)

    def test_transcript_paths_are_portable(self):
        for m in self.metas:
            doc = json.loads(m.read_text(encoding="utf-8"))
            self.assertFalse(Path(doc.get("transcript_path") or "").is_absolute(), m.name)

    def test_every_stored_transcript_passes_its_own_gate(self):
        for m in self.metas:
            doc = json.loads(m.read_text(encoding="utf-8"))
            reasons = fvt.quality_gate(
                "x" * int(doc.get("transcript_chars") or 0), doc.get("duration_seconds"))
            self.assertEqual(reasons, [], m.name + " stored despite " + str(reasons))


class TransientFailureTests(unittest.TestCase):
    """A rate limit must not be recorded as a bad video.

    The podcast lane buried 696 good episodes on 2026-08-20 by charging a DNS
    outage to each item's retry budget. IpBlocked is the same shape: YouTube
    returns it for every request once the IP is limited, so it says nothing
    about the video named in the call.
    """

    def test_rate_limit_is_classified_transient(self):
        for status in ["error:IpBlocked", "error:RequestBlocked", "error:TooManyRequests"]:
            self.assertTrue(fvt.is_transient(status), status)

    def test_a_real_video_failure_is_not_transient(self):
        for status in ["error:NoTranscriptFound", "error:VideoUnavailable", "no_captions"]:
            self.assertFalse(fvt.is_transient(status), status)

    def test_run_aborts_rather_than_marching_through_the_backlog(self):
        # Continuing past a rate limit converts one environmental failure into
        # a backlog of false ones.
        self.assertIn("aborted_on", FETCHER_SRC)
        self.assertIn("break", FETCHER_SRC)

    def test_attempts_are_only_spent_on_real_failures(self):
        self.assertIn("if not is_transient(result.get(\"status\", \"\")):", FETCHER_SRC)


class ThresholdCalibrationTests(unittest.TestCase):
    def test_a_seven_minute_sohn_pitch_survives(self):
        # "Ryan Packard pitches AppLovin at Sohn 2026" is 448s. An 8-minute
        # floor dropped it; that is why the floor is 300s.
        self.assertEqual(fvt.quality_gate("x" * 6000, 448), [])

    def test_char_floor_does_not_reimpose_a_duration_floor(self):
        # At a normal 800 chars/min a 6,000-char floor would silently require
        # 7.5 minutes. 4,000 keeps the real floor at ~5 minutes.
        self.assertLessEqual(fvt.MIN_TRANSCRIPT_CHARS / 800.0 * 60, fvt.MIN_DURATION_SECONDS + 1)


class PermanentFailureTests(unittest.TestCase):
    """Some failures never resolve by waiting; retrying them wastes a paced slot."""

    def test_age_restriction_is_permanent(self):
        self.assertTrue(fvt.is_permanent("error:AgeRestricted"))

    def test_permanent_and_transient_are_disjoint(self):
        for marker in fvt.PERMANENT_ERROR_MARKERS:
            self.assertFalse(fvt.is_transient("error:" + marker), marker)
        for marker in fvt.TRANSIENT_ERROR_MARKERS:
            self.assertFalse(fvt.is_permanent("error:" + marker), marker)

    def test_a_missing_transcript_is_neither(self):
        self.assertFalse(fvt.is_permanent("no_captions"))
        self.assertFalse(fvt.is_transient("no_captions"))


# The scheduled run after the backlog below was written: 05:17 ET, 2026-09-25.
NOW = datetime(2026, 9, 25, 9, 18, 10, tzinfo=timezone.utc)
NO_CAPTIONS = {"status": "no_captions", "detail": "TranscriptsDisabled"}
IP_BLOCKED = {"status": "error:IpBlocked", "detail": "YouTube is blocking requests from your IP"}


def _row(video_id: str, title: str = "", published: str = "2023-12-20T17:00:00+00:00") -> dict:
    return {"video_id": video_id, "title": title or "Video " + video_id,
            "published": published, "gate": "pending_transcript",
            "url": "https://www.youtube.com/watch?v=" + video_id}


def _captions(chars: int) -> dict:
    return {"status": "ok", "text": "x" * chars, "segments": [], "language": "en",
            "is_generated": True, "track_count": 1, "manual_available": False}


class _Killed(BaseException):
    """Stands in for youtube_lane's wall-clock kill: nothing after it runs."""


class CaptionLaneHarness(unittest.TestCase):
    """A temp vault with every network edge scripted.

    The Data API, the caption fetch and the pacing ledger are replaced and the
    clock is frozen, so a test can count exactly which videos a pass would have
    spent a real, rate-limited fetch on.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.now = NOW
        self.durations: dict[str, int] = {}
        self.answers: dict[str, list] = {}
        self.fetched: list[str] = []
        self.api_down = False
        self.rate = mock.MagicMock()
        self.rate.check.return_value = {"allowed": True, "wait_seconds": 0, "reason": "ok"}
        self.rate.record_block.return_value = {"blocked_until": "2026-09-25T09:48:10Z"}
        self.clock = mock.MagicMock()  # replaces the `time` module: sleeps are recorded, not slept
        self.out = io.StringIO()
        for patcher in (
            mock.patch.object(fvt, "videos_root", return_value=self.root),
            mock.patch.object(fvt, "rate", self.rate),
            mock.patch.object(fvt, "time", self.clock),
            mock.patch.object(fvt, "_dt_now", side_effect=lambda: self.now),
            mock.patch.object(fvt, "fetch_captions", side_effect=self._fetch),
            mock.patch.object(fvt.youtube_api, "videos", side_effect=self._api),
            mock.patch("sys.stdout", self.out),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _api(self, ids: list[str]) -> dict:
        if self.api_down:
            raise fvt.youtube_api.YouTubeAPIError("quotaExceeded")
        return {vid: {"contentDetails": {"duration": "PT{0}S".format(self.durations[vid])},
                      "snippet": {}}
                for vid in ids if vid in self.durations}

    def _fetch(self, video_id: str) -> dict:
        self.fetched.append(video_id)
        queue = self.answers.get(video_id) or [_captions(9000)]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, type) and issubclass(answer, BaseException):
            raise answer()
        return dict(answer)

    def discover(self, *rows: dict) -> None:
        (self.root / "discovery_latest.json").write_text(
            json.dumps({"videos": list(rows)}), encoding="utf-8")

    def seed(self, items: dict) -> None:
        (self.root / "caption_backlog.json").write_text(
            json.dumps({"items": items}), encoding="utf-8")

    def backlog(self) -> dict:
        path = self.root / "caption_backlog.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8")).get("items") or {}

    def store(self, row: dict) -> None:
        """Put a transcript and its meta on disk, as a finished fetch leaves them."""
        txt, meta = fvt.video_paths(row["video_id"], row["title"], row["published"])
        meta.write_text("{}\n", encoding="utf-8")
        txt.write_text("x\n", encoding="utf-8")

    def run_pass(self, **kwargs) -> dict:
        kwargs.setdefault("sleep_seconds", 0)
        kwargs.setdefault("wait_for_slot", True)
        return fvt.run(**kwargs)

    def assert_never_slept(self) -> None:
        naps = [c.args for c in self.clock.sleep.call_args_list if c.args != (0,)]
        self.assertEqual(naps, [], "the stage waited on the pacing budget")


class SettledVerdictTests(CaptionLaneHarness):
    """A verdict a fetch paid for is kept, not bought again on every pass."""

    def test_a_transcript_too_short_is_fetched_once(self):
        # RVCapital "Holiday 2023": 2,412 chars against the 4,000 floor. It was
        # re-fetched on every pass from 2026-09-01 and stood at 30 attempts.
        self.discover(_row("MRwajxeMfWg", "Holiday 2023"))
        self.durations["MRwajxeMfWg"] = 330
        self.answers["MRwajxeMfWg"] = [_captions(2412)]

        first = self.run_pass()
        second = self.run_pass()

        self.assertEqual(self.fetched, ["MRwajxeMfWg"])
        state = self.backlog()["MRwajxeMfWg"]
        self.assertEqual(state["status"], "rejected")
        self.assertEqual(state["reasons"], ["transcript_too_short_2412c"])
        self.assertEqual(first["fetchable"], 0)
        self.assertEqual((second["settled"], second["fetchable"]), (1, 0))

    def test_a_partial_caption_track_is_settled_too(self):
        # ~117 chars/minute over an hour: the track exists and does not cover it.
        self.discover(_row("partial001"))
        self.durations["partial001"] = 3600
        self.answers["partial001"] = [_captions(7000)]
        self.run_pass()
        self.run_pass()
        self.assertEqual(self.fetched, ["partial001"])
        self.assertTrue(self.backlog()["partial001"]["reasons"][0].startswith("caption_coverage"))

    def test_no_captions_on_an_old_video_is_fetched_once(self):
        # Four RVCapital holiday cards reached 46 attempts each this way.
        self.discover(_row("Mh5YiZGNAuI", "Holiday 2025", "2026-01-05T16:26:31+00:00"))
        self.durations["Mh5YiZGNAuI"] = 330
        self.answers["Mh5YiZGNAuI"] = [NO_CAPTIONS]
        self.run_pass()
        second = self.run_pass()
        self.assertEqual(self.fetched, ["Mh5YiZGNAuI"])
        # Still exactly the status video_whisper_backfill queues from.
        self.assertEqual(self.backlog()["Mh5YiZGNAuI"]["status"], "no_captions")
        self.assertEqual(second["settled"], 1)

    def test_refetch_still_overrides_a_settled_verdict(self):
        self.discover(_row("MRwajxeMfWg", "Holiday 2023"))
        self.durations["MRwajxeMfWg"] = 330
        self.seed({"MRwajxeMfWg": {"attempts": 30, "status": "rejected",
                                   "reasons": ["transcript_too_short_2412c"]}})
        self.run_pass(only_video="MRwajxeMfWg", refetch=True, wait_for_slot=False)
        self.assertEqual(self.fetched, ["MRwajxeMfWg"])


class FreshUploadTests(CaptionLaneHarness):
    """TranscriptsDisabled on a new upload can mean "not generated yet".

    youtube-transcript-api raises it whenever the player response has no
    caption tracks, which is also what a video looks like before YouTube's
    speech recognition has run over it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.born = NOW - timedelta(hours=1)
        self.discover(_row("freshpitch1", "A new Sohn pitch", self.born.isoformat()))
        self.durations["freshpitch1"] = 900

    def test_captions_that_appear_later_are_collected_on_one_more_look(self):
        self.answers["freshpitch1"] = [NO_CAPTIONS, _captions(12000)]
        first = self.run_pass()
        self.assertEqual(first["fetchable"], 0, "an unripe video must not hold the daemon open")
        waiting = self.run_pass()
        self.assertEqual(waiting["awaiting_captions"], 1)
        self.assertEqual(self.fetched, ["freshpitch1"])

        self.now = self.born + fvt.NO_CAPTIONS_GRACE + timedelta(minutes=1)
        self.run_pass()
        self.assertEqual(self.fetched, ["freshpitch1", "freshpitch1"])
        self.assertEqual(self.backlog()["freshpitch1"]["status"], "done")

    def test_a_second_no_captions_answer_is_final(self):
        self.answers["freshpitch1"] = [NO_CAPTIONS]
        self.run_pass()
        self.now = self.born + fvt.NO_CAPTIONS_GRACE + timedelta(hours=1)
        self.run_pass()
        self.now += timedelta(days=30)
        final = self.run_pass()
        self.assertEqual(self.fetched, ["freshpitch1", "freshpitch1"])
        self.assertEqual(final["settled"], 1)


class DurationRejectTests(CaptionLaneHarness):
    """A duration verdict cost no fetch, so only a new measurement reopens it."""

    def setUp(self) -> None:
        super().setUp()
        self.discover(_row("MFupgvHqKtQ", "Holiday 2021"))
        self.seed({"MFupgvHqKtQ": {"attempts": 0, "status": "rejected",
                                   "reasons": ["too_short_duration"],
                                   "checked_at": "2026-09-23T13:48:54Z"}})

    def test_still_under_the_floor_is_left_alone(self):
        self.durations["MFupgvHqKtQ"] = 289
        stats = self.run_pass()
        self.assertEqual(self.fetched, [])
        self.assertEqual(stats["settled"], 1)
        self.assertEqual(self.backlog()["MFupgvHqKtQ"]["checked_at"], "2026-09-23T13:48:54Z")

    def test_a_lowered_floor_reopens_it(self):
        # The floor has moved before: 480s dropped a 7:28 Sohn pitch.
        self.durations["MFupgvHqKtQ"] = 289
        with mock.patch.object(fvt, "MIN_DURATION_SECONDS", 240):
            self.run_pass()
        self.assertEqual(self.fetched, ["MFupgvHqKtQ"])

    def test_the_data_api_being_down_does_not_reopen_it(self):
        # No duration is not a new measurement. Reading it as one would turn
        # every short clip in the backlog into a caption fetch.
        self.api_down = True
        stats = self.run_pass()
        self.assertEqual(self.fetched, [])
        self.assertEqual(stats["fetchable"], 0)


class BlocksAreNeverChargedTests(CaptionLaneHarness):
    """An IP block says nothing about the video: the 696-episode lesson."""

    def test_repeated_blocks_neither_spend_attempts_nor_settle_the_video(self):
        self.discover(_row("goodvid01"), _row("goodvid02"))
        self.durations.update({"goodvid01": 1200, "goodvid02": 1200})
        self.answers["goodvid01"] = [IP_BLOCKED]
        for _ in range(fvt.MAX_ATTEMPTS + 2):
            stats = self.run_pass()
            self.assertEqual(stats["aborted_on"], "error:IpBlocked")
            self.assertEqual(stats["fetchable"], 2)
        state = self.backlog()["goodvid01"]
        self.assertEqual((state["attempts"], state["status"]), (0, "pending"))
        # Each pass stops at the block rather than marching through the rest.
        self.assertNotIn("goodvid02", self.fetched)
        self.assertEqual(self.rate.record_block.call_count, fvt.MAX_ATTEMPTS + 2)

    def test_a_blocked_second_look_is_retried_not_settled(self):
        # First asked an hour after upload; the second look is now due.
        born = NOW - fvt.NO_CAPTIONS_GRACE - timedelta(hours=3)
        first_look = (born + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.discover(_row("freshpitch1", "A new Sohn pitch", born.isoformat()))
        self.durations["freshpitch1"] = 900
        self.seed({"freshpitch1": {"attempts": 1, "status": "no_captions",
                                   "detail": "TranscriptsDisabled",
                                   "last_attempt_at": first_look}})
        self.answers["freshpitch1"] = [IP_BLOCKED, _captions(12000)]
        blocked = self.run_pass()
        self.assertEqual(blocked["fetchable"], 1)
        self.assertEqual(self.backlog()["freshpitch1"]["attempts"], 1)
        self.run_pass()
        self.assertEqual(self.backlog()["freshpitch1"]["status"], "done")

    def test_the_daemon_does_not_mistake_a_blocked_pass_for_a_finished_one(self):
        self.discover(_row("goodvid01"))
        self.durations["goodvid01"] = 1200
        self.answers["goodvid01"] = [IP_BLOCKED, _captions(20000)]
        totals = fvt.daemon(max_hours=1, sleep_seconds=0)
        self.assertEqual((totals["passes"], totals["blocks"]), (2, 1))
        self.assertEqual(totals["stopped"], "backlog_empty")
        # Only the fetch that YouTube actually answered was charged.
        self.assertEqual(self.backlog()["goodvid01"]["attempts"], 1)


class PerVerdictPersistenceTests(CaptionLaneHarness):
    def test_a_killed_pass_keeps_the_verdicts_it_already_paid_for(self):
        # youtube_lane ends this stage with a wall-clock kill. The backlog used
        # to be written once, at the end of a pass, so a kill threw away every
        # verdict in it and the next run bought them again.
        self.discover(_row("shortcard1"), _row("nocaption1"), _row("cutshort01"))
        self.durations.update({"shortcard1": 420, "nocaption1": 420, "cutshort01": 420})
        self.answers.update({"shortcard1": [_captions(2412)], "nocaption1": [NO_CAPTIONS],
                             "cutshort01": [_Killed, _captions(9000)]})
        with self.assertRaises(_Killed):
            self.run_pass()
        on_disk = self.backlog()
        self.assertEqual(on_disk["shortcard1"]["status"], "rejected")
        self.assertEqual(on_disk["nocaption1"]["status"], "no_captions")

        self.run_pass()
        self.assertEqual(self.fetched, ["shortcard1", "nocaption1", "cutshort01", "cutshort01"])


class DaemonStopTests(CaptionLaneHarness):
    """The daemon stops when nothing is left to fetch, not when its budget runs out."""

    # Copied from research-vault/videos/caption_backlog.json after the
    # 2026-09-24 run, stale fields included: that run made 21 fetches in three
    # passes, stored nothing, and was killed at 65 minutes.
    BACKLOG = {
        "Mh5YiZGNAuI": {"attempts": 46, "status": "no_captions", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:33Z", "last_attempt_at": "2026-09-24T09:59:55Z", "detail": "TranscriptsDisabled"},  # noqa: E501
        "1KJeDRw2fes": {"attempts": 46, "status": "no_captions", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:33Z", "last_attempt_at": "2026-09-24T10:03:08Z", "detail": "TranscriptsDisabled"},  # noqa: E501
        "fJdY0qP7G3k": {"attempts": 46, "status": "no_captions", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:33Z", "last_attempt_at": "2026-09-24T10:06:19Z", "detail": "TranscriptsDisabled"},  # noqa: E501
        "zy8uHixLAJw": {"attempts": 46, "status": "no_captions", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:33Z", "last_attempt_at": "2026-09-24T10:08:53Z", "detail": "TranscriptsDisabled"},  # noqa: E501
        "MRwajxeMfWg": {"attempts": 30, "status": "rejected", "reasons": ["transcript_too_short_2412c"], "checked_at": "2026-09-24T10:11:39Z", "last_attempt_at": "2026-09-24T10:11:39Z", "last_error": "error:IpBlocked"},  # noqa: E501
        "sMCRpPx-PNI": {"attempts": 30, "status": "no_captions", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:33Z", "last_attempt_at": "2026-09-24T10:14:52Z", "detail": "TranscriptsDisabled"},  # noqa: E501
        "McB5RMP_-_A": {"attempts": 30, "status": "no_captions", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:33Z", "last_attempt_at": "2026-09-24T10:19:55Z", "detail": "TranscriptsDisabled"},  # noqa: E501
        "oyoCJEblsaM": {"attempts": 0, "status": "rejected", "reasons": ["too_short_duration"], "checked_at": "2026-09-23T13:32:56Z"},  # noqa: E501
        "2oVx7wwaJgU": {"attempts": 4, "status": "parked", "reasons": ["too_short_duration"], "checked_at": "2026-09-01T18:31:19Z", "last_attempt_at": "2026-09-01T20:11:04Z", "last_error": "error:AgeRestricted"},  # noqa: E501
        "ZbzN8Ir6cIo": {"attempts": 1, "status": "done", "last_attempt_at": "2026-09-23T13:30:27Z", "chars": 46188},  # noqa: E501
        # Reset to pending by hand on 2026-09-01, then dropped from discovery.
        # No pass can reach them, and the old stop test counted them forever.
        "1jl4ZfgVH1o": {"attempts": 0, "status": "pending", "last_attempt_at": "2026-09-01T18:33:31Z", "attempts_reset_note": "rate limit is environmental, not this video"},  # noqa: E501
        "T7Y82fJuuoI": {"attempts": 0, "status": "pending", "last_attempt_at": "2026-09-01T18:33:34Z", "attempts_reset_note": "rate limit is environmental, not this video"},  # noqa: E501
    }
    ROWS = [
        _row("Mh5YiZGNAuI", "Holiday 2025", "2026-01-05T16:26:31+00:00"),
        _row("1KJeDRw2fes", "Holiday 2025", "2026-01-05T03:05:20+00:00"),
        _row("fJdY0qP7G3k", "Holiday 2024", "2025-01-02T13:59:51+00:00"),
        _row("zy8uHixLAJw", "Holiday 2024", "2025-01-02T02:50:01+00:00"),
        _row("MRwajxeMfWg", "Holiday 2023", "2024-01-03T16:48:13+00:00"),
        _row("sMCRpPx-PNI", "Holiday 2022", "2023-01-03T03:10:03+00:00"),
        _row("McB5RMP_-_A", "Holiday 2019c", "2020-01-06T15:09:50+00:00"),
        _row("oyoCJEblsaM", "Terry Smith on short-term trading", "2026-09-10T11:00:00+00:00"),
        _row("2oVx7wwaJgU", "Mohnish Pabrai tells a Charlie Munger story",
             "2026-05-06T19:54:54+00:00"),
        _row("ZbzN8Ir6cIo", "President Alexander Stubb: Who Decides the New World Order?",
             "2026-09-23T05:00:25+00:00"),
    ]

    def setUp(self) -> None:
        super().setUp()
        self.seed(json.loads(json.dumps(self.BACKLOG)))
        self.store(self.ROWS[-1])
        # Durations are not in the backlog; any value over the floor is what
        # the real ones were, since none of these was rejected on duration.
        self.durations.update({row["video_id"]: 330 for row in self.ROWS})
        self.durations.update({"oyoCJEblsaM": 52, "ZbzN8Ir6cIo": 2975})

    def test_yesterdays_backlog_costs_no_fetches_and_one_pass(self):
        self.discover(*self.ROWS)
        totals = fvt.daemon(max_hours=1, sleep_seconds=0)
        self.assertEqual(self.fetched, [])
        self.assertEqual((totals["passes"], totals["stopped"]), (1, "backlog_empty"))
        self.assert_never_slept()
        self.assertIn("[pass 1] fetched=0 settled=8 fetchable=0", self.out.getvalue())

    def test_a_new_upload_is_the_only_fetch(self):
        new = _row("newpitch01", "A new single-stock pitch", "2026-09-24T20:00:00+00:00")
        self.discover(*self.ROWS, new)
        self.durations["newpitch01"] = 1800
        self.answers["newpitch01"] = [_captions(30000)]
        rows = self.ROWS + [new]
        predicted = fvt.count_fetchable(rows, self.backlog(), self._api([r["video_id"] for r in rows]))

        totals = fvt.daemon(max_hours=1, sleep_seconds=0)

        self.assertEqual(self.fetched, ["newpitch01"])
        # What the stop test counts is what a pass fetches.
        self.assertEqual(predicted, len(self.fetched))
        self.assertEqual(self.rate.record_fetch.call_count, 1)
        self.assertEqual((totals["passes"], totals["stopped"]), (1, "backlog_empty"))
        self.assertEqual(self.backlog()["newpitch01"]["status"], "done")
        self.assert_never_slept()

    def test_orphaned_pending_items_do_not_hold_the_daemon_open(self):
        self.discover()
        totals = fvt.daemon(max_hours=1, sleep_seconds=0)
        self.assertEqual(totals["stopped"], "backlog_empty")
        self.assertEqual(self.backlog()["1jl4ZfgVH1o"]["status"], "pending")


class SettledPredicateTests(unittest.TestCase):
    def test_both_stamp_shapes_parse_to_the_same_instant(self):
        self.assertEqual(fvt._parse_when("2026-09-23T05:00:25+00:00"),
                         fvt._parse_when("2026-09-23T05:00:25Z"))

    def test_unknown_age_is_settled_rather_than_guessed(self):
        # A guess would cost a slot; discovery always carries `published`.
        checked = {"status": "no_captions", "last_attempt_at": "2026-09-24T10:00:00Z"}
        self.assertEqual(fvt.settled(checked, duration=600, published=None, now=NOW), "settled")
        self.assertEqual(fvt.settled(checked, duration=600, published="soon", now=NOW), "settled")
        self.assertEqual(fvt.settled({"status": "no_captions"}, duration=600,
                                     published="2026-09-25T08:00:00Z", now=NOW), "settled")

    def test_a_rejection_without_recorded_reasons_is_settled(self):
        self.assertEqual(fvt.settled({"status": "rejected"}, duration=None,
                                     published=None, now=NOW), "settled")

    def test_undecided_states_are_left_to_the_fetch(self):
        for status in ("pending", "done", None):
            self.assertIsNone(fvt.settled({"status": status}, duration=600,
                                          published=None, now=NOW), status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
