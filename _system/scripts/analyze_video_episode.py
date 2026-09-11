#!/usr/bin/env python3
"""Turn a video transcript into sourced, timestamped claims about ownable companies.

The video lane had no analysis stage at all. What it had was
`relevance.sustained_tickers` -- a count of how often an alias appeared -- which
is why BABA sat on the XPeng interview because the string "alibaba" occurred
four times, and why every card on the surface showed the first 260 characters of
its transcript: `[music] [music] [music] Thank you, man, for taking the time`.

**Almost none of this file is new logic.** Ticker attribution, quote
verification, deduplication and the chunking strategy all come from
`analyze_podcast_episode`, unchanged. That module's matching rules were repaired
four separate times against live output -- Costco claims filed under a Greek
containership lessor, a Vanguard claim under Invesco, a Boeing claim under BAE
Systems -- and each repair is a rule a fork would have quietly lost. Importing
it means video claims inherit those fixes and every future one.

Three things are genuinely different about video:

**A verified quote can be located in time.** Captions arrive with a `.start` per
segment; `transcript_segments` now keeps them. A quote that survives
verification is by construction a literal span of the transcript, so its offset
maps to a segment and the claim carries the moment it was said. That turns a
research note into `watch?v=...&t=1234s` -- the one thing video does that a
letter cannot, and the reason the lane is worth deepening at all.

**The guest's role changes what the transcript is evidence of.** A CEO on In
Good Company describing their own capacity plans is self-reported and interested;
a Sohn presenter is pitching a position with a target and a catalyst; Guy Spier
discussing a holding is an outside allocator's view. Asking all three "what
claims were made" wastes the thing that distinguishes them, so the prompt is
selected per channel and self-reported claims are marked as such in the output.

**Chapters are nearly free.** The chunk boundaries already exist and each
already has an offset, so one extra sentence per window buys a navigable
51-minute interview.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Titles carry whatever the uploader typed -- Norwegian characters throughout
# the Norges Bank catalogue, and a U+2060 WORD JOINER once killed a podcast run
# outright because Python picks cp1252 for a redirected stdout on Windows: the
# line reporting success was the crash. Same guard, same reason.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import transcript_segments  # noqa: E402
from analyze_podcast_episode import (  # noqa: E402
    CHUNK_CHARS,
    CHUNK_OVERLAP,
    MAX_CHUNKS,
    _clean_ticker,
    _norm,
    build_aliases,
    chunk_transcript,
    dedupe_claims,
    dedupe_numbers,
    relevant_chunks,
    resolve_tickers,
    validate_tickers,
    verify_quotes,
)
from llm_local import complete, extract_json  # noqa: E402

SYSTEM = (
    "You extract investable claims from transcripts of investing talks and "
    "interviews. You are precise, you never invent facts, and you only report "
    "what the speakers actually said. When you are unsure, you say nothing "
    "rather than guessing. You always reply with a single JSON object and no "
    "other text."
)

# What the transcript is evidence *of*, by channel. The registry carries an
# `analysis_role` per channel; this is the operative half of that setting.
#
# `self_reported` is not a stylistic note -- it travels into the published
# claim. An operator saying their margins will expand and an outside analyst
# saying the same thing are not the same evidence, and a research surface that
# renders them identically is lying by omission.
ROLES: dict[str, dict] = {
    "operator": {
        "label": "an operator interview",
        "self_reported": True,
        "guidance": (
            "The guest runs the business being discussed. Their claims about their own "
            "company are interested and forward-looking -- capacity, pricing, margins, "
            "competition, reinvestment, hiring. Capture those, and capture what they say "
            "about competitors and customers, which is often the more useful half. "
            "Do not treat the host's framing of a question as the guest's view."
        ),
    },
    "allocator": {
        "label": "an investor interview",
        "self_reported": False,
        "guidance": (
            "The speaker is an outside investor discussing positions. Capture the view "
            "and the reasoning behind it -- why this business, at what price, against "
            "what risk -- not merely that a company was named. A position mentioned "
            "without a reason is worth less than a reason given without a position."
        ),
    },
    "pitch": {
        "label": "an investment pitch",
        "self_reported": False,
        "guidance": (
            "This is a pitch for a specific position. Capture the thesis, the valuation "
            "or target if one is stated, the catalyst, and the risk the presenter "
            "concedes. A pitch that names no price and no catalyst is a story; say so by "
            "returning only what was actually stated."
        ),
    },
    "broad": {
        "label": "a talk",
        "self_reported": False,
        "guidance": (
            "The speaker may be an author, a founder or a researcher rather than an "
            "investor, and most of the talk may carry no investable view at all. That is "
            "an acceptable result: return an empty list rather than manufacturing a view "
            "from a general observation about an industry."
        ),
    },
}
DEFAULT_ROLE = "broad"

MAP_PROMPT = """Below is part of the transcript of {role_label} published on the channel "{channel}", titled "{title}".

