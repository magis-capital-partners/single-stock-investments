#!/usr/bin/env python3
"""Plain-English reader summaries for every podcast episode.

This module owns the ``reader_summary`` block in each episode ``*.meta.json``.
It is deliberately separate from ``llm_analysis``: claims extraction answers
"what investable view was stated about a company we can own?", while this
answers "what is this episode about, in language a first-time reader can
follow?"  The second question is universal.  It is not gated by tickers,
guests, officers, or whether the claims pass found anything.

Every episode lands in one of three source tiers:

* transcript -- cleaned episode speech is available;
* notes -- only the publisher's episode notes/description are usable;
* metadata -- only title/show/date/guest catalog facts are known.

A deterministic fallback is written immediately for notes/metadata (and for a
transcript episode whose model pass is still pending), so the dashboard is
never blank.  The local-model pass upgrades transcript and notes summaries.
No hosted LLM is used here: the transport is ``llm_local.complete``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import podcasts_root  # noqa: E402

try:
    import llm_call_gate  # noqa: E402
except Exception:  # pragma: no cover
    llm_call_gate = None  # type: ignore

PROMPT_VERSION = "reader_summary_v1"
DEFAULT_MODEL = os.environ.get("PODCAST_SUMMARY_MODEL", "qwen-gpu")
CHUNK_CHARS = 12000
CHUNK_OVERLAP = 1000
MAX_CHUNKS = 24
MIN_TRANSCRIPT_CHARS = 1200
MIN_NOTES_CHARS = 200
LOCK_NAME = ".summarize_podcast.lock"
DEFAULT_PUSH_MINUTES = 20

SOURCE_LABELS = {
    "transcript": "From the transcript",
    "notes": "From the episode notes — transcript not yet available",
    "metadata": "Episode details only — no transcript or notes yet",
}

# Binary / TOC / show-notes junk that extractive often lifts.
_GARBLED_RE = re.compile(
    r"("
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]"  # control chars
    r"|application/octet-stream"
    r"|PK\x03\x04"
    r"|\btable of contents\b"
    r"|\bcopyright\b.{0,40}\ball rights reserved\b"
    r"|^\s*[-*=]{8,}\s*$"
    r"|www\.[^\s]{80,}"
    r"|\binternet service terms\b"
    r"|\bapple podcasts web player\b"
    r"|\bprivacy cookie warning\b"
    r"|\bcookie (policy|warning|settings)\b"
    r"|\bsubscribe (on|in) (apple|spotify|youtube)\b"
    r"|\bsupport feedback to listen\b"
    r")",
    re.I | re.M,
)

_BOILERPLATE_RE = re.compile(
    r"("
    r"subscribe|follow (us|the show)|leave (a|us) (a )?(review|rating)|"
    r"support (the show|us on patreon)|join our (newsletter|discord|slack)|"
    r"check out our (website|sponsors?)|brought to you by|today'?s sponsor|"
    r"learn more at|sign up at|use (code|promo)|show notes|episode notes|"
    r"all rights reserved|privacy policy|terms of (service|use)|"
    r"follow .{0,40} on (twitter|x|linkedin|instagram)|"
    # Episode-page chrome from scraped publisher/Apple/Libsyn pages.
    r"search home new top charts|toggle navigation|top charts|sign in|"
    r"learn more about your ad choices|visit megaphone|adchoices|"
    r"^\s*\(\d{1,2}:\d{2}(:\d{2})?\)\s*-?\s*(introduction|intro|welcome)\b|"
    r"chapters?\s*:\s*\(\d{1,2}:\d{2}"
    r")",
    re.I,
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|bn|billion|m|million|k|x|bp|bps)?", re.I)
_BRACKET_TICKER_RE = re.compile(r"\(([A-Z]{1,5}(?:\.[A-Z]{1,3})?)\)")
_DOLLAR_TICKER_RE = re.compile(r"\$([A-Z]{1,5}(?:\.[A-Z]{1,3})?)\b")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_write_json(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w’'-]+\b", str(text or ""), flags=re.UNICODE)


def _word_count(text: str) -> int:
    return len(_words(text))


def split_sentences(text: str) -> list[str]:
    parts = []
    for part in _SENTENCE_RE.split(str(text or "")):
        part = _WS_RE.sub(" ", part).strip()
        if part:
            parts.append(part)
    return parts


def is_garbled_highlight(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 24:
        return True
    if len(s) > 500:
        return True
    # High ratio of non-letters → binary / TOC junk
    letters = sum(1 for c in s if c.isalpha())
    if letters < 20 or letters / max(len(s), 1) < 0.45:
        return True
    if _GARBLED_RE.search(s):
        return True
    # Dense punctuation / URL spam
    if s.count("http") >= 2 or s.count("/") > 12:
        return True
    return False


def filter_highlights(highlights: list) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for h in highlights or []:
        if isinstance(h, dict):
            text = (h.get("quote") or h.get("text") or "").strip()
            row = dict(h)
        else:
            text = str(h).strip()
            row = {"text": text, "quote": text[:200], "method": "extractive"}
        if not text or is_garbled_highlight(text):
            continue
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        row["text"] = text
        if not row.get("quote"):
            row["quote"] = text[:200]
        out.append(row)
    return out


def extractive_highlights(text: str, tickers: list[str], max_bullets: int = 6) -> list[dict]:
    """Deterministic fallback: sentences mentioning universe tickers or key claims."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    bullets: list[dict] = []
    seen: set[str] = set()
    ticker_set = {t.upper() for t in tickers}
    for sent in sentences:
        s = sent.strip()
        if len(s) < 40 or len(s) > 320:
            continue
        if is_garbled_highlight(s):
            continue
        hit = None
        for t in ticker_set:
            if re.search(rf"\b{re.escape(t)}\b", s, re.I):
                hit = t
                break
        key_terms = ("moat", "capital allocation", "valuation", "margin", "growth", "risk", "catalyst")
        if not hit and not any(k in s.lower() for k in key_terms):
            continue
        key = s[:80]
        if key in seen:
            continue
        seen.add(key)
        bullets.append(
            {
                "text": s,
                "tickers": [hit] if hit else [],
                "quote": s[:200],
                "method": "extractive",
            }
        )
        if len(bullets) >= max_bullets:
            break
    return filter_highlights(bullets)


