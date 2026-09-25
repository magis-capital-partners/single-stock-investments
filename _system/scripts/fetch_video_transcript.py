#!/usr/bin/env python3
"""Fetch published captions for discovered videos. Captions only -- never audio.

Phase 2 of the video lane. The podcast pipeline tries a published transcript
first and falls back to Whisper on the audio; this one has no fallback and that
is deliberate. Audio download was ruled out, so a video without captions is
dropped rather than transcribed. That single constraint removes the ToS
question, removes the 30-minutes-of-CPU-per-item cost that has the podcast
analysis queue 29 days deep, and keeps this job cheap enough to run beside the
Whisper backfill without competing with it.

**No audio path exists here, and a test enforces that.** `yt-dlp` is installed on
this box and would happily fetch a stream; the guard is that no call site may
exist, in the same spirit as the `reqGlobalCancel` ban in the trading code.

Three mechanical gates, applied before a video is admitted to the corpus. None
of them is a *relevance* judgement -- that is the transcript gate, and it comes
next:

  * **Duration.** Under the floor it is a clip or a trailer.
  * **Length.** A transcript too short to contain an argument.
  * **Coverage.** chars-per-minute below the floor means the caption track does
    not actually cover the video -- a partial track, a music segment, or an
    intro-only caption. This is the video analogue of the podcast corpus finding
    that 97% of what looked like transcripts were MP3s wearing a .txt extension:
    the file existed and was the wrong thing, and only reading the content said so.

The 25,000-byte podcast floor deliberately does NOT transfer. A 10-minute Sohn
pitch measured 10,359 characters on 2026-09-01 -- a genuine single-name pitch
that the podcast threshold would have thrown away. Podcast episodes run 45-90
minutes; conference pitches are short and dense.

**A fetch's answer is kept.** Discovery re-marks every video `pending_transcript`
from metadata alone on each run and never reads the backlog, so the backlog is
the only record of what a fetch already found. A transcript that failed the
gate is settled there (re-judged against the current thresholds from its
recorded length, never re-fetched unless it would now pass); a video with no
caption tracks is asked again when it reaches NO_CAPTIONS_YOUNG if it was first
asked younger, and monthly after that (see `settled()`). Re-reading a known answer spends a slot from a
20/hour budget and is one more chance of an IP block. `--refetch` overrides it.

    python _system/scripts/fetch_video_transcript.py --limit 10
    python _system/scripts/fetch_video_transcript.py --video QoDbkHOsslg
    python _system/scripts/fetch_video_transcript.py --report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# Video titles carry whatever the uploader typed. A U+2060 WORD JOINER in a
# podcast title killed an analysis run on 2026-08-29 because Python picks cp1252
# for a redirected stdout on Windows: the line reporting success was the crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import caption_rate_limit as rate  # noqa: E402
import transcript_segments  # noqa: E402
import youtube_api  # noqa: E402
from vault_paths import videos_root  # noqa: E402

BACKLOG_NAME = "caption_backlog.json"

# Deliberately permissive. An 8-minute floor was tried first and dropped "Ryan
# Packard pitches AppLovin at Sohn 2026" at 7:28 -- a genuine single-name pitch,
# the exact thing this lane exists to collect. The junk it was aimed at (RV
# Capital's "Holiday 2021" cards, marketing shorts) is not distinguishable from a
# short pitch by *duration*; it is distinguishable by content, and content is the
# relevance gate's job. So this floor only removes what no transcript could
# rescue, and the corpus carries a few Christmas greetings until Phase 3 runs.
MIN_DURATION_SECONDS = int(os.environ.get("VIDEO_MIN_DURATION", "300"))
# ~5 minutes of ordinary speech. Not the podcast 25,000 -- see the module
# docstring -- and not 6,000 either: at a normal 800 chars/minute that would
# reimpose a 7.5-minute floor through the back door and lose the same pitches.
MIN_TRANSCRIPT_CHARS = int(os.environ.get("VIDEO_MIN_CHARS", "4000"))
# Ordinary speech runs 700-1,000 chars/minute. Below 350 the track is not
# covering the video, whatever its length says.
MIN_CHARS_PER_MINUTE = int(os.environ.get("VIDEO_MIN_CPM", "350"))
# Give up on an item after this many distinct failures rather than retrying it
# forever; one dead video must not consume the run. Mirrors the whisper backlog.
MAX_ATTEMPTS = 4
# The one rejection reached without a caption fetch (quality_gate's duration
# reason shares the prefix). Every other reason came from reading a transcript.
DURATION_REJECT = "too_short_duration"
# A "no captions" answer is a description of YouTube's reply, not of the video.
# The transcript library raises TranscriptsDisabled whenever the player response
# has no caption tracks: for a fresh upload whose speech recognition has not run
# yet, and for every video on a day YouTube changes what it serves the client
# the library impersonates. So the answer is never final, only trusted for a
# while:
#
#   * asked within NO_CAPTIONS_YOUNG of upload, it is asked again once the video
#     is past that age -- the next daily run, while RSS still lists it (the feed
#     keeps 15 entries and these channels upload in bursts of 11-13);
#   * otherwise it is asked again after NO_CAPTIONS_RECHECK.
#
# Of 117 stored transcripts on 2026-09-24, three were fetched 4.6-8.5 hours after
# upload, and all three already had captions.
NO_CAPTIONS_YOUNG = timedelta(hours=12)
NO_CAPTIONS_RECHECK = timedelta(days=30)

# Failures that say nothing about the video, only about the moment. None of
# them spends an item's retry budget, and each one ends the pass, because once
# the cause is the environment every remaining item fails identically.
#
# The podcast lane learned this the expensive way: DNS failures resolve in
# milliseconds, so a brief outage burned each item's whole retry budget in under
# a second and marked 696 perfectly good episodes permanently failed on
# 2026-08-20.
#
# BLOCK markers are YouTube saying, by IP, "not you, not now". They are never
# held against a video.
BLOCK_ERROR_MARKERS = (
    "IpBlocked",
    "RequestBlocked",
    "TooManyRequests",
)
# Network, client and systemic failures. youtube-transcript-api uses `requests`,
# so a DNS failure, a reset or a TLS error arrives as ConnectionError/SSLError --
# the urllib names alone never matched. PoTokenRequired, YouTubeDataUnparsable
# and a consent-cookie failure describe the client, not the video; so does
# VideoUnplayable, which is also how the library reports a bot check worded
# slightly differently from the one it recognises, and an upcoming premiere.
# ParseError and AttributeError are what an empty or reshaped reply produces.
ENVIRONMENT_ERROR_MARKERS = (
    "YouTubeRequestFailed",
    "URLError",
    "TimeoutError",
    "Timeout",
    "RemoteDisconnected",
    "ConnectionResetError",
    "ConnectionError",
    "SSLError",
    "ChunkedEncodingError",
    "ProxyError",
    "PoTokenRequired",
    "YouTubeDataUnparsable",
    "FailedToCreateConsentCookie",
    "VideoUnplayable",
    "ParseError",
    "AttributeError",
    # An srv3 body with stray whitespace, or a track entry missing a field.
    "KeyError",
)
TRANSIENT_ERROR_MARKERS = BLOCK_ERROR_MARKERS + ENVIRONMENT_ERROR_MARKERS
# An environmental failure that keeps landing on one video, in passes where
# another video had just succeeded, is about the video after all -- a URL that
# always 404s would otherwise abort every pass forever. Only then is it counted,
# as a strike rather than an attempt, and a video is parked after this many.
# A block is never a strike.
MAX_STRIKES = 3
# Strikes are evidence about a video only while they are recent; an old strike
# says more about an old outage. A strike older than this is forgotten, and any
# fetch YouTube answers for the video clears them all.
STRIKE_WINDOW = timedelta(days=7)

# The mirror image of the transient set: conditions that will never resolve by
# waiting. An age-restricted video needs an authenticated session this lane does
# not have and will not grow, so retrying it four times is four wasted slots out
# of a deliberately small hourly budget.
PERMANENT_ERROR_MARKERS = (
    "AgeRestricted",
    "VideoUnavailable",
    "NotTranslatable",
    "InvalidVideoId",
)

PREFERRED_LANGS = ["en", "en-US", "en-GB"]


def is_transient(status: str) -> bool:
    return any(marker in (status or "") for marker in TRANSIENT_ERROR_MARKERS)


def is_block(status: str) -> bool:
    return any(marker in (status or "") for marker in BLOCK_ERROR_MARKERS)


def is_permanent(status: str) -> bool:
    return any(marker in (status or "") for marker in PERMANENT_ERROR_MARKERS)


def _dt_now() -> datetime:
    return datetime.now(timezone.utc)


def now_stamp() -> str:
    return _dt_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "video"


def video_paths(video_id: str, title: str, published: str | None) -> tuple[Path, Path]:
    """<videos>/library/<year>/<slug>-<video_id>.txt and .meta.json.

    The video id is the unique key and always present; the slug is there so the
    directory can be read by a human, exactly as the podcast corpus does.
    """
    year = (published or "")[:4]
    if not re.match(r"^\d{4}$", year):
        year = datetime.now(timezone.utc).strftime("%Y")
    out = videos_root(create=True) / "library" / year
    out.mkdir(parents=True, exist_ok=True)
    stem = slugify(title) + "-" + video_id
    return out / (stem + ".txt"), out / (stem + ".meta.json")


def backlog_path() -> Path:
    return videos_root(create=True) / BACKLOG_NAME


class BacklogUnreadable(RuntimeError):
    """The backlog exists but is not JSON. Refuse rather than start empty."""


def load_backlog() -> dict:
    path = backlog_path()
    if not path.exists():
        return {"items": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Reading it as empty would be written back at the end of the pass and
        # erase every verdict in it -- the one record of what fetches found.
        raise BacklogUnreadable("{0}: {1}".format(path, exc)) from exc
    return doc if isinstance(doc, dict) else {"items": {}}


def save_backlog(doc: dict) -> None:
    doc["updated_at"] = now_stamp()
    items = doc.get("items") or {}
    doc["pending_count"] = sum(1 for v in items.values() if v.get("status") == "pending")
    # A per-process temp name: video_whisper_backfill writes this same file
    # through `caption_backlog.json.tmp`, and two writers sharing one temp file
    # can publish a half-written mix of both.
    tmp = backlog_path().with_name("{0}.{1}.tmp".format(BACKLOG_NAME, os.getpid()))
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Windows refuses to replace a file another process has open (WinError 5),
    # and a reader holds it for milliseconds. Retry briefly before giving up.
    for attempt in range(5):
        try:
            tmp.replace(backlog_path())
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2)


def fetch_captions(video_id: str) -> dict:
    """Published captions only. Manual preferred over auto-generated.

    Returns {status, text, language, is_generated, track_count}. `status` is
    'ok', 'no_captions', or 'error:<Type>'.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"status": "error:MissingDependency",
                "detail": "pip install youtube-transcript-api"}

    api = YouTubeTranscriptApi()
    try:
        listing = list(api.list(video_id))
    except Exception as exc:  # noqa: BLE001 - library raises many shapes
        name = type(exc).__name__
        if "NoTranscript" in name or "TranscriptsDisabled" in name:
            return {"status": "no_captions", "detail": name}
        return {"status": "error:" + name, "detail": str(exc)[:200]}

    if not listing:
        return {"status": "no_captions", "detail": "empty track list"}

    # A human-written track is materially better for quote verification, which
    # the analysis stage depends on -- auto captions have no punctuation to
    # anchor a quote against.
    manual = [t for t in listing if not t.is_generated]
    ordered = manual + [t for t in listing if t.is_generated]
    english = [t for t in ordered if (t.language_code or "").lower().startswith("en")]
    chosen = english or ordered

    try:
        fetched = api.fetch(video_id, languages=[t.language_code for t in chosen])
    except Exception as exc:  # noqa: BLE001
        return {"status": "error:" + type(exc).__name__, "detail": str(exc)[:200]}

    # Every snippet carries .start and .duration. Flattening to text alone is
    # what cost the lane its deep links; assemble() keeps both and returns the
    # same string the old one-liner did.
    text, segments = transcript_segments.assemble(
        (getattr(s, "start", None), getattr(s, "duration", None), s.text or "")
        for s in fetched
    )
    return {
        "status": "ok" if text else "no_captions",
        # A listed track that fetched empty is not TranscriptsDisabled; say so.
        "detail": None if text else "empty transcript",
        "text": text,
        "segments": segments,
        "language": getattr(fetched, "language_code", None),
        "is_generated": bool(getattr(fetched, "is_generated", True)),
        "track_count": len(listing),
        "manual_available": bool(manual),
    }


