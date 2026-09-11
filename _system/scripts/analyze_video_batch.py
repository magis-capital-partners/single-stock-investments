#!/usr/bin/env python3
"""Drain the local-model analysis across the admitted video corpus.

Companion to analyze_video_episode.py, which handles one video. The scale here
is small -- 63 admitted videos, 2.53M characters, about 211 windows at the 12k
chunk size, or a single overnight run -- but the failure modes are the same ones
the podcast batch already paid for, so it borrows the guards rather than
rediscovering them: resume by transcript hash, checkpoint to the vault, yield to
Whisper, stand down when memory is short, and refuse to run twice at once.

**One local-model consumer at a time, across both corpora.** Whisper
transcription and llama-server on the same box measured 5.5x slower than running
them in sequence -- 3.0 episodes/hour became 0.55. A second analyser would be
the same mistake with an extra step, so this refuses to start while the podcast
batch holds its lock, and the podcast batch's own lock file is what it checks.
The two lanes share a vault, a GPU and a box; they should share a queue.

**Videos need no transcript floor.** The podcast batch filters on size and
strips per-show boilerplate because its corpus is whatever an RSS feed carried.
Every video here has already passed the spoken-content relevance gate, which is
a stricter test than any byte count -- so the gate's decision is taken as given
rather than re-litigated with a different rule.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import analyze_podcast_batch as apb  # noqa: E402
import transcript_segments  # noqa: E402
from analyze_podcast_episode import build_aliases, scan_aliases  # noqa: E402
from analyze_video_episode import analyze, load_registry, role_for  # noqa: E402
from llm_local import LocalLLMUnavailable  # noqa: E402
from vault_git import clear_stale_git_state, vault_lock  # noqa: E402
from vault_paths import videos_root  # noqa: E402

LOCK_NAME = ".analyze_video_batch.lock"
# The podcast batch's lock, checked so the two lanes queue behind each other.
PEER_LOCK_NAME = apb.LOCK_NAME
LOCK_STALE_SECONDS = 3600
DEFAULT_PUSH_MINUTES = 20


def _stamp() -> str:
    return apb._stamp()


def needs_analysis(meta: dict, digest: str, has_segments: bool) -> bool:
    """Whether this video's analysis is missing, stale, or missing its timings.

    The hash condition is the podcast batch's: re-transcription invalidates
    claims drawn from text that no longer exists. The second condition is new
    and exists because two lanes are draining at once. Caption timings arrive
    over hours -- one fetch every 150 seconds, and YouTube blocks this address
    when pushed harder -- while analysis runs at its own pace. Without this, a
    video analysed an hour before its sidecar landed would keep claims with no
    jump links permanently, and the ordering of two unrelated background jobs
    would decide whether the headline feature worked.
    """
    prior = meta.get("llm_analysis")
    if not isinstance(prior, dict):
        return True
    if prior.get("transcript_sha1") != digest:
        return True
    return has_segments and not prior.get("has_segments")


def candidates(root: Path) -> list[tuple[Path, Path, dict]]:
    """Admitted videos: ready and valuable first.

    Two keys, and the order between them matters. A video whose timings have
    already been recovered can produce jump links on this pass, so analysing it
    now costs one run instead of two -- that ranks ahead of everything.

    Within that, in-book mentions decide. Talks at Google is 29 of the 63 and is
    mostly authors on tour; ordering by date alone would spend the first hour of
    a run on book talks while the Fundsmith and Sohn material waits.
    """
    rows: list[tuple[Path, Path, dict]] = []
    library = root / "library"
    if not library.is_dir():
        return rows
    for meta_path in sorted(library.rglob("*.meta.json")):
        meta = apb.load_meta(meta_path)
        if meta.get("gate") != "admitted":
            continue
        txt = meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))
        if txt.exists():
            rows.append((txt, meta_path, meta))

    book = scan_aliases(build_aliases(limit_in_book=True))

    def book_hits(path: Path) -> int:
        try:
            low = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            return 0
        return sum(1 for alias in book if alias in low)

    scored = [
        (1 if transcript_segments.sidecar_path(row[0]).exists() else 0, book_hits(row[0]), row)
        for row in rows
    ]
    scored.sort(key=lambda t: (-t[0], -t[1], apb._neg_date(t[2][2].get("published") or "")))
    return [row for _timed, _hits, row in scored]


def _alive(pid: int) -> bool:
    """Whether a process id is still running, without signalling it."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            # Unknowable is not the same as free. Assume held: the cost of
            # waiting is a delay, the cost of guessing wrong is two analysers.
            return True
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def held(path: Path) -> str | None:
    """Why a lock is held, or None when it is genuinely free.

    **Liveness decides, not age.** These lock files record a pid and a timestamp
    once at startup and are never refreshed, so their mtime says when the batch
    began rather than whether it is still going. Judging staleness by mtime --
    which is what this function did first -- declared a perfectly healthy
    podcast batch stale one hour into an eight-hour run, and started a video
    batch beside it. That is precisely the concurrency this module exists to
    prevent: Whisper and llama-server sharing the box measured 5.5x slower than
    running in sequence.

    An unreadable or pid-less lock falls back to the age test, which is the only
    thing left to go on when a crash left the file behind.
    """
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    pid = 0
    if raw:
        head = raw.split()[0]
        if head.isdigit():
            pid = int(head)
    if pid and _alive(pid):
        return f"pid {pid} still running"
    if not pid:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return None
        if age < LOCK_STALE_SECONDS:
            return f"no pid recorded, {age:.0f}s old"
    return None