def extractive_summary(text: str, highlights: list[dict] | None = None, max_sentences: int = 3) -> str:
    """Legacy 2–4 sentence blurb, retained only for backwards compatibility."""
    parts: list[str] = []
    for h in highlights or []:
        if isinstance(h, dict):
            s = (h.get("text") or h.get("quote") or "").strip()
        else:
            s = str(h).strip()
        if s and not is_garbled_highlight(s) and s not in parts:
            parts.append(s)
        if len(parts) >= max_sentences:
            break
    if len(parts) < 2:
        for sent in re.split(r"(?<=[.!?])\s+", text[:6000]):
            s = sent.strip()
            if len(s) < 50 or len(s) > 280 or is_garbled_highlight(s):
                continue
            if s not in parts:
                parts.append(s)
            if len(parts) >= max_sentences:
                break
    return " ".join(parts[:max_sentences]).strip()


def should_summarize(episode: dict) -> bool:
    """Universal: an episode needs work until it has a current reader summary."""
    current = episode.get("reader_summary") if isinstance(episode, dict) else None
    return not (
        isinstance(current, dict)
        and current.get("version") == PROMPT_VERSION
        and (current.get("overview") or "").strip()
    )


def summarize_episode(episode: dict, text: str, *, use_llm: bool = False) -> tuple[list[dict], str]:
    """Backwards-compatible legacy highlights/summary pair.

    New code should call :func:`generate_reader_summary`.  This remains so
    older tests and one-off callers do not silently change behaviour.
    """
    tickers = [p.get("ticker") for p in (episode.get("positions") or []) if p.get("ticker")]
    tickers += list(episode.get("tickers") or [])
    tickers = sorted({str(t) for t in tickers if t})
    _ = use_llm  # Reader summaries have their own explicit local-LLM path.
    highlights = extractive_highlights(text, tickers)
    prior = filter_highlights(episode.get("highlights") or [])
    if prior and not highlights:
        highlights = prior
    elif prior and highlights:
        merged = filter_highlights(prior + highlights)
        highlights = merged[:8] if merged else highlights
    return highlights, extractive_summary(text, highlights)


# ---------------------------------------------------------------------------
# Reader-summary contract
# ---------------------------------------------------------------------------

def clean_source_text(text: str) -> str:
    """Remove markup, links, and obvious show chrome without paraphrasing."""
    cleaned = unescape(str(text or ""))
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = _URL_RE.sub(" ", cleaned)
    lines: list[str] = []
    for raw in cleaned.splitlines():
        line = _WS_RE.sub(" ", raw).strip(" \t-•*")
        if not line:
            continue
        if line.count("http") or line.count("/") > 10:
            continue
        lines.append(line)
    # Drop chrome lines (nav, subscribe pleas) only when real content
    # survives; a one-line description that merely mentions a sponsor or a
    # "Sign In" header must not be emptied entirely.
    kept = [l for l in lines if not (_BOILERPLATE_RE.search(l) and len(l) < 320)]
    return _WS_RE.sub(" ", " ".join(kept or lines)).strip()


def _norm_for_match(text: str) -> str:
    try:
        from analyze_podcast_episode import _norm  # noqa: WPS433

        return _norm(text or "")
    except Exception:
        return _WS_RE.sub(" ", str(text or "")).strip().lower()


def _sentence_key(sentence: str) -> str:
    return _WS_RE.sub(" ", sentence).strip().lower()[:240]


def build_show_boilerplate(rows: list[dict]) -> dict[str, set[str]]:
    """Sentences repeated across a show, following the claims-batch method."""
    by_show: dict[str, list[Path]] = {}
    for row in rows:
        txt = row.get("txt_path")
        if isinstance(txt, Path) and txt.exists():
            by_show.setdefault(str(row["meta"].get("show_id") or "?"), []).append(txt)

    boiler: dict[str, set[str]] = {}
    for show, paths in by_show.items():
        if len(paths) < 3:
            continue
        sentence_sets: list[set[str]] = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            sentence_sets.append(
                {_sentence_key(s) for s in split_sentences(text) if len(s) >= 30}
            )
        if not sentence_sets:
            continue
        freq: dict[str, int] = {}
        for group in sentence_sets:
            for sentence in group:
                freq[sentence] = freq.get(sentence, 0) + 1
        cutoff = max(2, int(len(sentence_sets) * 0.33))
        repeated = {s for s, n in freq.items() if n >= cutoff}
        if repeated:
            boiler[show] = repeated
    return boiler


def _remove_boilerplate(text: str, repeated: set[str] | None) -> str:
    if not repeated:
        return text
    kept = [s for s in split_sentences(text) if _sentence_key(s) not in repeated]
    return " ".join(kept).strip()