def quality_gate(text: str, duration_seconds: int | None) -> list[str]:
    """Mechanical rejects only. Relevance is decided later, on this same text."""
    return gate_reasons(len(text or ""), duration_seconds)


def gate_reasons(chars: int, duration_seconds: int | None) -> list[str]:
    """quality_gate on the measurements alone, so a recorded reject can be
    re-judged against today's thresholds without fetching the text again."""
    reasons: list[str] = []
    if duration_seconds is not None and duration_seconds < MIN_DURATION_SECONDS:
        reasons.append("too_short_duration_{0}s".format(duration_seconds))
    if chars < MIN_TRANSCRIPT_CHARS:
        reasons.append("transcript_too_short_{0}c".format(chars))
    if duration_seconds and duration_seconds >= 60:
        cpm = chars / (duration_seconds / 60.0)
        if cpm < MIN_CHARS_PER_MINUTE:
            # The track exists but does not cover the video.
            reasons.append("caption_coverage_{0:.0f}cpm".format(cpm))
    return reasons


def _parse_when(value: str | None) -> datetime | None:
    """RSS stamps end in +00:00 and Data API stamps in Z; accept both."""
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def settled(state: dict, *, duration: int | None, published: str | None,
            now: datetime) -> str | None:
    """Why fetching this item again would only repeat a known answer, or None.

    `run()` once honoured just one of the verdicts it writes, `parked`, and
    re-fetched every `rejected` and `no_captions` item on every pass. On
    2026-09-23 the captions stage made 21 fetches and 20 of them re-asked seven
    videos it had already answered -- four RVCapital holiday cards were on 43
    attempts each -- and hit the hourly cap to store one new transcript.

    Returns "settled" for a known answer, "awaiting_captions" for a fresh
    upload whose second look is not due yet, and None when a fetch could still
    learn something.
    """
    status = state.get("status")
    if status == "rejected":
        reasons = [str(r) for r in state.get("reasons") or []]
        if reasons and all(r.startswith(DURATION_REJECT) for r in reasons):
            # Decided on duration before any fetch, which triage() re-derives
            # for free. Only a measured duration that now clears the floor
            # reopens it; a missing one (the Data API down) must not turn
            # every short clip into a caption fetch.
            if duration is not None and duration >= MIN_DURATION_SECONDS:
                return None
            return "settled"
        # A transcript was read and failed the gate. Tomorrow it will be the
        # same transcript -- but the thresholds may have moved, and the
        # measurement is on record, so re-judge it rather than trust the old
        # verdict. Only a verdict that would now pass costs a fetch.
        recorded = state.get("duration_seconds")
        judged_on = recorded if recorded is not None else duration
        chars = _recorded_chars(state, reasons, judged_on)
        if chars is None:
            return "settled"
        if gate_reasons(chars, judged_on):
            return "settled"
        return None
    if status == "no_captions":
        checked = _parse_when(state.get("last_attempt_at"))
        if checked is None:
            return None
        born = _parse_when(published)
        if born is not None and checked - born < NO_CAPTIONS_YOUNG:
            # Asked while YouTube may still have been generating captions.
            # Look again once the video is past that age -- not before, and
            # not on every pass until then.
            return "awaiting_captions" if now - born < NO_CAPTIONS_YOUNG else None
        # Trusted for a month, then asked again: cheap insurance against a
        # day when YouTube served every video without its caption tracks.
        return "settled" if now - checked < NO_CAPTIONS_RECHECK else None
    return None