{guidance}

Companies of interest (report claims about these; ignore passing mentions that carry no view):
{universe}

Extract only what this passage actually says. Reply with JSON:

{{
  "claims": [
    {{
      "company": "the company name as said",
      "ticker": "ticker if one of the companies of interest, else null",
      "stance": "bullish" | "bearish" | "mixed" | "neutral",
      "claim": "one sentence, in your own words, stating the view or fact",
      "quote": "the EXACT words from the passage that support this, copied verbatim, 10-40 words",
      "speaker": "name if identifiable, else null"
    }}
  ],
  "numbers": [
    {{"what": "what the figure measures", "value": "the figure as said", "quote": "exact supporting words"}}
  ],
  "topic": "3-6 words naming what this passage is about"
}}

Rules:
- "quote" MUST be COPIED AND PASTED from the passage above, character for character.
  Do not paraphrase it. Do not fix grammar, fillers or punctuation. Do not join
  two sentences that are not adjacent. Do not shorten with "...". If you cannot
  find an exact span that supports the claim, omit the claim entirely.
  A quote that does not appear verbatim in the passage is discarded automatically,
  so an approximate quote loses the claim with it.
- If the passage contains no view about any company, return {{"claims": [], "numbers": [], "topic": "..."}}.
- Ignore channel boilerplate, sponsor reads, and the host's introduction of the guest.
- Transcripts of spoken audio contain marks like [music] and [applause]. They are
  not speech. Never quote them.

PASSAGE:
{chunk}"""

REDUCE_PROMPT = """You are consolidating extracted claims from {role_label} on "{channel}": "{title}".

Here are the claims found across it:
{claims}

Reply with JSON:

{{
  "thesis": "3-4 sentences on what this video actually argues, for an investor who did not watch it",
  "tickers": ["the tickers genuinely discussed with a view, most important first"],
  "themes": [{{"theme": "short label", "stance": "bullish" | "bearish" | "mixed" | "neutral"}}]
}}

