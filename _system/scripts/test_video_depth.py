"""What the video lane publishes, and what it must never publish.

Companion to test_video_delivery.py, which covers collection and routing. These
cover the depth added on top: the card summary, the timing sidecar, the detail
shard, and the concurrency rule that keeps two local-model consumers off one box.

Every assertion here stands for something that actually went wrong. The sound
marks were the published card text for the life of the lane; the short-segment
jump bound was worth 465 anchors on one interview; the peer lock was tested by
mtime first and started a video batch beside a healthy seven-hour podcast run.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_video_detail as video_detail  # noqa: E402
import transcript_segments  # noqa: E402
import video_text  # noqa: E402


class CardSummaryTests(unittest.TestCase):
    """The card body, which used to be transcript[:260]."""

    def test_sound_marks_never_reach_a_card(self):
        for raw in (
            "[music] [music] [music] Thank you, man, for taking the time",
            "[applause] [snofter] Hvor mange av dere har lagret hermetikk",
            "[musikk] [musikk] United [musikk] States and Israel",
        ):
            cleaned = video_text.clean_preview(raw)
            for mark in ("[music]", "[musikk]", "[applause]", "[snofter]"):
                self.assertNotIn(mark, cleaned, f"{mark} survived in {cleaned!r}")

    def test_summary_prefers_the_most_supported_source(self):
        """Order is by how much work stands behind the text."""
        self.assertEqual(
            video_text.card_summary(
                thesis="A thesis drawn from verified quotes.",
                description="The channel blurb.",
                claim="One verified claim.",
                transcript_preview="[music] hello",
            ),
            ("A thesis drawn from verified quotes.", "thesis"),
        )
        self.assertEqual(
            video_text.card_summary(description="The channel blurb.")[1], "description")
        self.assertEqual(video_text.card_summary(claim="One verified claim.")[1], "claim")
        self.assertEqual(
            video_text.card_summary(transcript_preview="[music] Real speech here.")[1],
            "transcript")
        self.assertEqual(video_text.card_summary()[1], "none")

    def test_a_description_is_cut_at_the_boilerplate(self):
        summary, source = video_text.card_summary(
            description="The real summary sentence.\n\nSubscribe here! Follow us on X.")
        self.assertEqual(source, "description")
        self.assertNotIn("Subscribe", summary)


class TranscriptTimingTests(unittest.TestCase):
    """The sidecar that made jump links possible."""

    SEGMENTS = [(0.0, 2.0, "How far ahead of uh Europe"),
                (2.0, 3.0, "and the US do you think"),
                (5.0, 4.0, "Chinese producers are now?")]

    def test_assembled_text_matches_the_flattening_it_replaced(self):
        """The .txt is what the relevance gate admitted; it must not move."""
        old = re.sub(
            r"\s+", " ",
            " ".join((t or "").strip() for _s, _d, t in self.SEGMENTS)).strip()
        text, segments = transcript_segments.assemble(self.SEGMENTS)
        self.assertEqual(text, old)
        for row in segments:
            self.assertEqual(text[row["c"]:row["c"] + len(row["text"])], row["text"])

    def test_internal_whitespace_does_not_lose_a_segment(self):
        """A caption cue wraps mid-sentence; the transcript collapsed that newline."""
        segments = [(0.0, 1.0, "the\nrobot"), (1.0, 1.0, "and capacity")]
        text, assembled = transcript_segments.assemble(segments)
        self.assertEqual(text, "the robot and capacity")
        self.assertEqual(
            [(r["c"], r["t"]) for r in transcript_segments.index_parts(text, segments)],
            [(r["c"], r["t"]) for r in assembled],
        )

    def test_a_quote_resolves_to_when_it_was_said(self):
        text, segments = transcript_segments.assemble(self.SEGMENTS)
        self.assertEqual(transcript_segments.locate(text, "and the US", segments), 2.0)
        # A quote spanning a boundary resolves to where it starts.
        self.assertEqual(
            transcript_segments.locate(text, "Europe and the US", segments), 0.0)
        self.assertEqual(
            transcript_segments.youtube_link("abc123", 5.0),
            "https://www.youtube.com/watch?v=abc123&t=5s")
        self.assertEqual(
            transcript_segments.youtube_link("abc123", None),
            "https://www.youtube.com/watch?v=abc123")

    def test_a_gap_in_a_sparse_sidecar_cannot_be_matched_across(self):
        """Backfilling against regenerated captions leaves holes, not lies."""
        sparse = [{"t": 0.0, "c": 0, "text": "How far ahead of uh Europe"},
                  {"t": 90.0, "c": 900, "text": "Chinese producers are now?"}]
        index = transcript_segments.SearchIndex(sparse, lambda s: s.lower())
        self.assertEqual(index.seconds_for("far ahead of uh europe"), 0.0)
        self.assertIsNone(index.seconds_for("uh europe chinese producers"))

    def test_a_short_segment_may_not_jump(self):
        """"And" and "now." matching thousands of characters downstream dragged
        the cursor past 465 good anchors on the XPeng interview."""
        text = "And now the margin question " + ("x" * 4000) + " And"
        segments = transcript_segments.index_parts(
            text, [(0.0, 1.0, "And now the margin question"), (300.0, 1.0, "And")])
        self.assertEqual(len(segments), 1)


class VideoDetailShardTests(unittest.TestCase):
    def _meta(self, **over):
        meta = {
            "video_id": "vid1",
            "title": "A talk",
            "channel_id": "chan1",
            "channel_title": "Some Channel",
            "published": "2026-09-01T00:00:00+00:00",
            "duration_seconds": 1800,
            "gate": "admitted",
            "description": "The speaker explains the business. A second sentence.",
            "transcript_source": "youtube_captions",
            "relevance": {
                "sustained_tickers": [
                    {"ticker": "ABC", "mentions": 8, "distinct_chunks": 3,
                     "aliases": {"abc corp": 8}}],
                "mentioned_only": [
                    {"ticker": "XYZ", "mentions": 1, "distinct_chunks": 1,
                     "aliases": {"xyz": 1}}],
                "routes": ["sustained_company_1"],
            },
        }
        meta.update(over)
        return meta

    def _build(self, meta):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "vid1.meta.json"
            meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            (root / "vid1.txt").write_text("[music] hello there everyone\n", encoding="utf-8")
            return video_detail.build_detail(meta_path, meta)

    def test_the_gate_evidence_the_row_could_not_carry_is_published(self):
        """A ticker has to say why it is there."""
        detail = self._build(self._meta())
        self.assertEqual(detail["gate_tickers"], ["ABC"])
        self.assertEqual(detail["mentioned_tickers"], ["XYZ"])
        self.assertEqual(
            {row["ticker"]: row["kind"] for row in detail["ticker_evidence"]},
            {"ABC": "sustained", "XYZ": "mentioned"},
        )
        self.assertEqual(
            next(r["aliases"] for r in detail["ticker_evidence"] if r["ticker"] == "ABC"),
            ["abc corp"],
        )

    def test_an_unanalysed_video_says_so_rather_than_implying_claims(self):
        detail = self._build(self._meta())
        self.assertIsNone(detail["analysis"])
        self.assertEqual(detail["claims"], [])
        self.assertEqual(detail["summary_source"], "description")

    def test_a_timestamped_claim_carries_a_link_to_the_moment(self):
        detail = self._build(self._meta(llm_analysis={
            "thesis": "The business is compounding.",
            "tickers": ["ABC"],
            "role": "operator",
            "quote_verified_rate": 0.8,
            "chapters": [{"topic": "Margins", "t_start": 60.0}],
            "claims": [
                {"company": "ABC Corp", "ticker": "ABC", "stance": "bullish",
                 "claim": "Margins expand.", "quote": "margins will expand",
                 "t_start": 123.4},
                {"company": "ABC Corp", "ticker": "ABC", "stance": "bearish",
                 "claim": "Competition bites.", "quote": "competition is fierce"},
            ],
        }))
        self.assertEqual(detail["summary_source"], "thesis")
        self.assertEqual(detail["claims"][0]["link"],
                         "https://www.youtube.com/watch?v=vid1&t=123s")
        # A claim with no timing gets no link rather than a guessed one.
        self.assertIsNone(detail["claims"][1]["link"])
        self.assertEqual(detail["chapters"][0]["link"],
                         "https://www.youtube.com/watch?v=vid1&t=60s")
        # Two opposed readings of one company is itself the finding.
        self.assertEqual(detail["stances"], {"ABC": "mixed"})
        self.assertEqual(detail["analysis"]["quote_verified_rate"], 0.8)

    def test_no_published_card_body_contains_a_sound_mark(self):
        """The regression this whole change exists to prevent."""
        published = ROOT / "dashboard" / "data" / "insights" / "videos.json"
        if not published.exists():
            self.skipTest("no published catalog in this checkout")
        doc = json.loads(published.read_text(encoding="utf-8"))
        offenders = [
            row.get("video_id")
            for row in (doc.get("video_index") or [])
            if re.search(r"\[(music|musikk|applause|snofter|laughter)\]",
                         str(row.get("summary") or ""), re.IGNORECASE)
        ]
        self.assertEqual(offenders, [], f"sound marks in published summaries: {offenders}")

    def test_every_published_timestamp_lies_inside_its_video(self):
        details = ROOT / "dashboard" / "data" / "insights" / "video_details"
        if not details.is_dir():
            self.skipTest("no detail shards in this checkout")
        bad: list[str] = []
        for path in details.glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            duration = doc.get("duration_seconds") or 0
            for row in (doc.get("claims") or []) + (doc.get("chapters") or []):
                seconds = row.get("t_start")
                if seconds is None:
                    continue
                if seconds < 0 or (duration and seconds > duration):
                    bad.append(f"{doc.get('video_id')}@{seconds}s of {duration}s")
        self.assertEqual(bad, [], f"timestamps outside their video: {bad}")

    def test_every_published_quote_appears_in_its_transcript(self):
        """The deterministic hallucination check, asserted on what shipped.

        Verification happens during analysis; this re-runs it against the
        published shard, so a bug between the two stages cannot ship a quote
        nobody said.
        """
        from vault_paths import videos_root

        details = ROOT / "dashboard" / "data" / "insights" / "video_details"
        if not details.is_dir():
            self.skipTest("no detail shards in this checkout")
        try:
            root = videos_root()
        except OSError:
            self.skipTest("research vault not available")
        if root is None or not (root / "library").is_dir():
            self.skipTest("research vault not available")

        def norm(text):
            return re.sub(r"\s+", " ", str(text or "")).strip().lower()

        transcripts = {
            path.stem.rsplit("-", 1)[-1]: path
            for path in (root / "library").rglob("*.txt")
        }
        bad: list[str] = []
        for path in details.glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            source = transcripts.get(str(doc.get("video_id")))
            if not source:
                continue
            hay = norm(source.read_text(encoding="utf-8", errors="replace"))
            for claim in (doc.get("claims") or []):
                quote = norm(claim.get("quote"))
                # Punctuation folding is the analyser's business; a quote that
                # differs only by an apostrophe is checked there. Here the words
                # themselves must be present.
                if quote and quote not in hay:
                    words = quote.split()
                    if len(words) < 4 or " ".join(words[:6]) not in hay:
                        bad.append(f"{doc.get('video_id')}: {quote[:60]}")
        self.assertEqual(bad, [], f"published quotes not found in transcript: {bad}")


class LocalModelConcurrencyTests(unittest.TestCase):
    """Whisper beside llama-server measured 5.5x slower than the two in sequence."""

    def test_the_video_batch_stands_down_for_the_podcast_batch(self):
        batch = (SCRIPTS / "analyze_video_batch.py").read_text(encoding="utf-8")
        self.assertIn("PEER_LOCK_NAME", batch)
        self.assertIn("apb.LOCK_NAME", batch)
        # Liveness, not mtime. These lock files are written once and never
        # refreshed, so an age test called a healthy seven-hour podcast batch
        # stale and started a video batch beside it.
        self.assertIn("def _alive", batch)

    def test_one_supervisor_drains_both_queues(self):
        """A second supervisor would reintroduce the concurrency the lock prevents,
        and sharing one mutex between two supervisors would starve videos: this
        one holds it while idling for an hour on an empty queue."""
        supervisor = (SCRIPTS / "analysis_supervisor.ps1").read_text(encoding="utf-8")
        self.assertIn("analyze_video_batch.py", supervisor)
        self.assertIn("analyze_podcast_batch.py", supervisor)
        self.assertEqual(supervisor.count("New-Object System.Threading.Mutex"), 1)
        self.assertFalse(
            (SCRIPTS / "video_analysis_supervisor.ps1").exists(),
            "a second analysis supervisor is exactly the concurrency this prevents",
        )

    def test_the_vault_push_stages_videos_not_podcasts(self):
        """_push_locked stages one corpus directory and defaults to podcasts.

        Reusing it unchanged staged the podcast lane's in-progress files,
        committed them under a "chore(videos)" message, and left every video
        result uncommitted.
        """
        import inspect

        import analyze_podcast_batch as apb
        import analyze_video_batch

        self.assertIn("subdir", inspect.signature(apb._push_locked).parameters)
        source = inspect.getsource(analyze_video_batch.vault_push)
        self.assertIn('subdir="videos"', source)

    def test_the_batch_reports_remaining_for_the_supervisor(self):
        import analyze_video_batch

        self.assertIn("remaining", analyze_video_batch.status())


class VideoAnalysisContractTests(unittest.TestCase):
    def test_attribution_is_imported_not_reimplemented(self):
        """Those matching rules were repaired four times against live output."""
        episode = (SCRIPTS / "analyze_video_episode.py").read_text(encoding="utf-8")
        self.assertIn("from analyze_podcast_episode import", episode)
        for borrowed in ("validate_tickers", "resolve_tickers", "verify_quotes",
                         "dedupe_claims", "build_aliases"):
            self.assertIn(borrowed, episode)
            self.assertNotIn(f"def {borrowed}(", episode)

    def test_every_channel_with_a_corpus_has_an_analysis_role(self):
        from analyze_video_episode import ROLES, role_for

        registry = json.loads(
            (ROOT / "_system" / "reference" / "video" / "channel_registry.json")
            .read_text(encoding="utf-8"))
        published = ROOT / "dashboard" / "data" / "insights" / "videos.json"
        if not published.exists():
            self.skipTest("no published catalog in this checkout")
        channels = json.loads(published.read_text(encoding="utf-8")).get("video_by_channel") or {}
        for channel_id in channels:
            self.assertIn(role_for(channel_id, registry), ROLES)

    def test_a_timestamp_is_only_attached_after_verification(self):
        """An unverified quote is one the speaker may not have said; a timestamp
        would dress it as sourced."""
        episode = (SCRIPTS / "analyze_video_episode.py").read_text(encoding="utf-8")
        verify = episode.index("claims, stats = verify_quotes(")
        attach = episode.index('stats["claims_timestamped"] = attach_timestamps(')
        self.assertLess(verify, attach)


if __name__ == "__main__":
    unittest.main(verbosity=2)