_CHARS_REASON = re.compile(r"^transcript_too_short_(\d+)c$")
_CPM_REASON = re.compile(r"^caption_coverage_(\d+)cpm$")


def _recorded_chars(state: dict, reasons: list[str], duration: int | None) -> int | None:
    """The transcript length a reject was judged on: recorded since 2026-09-25,
    and carried in the reason string before -- directly
    (`transcript_too_short_2412c`) or as a rate (`caption_coverage_117cpm`),
    which the video's duration turns back into a length."""
    if isinstance(state.get("chars"), int):
        return state["chars"]
    for reason in reasons:
        match = _CHARS_REASON.match(reason)
        if match:
            return int(match.group(1))
    for reason in reasons:
        match = _CPM_REASON.match(reason)
        if match and duration:
            return int(int(match.group(1)) * duration / 60.0)
    return None


def triage(row: dict, state: dict, duration: int | None, *,
           refetch: bool = False, now: datetime | None = None,
           broadcast: str | None = None) -> str:
    """Decide one discovered video without a network call.

    Returns "fetch", or the reason no fetch is needed. The daemon's stop test
    counts the rows that come back "fetch", so what a pass fetches and what the
    daemon waits for are one decision rather than two that can drift apart.
    """
    if state.get("status") == "parked":
        return "parked"
    if broadcast in ("upcoming", "live"):
        # A scheduled premiere or a stream still on air has no captions yet,
        # and asking anyway returns VideoUnplayable -- an environmental error
        # that ends the pass and backs the whole lane off. The Data API's
        # snippet already says so, at no caption-slot cost.
        return "awaiting_broadcast"
    txt_path, meta_path = video_paths(row["video_id"], row.get("title") or "",
                                      row.get("published"))
    # Both files, not just one. A run killed between the two writes leaves a
    # meta with no transcript; requiring both makes that state self-healing
    # rather than a permanent skip over a video we never actually stored.
    if txt_path.exists() and meta_path.exists() and not refetch:
        return "existing"
    if not refetch:
        known = settled(state, duration=duration, published=row.get("published"),
                        now=now or _dt_now())
        if known:
            return known
    # Cheapest possible reject: a short video never needs a caption fetch.
    if duration is not None and duration < MIN_DURATION_SECONDS:
        return DURATION_REJECT
    return "fetch"