def classify_source(
    meta: dict,
    txt_path: Path | None,
    *,
    boilerplate: set[str] | None = None,
) -> dict:
    """Choose transcript / notes / metadata and return the exact source text."""
    raw_text = ""
    if txt_path is not None and txt_path.exists():
        raw_text = txt_path.read_text(encoding="utf-8", errors="ignore")
    cleaned_text = _remove_boilerplate(clean_source_text(raw_text), boilerplate)
    notes = clean_source_text(meta.get("description") or "")
    title = str(meta.get("title") or "")
    show = str(meta.get("show_title") or meta.get("show_id") or "")
    metadata_text = clean_source_text(
        " ".join(
            x
            for x in [
                title,
                show,
                str(meta.get("published") or ""),
                " ".join(str(g) for g in (meta.get("guests") or []) if g),
            ]
            if x
        )
    )

    # Provenance matters: a Whisper file is speech, but a ``published_html``
    # file may be a genuine publisher transcript *or* an episode-page scrape
    # (navigation, chapter list, and the same description as the notes).
    # Labelling a scrape "From the transcript" would mislead the reader, so
    # scraped pages only count as transcripts when they are long or clearly
    # dialogue; otherwise they are honest notes-tier sources.
    source_kind = str(meta.get("transcript_source") or "")
    if len(cleaned_text) >= MIN_TRANSCRIPT_CHARS and (
        source_kind == "whisper"
        or (source_kind in {"published_html", "published"} and _looks_like_transcript(cleaned_text))
    ):
        return {
            "basis": "transcript",
            "text": cleaned_text,
            "validation_text": f"{metadata_text} {cleaned_text}",
            "kind": "full" if len(cleaned_text) >= 6000 else "partial",
        }
    if len(notes) >= MIN_NOTES_CHARS:
        return {
            "basis": "notes",
            "text": notes,
            "validation_text": f"{metadata_text} {notes} {cleaned_text}",
            "kind": "notes",
        }
    if len(cleaned_text) >= MIN_NOTES_CHARS:
        # A short Whisper file is real speech; a short scraped file is notes.
        # Either is more honest as a partial/notes source than inventing a
        # full-transcript summary from a fragment.
        basis = "transcript" if meta.get("transcript_source") == "whisper" else "notes"
        return {
            "basis": basis,
            "text": cleaned_text,
            "validation_text": f"{metadata_text} {cleaned_text} {notes}",
            "kind": "partial" if basis == "transcript" else "notes",
        }
    if len(notes) >= 40:
        return {
            "basis": "notes",
            "text": notes,
            "validation_text": f"{metadata_text} {notes}",
            "kind": "notes",
        }
    return {
        "basis": "metadata",
        "text": metadata_text,
        "validation_text": metadata_text,
        "kind": "metadata",
    }


