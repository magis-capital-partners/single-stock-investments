#!/usr/bin/env python3
"""Keep the timestamps that caption and Whisper fetches used to throw away.

Both transcript paths collapsed their segment lists into one flat string --
``" ".join(s.text for s in fetched)`` in fetch_video_transcript, and the same
shape over ``seg.text`` in fetch_podcast_transcript. The ``.start`` that arrived
free with every segment went on the floor, and a 51-minute interview became a
single 46,000-character line with no way back to a moment in the video.

That loss is what made video research strictly worse than reading a letter: a
deep link to ``&t=1234s`` is the one thing the medium can do that a PDF cannot.

The fix is a sidecar rather than a new transcript format. Three consumers read
the flat ``.txt`` today -- the relevance scorer, the alias matcher, and the
verbatim-quote check in the analysis stage -- and every admitted video's gate
decision was made against that exact text. Reshaping it would move the admission
gate and invalidate the ratchet baseline for reasons that have nothing to do
with relevance. So ``.txt`` stays byte-identical and the timing rides alongside.

**Offsets are recorded, not reconstructed.** Each segment carries ``c``, its
character offset into the finished text. Mapping a quote back to a timestamp is
then a bisect over a sorted list, not a re-derivation that has to reproduce the
original whitespace handling exactly. The analysis stage has already verified
that its quotes appear verbatim in the flat text, so the offset it hands us is
real and the lookup is exact.
"""
from __future__ import annotations

import bisect
import json
import re
from pathlib import Path

SIDECAR_SUFFIX = ".segments.json"