def _duration(meta_by_id: dict, video_id: str) -> int | None:
    api_item = meta_by_id.get(video_id) or {}
    return youtube_api.parse_duration((api_item.get("contentDetails") or {}).get("duration"))


def _broadcast(meta_by_id: dict, video_id: str) -> str | None:
    """`upcoming` / `live` / `none` from the Data API snippet, if we have it."""
    snippet = (meta_by_id.get(video_id) or {}).get("snippet") or {}
    return snippet.get("liveBroadcastContent")


def count_fetchable(rows: list[dict], items: dict, meta_by_id: dict) -> int:
    """Rows the next pass would spend a caption fetch on."""
    now = _dt_now()
    return sum(
        1 for row in rows
        if triage(row, items.get(row["video_id"]) or {"status": "pending"},
                  _duration(meta_by_id, row["video_id"]), now=now,
                  broadcast=_broadcast(meta_by_id, row["video_id"])) == "fetch"
    )


def load_pending(limit: int | None, only_video: str | None) -> list[dict]:
    disc = videos_root() / "discovery_latest.json"
    if not disc.exists():
        raise SystemExit("no discovery_latest.json -- run discover_videos.py first")
    doc = json.loads(disc.read_text(encoding="utf-8"))
    rows = [v for v in doc.get("videos") or [] if v.get("gate") == "pending_transcript"]
    if only_video:
        rows = [v for v in rows if v.get("video_id") == only_video]
    return rows[:limit] if limit else rows