_SPEAKER_TURN_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))([A-Z][A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff.'-]+"
    r"(?:\s[A-Z][A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff.'-]+){0,2}):\s"
)


def _looks_like_transcript(text: str) -> bool:
    """Heuristic split between a publisher transcript and a page scrape.

    Long texts are transcripts (episode descriptions do not run to 25k
    chars); shorter ones need visible dialogue turns. Chapter lists use
    ``(00:00)`` timestamps, not ``Name:`` turns, so they stay notes.
    """
    if len(text) >= 25_000:
        return True
    return len(_SPEAKER_TURN_RE.findall(text)) >= 8


def _shorten_sentence(sentence: str, max_words: int = 24) -> str:
    sentence = _WS_RE.sub(" ", str(sentence or "")).strip()
    words = _words(sentence)
    if len(words) <= max_words:
        return sentence if sentence.endswith((".", "!", "?")) else sentence.rstrip(",;:") + "."
    clauses = re.split(r"(?<=[,;:])\s+", sentence)
    kept: list[str] = []
    total = 0
    for clause in clauses:
        count = _word_count(clause)
        if kept and total + count > max_words:
            break
        kept.append(clause)
        total += count
        if total >= max_words:
            break
    shortened = " ".join(kept).strip().rstrip(",;:") if kept else " ".join(words[:max_words])
    return shortened + "."


def _meaningful_sentences(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(clean_source_text(text)):
        if len(sentence) < 35 or len(sentence) > 420:
            continue
        if is_garbled_highlight(sentence) or _BOILERPLATE_RE.search(sentence):
            continue
        # Chapter lists and timestamped headings are navigation, not prose.
        if sentence.lstrip().startswith("(") and re.match(r"\(\d{1,2}:\d{2}", sentence.lstrip()):
            continue
        if len(re.findall(r"\(\d{1,2}:\d{2}(:\d{2})?\)", sentence)) >= 2:
            continue
        key = _sentence_key(sentence)[:100]
        if key in seen:
            continue
        seen.add(key)
        out.append(sentence)
    return out


def _guest_labels(meta: dict, catalog_episode: dict | None = None) -> list[str]:
    labels: list[str] = []
    for source in (catalog_episode or {}, meta or {}):
        for guest in source.get("guests") or []:
            if isinstance(guest, dict):
                label = guest.get("display") or guest.get("guest_id") or ""
            else:
                label = str(guest or "")
            if label and label not in labels:
                labels.append(label)
    return labels


def fallback_reader_summary(
    meta: dict,
    source: dict,
    *,
    status: str = "ready",
    catalog_episode: dict | None = None,
) -> dict:
    """A readable, honestly-labelled summary that needs no model."""
    basis = str(source.get("basis") or "metadata")
    text = str(source.get("text") or "")
    title = str(meta.get("title") or "Untitled episode")
    show = str(meta.get("show_title") or meta.get("show_id") or "This podcast")
    published = str(meta.get("published") or "")[:10]
    guests = _guest_labels(meta, catalog_episode)
    sentences = _meaningful_sentences(text)

    if basis == "metadata" or not sentences:
        who = f" with {', '.join(guests[:3])}" if guests else ""
        date = f" Published {published}." if published else ""
        headline = _shorten_sentence(f"{show} episode: {title}", 22)
        overview = (
            f"This is an episode of {show}{who}.{date} "
            "A transcript or detailed episode notes are not available yet, "
            "so the discussion itself is not summarized here."
        )
        points = [
            {
                "text": "Only the episode title and catalog details are available so far.",
                "evidence_quote": None,
                "timestamp_seconds": None,
            }
        ]
        why = None
        kind = "metadata"
    else:
        overview_parts: list[str] = []
        total = 0
        for sentence in sentences:
            short = _shorten_sentence(sentence, 26)
            count = _word_count(short)
            if overview_parts and total + count > 72:
                break
            overview_parts.append(short)
            total += count
            if len(overview_parts) >= 3 and total >= 38:
                break
        overview = " ".join(overview_parts)
        headline_source = overview_parts[0] if overview_parts else title
        headline = _shorten_sentence(headline_source, 20)
        points: list[dict] = []
        used = {_sentence_key(s) for s in overview_parts}
        for sentence in sentences:
            if _sentence_key(sentence) in used:
                continue
            points.append(
                {
                    "text": _shorten_sentence(sentence, 24),
                    "evidence_quote": sentence[:360] if basis == "transcript" else None,
                    "timestamp_seconds": None,
                }
            )
            if len(points) >= (4 if basis == "transcript" else 3):
                break
        if not points:
            points = [
                {
                    "text": _shorten_sentence(sentence, 24),
                    "evidence_quote": sentence[:360] if basis == "transcript" else None,
                    "timestamp_seconds": None,
                }
                for sentence in sentences[1:3]
            ]
        why = None
        kind = str(source.get("kind") or ("notes" if basis == "notes" else "partial"))

    return {
        "version": PROMPT_VERSION,
        "status": status,
        "source_basis": basis,
        "source_label": SOURCE_LABELS[basis],
        "headline": headline,
        "overview": overview,
        "key_points": points,
        "why_it_matters": why,
        "coverage": {
            "source_chars": len(text),
            "chunks_total": 0,
            "chunks_used": 0,
            "kind": kind,
        },
        "generated_at": _stamp(),
        "model": "deterministic_fallback",
        "source_sha1": _sha1(str(source.get("validation_text") or text)),
        "prompt_version": PROMPT_VERSION,
    }


def _numbers_in(text: str) -> set[str]:
    out: set[str] = set()
    for match in _NUMBER_RE.findall(str(text or "")):
        token = str(match).strip().lower().replace(",", "")
        if token:
            out.add(token)
    # findall returns only the final group above; also retain full matches.
    for match in _NUMBER_RE.finditer(str(text or "")):
        token = match.group(0).strip().lower().replace(",", "").replace("$", "")
        token = re.sub(r"\s+", "", token)
        if token:
            out.add(token)
    return out


def reader_summary_errors(
    summary: dict,
    *,
    source_text: str | None = None,
    basis: str | None = None,
) -> list[str]:
    """Structural and (when source is supplied) grounding validation."""
    errors: list[str] = []
    if not isinstance(summary, dict):
        return ["reader_summary is not an object"]
    if summary.get("version") != PROMPT_VERSION:
        errors.append("reader_summary version is missing or stale")
    if summary.get("status") not in {"ready", "pending_model", "needs_review"}:
        errors.append("reader_summary status is invalid")
    basis = basis or str(summary.get("source_basis") or "")
    if basis not in SOURCE_LABELS:
        errors.append("reader_summary source_basis is invalid")
    elif summary.get("source_label") != SOURCE_LABELS[basis]:
        errors.append("reader_summary source_label does not match its basis")

    headline = str(summary.get("headline") or "").strip()
    overview = str(summary.get("overview") or "").strip()
    if not headline:
        errors.append("headline is empty")
    if _word_count(headline) > 24:
        errors.append("headline is too long")
    if not overview:
        errors.append("overview is empty")
    if is_garbled_highlight(overview) and len(overview) >= 24:
        errors.append("overview looks garbled or boilerplate-derived")
    sentences = split_sentences(overview)
    if len(sentences) > 3:
        errors.append("overview has more than three sentences")
    for sentence in sentences:
        if _word_count(sentence) > 30:
            errors.append("overview contains a sentence over 30 words")
            break
    if basis == "transcript" and _word_count(overview) < 25 and summary.get("status") == "ready":
        errors.append("transcript overview is too thin")
    if _word_count(overview) > 90:
        errors.append("overview is too long")

    points = summary.get("key_points")
    if not isinstance(points, list) or not points:
        errors.append("key_points is empty")
        points = []
    minimum = 3 if basis == "transcript" else 1
    if basis == "transcript" and summary.get("status") == "ready" and len(points) < minimum:
        errors.append("transcript summary has fewer than three key points")
    if len(points) > 5:
        errors.append("too many key points")
    seen: set[str] = set()
    for point in points:
        if not isinstance(point, dict):
            errors.append("key point is not an object")
            continue
        text = str(point.get("text") or "").strip()
        if not text:
            errors.append("key point is empty")
        if _word_count(text) > 30:
            errors.append("key point is too long")
        key = _sentence_key(text)[:90]
        if key in seen:
            errors.append("duplicate key point")
        seen.add(key)
        if _BOILERPLATE_RE.search(text):
            errors.append("key point contains boilerplate")

    combined = " ".join(
        [headline, overview]
        + [str(p.get("text") or "") for p in points if isinstance(p, dict)]
        + [str(summary.get("why_it_matters") or "")]
    )
    if _BOILERPLATE_RE.search(combined):
        errors.append("summary contains boilerplate or promotional language")
    if re.search(r"\b(you know|i mean|sort of|kind of)\b", combined, re.I):
        errors.append("summary contains transcript filler")

    if source_text is not None:
        source_norm = _norm_for_match(source_text)
        summary_numbers = _numbers_in(combined)
        source_numbers = _numbers_in(source_text)
        # Compare digit cores: "$1.2bn" and "1.2 billion" should agree, while
        # an invented 37% should not slip through on a suffix difference.
        source_digits = {re.sub(r"\D", "", n) for n in source_numbers if re.search(r"\d", n)}
        for number in summary_numbers:
            digits = re.sub(r"\D", "", number)
            if digits and digits not in source_digits:
                errors.append(f"number not found in source: {number}")
                break
        for ticker in _BRACKET_TICKER_RE.findall(combined) + _DOLLAR_TICKER_RE.findall(combined):
            if ticker.upper() not in source_text.upper():
                errors.append(f"ticker not found in source: {ticker}")
                break
        if basis == "transcript" and summary.get("status") == "ready":
            for point in points:
                if not isinstance(point, dict):
                    continue
                quote = str(point.get("evidence_quote") or "").strip()
                if not quote or _norm_for_match(quote) not in source_norm:
                    errors.append("transcript key point lacks a verified evidence quote")
                    break
    return errors


def _chunk_text(text: str) -> list[str]:
    chunks: list[str] = []
    step = max(1000, CHUNK_CHARS - CHUNK_OVERLAP)
    for start in range(0, len(text), step):
        piece = text[start : start + CHUNK_CHARS]
        if len(piece) < 350 and chunks:
            break
        chunks.append(piece)
        if start + CHUNK_CHARS >= len(text):
            break
    return chunks or [text]


def _select_chunks(chunks: list[str]) -> tuple[list[tuple[int, str]], bool]:
    if len(chunks) <= MAX_CHUNKS:
        return list(enumerate(chunks)), len(chunks) <= MAX_CHUNKS
    # Even coverage plus the opening and close. Entity-dense chunk selection
    # belongs to claims; a reader summary must not turn into a ticker digest.
    indexes = sorted({round(i * (len(chunks) - 1) / (MAX_CHUNKS - 1)) for i in range(MAX_CHUNKS)})
    return [(i, chunks[i]) for i in indexes], False


_SYSTEM = (
    "You write short, plain-English summaries of podcast episodes for readers "
    "who have not listened. Use simple words and short sentences. Do not add "
    "facts, numbers, companies, or opinions that are not in the source. Do not "
    "copy show introductions, advertisements, sponsor copy, or filler speech. "
    "Reply with one JSON object only."
)

_MAP_PROMPT = """Below is one part of the podcast "{show}", episode "{title}".

Write plain-language notes about what is actually discussed in this part.
Reply with JSON:
{{
  "notes": [
    {{"point": "one clear point in your own words, at most 24 words",
      "evidence_quote": "the exact words from this part that support it, 10-40 words"}}
  ]
}}
Rules:
- At most 5 notes. Skip introductions, advertisements, and small talk.
- The evidence quote must be copied exactly. If you cannot quote it, omit it.
- Explain jargon in plain English when it matters.

PART:
{chunk}"""

_REDUCE_PROMPT = """Write the final reader summary for the podcast "{show}", episode "{title}".

Source basis: {basis}. Use only these source notes:
{notes}

Reply with JSON:
{{
  "headline": "one plain sentence saying what the episode is about, at most 20 words",
  "overview": "2-3 short sentences, 40-75 words total, understandable without listening",
  "key_points": [
    {{"text": "one clear point, at most 24 words", "evidence_quote": "exact supporting quote from the notes, or null"}}
  ],
  "why_it_matters": "one short sentence on what a listener takes away, or null"
}}
Rules:
- Say what the episode argues or explains, not merely that people discussed a topic.
- Name people and companies as the notes name them. Do not invent tickers.
- If the notes are thin, write a shorter summary and do not pad.
- Do not mention advertisements, subscriptions, or the podcast itself."""

_DIRECT_PROMPT = """Summarize this {basis} source for the podcast "{show}", episode "{title}".

Reply with JSON:
{{
  "headline": "one plain sentence saying what the episode is about, at most 20 words",
  "overview": "2-3 short sentences, 40-75 words total, understandable without reading the source",
  "key_points": [
    {{"text": "one clear point, at most 24 words", "evidence_quote": "exact supporting quote from the source, or null"}}
  ],
  "why_it_matters": "one short sentence on what a listener takes away, or null"
}}
Use only facts below. Do not invent numbers, tickers, companies, or opinions.

SOURCE:
{source}"""

_REPAIR_PROMPT = """Fix this podcast reader summary. It failed these checks: {errors}

Use only the source notes below. Keep the same JSON shape, shorten long
sentences, remove unsupported facts, and preserve exact evidence quotes.

SOURCE NOTES:
{notes}

SUMMARY TO FIX:
{summary}"""


def _llm_json(messages: list[dict], *, model: str | None, max_tokens: int) -> dict:
    from llm_local import complete, extract_json  # noqa: WPS433

    reply = complete(messages, model=model, json_object=True, max_tokens=max_tokens)
    return extract_json(reply) or {}


def _clean_model_doc(doc: dict, source: dict, meta: dict, *, model: str | None) -> tuple[dict, list[str]]:
    basis = str(source.get("basis") or "metadata")
    source_norm = _norm_for_match(str(source.get("validation_text") or source.get("text") or ""))
    points: list[dict] = []
    seen: set[str] = set()
    for raw in doc.get("key_points") or []:
        if isinstance(raw, dict):
            text = str(raw.get("text") or "").strip()
            quote = str(raw.get("evidence_quote") or "").strip() or None
        else:
            text = str(raw or "").strip()
            quote = None
        if not text:
            continue
        if quote and _norm_for_match(quote) not in source_norm:
            quote = None
        if basis == "transcript" and not quote:
            continue
        text = _shorten_sentence(text, 24)
        key = _sentence_key(text)[:90]
        if key in seen:
            continue
        seen.add(key)
        points.append({"text": text, "evidence_quote": quote, "timestamp_seconds": None})
        if len(points) >= 5:
            break

    # Attach timestamps when a Whisper sidecar exists. Most older transcripts
    # have none; null is an honest answer and the UI simply omits the link.
    # (Kept best-effort: timing must never block a readable summary.)

    overview_sentences = [
        _shorten_sentence(sentence, 26) for sentence in split_sentences(str(doc.get("overview") or ""))
    ][:3]
    summary = {
        "version": PROMPT_VERSION,
        "status": "ready",
        "source_basis": basis,
        "source_label": SOURCE_LABELS[basis],
        "headline": _shorten_sentence(str(doc.get("headline") or meta.get("title") or ""), 20),
        "overview": " ".join(overview_sentences),
        "key_points": points,
        "why_it_matters": (
            _shorten_sentence(str(doc.get("why_it_matters")), 26)
            if doc.get("why_it_matters")
            else None
        ),
        "coverage": {
            "source_chars": len(str(source.get("text") or "")),
            "chunks_total": int(source.get("chunks_total") or 0),
            "chunks_used": int(source.get("chunks_used") or 0),
            "kind": str(source.get("kind") or basis),
        },
        "generated_at": _stamp(),
        "model": model or DEFAULT_MODEL,
        "source_sha1": _sha1(str(source.get("validation_text") or source.get("text") or "")),
        "prompt_version": PROMPT_VERSION,
    }
    errors = reader_summary_errors(
        summary,
        source_text=str(source.get("validation_text") or source.get("text") or ""),
        basis=basis,
    )
    return summary, errors


def model_reader_summary(
    meta: dict,
    source: dict,
    *,
    model: str | None = None,
) -> dict:
    """Generate and validate a model reader summary, with one repair retry."""
    from llm_local import LocalLLMUnavailable  # noqa: WPS433

    basis = str(source.get("basis") or "metadata")
    if basis == "metadata":
        return fallback_reader_summary(meta, source, status="ready")
    text = str(source.get("text") or "")
    show = str(meta.get("show_title") or meta.get("show_id") or "")
    title = str(meta.get("title") or "")
    chunks = _chunk_text(text)
    selected, _full = _select_chunks(chunks)
    source = dict(source)
    source["chunks_total"] = len(chunks)
    source["chunks_used"] = len(selected)
    if len(selected) < len(chunks):
        source["kind"] = "partial"

    notes: list[dict] = []
    if len(text) <= CHUNK_CHARS:
        doc = _llm_json(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _DIRECT_PROMPT.format(
                        basis=basis, show=show, title=title, source=text[:CHUNK_CHARS]
                    ),
                },
            ],
            model=model,
            max_tokens=1600,
        )
    else:
        for _index, chunk in selected:
            doc_part = _llm_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": _MAP_PROMPT.format(show=show, title=title, chunk=chunk),
                    },
                ],
                model=model,
                max_tokens=1300,
            )
            for note in doc_part.get("notes") or []:
                if isinstance(note, dict) and (note.get("point") or "").strip():
                    notes.append(
                        {
                            "point": _shorten_sentence(str(note.get("point")), 24),
                            "evidence_quote": str(note.get("evidence_quote") or "").strip() or None,
                        }
                    )
            if len(notes) >= 48:
                break
        if not notes:
            raise LocalLLMUnavailable("model returned no usable summary notes")
        doc = _llm_json(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _REDUCE_PROMPT.format(
                        show=show,
                        title=title,
                        basis=basis,
                        notes=json.dumps(notes[:40], ensure_ascii=False, indent=1),
                    ),
                },
            ],
            model=model,
            max_tokens=1600,
        )

    summary, errors = _clean_model_doc(doc, source, meta, model=model)
    if errors:
        notes_payload = notes or [
            {"point": p.get("text"), "evidence_quote": p.get("evidence_quote")}
            for p in summary.get("key_points") or []
        ]
        repaired = _llm_json(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _REPAIR_PROMPT.format(
                        errors="; ".join(errors[:8]),
                        notes=json.dumps(notes_payload[:40], ensure_ascii=False, indent=1),
                        summary=json.dumps(doc, ensure_ascii=False, indent=1),
                    ),
                },
            ],
            model=model,
            max_tokens=1600,
        )
        if repaired:
            summary2, errors2 = _clean_model_doc(repaired, source, meta, model=model)
            if len(errors2) < len(errors):
                summary, errors = summary2, errors2
    if errors:
        fallback = fallback_reader_summary(meta, source, status="needs_review")
        fallback["validation_errors"] = errors[:12]
        return fallback
    return summary