# Below this many characters a caption segment carries no positional
# information -- it is "And" or "now." and occurs everywhere -- so it may only
# be placed where the cursor already is, never used to jump.
MIN_ANCHOR_CHARS = 12
SHORT_JUMP_CHARS = 40
# How far a substantial segment may skip to re-synchronise after drifted text.
# Generous enough to cross a re-punctuated run, far short of the thousands of
# characters a coincidental match reached.
MAX_JUMP_CHARS = 800

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace runs the way both fetch paths already did."""
    return _WS.sub(" ", str(text or "")).strip()


def assemble(raw_segments) -> tuple[str, list[dict]]:
    """Build the flat transcript and the segment index in one pass.

    ``raw_segments`` yields ``(start_seconds, duration_seconds, text)``. Returns
    the text that the old one-liner produced -- byte for byte -- alongside the
    index describing it.

    The equivalence matters enough to spell out. The old code joined stripped
    segments with a space and then collapsed the result; this normalises each
    segment first and drops the ones that empty out. Both produce the same
    string: an empty segment contributed two adjacent join-spaces that the
    collapse folded back to one, and a segment with an internal newline was
    folded by that same collapse. Normalising first only moves when the folding
    happens, which is what lets the offsets be exact.
    """
    parts: list[str] = []
    segments: list[dict] = []
    offset = 0
    for start, duration, text in raw_segments:
        cleaned = normalize(text)
        if not cleaned:
            continue
        if parts:
            offset += 1  # the join space that precedes this segment
        segments.append({
            "t": round(float(start), 2) if start is not None else None,
            "d": round(float(duration), 2) if duration else None,
            "c": offset,
            "text": cleaned,
        })
        parts.append(cleaned)
        offset += len(cleaned)
    return " ".join(parts), segments


def index_parts(text: str, raw_segments) -> list[dict]:
    """Index segments against text the caller already built, without rebuilding it.

    ``assemble`` owns the joining and so knows every offset for free. The Whisper
    path does not: it joins with newlines, filters on the raw segment rather than
    the stripped one, and that exact expression decides what lands in every
    podcast transcript. Reproducing it here to recover offsets would mean two
    copies of a rule that only matters because it must not change.

    So this walks the finished text instead, advancing a cursor through it one
    segment at a time. A segment that cannot be found is skipped rather than
    guessed at -- the sidecar is allowed to be sparse, and a wrong timestamp is
    worse than a missing one.

    **A bounded jump is what makes the cursor survive drift.** Matching a
    re-generated caption track against the stored transcript, an unbounded
    ``find`` let short generic segments land anywhere downstream: ``'And'``,
    ``'now.'`` and ``'than'`` matched 3,000 to 10,000 characters ahead, dragging
    the cursor past everything between them. Seven such jumps reduced the XPeng
    interview from 519 usable anchors to 91, and opened a 10,416-character hole
    where the largest honest gap is 609.

    A segment's length is what licenses a jump, because length is what makes a
    match mean something: a four-character match carries no positional
    information, and a forty-character one does. Hence two bounds rather than
    one. Measured across nearby settings the result moves by about 2%, so these
    are a plateau rather than a fit to one video.
    """
    segments: list[dict] = []
    cursor = 0
    for start, duration, part in raw_segments:
        cleaned = str(part or "").strip()
        if not cleaned or start is None:
            continue
        idx = text.find(cleaned, cursor)
        if idx < 0:
            # A caption cue routinely wraps mid-sentence, and the transcript it
            # was assembled into collapsed that newline. Stripping alone does
            # not, so the cue's own text is not a substring of the transcript
            # built from it -- the segment goes missing from its own sidecar.
            cleaned = normalize(cleaned)
            idx = text.find(cleaned, cursor)
            if idx < 0:
                continue
        allowed = MAX_JUMP_CHARS if len(cleaned) >= MIN_ANCHOR_CHARS else SHORT_JUMP_CHARS
        if idx - cursor > allowed:
            continue
        segments.append({
            "t": round(float(start), 2),
            "d": round(float(duration), 2) if duration else None,
            "c": idx,
            "text": cleaned,
        })
        cursor = idx + len(cleaned)
    return segments


def sidecar_path(txt_path: Path) -> Path:
    return txt_path.with_name(txt_path.name.replace(".txt", "") + SIDECAR_SUFFIX)


def write_sidecar(txt_path: Path, segments: list[dict]) -> Path | None:
    """Write the segment index beside a transcript. No segments, no sidecar.

    A missing sidecar is a supported state, not a failure: every transcript
    fetched before this module existed has none, and the analysis stage simply
    publishes those claims without a timestamp.
    """
    if not segments:
        return None
    path = sidecar_path(txt_path)
    path.write_text(json.dumps(segments, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")
    return path


def load_sidecar(txt_path: Path) -> list[dict]:
    path = sidecar_path(txt_path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in doc if isinstance(row, dict) and row.get("t") is not None] \
        if isinstance(doc, list) else []


def offset_to_seconds(segments: list[dict], offset: int) -> float | None:
    """The start time of the segment containing this character offset."""
    if not segments or offset is None or offset < 0:
        return None
    starts = [int(row.get("c") or 0) for row in segments]
    idx = bisect.bisect_right(starts, int(offset)) - 1
    if idx < 0:
        idx = 0
    value = segments[idx].get("t")
    return float(value) if value is not None else None


def locate(text: str, quote: str, segments: list[dict]) -> float | None:
    """Find a verbatim quote in the transcript and return when it was said.

    Returns None when the quote is not a literal substring. That is the same
    condition the analysis stage uses to discard a claim, so a None here means
    the claim should not have survived -- worth failing quietly rather than
    guessing at a timestamp for text nobody said.
    """
    if not text or not quote or not segments:
        return None
    idx = text.find(quote)
    if idx < 0:
        # The transcript is whitespace-normalised; a quote that travelled
        # through JSON may not be.
        idx = text.find(normalize(quote))
        if idx < 0:
            return None
    return offset_to_seconds(segments, idx)


class SearchIndex:
    """Quote -> timestamp, searched in the same normalised space as the verifier.

    The analysis stage does not check a quote against the raw transcript. It
    folds curly apostrophes, en dashes and ellipses first, because the model
    writes "it's" where a published caption has "it's" and a literal check
    throws away a perfectly good quote over the encoding -- 32 of 37 claims on
    one episode. So a quote that verified may not appear in the raw text at all,
    and ``locate`` above would find nothing.

    Rebuilding the raw offset from the folded one is the wrong repair: the fold
    is not length-preserving (an ellipsis becomes three characters) and
    lowercasing is not either for every codepoint, so the mapping drifts.

    Instead the haystack is built from the segments using the caller's own
    normaliser. Both sides of the search then come from one construction, so
    they agree by definition rather than by a length argument that has to hold
    for every codepoint a caption can carry.

    **Gaps are sealed, not papered over.** A backfilled sidecar can be sparse:
    YouTube regenerated the XPeng interview's auto-captions with better
    punctuation, so only 556 of 1,371 segments still match the transcript the
    gate admitted. The survivors are correctly ordered -- the indexer only ever
    advances -- but joining them with a space would make two segments minutes
    apart read as adjacent, and a quote spanning that seam would be timed to the
    wrong moment. So a discontinuity is joined with a character no transcript
    contains, which cannot appear in a quote and therefore cannot be matched
    across. A quote inside a gap returns no timestamp, which is the honest
    answer.
    """

    SEAM = "\x00"

    __slots__ = ("haystack", "_offsets", "_times")

    def __init__(self, segments: list[dict], normalizer):
        parts: list[str] = []
        self._offsets: list[int] = []
        self._times: list[float] = []
        pos = 0
        prev_end: int | None = None
        for row in segments or []:
            raw = row.get("text") or ""
            cleaned = normalizer(raw)
            if not cleaned or row.get("t") is None:
                continue
            start = row.get("c")
            if parts:
                # One join space is what contiguous segments were written with;
                # anything else means text is missing between them.
                contiguous = (
                    prev_end is not None and start is not None
                    and int(start) == prev_end + 1
                )
                parts.append(" " if contiguous else self.SEAM)
                pos += 1
            self._offsets.append(pos)
            self._times.append(float(row["t"]))
            parts.append(cleaned)
            pos += len(cleaned)
            prev_end = (int(start) + len(raw)) if start is not None else None
        self.haystack = "".join(parts)

    def __bool__(self) -> bool:
        return bool(self._offsets)

    def seconds_for(self, needle: str) -> float | None:
        """When the speaker began the segment this quote starts in."""
        if not needle or not self._offsets:
            return None
        idx = self.haystack.find(needle)
        if idx < 0:
            return None
        pos = bisect.bisect_right(self._offsets, idx) - 1
        return self._times[max(pos, 0)]


def youtube_link(video_id: str, seconds: float | None) -> str:
    base = f"https://www.youtube.com/watch?v={video_id}"
    if seconds is None:
        return base
    return f"{base}&t={int(max(0.0, float(seconds)))}s"