def run(*, limit: int | None = None, only_video: str | None = None,
        refetch: bool = False, sleep_seconds: float = 1.0,
        wait_for_slot: bool = False, deadline: datetime | None = None) -> dict:
    rows = load_pending(limit, only_video)
    if not rows:
        return {"considered": 0, "note": "nothing pending", "fetchable": 0}
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    backlog = load_backlog()
    items = backlog.setdefault("items", {})

    # One API call per 50 videos buys the duration that RSS does not carry.
    meta_by_id: dict[str, dict] = {}
    try:
        meta_by_id = youtube_api.videos([r["video_id"] for r in rows])
    except youtube_api.YouTubeAPIError as exc:
        print("api unavailable ({0}); proceeding without duration".format(exc), flush=True)

    stats = {"considered": len(rows), "fetched": 0, "no_captions": 0,
             "rejected_quality": 0, "skipped_existing": 0, "errors": 0, "parked": 0,
             "settled": 0, "awaiting_captions": 0, "awaiting_broadcast": 0}

    # Videos that last failed transiently go to the back. A pass stops at its
    # first environmental failure, so a video that fails that way every time
    # would otherwise stop every pass before anything behind it is asked.
    rows = sorted(rows, key=lambda r: int(
        (items.get(r["video_id"]) or {}).get("transient_failures") or 0))
    # Set by the first fetch YouTube answers in this pass: proof that, just
    # now, the environment was fine.
    healthy_this_pass = False

    for row in rows:
        vid = row["video_id"]
        state = items.setdefault(vid, {"attempts": 0, "status": "pending"})
        duration = _duration(meta_by_id, vid)
        action = triage(row, state, duration, refetch=refetch,
                        broadcast=_broadcast(meta_by_id, vid))
        if action == "existing":
            stats["skipped_existing"] += 1
            state["status"] = "done"
            continue
        if action == DURATION_REJECT:
            state.update({"status": "rejected", "reasons": [DURATION_REJECT],
                          "checked_at": now_stamp()})
            stats["rejected_quality"] += 1
            print("skip  {0} {1}s  {2}".format(vid, duration, (row.get("title") or "")[:44]),
                  flush=True)
            continue
        if action != "fetch":
            # parked, settled or awaiting_*: nothing to ask YouTube.
            stats[action] += 1
            continue

        txt_path, meta_path = video_paths(vid, row.get("title") or "", row.get("published"))
        api_item = meta_by_id.get(vid) or {}

        # Pacing is checked immediately before the network call, never at the
        # top of the loop: skips and duration rejects cost nothing and must not
        # consume a slot. In batch mode an exhausted budget ends the run; in
        # daemon mode it waits, which is the whole point of running a daemon.
        decision = rate.check()
        while not decision["allowed"]:
            # A daemon whose next slot lies past its deadline stops now rather
            # than sleeping until youtube_lane's wall clock kills it.
            past_deadline = deadline is not None and (
                _dt_now() + timedelta(seconds=decision["wait_seconds"]) > deadline)
            if not wait_for_slot or past_deadline:
                stats["stopped_on"] = (("deadline:" if past_deadline else "rate_budget:")
                                       + decision["reason"])
                stats["fetchable"] = count_fetchable(rows, items, meta_by_id)
                print("hold  {0}  {1}, {2}s -- {3} left for the next run".format(
                    vid, decision["reason"], decision["wait_seconds"],
                    stats["fetchable"]), flush=True)
                save_backlog(backlog)
                return stats
            nap = min(decision["wait_seconds"], 300)
            print("wait  {0}s ({1})".format(nap, decision["reason"]), flush=True)
            time.sleep(nap)
            decision = rate.check()

        rate.record_fetch()
        result = fetch_captions(vid)
        state["last_attempt_at"] = now_stamp()
        if not is_transient(result.get("status", "")):
            # A transient failure is not this video's fault; see
            # TRANSIENT_ERROR_MARKERS. Only real failures spend retry budget.
            state["attempts"] = int(state.get("attempts", 0)) + 1
            # YouTube answered for this video, so earlier strikes were not
            # about it.
            state.pop("strikes", None)
            state.pop("last_strike_at", None)

        if result["status"] == "no_captions":
            # The request itself succeeded, so the IP is evidently not blocked;
            # that is as much evidence of health as a transcript would be.
            rate.record_success()
            healthy_this_pass = True
            # No fallback by design: audio transcription is not part of this lane.
            state.update({"status": "no_captions", "detail": result.get("detail")})
            stats["no_captions"] += 1
            print("none  {0}  {1}".format(vid, (row.get("title") or "")[:50]), flush=True)
            # Saved per verdict, not per pass. youtube_lane bounds this stage
            # with a wall-clock kill, and a kill used to discard the backlog
            # updates of the whole pass, so the next run paid again for
            # answers it already had.
            save_backlog(backlog)
            time.sleep(sleep_seconds)
            continue

        if result["status"].startswith("error"):
            state["last_error"] = result["status"]
            stats["errors"] += 1
            if is_transient(result["status"]):
                state["transient_failures"] = int(state.get("transient_failures") or 0) + 1
                state["status"] = "pending"
                if healthy_this_pass and not is_block(result["status"]):
                    # Another video was answered moments ago, so this one
                    # failing is at least partly about this one. A strike, not
                    # an attempt; see MAX_STRIKES. An IP block never strikes.
                    last = _parse_when(state.get("last_strike_at"))
                    if last is None or _dt_now() - last > STRIKE_WINDOW:
                        state["strikes"] = 0
                    state["strikes"] = int(state.get("strikes") or 0) + 1
                    state["last_strike_at"] = now_stamp()
                    if state["strikes"] >= MAX_STRIKES:
                        state["status"] = "parked"
                        print("err   {0}  {1}  (parked after {2} strikes)".format(
                            vid, result["status"], state["strikes"]), flush=True)
                # Persist the backoff before doing anything else: a restart must
                # not read as "we waited". Then stop -- once the IP is limited
                # every remaining item fails identically, and continuing would
                # convert one rate limit into a backlog of false failures. That
                # holds after a strike too: an outage that began mid-pass must
                # not get the chance to park a second video.
                blocked = rate.record_block()
                stats["aborted_on"] = result["status"]
                print("stop  {0}  {1} -- backing off until {2}, {3} left".format(
                    vid, result["status"], blocked.get("blocked_until"),
                    count_fetchable(rows, items, meta_by_id)), flush=True)
                break
            if is_permanent(result["status"]):
                state["status"] = "parked"
            else:
                state["status"] = ("parked" if state["attempts"] >= MAX_ATTEMPTS
                                   else "pending")
            print("err   {0}  {1}  ({2})".format(vid, result["status"],
                                                 state["status"]), flush=True)
            save_backlog(backlog)
            time.sleep(sleep_seconds)
            continue

        rate.record_success()
        healthy_this_pass = True
        text = result.get("text") or ""
        reasons = quality_gate(text, duration)
        if reasons:
            # The measurement goes on record so settled() can re-judge it
            # if the thresholds move, without fetching the text again.
            state.update({"status": "rejected", "reasons": reasons, "checked_at": now_stamp(),
                          "chars": len(text), "duration_seconds": duration})
            stats["rejected_quality"] += 1
            print("drop  {0}  {1}  {2}".format(vid, ",".join(reasons),
                                               (row.get("title") or "")[:36]), flush=True)
            save_backlog(backlog)
            time.sleep(sleep_seconds)
            continue

        snippet = api_item.get("snippet") or {}
        meta = {
            "video_id": vid,
            "url": row.get("url"),
            "title": row.get("title"),
            "channel_id": row.get("channel_id"),
            "channel_title": row.get("channel_title"),
            "tier": row.get("tier"),
            "trust": row.get("trust"),
            "published": row.get("published"),
            "description": snippet.get("description") or row.get("description"),
            "duration_seconds": duration,
            "views": row.get("views"),
            "caption_language": result.get("language"),
            "caption_is_generated": result.get("is_generated"),
            "caption_manual_available": result.get("manual_available"),
            "caption_track_count": result.get("track_count"),
            "transcript_chars": len(text),
            "chars_per_minute": round(len(text) / (duration / 60.0), 1) if duration else None,
            "transcript_source": "youtube_captions",
            "segment_count": len(result.get("segments") or []),
            "transcript_path": txt_path.relative_to(videos_root()).as_posix(),
            "resolve_preview": row.get("resolve_preview"),
            # Set by the Phase 3 transcript gate, which has not run yet.
            "relevance": None,
            "gate": "transcript_fetched",
            "fetched_at": now_stamp(),
        }
        # Meta first, transcript second. The invariant worth holding is "every
        # transcript has a meta describing it". The reverse orphan is harmless:
        # the skip check requires both, so the next run simply retries it.
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        txt_path.write_text(text + "\n", encoding="utf-8")
        transcript_segments.write_sidecar(txt_path, result.get("segments") or [])
        state.update({"status": "done", "chars": len(text)})
        stats["fetched"] += 1
        kind = "auto" if result.get("is_generated") else "MANUAL"
        print("ok    {0}  {1:>6}c  {2:>4}s  {3:6s} {4}".format(
            vid, len(text), duration or 0, kind, (row.get("title") or "")[:38]), flush=True)
        save_backlog(backlog)
        time.sleep(sleep_seconds)

    save_backlog(backlog)
    stats["fetchable"] = count_fetchable(rows, items, meta_by_id)
    return stats