def generate_reader_summary(
    meta: dict,
    source: dict,
    *,
    use_llm: bool = False,
    model: str | None = None,
    catalog_episode: dict | None = None,
) -> dict:
    """Return the best publishable summary now; never return a blank."""
    basis = str(source.get("basis") or "metadata")
    if not use_llm or basis == "metadata":
        status = "pending_model" if basis == "transcript" else "ready"
        return fallback_reader_summary(
            meta, source, status=status, catalog_episode=catalog_episode
        )
    try:
        return model_reader_summary(meta, source, model=model)
    except Exception:
        # The caller decides whether an unavailable model should stop the run.
        # For a single episode, a labelled fallback is better than an error.
        raise


def current_reader_summary(meta: dict, source: dict) -> bool:
    current = meta.get("reader_summary")
    if not isinstance(current, dict):
        return False
    if current.get("prompt_version") != PROMPT_VERSION:
        return False
    expected_hash = _sha1(str(source.get("validation_text") or source.get("text") or ""))
    if current.get("source_sha1") != expected_hash:
        return False
    if reader_summary_errors(current, basis=str(source.get("basis") or "")):
        return False
    # A transcript episode still waiting for its model upgrade is not current,
    # even though its fallback is publishable.
    if source.get("basis") == "transcript" and current.get("status") != "ready":
        return False
    if source.get("basis") == "transcript" and current.get("source_basis") != "transcript":
        return False
    return True