def vault_push(message: str) -> bool:
    """Commit the vault. Same lock as every other writer to this tree.

    The Whisper daemon commits here every 15 minutes and two git processes
    collide on .git/index.lock -- the collision that wedged the vault for
    fourteen hours on 2026-08-31.
    """
    repo = videos_root().parent
    try:
        with vault_lock(repo, owner="analyze_video_batch",
                        log=lambda m: print(f"[{_stamp()}]{m}", flush=True)):
            clear_stale_git_state(repo, log=lambda m: print(f"[{_stamp()}]{m}", flush=True))
            return apb._push_locked(repo, message)
    except TimeoutError as exc:
        print(f"[{_stamp()}] vault lock: {exc}; skipping this push", flush=True)
        return False


def status() -> dict:
    root = videos_root(create=True)
    rows = candidates(root)
    analysed = timestamped = fresh = 0
    claims = 0
    for txt, _meta_path, meta in rows:
        analysis = meta.get("llm_analysis")
        if not isinstance(analysis, dict):
            continue
        analysed += 1
        claims += len(analysis.get("claims") or [])
        if analysis.get("has_segments"):
            timestamped += 1
        if not needs_analysis(meta, apb.sha1_text(txt),
                              transcript_segments.sidecar_path(txt).exists()):
            fresh += 1
    return {
        "admitted": len(rows),
        "analysed": analysed,
        "current": fresh,
        "stale_or_missing": len(rows) - fresh,
        "with_timestamps": timestamped,
        "claims": claims,
        # The supervisor reads this key from both batches; keep the name.
        "remaining": len(rows) - fresh,
    }


