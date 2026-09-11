#!/usr/bin/env python3
"""Build the admitted YouTube research catalog used by the dashboard.

The row is deliberately lean -- it renders a list of 63 -- so the evidence
behind it lives in per-video shards built by `build_video_detail.py` and
fetched on click. What changed at schema 2 is that the row no longer carries
`transcript[:260]` as its body: `summary` is the best available sentence about
the video and `summary_source` says which of four sources produced it.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import video_text
from vault_paths import path_to_videos_ref, videos_ref, videos_root

ROOT = Path(__file__).resolve().parents[2]
INDEX_MIRROR_PATH = ROOT / "_system" / "reference" / "video" / "insights_index_mirror.json"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _transcript_for(meta_path: Path) -> Path:
    return meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))


def _transcript_head(path: Path, limit: int = 600) -> str:
    try:
        text = " ".join(path.read_text(encoding="utf-8", errors="replace").split())
    except OSError:
        return ""
    return text[:limit].rstrip()


def _preview(path: Path, limit: int = 260) -> str:
    """The transcript opening, with the non-speech removed.

    This used to be the card body outright, which is how the surface came to
    read `[music] [music] [music] Thank you, man, for taking the time`. It is
    now the last entry in `video_text.card_summary`'s chain and is reached only
    when a video has no analysis and no description.
    """
    return video_text.clean_preview(_transcript_head(path), limit=limit)


def index_row(meta_path: Path, doc: dict) -> dict:
    transcript = _transcript_for(meta_path)
    relevance = doc.get("relevance") or {}
    sustained = relevance.get("sustained_tickers") or []
    people = relevance.get("people") or []
    analysis = doc.get("llm_analysis")
    analysis = analysis if isinstance(analysis, dict) else {}
    claims = [c for c in (analysis.get("claims") or []) if isinstance(c, dict)]

    gate_tickers = sorted({
        str(row.get("ticker")).upper()
        for row in sustained
        if isinstance(row, dict) and row.get("ticker")
    })
    # Symbols somebody argued about, ahead of symbols a keyword counted. The
    # XPeng interview was admitted on BABA because "alibaba" occurred four
    # times, while what it actually argues is that the company replaced Nvidia
    # silicon with its own -- so a search for NVDA could not find it. Union,
    # analysis first, keeps the gate's decision visible without letting a
    # mention rank ahead of a view.
    tickers: list[str] = []
    for ticker in [*(analysis.get("tickers") or []), *gate_tickers]:
        ticker = str(ticker or "").upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)

    stances: dict[str, str] = {}
    for claim in claims:
        ticker = str(claim.get("ticker") or "").upper()
        if not ticker:
            continue
        stance = str(claim.get("stance") or "neutral").lower()
        if ticker in stances and stances[ticker] != stance:
            stances[ticker] = "mixed"
        else:
            stances.setdefault(ticker, stance)

    summary, summary_source = video_text.card_summary(
        thesis=analysis.get("thesis") or "",
        description=doc.get("description") or "",
        claim=(claims[0].get("claim") if claims else "") or "",
        transcript_preview=_transcript_head(transcript),
    )
    source_ref = path_to_videos_ref(transcript)
    if not source_ref:
        try:
            source_ref = videos_ref(transcript.relative_to(videos_root()).as_posix())
        except (ValueError, OSError):
            source_ref = videos_ref(transcript.name)
    return {
        "video_id": doc.get("video_id"),
        "title": doc.get("title"),
        "channel_id": doc.get("channel_id"),
        "channel_title": doc.get("channel_title") or doc.get("channel"),
        "published": doc.get("published"),
        "duration_seconds": doc.get("duration_seconds"),
        "views": doc.get("views"),
        "tier": doc.get("tier"),
        "trust": doc.get("trust"),
        "tickers": tickers,
        "gate_tickers": gate_tickers,
        "stances": stances,
        "people": [
            row.get("guest_id")
            for row in people
            if isinstance(row, dict) and row.get("guest_id")
        ],
        "routes": relevance.get("routes") or [],
        "transcript_source": doc.get("transcript_source"),
        "summary": summary,
        # Which source answered "what is this about". A thesis drawn from
        # verified quotes and a sentence lifted off the top of a transcript are
        # different claims on the reader's attention.
        "summary_source": summary_source,
        "claim_count": len(claims),
        "chapter_count": len(analysis.get("chapters") or []),
        "quote_verified_rate": analysis.get("quote_verified_rate"),
        "has_analysis": bool(analysis),
        "has_timings": bool(doc.get("segment_count")),
        "transcript_preview": _preview(transcript),
        "source_document": source_ref,
        "link": doc.get("url") or (
            "https://www.youtube.com/watch?v=" + str(doc.get("video_id"))
            if doc.get("video_id") else None
        ),
    }


def _status_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    backlog = load_json(root / "caption_backlog.json")
    for row in (backlog.get("items") or {}).values():
        if isinstance(row, dict):
            counts[str(row.get("status") or "unknown")] += 1
    whisper = load_json(root / "whisper_backlog.json")
    for row in whisper.get("items") or []:
        if isinstance(row, dict):
            counts["whisper_" + str(row.get("status") or "unknown")] += 1
    return dict(sorted(counts.items()))


def build_catalog(root: Path | None = None) -> dict:
    root = root or videos_root(create=True)
    rows = []
    library = root / "library"
    if library.is_dir():
        for meta_path in sorted(library.rglob("*.meta.json")):
            doc = load_json(meta_path)
            if doc.get("gate") != "admitted" or not _transcript_for(meta_path).exists():
                continue
            rows.append(index_row(meta_path, doc))
    rows.sort(key=lambda row: (row.get("published") or "", row.get("title") or ""), reverse=True)

    by_channel: dict[str, dict] = {}
    for row in rows:
        channel_id = row.get("channel_id") or "unknown"
        group = by_channel.setdefault(channel_id, {
            "channel_id": channel_id,
            "channel_title": row.get("channel_title") or channel_id,
            "video_count": 0,
            "video_ids": [],
        })
        if row.get("video_id"):
            group["video_ids"].append(row["video_id"])
        group["video_count"] = len(group["video_ids"])

    dates = [row["published"] for row in rows if row.get("published")]
    return {
        "generated_at": now_stamp(),
        "schema_version": 2,
        "video_count": len(rows),
        "newest_published": max(dates) if dates else None,
        "status_counts": _status_counts(root),
        "video_index": rows,
        "video_by_channel": by_channel,
    }


def write_catalog(
    root: Path | None = None,
    output: Path | None = None,
    *,
    write_mirror: bool = False,
) -> Path:
    root = root or videos_root(create=True)
    output = output or (root / "insights.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(root)
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if write_mirror:
        INDEX_MIRROR_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_MIRROR_PATH.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    path = write_catalog(output=args.output, write_mirror=True)
    doc = load_json(path)
    print(f"video catalog: {doc.get('video_count', 0)} admitted -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