Base the thesis only on the claims above. If they are thin, say so plainly rather than padding."""


def role_for(channel_id: str, registry: dict | None = None) -> str:
    """The analysis role for a channel, from the registry.

    Falls back through the registry's own tier vocabulary before defaulting:
    a `guest` channel is somebody's own channel and so is an allocator, and a
    channel nobody has classified gets the role that assumes the least.
    """
    registry = registry if registry is not None else load_registry()
    for row in (registry.get("channels") or []):
        if not isinstance(row, dict) or row.get("channel_id") != channel_id:
            continue
        explicit = str(row.get("analysis_role") or "").strip().lower()
        if explicit in ROLES:
            return explicit
        return "allocator" if row.get("tier") == "guest" else DEFAULT_ROLE
    return DEFAULT_ROLE


def load_registry() -> dict:
    path = ROOT / "_system" / "reference" / "video" / "channel_registry.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def attach_timestamps(rows: list[dict], index) -> int:
    """Give every verified quote the moment it was said.

    Runs after verification, never before: an unverified quote is one the
    speaker may not have said, and a timestamp would dress it as sourced.
    """
    if not index:
        return 0
    found = 0
    for row in rows or []:
        seconds = index.seconds_for(_norm(row.get("quote") or ""))
        if seconds is not None:
            row["t_start"] = round(seconds, 1)
            found += 1
    return found


def build_chapters(chunks: list[str], topics: dict[int, str],
                   segments: list[dict]) -> list[dict]:
    """One navigable entry per analysed window.

    Chunk boundaries are already character offsets into the transcript, and the
    sidecar maps a character offset to a time, so the only new cost is the
    `topic` field the map prompt already returns.
    """
    if not segments or not topics:
        return []
    step = CHUNK_CHARS - CHUNK_OVERLAP
    out: list[dict] = []
    for idx in sorted(topics):
        topic = str(topics[idx] or "").strip()
        if not topic or idx >= len(chunks):
            continue
        seconds = transcript_segments.offset_to_seconds(segments, idx * step)
        if seconds is None:
            continue
        out.append({"topic": topic[:70], "t_start": round(seconds, 1)})
    out.sort(key=lambda row: row["t_start"])
    # Overlapping windows can label the same minute twice.
    deduped: list[dict] = []
    for row in out:
        if deduped and abs(row["t_start"] - deduped[-1]["t_start"]) < 1.0:
            continue
        deduped.append(row)
    return deduped


def analyze(transcript: str, *, title: str, channel: str, role: str = DEFAULT_ROLE,
            segments: list[dict] | None = None, model: str | None = None,
            aliases: dict[str, str] | None = None) -> dict:
    aliases = aliases if aliases is not None else build_aliases()
    segments = segments or []
    spec = ROLES.get(role) or ROLES[DEFAULT_ROLE]

    chunks = chunk_transcript(transcript)
    picked = relevant_chunks(chunks, aliases)

    universe_note = "(none matched in this video; report any company discussed with a clear view)"
    if picked:
        names = sorted({aliases[a] for a in aliases if any(a in c.lower() for _, c in picked)})
        if names:
            universe_note = ", ".join(names[:40])

    if not picked:
        picked = [(0, chunks[0])] if chunks else []

    raw_claims: list[dict] = []
    raw_numbers: list[dict] = []
    topics: dict[int, str] = {}
    for idx, chunk in picked:
        reply = complete(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": MAP_PROMPT.format(
                 role_label=spec["label"], guidance=spec["guidance"],
                 channel=channel, title=title,
                 universe=universe_note, chunk=chunk)}],
            model=model, json_object=True, max_tokens=3000,
        )
        doc = extract_json(reply) or {}
        raw_claims.extend(doc.get("claims") or [])
        raw_numbers.extend(doc.get("numbers") or [])
        if doc.get("topic"):
            topics[idx] = doc["topic"]

    claims, stats = verify_quotes(raw_claims, transcript)
    numbers, num_stats = verify_quotes(raw_numbers, transcript)
    stats["tickers_rejected"] = validate_tickers(claims, aliases)
    stats["tickers_resolved_post_hoc"] = resolve_tickers(claims, aliases)
    before = len(claims)
    claims = dedupe_claims(claims)
    stats["duplicate_claims_dropped"] = before - len(claims)
    numbers = dedupe_numbers(numbers)

    # Figures with no thesis around them are a page of statistics with nothing
    # saying what they are about. Same rule the podcast lane settled on.
    if not claims:
        numbers = []

    index = transcript_segments.SearchIndex(segments, _norm) if segments else None
    stats["claims_timestamped"] = attach_timestamps(claims, index)
    attach_timestamps(numbers, index)
    if spec["self_reported"]:
        for claim in claims:
            claim["self_reported"] = True

    summary_doc: dict = {"thesis": "", "tickers": [], "themes": []}
    if claims:
        brief = json.dumps([{k: c.get(k) for k in ("company", "ticker", "stance", "claim")}
                            for c in claims[:24]], indent=1)
        reply = complete(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": REDUCE_PROMPT.format(
                 role_label=spec["label"], channel=channel, title=title, claims=brief)}],
            model=model, json_object=True, max_tokens=800,
        )
        summary_doc = extract_json(reply) or summary_doc

    verified_syms = [t for t in (c.get("ticker") for c in claims) if t]
    tickers: list[str] = []
    for ticker in list(dict.fromkeys(verified_syms)):
        if ticker not in tickers:
            tickers.append(ticker)
    for ticker in (summary_doc.get("tickers") or []):
        ticker = _clean_ticker(ticker)
        if ticker and ticker in verified_syms and ticker not in tickers:
            tickers.append(ticker)

    return {
        "thesis": (summary_doc.get("thesis") or "").strip(),
        "tickers": tickers,
        "themes": summary_doc.get("themes") or [],
        "claims": claims,
        "numbers": numbers,
        "chapters": build_chapters(chunks, topics, segments),
        "role": role,
        "method": "local_llm",
        "chunks_total": len(chunks),
        "chunks_analyzed": len(picked),
        "has_segments": bool(segments),
        **stats,
        "number_quotes_verified": num_stats.get("quotes_verified", 0),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Analyse one video transcript.")
    parser.add_argument("transcript", help="Path to a .txt transcript")
    parser.add_argument("--title", default="")
    parser.add_argument("--channel", default="")
    parser.add_argument("--role", default=None, choices=sorted(ROLES))
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    path = Path(args.transcript)
    text = path.read_text(encoding="utf-8", errors="ignore")
    title, channel, role = args.title, args.channel, args.role
    meta_path = path.with_name(path.name.replace(".txt", ".meta.json"))
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
        title = title or meta.get("title") or ""
        channel = channel or meta.get("channel_title") or ""
        role = role or role_for(meta.get("channel_id") or "")

    result = analyze(text, title=title, channel=channel, role=role or DEFAULT_ROLE,
                     segments=transcript_segments.load_sidecar(path), model=args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
