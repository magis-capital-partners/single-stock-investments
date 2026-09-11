#!/usr/bin/env python3
"""Recover segment timings for videos fetched before the sidecar existed.

Every admitted video was fetched by code that did ``" ".join(s.text for s in
fetched)`` and dropped ``s.start`` on the floor. The text survives; the timing
does not, and it cannot be derived from the text -- so the captions have to be
asked for again.

**The stored transcript is never rewritten.** That file is what the relevance
gate admitted the video on and what the ratchet baseline was computed against.
Re-fetching a caption track a year later can return a re-generated one, and
silently swapping it would move admission decisions for reasons that have
nothing to do with relevance. So the fresh segments are indexed *against the
stored text* with ``index_parts``: what lands on disk is a sidecar, and only a
sidecar. Where the caption track has drifted, the segments that still match are
kept and the rest are dropped, which degrades to a sparse sidecar rather than a
wrong one.

**Pacing is the existing limiter's, not a new one.** YouTube blocked this
address fifteen times in a single ten-hour run at 150-second spacing, and the
lane's backoff ladder is persisted precisely so a restart does not reset the
wait. Adding a second fetch path with its own idea of pacing would spend the
lane's quota twice; this borrows ``caption_rate_limit`` whole and stops when it
says to stop.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import caption_rate_limit as rate  # noqa: E402
import transcript_segments  # noqa: E402

from vault_paths import videos_root  # noqa: E402

# A sparse sidecar costs recall, never precision. SearchIndex seals the gap
# between two non-adjacent segments with a character no transcript contains, so
# a quote falling inside a gap returns no timestamp rather than a wrong one, and
# the survivors stay correctly ordered because the indexer only ever advances.
#
# That is what makes a low floor safe. YouTube regenerated the XPeng
# interview's auto-captions with better punctuation -- "has advantage of"
# became "has the advantage of" -- so only 556 of 1,371 segments still match
# the transcript the gate admitted. Refusing that video outright bought nothing:
# those 556 anchors are real, correctly ordered, and average one every 5.5
# seconds. The floor exists only to reject a track that is a different
# recording, where matches would be coincidental rather than sparse.
MIN_COVERAGE = 0.20


def targets(root: Path, *, only_missing: bool = True) -> list[tuple[Path, Path, dict]]:
    rows: list[tuple[Path, Path, dict]] = []
    library = root / "library"
    if not library.is_dir():
        return rows
    for meta_path in sorted(library.rglob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("gate") != "admitted":
            continue
        txt = meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))
        if not txt.exists():
            continue
        if only_missing and transcript_segments.sidecar_path(txt).exists():
            continue
        rows.append((txt, meta_path, meta))
    # Newest first: recent research is what a reader opens, and a run cut short
    # by a block should have covered it.
    rows.sort(key=lambda row: str(row[2].get("published") or ""), reverse=True)
    return rows


def best_track(video_id: str, stored: str) -> dict:
    """The caption track that actually produced the stored transcript.

    ``fetch_captions`` asks for tracks by *language code*, so on a video
    carrying both a manual and an auto-generated English track the library picks
    between them and the original fetch's choice is not recorded anywhere. The
    XPeng interview is exactly that case: re-fetching returned the other track
    and 91 of 1,371 segments located, a 6.6% match that the coverage floor
    correctly refused.

    Guessing which track it was is unnecessary when the stored text can simply
    be asked. Each English track is indexed against it and the best match wins --
    a perfect score for the track that produced it, near-zero for the other one.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"status": "error:MissingDependency"}

    try:
        listing = list(YouTubeTranscriptApi().list(video_id))
    except Exception as exc:  # noqa: BLE001 - the library raises many shapes
        name = type(exc).__name__
        if "NoTranscript" in name or "TranscriptsDisabled" in name:
            return {"status": "no_captions", "detail": name}
        return {"status": "error:" + name, "detail": str(exc)[:200]}

    manual = [t for t in listing if not t.is_generated]
    ordered = manual + [t for t in listing if t.is_generated]
    english = [t for t in ordered if (t.language_code or "").lower().startswith("en")]
    best: dict = {"status": "no_segments", "coverage": 0.0, "located": 0, "fresh": 0}
    for track in (english or ordered):
        try:
            fetched = list(track.fetch())
        except Exception:  # noqa: BLE001 - a single bad track must not end the video
            continue
        if not fetched:
            continue
        indexed = transcript_segments.index_parts(
            stored,
            ((getattr(s, "start", None), getattr(s, "duration", None), s.text or "")
             for s in fetched),
        )
        coverage = len(indexed) / len(fetched)
        if coverage > best.get("coverage", 0.0):
            best = {"status": "ok", "segments": indexed, "coverage": coverage,
                    "located": len(indexed), "fresh": len(fetched),
                    "is_generated": bool(track.is_generated)}
        # A track that matches this well is the one; stop paying for the rest.
        if coverage >= 0.98:
            break
    return best


