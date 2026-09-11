#!/usr/bin/env python3
"""What a video card says, and where that sentence comes from.

Every card on the video surface showed ``transcript[:260]``. On a spoken-word
corpus that is not a weak summary, it is the wrong field: the opening seconds of
a video are titles, applause and a host clearing their throat, so the published
text read ``[music] [music] [music] Thank you, man, for taking the time to talk
with me`` and ``[applause] [snofter] Hvor mange av dere har lagret hermetikk``.

Four sources can answer "what is this video about", and they are not equally
good, so they are tried in order and the winner is recorded. ``summary_source``
travels into the payload because a thesis the model wrote from verified claims
and a sentence lifted off the top of a transcript are different kinds of claim
on the reader's attention, and the surface should be able to say which it has.
"""
from __future__ import annotations

import re

# Sound marks are not speech. They appear mid-sentence as well as at the start,
# so this runs over the whole candidate, not just its head. Bounded to 24
# characters so it cannot eat a bracketed aside that carries meaning.
_SOUND_MARK = re.compile(r"\[[^\]]{1,24}\]")
# Filler the transcript opens on once the marks are gone.
_LEADING_FILLER = re.compile(
    r"^(?:(?:uh|um|er|ah|so|and|but|okay|ok|yeah|right|well|you know|i mean|"
    r"applause|music|musikk|laughter|foreign)[\s,.-]+)+",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


def strip_sound_marks(text: str) -> str:
    return _WS.sub(" ", _SOUND_MARK.sub(" ", str(text or ""))).strip()


def clean_preview(text: str, limit: int = 300) -> str:
    """A transcript opening with the non-speech taken out.

    The last resort in the chain below, and still worth cleaning: a video with
    no analysis and no description should show a readable sentence rather than
    a stage direction.
    """
    cleaned = _LEADING_FILLER.sub("", strip_sound_marks(text))
    if len(cleaned) <= limit:
        return cleaned.strip()
    cut = cleaned[:limit]
    # Prefer a sentence end, then a word boundary, over a mid-word truncation.
    for mark in (". ", "? ", "! "):
        idx = cut.rfind(mark)
        if idx > limit * 0.5:
            return cut[:idx + 1].strip()
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).strip() + "..."


def first_sentences(text: str, count: int = 2, limit: int = 300) -> str:
    """The opening of a YouTube description, which is usually written by a human.

    Descriptions run to chapter lists, sponsor links and social handles, so only
    the prose at the top is usable -- and the cut is made at a blank line as
    well as at sentence count, because the boilerplate is nearly always a
    paragraph break away from the summary.
    """
    head = str(text or "").split("\n\n")[0]
    head = strip_sound_marks(head)
    if not head:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", head)
    out = " ".join(parts[:count]).strip()
    return out[:limit].rstrip()


def card_summary(*, thesis: str = "", description: str = "", claim: str = "",
                 transcript_preview: str = "") -> tuple[str, str]:
    """The best available sentence about a video, and which source produced it.

    Order is by how much work stands behind the text. A thesis was written from
    claims whose quotes were each verified against the transcript. A description
    is a human's own summary, but of the video they were promoting. A claim is
    one verified assertion rather than a summary of the whole. The transcript
    opening is what is left when none of those exist.
    """
    thesis = strip_sound_marks(thesis)
    if thesis:
        return thesis, "thesis"
    described = first_sentences(description)
    if described:
        return described, "description"
    claim = strip_sound_marks(claim)
    if claim:
        return claim, "claim"
    preview = clean_preview(transcript_preview)
    if preview:
        return preview, "transcript"
    return "", "none"