def daemon(*, max_hours: float | None = None, sleep_seconds: float = 1.0) -> dict:
    """Drain the backlog across as many passes as the pacing budget allows.

    A single pass ends when it hits a block, because every further item would
    fail identically. The daemon exists so that ending a pass is not the same as
    giving up: it waits out the persisted backoff and starts another. This is the
    whisper backfill's `--until-empty` shape, with the budget rather than the CPU
    as the thing being yielded to. It stops as soon as a pass leaves nothing a
    fetch could answer; waiting out the pacing budget with nothing to spend it
    on is how the caption stage used to fill its whole window.
    """
    started = _dt_now()
    deadline = started + timedelta(hours=max_hours) if max_hours is not None else None
    totals = {"passes": 0, "fetched": 0, "no_captions": 0, "rejected_quality": 0,
              "errors": 0, "blocks": 0}
    while True:
        if deadline is not None and _dt_now() >= deadline:
            totals["stopped"] = "max_hours"
            return totals

        stats = run(sleep_seconds=sleep_seconds, wait_for_slot=True, deadline=deadline)
        totals["passes"] += 1
        for key in ("fetched", "no_captions", "rejected_quality", "errors"):
            totals[key] += int(stats.get(key) or 0)
        if stats.get("aborted_on"):
            totals["blocks"] += 1

        # Counted by the same triage the pass fetches by. This used to be every
        # `pending` item in the backlog, which on 2026-09-23 included two
        # videos discovery no longer lists. No pass can settle those, so the
        # count never reached zero and the daemon kept starting passes -- each
        # re-fetching seven answered videos -- until youtube_lane's wall clock
        # killed it at 65 minutes.
        remaining = int(stats.get("fetchable") or 0)
        totals["fetchable"] = remaining
        print("[pass {0}] fetched={1} settled={2} fetchable={3}".format(
            totals["passes"], stats.get("fetched", 0), stats.get("settled", 0),
            remaining), flush=True)
        if remaining == 0 and not stats.get("aborted_on"):
            totals["stopped"] = "backlog_empty"
            return totals
        if str(stats.get("stopped_on") or "").startswith("deadline:"):
            totals["stopped"] = stats["stopped_on"]
            return totals

        # The next pass will block on the pacing check anyway; sleeping here
        # keeps the log from filling with wait lines. A wait that would outlast
        # the window ends the daemon instead: sleeping into the wall-clock kill
        # buys nothing.
        decision = rate.check()
        if not decision["allowed"] and deadline is not None and (
                _dt_now() + timedelta(seconds=decision["wait_seconds"]) > deadline):
            totals["stopped"] = "deadline:" + decision["reason"]
            print("stop  next slot is past the window ({0})".format(decision["reason"]),
                  flush=True)
            return totals
        if not decision["allowed"]:
            nap = min(decision["wait_seconds"], 900)
            print("idle  {0}s ({1})".format(nap, decision["reason"]), flush=True)
            time.sleep(nap)