def backfill_one(txt: Path, meta_path: Path, meta: dict) -> dict:
    video_id = str(meta.get("video_id") or "")
    if not video_id:
        return {"status": "no_video_id"}

    stored = txt.read_text(encoding="utf-8", errors="replace").strip()
    result = best_track(video_id, stored)
    if result.get("status") != "ok":
        return {"status": result.get("status") or "error", "detail": result.get("detail")}

    indexed = result["segments"]
    coverage = result["coverage"]
    if coverage < MIN_COVERAGE:
        return {"status": "drifted", "coverage": round(coverage, 3),
                "fresh": result["fresh"], "located": result["located"]}

    transcript_segments.write_sidecar(txt, indexed)
    meta["segment_count"] = len(indexed)
    # Coverage qualifies every timestamp derived from this sidecar; the detail
    # view shows it rather than implying the timings are complete.
    meta["segment_coverage"] = round(coverage, 3)
    meta["segments_backfilled_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    return {"status": "ok", "segments": len(indexed), "coverage": round(coverage, 3)}


def run(*, limit: int | None, hours: float | None, only_missing: bool) -> dict:
    root = videos_root(create=True)
    rows = targets(root, only_missing=only_missing)
    print(f"{len(rows)} admitted video(s) without timings", flush=True)

    stats = {"ok": 0, "drifted": 0, "failed": 0, "skipped_rate_limit": 0}
    deadline = time.time() + hours * 3600 if hours else None

    for txt, meta_path, meta in rows:
        if limit is not None and stats["ok"] >= limit:
            break
        if deadline and time.time() >= deadline:
            print("deadline reached", flush=True)
            break

        gate = rate.check()
        while not gate["allowed"]:
            wait = int(gate["wait_seconds"])
            # A backoff is measured in hours. Waiting it out inside this process
            # would hold the run open all night for nothing; the supervisor will
            # start another one.
            if gate["reason"].startswith("backoff") or wait > 900:
                print(f"rate limiter says stop: {gate['reason']} "
                      f"({wait}s); {len(rows) - stats['ok']} remaining", flush=True)
                stats["skipped_rate_limit"] = len(rows) - stats["ok"]
                return stats
            time.sleep(min(wait, 900))
            gate = rate.check()

        rate.record_fetch()
        title = str(meta.get("title") or txt.stem)[:44]
        outcome = backfill_one(txt, meta_path, meta)
        status = outcome.get("status")

        if status == "ok":
            rate.record_success()
            stats["ok"] += 1
            print(f"ok    {meta.get('video_id')}  {outcome['segments']:5d} seg  "
                  f"cov={outcome['coverage']}  {title}", flush=True)
        elif status == "drifted":
            rate.record_success()
            stats["drifted"] += 1
            print(f"drift {meta.get('video_id')}  located "
                  f"{outcome['located']}/{outcome['fresh']} "
                  f"(cov={outcome['coverage']}) -- transcript left alone  {title}", flush=True)
        else:
            stats["failed"] += 1
            blocked = str(status).lower()
            if "block" in blocked or "ipblocked" in blocked or "toomany" in blocked:
                rate.record_block()
                print(f"BLOCK {meta.get('video_id')}  {status}; backing off", flush=True)
                stats["skipped_rate_limit"] = len(rows) - stats["ok"]
                return stats
            print(f"err   {meta.get('video_id')}  {status}  {title}", flush=True)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N successful backfills.")
    parser.add_argument("--hours", type=float, default=None, help="Stop cleanly after N hours.")
    parser.add_argument("--all", action="store_true",
                        help="Include videos that already have a sidecar.")
    parser.add_argument("--status", action="store_true", help="Report coverage and exit.")
    args = parser.parse_args()

    if args.status:
        root = videos_root(create=True)
        missing = len(targets(root, only_missing=True))
        total = len(targets(root, only_missing=False))
        print(json.dumps({"admitted": total, "with_timings": total - missing,
                          "missing": missing, "limiter": rate.status()}, indent=2))
        return 0

    print(json.dumps(run(limit=args.limit, hours=args.hours,
                         only_missing=not args.all), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