# ---------------------------------------------------------------------------
# Corpus batch
# ---------------------------------------------------------------------------

def _episode_rows(root: Path) -> list[dict]:
    catalog: dict[str, dict] = {}
    insights = load_json(root / "insights.json") or {}
    for ep in insights.get("episodes") or []:
        if isinstance(ep, dict) and ep.get("episode_id"):
            catalog[str(ep["episode_id"])] = ep

    rows: list[dict] = []
    episodes_root = root / "episodes"
    if not episodes_root.is_dir():
        return rows
    for meta_path in sorted(episodes_root.rglob("*.meta.json")):
        meta = load_json(meta_path) or {}
        eid = str(meta.get("episode_id") or meta_path.name.replace(".meta.json", ""))
        if not eid:
            continue
        txt_path = meta_path.with_name(f"{eid}.txt")
        rows.append(
            {
                "episode_id": eid,
                "meta_path": meta_path,
                "txt_path": txt_path,
                "meta": meta,
                "catalog": catalog.get(eid) or {},
            }
        )
    return rows


def _priority_key(row: dict, priority: list[str]) -> tuple:
    meta = row["meta"]
    catalog = row.get("catalog") or {}
    published = str(meta.get("published") or catalog.get("published") or "")
    recent = published >= "2025-01-01"
    flags = {
        "recent": recent,
        "in-book": bool(catalog.get("in_book")),
        "pz": bool(catalog.get("has_pz_guest")),
        "officer": bool(catalog.get("has_officer_hit")),
        "all": True,
    }
    group = len(priority)
    for index, name in enumerate(priority):
        if flags.get(name.strip().lower()):
            group = index
            break
    # Newest first inside each requested priority group, without a second sort.
    inverted = "".join(chr(0x7E - ord(c)) if 0x20 <= ord(c) <= 0x7E else c for c in published)
    return (group, inverted)