def run(*, limit: int | None, model: str | None, push: bool, push_minutes: int,
        hours: float | None, max_wait_minutes: int | None) -> dict:
    root = videos_root(create=True)
    lock = root.parent / LOCK_NAME
    peer = root.parent / PEER_LOCK_NAME

    peer_why = held(peer)
    if peer_why is not None:
        print(f"podcast analysis holds {peer} ({peer_why}); "
              "one local-model consumer at a time -- exiting")
        return {"skipped": "peer_locked"}
    own_why = held(lock)
    if own_why is not None:
        print(f"another video batch holds {lock} ({own_why}); exiting")
        return {"skipped": "locked"}
    lock.write_text(f"{os.getpid()} {_stamp()}\n", encoding="utf-8")

    print(f"[{_stamp()}] priority -> {apb.deprioritise()}", flush=True)
    aliases = build_aliases()
    registry = load_registry()
    deadline = datetime.now(timezone.utc) + timedelta(hours=hours) if hours else None

    done = failed = skipped = no_timing = 0
    since_push = 0
    last_push = datetime.now(timezone.utc)
    try:
        rows = candidates(root)
        print(f"[{_stamp()}] {len(rows)} admitted videos", flush=True)
        for txt, meta_path, meta in rows:
            if apb._stop or (limit is not None and done >= limit):
                break
            if deadline and datetime.now(timezone.utc) >= deadline:
                print(f"[{_stamp()}] deadline reached", flush=True)
                break

            digest = apb.sha1_text(txt)
            segments = transcript_segments.load_sidecar(txt)
            if not needs_analysis(meta, digest, bool(segments)):
                skipped += 1
                continue

            apb.wait_for_memory()
            if max_wait_minutes is not None:
                apb.wait_for_whisper(max_wait_minutes)
            if apb._stop:
                break

            title = meta.get("title") or txt.stem
            role = role_for(meta.get("channel_id") or "", registry)
            if not segments:
                no_timing += 1
            started = time.time()
            try:
                result = analyze(
                    txt.read_text(encoding="utf-8", errors="ignore"),
                    title=title,
                    channel=meta.get("channel_title") or meta.get("channel_id") or "",
                    role=role,
                    segments=segments,
                    model=model,
                    aliases=aliases,
                )
            except LocalLLMUnavailable as exc:
                print(f"[{_stamp()}] LLM unavailable: {exc}", flush=True)
                break
            except Exception as exc:  # one bad video must not end the run
                failed += 1
                print(f"[{_stamp()}] FAILED {title[:48]}: {type(exc).__name__} {exc}", flush=True)
                continue

            result["transcript_sha1"] = digest
            result["analyzed_at"] = _stamp()
            meta["llm_analysis"] = result
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

            done += 1
            since_push += 1
            claims = result.get("claims") or []
            stamped = result.get("claims_timestamped") or 0
            print(f"[{_stamp()}] {done:3d} {time.time() - started:5.0f}s  "
                  f"{role:9s} claims={len(claims):2d} t={stamped:2d} "
                  f"verified={result.get('quote_verified_rate')} "
                  f"tickers={','.join((result.get('tickers') or [])[:4]) or '-'}  "
                  f"{title[:40]}", flush=True)

            due = (datetime.now(timezone.utc) - last_push).total_seconds() >= push_minutes * 60
            if push and (due or since_push >= 10):
                if vault_push(f"chore(videos): local-model analysis {_stamp()}"):
                    print(f"[{_stamp()}] pushed vault ({since_push} videos)", flush=True)
                last_push = datetime.now(timezone.utc)
                since_push = 0
    finally:
        if push and since_push:
            vault_push(f"chore(videos): local-model analysis {_stamp()}")
        lock.unlink(missing_ok=True)

    if no_timing:
        print(f"[{_stamp()}] {no_timing} video(s) had no segment sidecar; "
              "their claims carry no timestamp until captions are re-fetched", flush=True)
    return {"analysed": done, "failed": failed, "skipped": skipped,
            "without_timestamps": no_timing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Stop after N videos.")
    parser.add_argument("--hours", type=float, default=None, help="Stop cleanly after N hours.")
    parser.add_argument("--model", default=None, help="Model identifier on the local server.")
    parser.add_argument("--no-push", action="store_true", help="Do not commit/push the vault.")
    parser.add_argument("--push-every-minutes", type=int, default=DEFAULT_PUSH_MINUTES)
    parser.add_argument("--status", action="store_true", help="Report coverage and exit.")
    parser.add_argument("--max-wait-minutes", type=int, default=apb.DEFAULT_MAX_WAIT_MINUTES,
                        help="Longest wait for Whisper to go idle before proceeding anyway.")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(status(), indent=2))
        return 0

    apb._install_stop_handlers()
    result = run(
        limit=args.limit,
        model=args.model,
        push=not args.no_push,
        push_minutes=args.push_every_minutes,
        hours=args.hours,
        max_wait_minutes=args.max_wait_minutes,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
