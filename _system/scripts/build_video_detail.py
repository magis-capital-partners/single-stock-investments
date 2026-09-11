#!/usr/bin/env python3
"""Per-video detail shards: everything the catalog row had to leave behind.

``build_video_insights.index_row`` publishes fourteen fields per video, and the
pipeline computes considerably more than that. The XPeng interview's meta
carries NVDA, TSLA and EVO.ST under ``mentioned_only``, the aliases that fired
each ticker match, YouTube's own description, the unresolved person/company
pairs the entity resolver gave up on, and the caption provenance -- none of
which reached the dashboard, because a catalog row that carried them for 63
videos would be a payload nobody wants to download to render a list.

So the split is the one the podcast lane already uses: a lean index for the
list, a shard per item fetched when something is opened. What is new here is
what the shards carry.

**A ticker now has to say why it is there.** The row published a bare symbol.
BABA sat on the XPeng interview because the string "alibaba" occurred four
times, which is a fact about the transcript rather than about the video, and
nothing on the surface distinguished it from a symbol somebody argued about for
ten minutes. The shard separates the three cases -- discussed with a view,
sustained mentions, mentioned once -- and shows the alias and the count behind
each.

**A claim carries its quote, its moment and its qualification.** Every quote
was verified as a literal span of the transcript before publication, and where
the caption timings survived it also carries the second it was said, as a link
that opens the video there. Claims from an operator interview are marked
self-reported, because a CEO's forecast for their own margins is not the same
evidence as an outside analyst's.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import transcript_segments  # noqa: E402
import video_text  # noqa: E402
from vault_paths import path_to_videos_ref, videos_ref, videos_root  # noqa: E402

DETAIL_DIR = ROOT / "dashboard" / "data" / "insights" / "video_details"
# Enough to read the argument; the full transcript is one click away in the
# vault and does not belong in a shard fetched on click.
MAX_CLAIMS = 40
MAX_NUMBERS = 24
MAX_CHAPTERS = 12


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def shard_name(video_id: str) -> str:
    """Mirrors the podcast shard rule so one frontend helper serves both."""
    safe = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in str(video_id or ""))
    return safe[:180] or "unknown"


def _ticker_evidence(relevance: dict) -> list[dict]:
    """The keyword gate's own working, per symbol.

    `kind` is the distinction the catalog row could not make: `sustained` is
    what admitted the video, `mentioned` was computed and then dropped.
    """
    out: list[dict] = []
    for kind, key in (("sustained", "sustained_tickers"), ("mentioned", "mentioned_only")):
        for row in (relevance.get(key) or []):
            if not isinstance(row, dict) or not row.get("ticker"):
                continue
            out.append({
                "ticker": str(row["ticker"]).upper(),
                "kind": kind,
                "mentions": row.get("mentions"),
                "distinct_chunks": row.get("distinct_chunks"),
                "aliases": sorted((row.get("aliases") or {}).keys()),
            })
    return out


def _claims(analysis: dict, video_id: str) -> list[dict]:
    rows: list[dict] = []
    for claim in (analysis.get("claims") or [])[:MAX_CLAIMS]:
        if not isinstance(claim, dict) or not str(claim.get("claim") or "").strip():
            continue
        seconds = claim.get("t_start")
        rows.append({
            "company": claim.get("company"),
            "ticker": claim.get("ticker"),
            "stance": claim.get("stance") or "neutral",
            "claim": claim.get("claim"),
            "quote": claim.get("quote"),
            "speaker": claim.get("speaker"),
            "self_reported": bool(claim.get("self_reported")),
            # How the security master placed this symbol. Published because the
            # same attribution bug has now been found four times, each by
            # auditing live output rather than by a failing test.
            "ticker_basis": claim.get("ticker_basis"),
            "t_start": seconds,
            "link": transcript_segments.youtube_link(video_id, seconds) if seconds is not None else None,
        })
    return rows


def _numbers(analysis: dict, video_id: str) -> list[dict]:
    rows: list[dict] = []
    for row in (analysis.get("numbers") or [])[:MAX_NUMBERS]:
        if not isinstance(row, dict) or not str(row.get("value") or "").strip():
            continue
        seconds = row.get("t_start")
        rows.append({
            "what": row.get("what"),
            "value": row.get("value"),
            "quote": row.get("quote"),
            "t_start": seconds,
            "link": transcript_segments.youtube_link(video_id, seconds) if seconds is not None else None,
        })
    return rows


def _chapters(analysis: dict, video_id: str) -> list[dict]:
    rows: list[dict] = []
    for row in (analysis.get("chapters") or [])[:MAX_CHAPTERS]:
        if not isinstance(row, dict) or row.get("t_start") is None:
            continue
        rows.append({
            "topic": row.get("topic"),
            "t_start": row.get("t_start"),
            "link": transcript_segments.youtube_link(video_id, row.get("t_start")),
        })
    return rows


def analysis_summary(analysis: dict) -> dict | None:
    """What qualifies the claims, kept with them.

    A video analysed at a 0.50 verified rate had half its extracted claims
    discarded for quoting text nobody said. That is a fact about the video, not
    a debugging statistic, and the reader needs it to weigh what is shown.
    """
    if not analysis:
        return None
    claims = analysis.get("claims") or []
    return {
        "method": analysis.get("method"),
        "role": analysis.get("role"),
        "analyzed_at": analysis.get("analyzed_at"),
        "chunks_analyzed": analysis.get("chunks_analyzed"),
        "chunks_total": analysis.get("chunks_total"),
        "quote_verified_rate": analysis.get("quote_verified_rate"),
        "quotes_checked": analysis.get("quotes_checked"),
        "claim_count": len(claims),
        "claims_with_ticker": sum(1 for c in claims if isinstance(c, dict) and c.get("ticker")),
        "claims_timestamped": analysis.get("claims_timestamped") or 0,
        "tickers_rejected": analysis.get("tickers_rejected"),
        "number_count": len(analysis.get("numbers") or []),
        "has_segments": bool(analysis.get("has_segments")),
    }


def source_ref(transcript: Path) -> str:
    ref = path_to_videos_ref(transcript)
    if ref:
        return ref
    try:
        return videos_ref(transcript.relative_to(videos_root()).as_posix())
    except (ValueError, OSError):
        return videos_ref(transcript.name)


def build_detail(meta_path: Path, meta: dict) -> dict:
    video_id = str(meta.get("video_id") or "")
    transcript = meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))
    relevance = meta.get("relevance") or {}
    analysis = meta.get("llm_analysis")
    analysis = analysis if isinstance(analysis, dict) else {}

    claims = _claims(analysis, video_id)
    evidence = _ticker_evidence(relevance)
    preview = ""
    try:
        preview = " ".join(transcript.read_text(encoding="utf-8", errors="replace").split())[:600]
    except OSError:
        pass

    summary, summary_source = video_text.card_summary(
        thesis=analysis.get("thesis") or "",
        description=meta.get("description") or "",
        claim=(claims[0]["claim"] if claims else ""),
        transcript_preview=preview,
    )

    stances: dict[str, str] = {}
    for claim in claims:
        ticker = claim.get("ticker")
        if not ticker:
            continue
        prior = stances.get(ticker)
        stance = str(claim.get("stance") or "neutral").lower()
        # Two opposed readings of one company is itself the finding.
        if prior and prior != stance:
            stances[ticker] = "mixed"
        else:
            stances.setdefault(ticker, stance)

    return {
        "video_id": video_id,
        "title": meta.get("title"),
        "channel_id": meta.get("channel_id"),
        "channel_title": meta.get("channel_title"),
        "published": meta.get("published"),
        "duration_seconds": meta.get("duration_seconds"),
        "views": meta.get("views"),
        "tier": meta.get("tier"),
        "trust": meta.get("trust"),
        "link": meta.get("url") or transcript_segments.youtube_link(video_id, None),
        "description": (meta.get("description") or "")[:2000] or None,
        "summary": summary,
        "summary_source": summary_source,
        "thesis": (analysis.get("thesis") or "").strip() or None,
        "themes": [t for t in (analysis.get("themes") or []) if isinstance(t, dict)],
        "claims": claims,
        "numbers": _numbers(analysis, video_id),
        "chapters": _chapters(analysis, video_id),
        "stances": stances,
        # Symbols somebody actually argued about, which is not the same list as
        # the symbols the keyword gate counted.
        "tickers": [t for t in (analysis.get("tickers") or []) if t],
        "gate_tickers": [row["ticker"] for row in evidence if row["kind"] == "sustained"],
        "mentioned_tickers": [row["ticker"] for row in evidence if row["kind"] == "mentioned"],
        "ticker_evidence": evidence,
        "routes": relevance.get("routes") or [],
        "people": [p.get("guest_id") for p in (relevance.get("people") or [])
                   if isinstance(p, dict) and p.get("guest_id")],
        "ambiguous": [a for a in ((meta.get("resolve_preview") or {}).get("ambiguous") or [])
                      if isinstance(a, dict)][:8],
        "analysis": analysis_summary(analysis),
        "provenance": {
            "transcript_source": meta.get("transcript_source"),
            "caption_language": meta.get("caption_language"),
            "caption_is_generated": meta.get("caption_is_generated"),
            "caption_manual_available": meta.get("caption_manual_available"),
            "transcript_chars": meta.get("transcript_chars"),
            "chars_per_minute": meta.get("chars_per_minute"),
            "segment_count": meta.get("segment_count"),
            "segment_coverage": meta.get("segment_coverage"),
            "fetched_at": meta.get("fetched_at"),
            "gate_thresholds": relevance.get("thresholds"),
            "scored_at": relevance.get("scored_at"),
        },
        "source_document": source_ref(transcript),
        "generated_at": now_stamp(),
    }


def build_all(root: Path | None = None, output_dir: Path | None = None) -> dict:
    root = root or videos_root(create=True)
    output_dir = output_dir or DETAIL_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, dict] = {}
    library = root / "library"
    if library.is_dir():
        for meta_path in sorted(library.rglob("*.meta.json")):
            meta = load_json(meta_path)
            if meta.get("gate") != "admitted":
                continue
            transcript = meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))
            if not transcript.exists():
                continue
            detail = build_detail(meta_path, meta)
            if not detail.get("video_id"):
                continue
            written[detail["video_id"]] = detail

    keep = set()
    for video_id, detail in written.items():
        path = output_dir / f"{shard_name(video_id)}.json"
        path.write_text(json.dumps(detail, separators=(",", ":"), ensure_ascii=False) + "\n",
                        encoding="utf-8")
        keep.add(path.name)

    # A video that loses admission must not keep serving a stale shard.
    removed = 0
    for path in output_dir.glob("*.json"):
        if path.name not in keep:
            path.unlink()
            removed += 1

    analysed = sum(1 for d in written.values() if d.get("analysis"))
    timestamped = sum(1 for d in written.values()
                      if any(c.get("t_start") is not None for c in d.get("claims") or []))
    return {
        "shards": len(written),
        "removed": removed,
        "with_analysis": analysed,
        "with_timestamps": timestamped,
        "claims": sum(len(d.get("claims") or []) for d in written.values()),
        "by_summary_source": {
            source: sum(1 for d in written.values() if d.get("summary_source") == source)
            for source in ("thesis", "description", "claim", "transcript", "none")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    stats = build_all(output_dir=args.output_dir)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