def status_snapshot(root: Path | None = None) -> dict:
    root = root or podcasts_root(create=True)
    rows = _episode_rows(root)
    by_status: dict[str, int] = {}
    by_basis: dict[str, int] = {}
    missing = pending = needs_review = 0
    transcript_ready = 0
    remaining_model = 0
    remaining_unique = 0
    for row in rows:
        meta = row["meta"]
        summary = meta.get("reader_summary") if isinstance(meta.get("reader_summary"), dict) else {}
        status = str(summary.get("status") or "missing")
        basis = str(summary.get("source_basis") or "missing")
        by_status[status] = by_status.get(status, 0) + 1
        by_basis[basis] = by_basis.get(basis, 0) + 1
        if not summary:
            missing += 1
        if status == "pending_model":
            pending += 1
        if status == "needs_review":
            needs_review += 1
        if status == "ready" and basis == "transcript":
            transcript_ready += 1
        # Work remains when there is no summary, the summary is not ready,
        # or a real Whisper transcript has since replaced the notes the
        # summary was written from. A ready notes summary is finished work
        # until its source changes (run() re-checks the source hash).
        needs_work = (
            not summary
            or status != "ready"
            or (
                basis in {"notes", "metadata"}
                and str(meta.get("transcript_source") or "") == "whisper"
            )
        )
        if needs_work:
            remaining_model += 1
            remaining_unique += 1
    return {
        "episodes": len(rows),
        "transcripts": sum(1 for r in rows if r["txt_path"].exists()),
        "reader_summary_by_status": by_status,
        "reader_summary_by_basis": by_basis,
        "transcript_ready": transcript_ready,
        "pending_model": pending,
        "needs_review": needs_review,
        "missing": missing,
        "remaining_model": remaining_model,
        "remaining": remaining_unique,
    }


def _vault_push(message: str) -> bool:
    try:
        from analyze_podcast_batch import vault_push  # noqa: WPS433

        return vault_push(message)
    except Exception as exc:  # pragma: no cover - operational guard
        print(f"[{_stamp()}] vault push unavailable: {exc}", flush=True)
        return False