def report() -> int:
    backlog = load_backlog()
    items = backlog.get("items") or {}
    by_status: dict[str, int] = {}
    for state in items.values():
        by_status[state.get("status", "?")] = by_status.get(state.get("status", "?"), 0) + 1
    lib = videos_root() / "library"
    txts = list(lib.rglob("*.txt")) if lib.is_dir() else []
    chars = sum(p.stat().st_size for p in txts)
    print(json.dumps({
        "backlog_items": len(items),
        "by_status": by_status,
        "transcripts_on_disk": len(txts),
        "total_chars": chars,
        "quota_spent_today": youtube_api.spent_today(),
    }, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=None, help="Only process this many videos")
    p.add_argument("--video", default=None, help="Only this video id")
    p.add_argument("--refetch", action="store_true", help="Re-fetch even if a transcript exists")
    p.add_argument("--sleep", type=float, default=1.0, help="Seconds between caption fetches")
    p.add_argument("--report", action="store_true", help="Summarise corpus and backlog")
    p.add_argument("--daemon", action="store_true",
                   help="Wait for a pacing slot instead of stopping. Safe to leave running.")
    p.add_argument("--rate-status", action="store_true", help="Show pacing state and exit")
    p.add_argument("--hours", type=float, default=None,
                   help="With --daemon, stop after this many hours")
    args = p.parse_args()

    if args.rate_status:
        print(json.dumps(rate.status(), indent=2))
        return 0
    if args.report:
        return report()

    if args.daemon:
        stats = daemon(max_hours=args.hours, sleep_seconds=args.sleep)
    else:
        stats = run(limit=args.limit, only_video=args.video, refetch=args.refetch,
                    sleep_seconds=args.sleep, wait_for_slot=False)
    print("\n" + json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
