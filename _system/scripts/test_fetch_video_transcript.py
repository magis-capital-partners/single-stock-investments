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
        # The clock is frozen, so a daemon that never stops would hang the
        # suite. Fail it instead: no test here needs more than a few passes.
        real_run, self.passes = fvt.run, 0

        def bounded_run(*args, **kwargs):
            self.passes += 1
            if self.passes > 25:
                raise AssertionError("run() called 25 times: the daemon is not stopping")
            return real_run(*args, **kwargs)

        for patcher in (
            mock.patch.object(fvt, "run", side_effect=bounded_run),
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

    def test_captions_that_appear_later_are_collected_on_the_next_daily_run(self):
        self.answers["freshpitch1"] = [NO_CAPTIONS, _captions(12000)]
        first = self.run_pass()
        self.assertEqual(first["fetchable"], 0, "an unripe video must not hold the daemon open")
        waiting = self.run_pass()
        self.assertEqual(waiting["awaiting_captions"], 1)
        self.assertEqual(self.fetched, ["freshpitch1"])

        # Tomorrow's 05:17 run: RSS still lists it (15 entries), captions exist.
        self.now = NOW + timedelta(days=1)
        self.run_pass()
        self.assertEqual(self.fetched, ["freshpitch1", "freshpitch1"])
        self.assertEqual(self.backlog()["freshpitch1"]["status"], "done")

    def test_a_mature_no_captions_answer_is_trusted_for_a_month_then_asked_again(self):
        self.answers["freshpitch1"] = [NO_CAPTIONS]
        self.run_pass()
        second_look = NOW + timedelta(days=1)
        self.now = second_look
        self.run_pass()
        self.now = second_look + fvt.NO_CAPTIONS_RECHECK - timedelta(hours=1)
        trusted = self.run_pass()
        self.assertEqual(trusted["settled"], 1)
        self.assertEqual(self.fetched, ["freshpitch1", "freshpitch1"])
        # A day YouTube served every video without its tracks must not be
        # permanent: after a month the answer is asked for again.
        self.now = second_look + fvt.NO_CAPTIONS_RECHECK + timedelta(hours=1)
        self.run_pass()
        self.assertEqual(self.fetched, ["freshpitch1"] * 3)


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

    def test_the_first_block_stops_the_pass_before_the_rest_of_the_backlog(self):
        self.discover(_row("goodvid01"), _row("goodvid02"))
        self.durations.update({"goodvid01": 1200, "goodvid02": 1200})
        self.answers["goodvid01"] = [IP_BLOCKED]
        stats = self.run_pass()
        self.assertEqual(stats["aborted_on"], "error:IpBlocked")
        self.assertEqual(stats["fetchable"], 2)
        self.assertEqual(self.fetched, ["goodvid01"])

    def test_repeated_blocks_never_spend_attempts_strikes_or_settle_the_video(self):
        # Even when another video was answered just before -- a block is by IP.
        self.discover(_row("goodvid01"), _row("goodvid02"))
        self.durations.update({"goodvid01": 1200, "goodvid02": 1200})
        self.answers["goodvid01"] = [IP_BLOCKED]
        for _ in range(fvt.MAX_ATTEMPTS + fvt.MAX_STRIKES + 2):
            stats = self.run_pass()
            self.assertEqual(stats["aborted_on"], "error:IpBlocked")
        state = self.backlog()["goodvid01"]
        self.assertEqual((state["attempts"], state["status"]), (0, "pending"))
        self.assertNotIn("strikes", state)
        self.assertEqual(stats["fetchable"], 1)

    def test_network_failures_through_requests_are_never_charged(self):
        # youtube-transcript-api uses `requests`: DNS failures, resets and TLS
        # errors arrive as ConnectionError / SSLError, not the urllib names.
        for status in ("error:ConnectionError", "error:SSLError", "error:ReadTimeout", "error:KeyError",
                       "error:PoTokenRequired", "error:YouTubeDataUnparsable",
                       "error:VideoUnplayable"):
            with self.subTest(status=status):
                self.fetched.clear()
                self.passes = 0
                self.discover(_row("goodvid01"))
                self.durations["goodvid01"] = 1200
                self.seed({})
                self.answers["goodvid01"] = [{"status": status, "detail": "x"}]
                for _ in range(fvt.MAX_ATTEMPTS + 1):
                    self.run_pass()
                state = self.backlog()["goodvid01"]
                self.assertEqual((state["attempts"], state["status"]), (0, "pending"))

    def test_a_blocked_second_look_is_retried_not_settled(self):
        # First asked an hour after upload; the second look is now due.
        born = NOW - fvt.NO_CAPTIONS_YOUNG - timedelta(hours=3)
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


class StrikeTests(CaptionLaneHarness):
    """A video that fails "environmentally" every time must not stall the lane."""

    POISON = {"status": "error:YouTubeRequestFailed", "detail": "404 for this URL"}

    def test_a_poison_video_first_in_order_no_longer_starves_the_rest(self):
        self.discover(_row("poison0001"), _row("goodvid01"), _row("goodvid02"))
        self.durations.update({"poison0001": 900, "goodvid01": 900, "goodvid02": 900})
        self.answers["poison0001"] = [self.POISON]
        self.run_pass()
        self.assertEqual(self.fetched, ["poison0001"])
        self.run_pass()
        self.assertEqual(self.fetched, ["poison0001", "goodvid01", "goodvid02", "poison0001"])
        state = self.backlog()["poison0001"]
        # Struck once (others had just been answered), never charged an attempt.
        self.assertEqual((state["attempts"], state["strikes"], state["status"]),
                         (0, 1, "pending"))

    RECENT = "2026-09-24T09:30:00Z"

    def _struck_twice(self, vid: str) -> dict:
        return {"attempts": 0, "status": "pending", "transient_failures": 2,
                "strikes": 2, "last_strike_at": self.RECENT}

    def test_the_third_strike_parks_it_and_still_ends_the_pass(self):
        self.discover(_row("goodvid01"), _row("poison0001"), _row("goodvid02"))
        self.durations.update({"poison0001": 900, "goodvid01": 900, "goodvid02": 900})
        self.seed({"poison0001": self._struck_twice("poison0001")})
        self.answers["poison0001"] = [self.POISON]
        stats = self.run_pass()
        self.assertEqual(self.backlog()["poison0001"]["status"], "parked")
        self.assertEqual(stats["aborted_on"], "error:YouTubeRequestFailed")
        # Struck videos sort last, so the good ones were asked first.
        self.assertEqual(self.fetched, ["goodvid01", "goodvid02", "poison0001"])
        self.assertEqual(self.rate.record_block.call_count, 1)

    def test_an_outage_mid_pass_parks_at_most_one_video(self):
        # The reviewer's case: one success, then the network drops, and the
        # videos left each carry two recent strikes.
        self.discover(_row("goodvid01"), _row("struck001"), _row("struck002"))
        self.durations.update({"goodvid01": 900, "struck001": 900, "struck002": 900})
        self.seed({"struck001": self._struck_twice("struck001"),
                   "struck002": self._struck_twice("struck002")})
        outage = {"status": "error:ConnectionError", "detail": "reset"}
        self.answers.update({"struck001": [outage], "struck002": [outage]})
        self.run_pass()
        statuses = sorted(self.backlog()[v]["status"] for v in ("struck001", "struck002"))
        self.assertEqual(statuses, ["parked", "pending"])

    def test_old_strikes_are_forgotten(self):
        self.discover(_row("goodvid01"), _row("poison0001"))
        self.durations.update({"poison0001": 900, "goodvid01": 900})
        stale = dict(self._struck_twice("poison0001"), last_strike_at="2026-09-01T09:30:00Z")
        self.seed({"poison0001": stale})
        self.answers["poison0001"] = [self.POISON]
        self.run_pass()
        state = self.backlog()["poison0001"]
        self.assertEqual((state["status"], state["strikes"]), ("pending", 1))

    def test_an_answer_for_the_video_clears_its_strikes(self):
        self.discover(_row("poison0001"))
        self.durations["poison0001"] = 900
        self.seed({"poison0001": self._struck_twice("poison0001")})
        self.answers["poison0001"] = [NO_CAPTIONS]
        self.run_pass()
        self.assertNotIn("strikes", self.backlog()["poison0001"])

    def test_a_failure_with_no_proof_of_health_is_not_a_strike(self):
        self.discover(_row("poison0001"))
        self.durations["poison0001"] = 900
        self.answers["poison0001"] = [self.POISON]
        for _ in range(fvt.MAX_STRIKES + 2):
            self.run_pass()
        state = self.backlog()["poison0001"]
        self.assertEqual((state["status"], state.get("strikes")), ("pending", None))


class RejudgedRejectTests(CaptionLaneHarness):
    """A transcript reject is re-judged from its recorded length, not re-fetched."""

    def setUp(self) -> None:
        super().setUp()
        self.discover(_row("MRwajxeMfWg", "Holiday 2023"))
        self.durations["MRwajxeMfWg"] = 330
        # The legacy record: the length lives only in the reason string.
        self.seed({"MRwajxeMfWg": {"attempts": 30, "status": "rejected",
                                   "reasons": ["transcript_too_short_2412c"]}})

    def test_unchanged_thresholds_keep_it_settled(self):
        self.assertEqual(self.run_pass()["settled"], 1)
        self.assertEqual(self.fetched, [])

    def test_a_lowered_char_floor_reopens_it(self):
        with mock.patch.object(fvt, "MIN_TRANSCRIPT_CHARS", 2000):
            self.run_pass()
        self.assertEqual(self.fetched, ["MRwajxeMfWg"])

    def test_a_legacy_coverage_reject_is_rejudged_from_its_rate(self):
        # 117 cpm over an hour: ~7,000 chars, recorded only as a rate.
        self.discover(_row("partial001"))
        self.durations["partial001"] = 3600
        self.seed({"partial001": {"attempts": 3, "status": "rejected",
                                  "reasons": ["caption_coverage_117cpm"]}})
        self.assertEqual(self.run_pass()["settled"], 1)
        with mock.patch.object(fvt, "MIN_CHARS_PER_MINUTE", 100):
            self.run_pass()
        self.assertEqual(self.fetched, ["partial001"])

    def test_a_new_reject_records_what_it_was_judged_on(self):
        self.seed({})
        self.answers["MRwajxeMfWg"] = [_captions(2412)]
        self.run_pass()
        state = self.backlog()["MRwajxeMfWg"]
        self.assertEqual((state["chars"], state["duration_seconds"]), (2412, 330))


class DeadlineTests(CaptionLaneHarness):
    def test_a_slot_past_the_window_ends_the_daemon_instead_of_sleeping(self):
        self.discover(_row("goodvid01"))
        self.durations["goodvid01"] = 900
        self.rate.check.return_value = {"allowed": False, "wait_seconds": 7200,
                                        "reason": "backoff_until_2026-09-25T11:18:10Z"}
        totals = fvt.daemon(max_hours=1, sleep_seconds=0)
        self.assertTrue(totals["stopped"].startswith("deadline:"), totals)
        self.assertEqual(self.fetched, [])
        self.assert_never_slept()
        self.assertEqual(self.backlog()["goodvid01"]["status"], "pending")

    def test_a_slot_inside_the_window_is_waited_for(self):
        self.discover(_row("goodvid01"))
        self.durations["goodvid01"] = 900
        allowed = {"allowed": True, "wait_seconds": 0, "reason": "ok"}
        self.rate.check.side_effect = [
            {"allowed": False, "wait_seconds": 160, "reason": "spacing"}, allowed, allowed]
        totals = fvt.daemon(max_hours=1, sleep_seconds=0)
        self.assertEqual(totals["stopped"], "backlog_empty")
        self.assertEqual(self.fetched, ["goodvid01"])
        self.clock.sleep.assert_any_call(160)


    def test_a_naive_deadline_is_read_as_utc(self):
        self.discover(_row("goodvid01"))
        self.durations["goodvid01"] = 900
        self.rate.check.return_value = {"allowed": False, "wait_seconds": 7200, "reason": "x"}
        stats = self.run_pass(deadline=(NOW + timedelta(hours=1)).replace(tzinfo=None))
        self.assertEqual(stats["stopped_on"], "deadline:x")


class PremiereTests(CaptionLaneHarness):
    """A scheduled premiere has no captions yet and must not cost a slot or a strike."""

    def test_upcoming_and_live_broadcasts_are_not_asked(self):
        self.discover(_row("premiere01"), _row("livenow001"), _row("goodvid01"))
        self.durations.update({"premiere01": 0, "livenow001": 0, "goodvid01": 900})
        real_api = self._api

        def api(ids):
            meta = real_api(ids)
            meta["premiere01"]["snippet"] = {"liveBroadcastContent": "upcoming"}
            meta["livenow001"]["snippet"] = {"liveBroadcastContent": "live"}
            return meta

        with mock.patch.object(fvt.youtube_api, "videos", side_effect=api):
            stats = self.run_pass()
        self.assertEqual(self.fetched, ["goodvid01"])
        self.assertEqual((stats["awaiting_broadcast"], stats["fetchable"]), (2, 0))


class UnreadableBacklogTests(CaptionLaneHarness):
    def test_a_corrupt_backlog_is_refused_not_overwritten_as_empty(self):
        self.discover(_row("goodvid01"))
        path = self.root / "caption_backlog.json"
        path.write_text('{"items": {"MRwajxeMfWg": {"status": "rejec', encoding="utf-8")
        with self.assertRaises(fvt.BacklogUnreadable):
            self.run_pass()
        self.assertEqual(path.read_text(encoding="utf-8"),
                         '{"items": {"MRwajxeMfWg": {"status": "rejec')
        self.assertEqual(self.fetched, [])


try:
    import requests
    from youtube_transcript_api import _errors as yta_errors
except ImportError:  # CI does not install the transcript library
    yta_errors = None


@unittest.skipIf(yta_errors is None, "youtube-transcript-api not installed")
class LibraryClassificationTests(unittest.TestCase):
    """fetch_captions() against the real exception classes, not pre-classified answers."""

    def classify(self, exc: BaseException) -> dict:
        api = mock.MagicMock()
        api.return_value.list.side_effect = exc
        with mock.patch("youtube_transcript_api.YouTubeTranscriptApi", api):
            return fvt.fetch_captions("abcdefghijk")

    def test_network_failures_are_transient_not_verdicts(self):
        for exc in (requests.exceptions.ConnectionError("dns"),
                    requests.exceptions.SSLError("tls"),
                    requests.exceptions.ReadTimeout("slow"),
                    yta_errors.PoTokenRequired("abcdefghijk"),
                    yta_errors.YouTubeDataUnparsable("abcdefghijk"),
                    yta_errors.VideoUnplayable("abcdefghijk", "Sign in to confirm you're not a bot", [])):
            with self.subTest(exc=type(exc).__name__):
                result = self.classify(exc)
                self.assertTrue(fvt.is_transient(result["status"]), result)
                self.assertFalse(fvt.is_permanent(result["status"]), result)

    def test_blocks_are_blocks(self):
        for exc in (yta_errors.IpBlocked("abcdefghijk"), yta_errors.RequestBlocked("abcdefghijk")):
            with self.subTest(exc=type(exc).__name__):
                self.assertTrue(fvt.is_block(self.classify(exc)["status"]))

    def test_transcripts_disabled_is_a_no_captions_answer(self):
        self.assertEqual(self.classify(yta_errors.TranscriptsDisabled("abcdefghijk"))["status"],
                         "no_captions")

    def test_age_restriction_is_still_permanent(self):
        self.assertTrue(fvt.is_permanent(
            self.classify(yta_errors.AgeRestricted("abcdefghijk"))["status"]))


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

    def test_unknown_age_falls_back_to_the_monthly_recheck(self):
        # No `published` means no "young" window, not a guess either way.
        checked = {"status": "no_captions", "last_attempt_at": "2026-09-24T10:00:00Z"}
        self.assertEqual(fvt.settled(checked, duration=600, published=None, now=NOW), "settled")
        self.assertEqual(fvt.settled(checked, duration=600, published="soon", now=NOW), "settled")
        later = NOW + fvt.NO_CAPTIONS_RECHECK
        self.assertIsNone(fvt.settled(checked, duration=600, published=None, now=later))

    def test_a_no_captions_record_without_a_check_time_is_asked(self):
        self.assertIsNone(fvt.settled({"status": "no_captions"}, duration=600,
                                      published="2026-09-25T08:00:00Z", now=NOW))

    def test_a_rejection_without_recorded_reasons_is_settled(self):
        self.assertEqual(fvt.settled({"status": "rejected"}, duration=None,
                                     published=None, now=NOW), "settled")

    def test_undecided_states_are_left_to_the_fetch(self):
        for status in ("pending", "done", None):
            self.assertIsNone(fvt.settled({"status": status}, duration=600,
                                          published=None, now=NOW), status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