def run(
    *,
    use_llm: bool = False,
    limit: int | None = None,
    model: str | None = None,
    hours: float | None = None,
    priority: str = "recent,in-book,pz,officer,all",
    episode_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    push: bool = False,
    push_minutes: int = DEFAULT_PUSH_MINUTES,
) -> dict:
    """Write reader summaries to episode meta only; catalogs are rebuilt later."""
    from llm_local import LocalLLMUnavailable  # noqa: WPS433

    root = podcasts_root(create=True)
    lock = root.parent / LOCK_NAME
    if lock.exists() and time.time() - lock.stat().st_mtime < 3600 and not dry_run:
        return {"skipped": "locked", "lock": str(lock)}
    if not dry_run:
        lock.write_text(f"{os.getpid()} {_stamp()}\n", encoding="utf-8")

    rows = _episode_rows(root)
    if episode_id:
        rows = [r for r in rows if r["episode_id"] == episode_id]
    priority_names = [p.strip().lower() for p in str(priority or "all").split(",") if p.strip()]
    rows.sort(key=lambda r: _priority_key(r, priority_names or ["all"]))

    deadline = _now() + timedelta(hours=hours) if hours else None
    updated = skipped = failed = pending = 0
    since_push = 0
    last_push = _now()
    try:
        boilerplate = build_show_boilerplate(rows)
        for row in rows:
            if limit is not None and updated >= limit:
                break
            if deadline and _now() >= deadline:
                break
            meta = dict(row["meta"])
            source = classify_source(
                meta,
                row["txt_path"],
                boilerplate=boilerplate.get(str(meta.get("show_id") or "?")),
            )
            if not force and current_reader_summary(meta, source):
                skipped += 1
                continue

            try:
                if use_llm and source.get("basis") in {"transcript", "notes"}:
                    summary = model_reader_summary(meta, source, model=model)
                else:
                    summary = generate_reader_summary(
                        meta,
                        source,
                        use_llm=False,
                        catalog_episode=row.get("catalog"),
                    )
            except LocalLLMUnavailable as exc:
                # Publish/retain a fallback, then stop: every later episode
                # would hit the same dead server and burn its repair budget.
                if not dry_run:
                    fallback = fallback_reader_summary(
                        meta,
                        source,
                        status="pending_model" if source.get("basis") == "transcript" else "ready",
                        catalog_episode=row.get("catalog"),
                    )
                    meta["reader_summary"] = fallback
                    _atomic_write_json(row["meta_path"], meta)
                pending += 1
                print(f"[{_stamp()}] LLM unavailable: {exc}", flush=True)
                break
            except Exception as exc:  # one bad episode must not end the run
                failed += 1
                print(
                    f"[{_stamp()}] FAILED {row['episode_id']}: {type(exc).__name__} {exc}",
                    flush=True,
                )
                continue

            errors = reader_summary_errors(
                summary,
                source_text=str(source.get("validation_text") or ""),
                basis=str(source.get("basis") or ""),
            )
            # A fallback that fails its own structural check is still better
            # than blank only if it has an overview; otherwise keep looking.
            if errors and summary.get("status") == "ready" and summary.get("model") != "deterministic_fallback":
                summary["status"] = "needs_review"
                summary["validation_errors"] = errors[:12]
            if summary.get("status") == "pending_model":
                pending += 1
            if dry_run:
                updated += 1
                print(
                    json.dumps(
                        {"episode_id": row["episode_id"], "reader_summary": summary},
                        ensure_ascii=False,
                    )
                )
                continue

            meta["reader_summary"] = summary
            meta["reader_summary_updated_at"] = _stamp()
            _atomic_write_json(row["meta_path"], meta)
            row["meta"] = meta
            updated += 1
            since_push += 1
            print(
                f"[{_stamp()}] {updated:4d} {summary.get('status')} "
                f"{summary.get('source_basis')} {row['episode_id'][:54]}",
                flush=True,
            )

            due = (_now() - last_push).total_seconds() >= push_minutes * 60
            if push and (due or since_push >= 10):
                if _vault_push(f"chore(podcasts): reader summaries {_stamp()}"):
                    print(f"[{_stamp()}] pushed vault ({since_push} episodes)", flush=True)
                last_push = _now()
                since_push = 0
    finally:
        if push and since_push and not dry_run:
            _vault_push(f"chore(podcasts): reader summaries {_stamp()}")
        if not dry_run:
            try:
                lock.unlink()
            except OSError:
                pass

    return {
        "updated": updated,
        "skipped_current": skipped,
        "failed": failed,
        "pending_model": pending,
        "episode_count": len(rows),
        "status": status_snapshot(root),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--llm", action="store_true", help="Use the local model (default: deterministic fallbacks only)")
    p.add_argument("--fallbacks-only", action="store_true", help="Write Tier B/C fallbacks and pending transcript fallbacks")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--hours", type=float, default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--priority", default="recent,in-book,pz,officer,all")
    p.add_argument("--episode", default=None, help="Only this episode_id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Regenerate even when the source hash is current")
    p.add_argument("--status", action="store_true", help="Print reader-summary coverage and exit")
    p.add_argument("--push", action="store_true", help="Checkpoint reader summaries to the research vault")
    p.add_argument("--push-every-minutes", type=int, default=DEFAULT_PUSH_MINUTES)
    args = p.parse_args()

    if args.status:
        print(json.dumps(status_snapshot(), indent=2))
        return 0

    summary = run(
        use_llm=bool(args.llm and not args.fallbacks_only),
        limit=args.limit,
        model=args.model,
        hours=args.hours,
        priority=args.priority,
        episode_id=args.episode,
        dry_run=args.dry_run,
        force=args.force,
        push=args.push,
        push_minutes=args.push_every_minutes,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
