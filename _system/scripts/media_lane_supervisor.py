#!/usr/bin/env python3
"""Always-on podcast + YouTube media lane for a Mac Mini (or any Unix host).

One process. One lock. Strict sequencing:

  1. Podcast Whisper backlog (feeds everything else)
  2. YouTube discover / captions (Whisper for videos only when podcast queue is empty)
  3. Podcast reader summaries, published immediately (alternating with video
     analysis when both have work, so neither surface starves)
  4. Local-model claims analysis (videos first, then podcasts) — same qwen endpoint as Windows

Never run Whisper transcription beside the LLM server. Measured on the Windows
workstation: that concurrency dropped transcription from ~3.0 to ~0.55
episodes/hour. Here the phases are mutually exclusive by construction, so the
Mac Mini does not need a second mutex dance.

Resource posture (defaults tuned for a small Apple Silicon Mini):

  * nice +15
  * Whisper threads capped (default 4, or half the cores)
  * pause when reclaimable memory is below MEDIA_LANE_MEMORY_FLOOR_MB (2500)
  * small Whisper chunks so a stop request is cheap
  * idle sleep when both queues are empty (does not exit — launchd KeepAlive)

Install on the Mini::

    bash _system/scripts/install_mac_media_lane.sh

Status::

    python _system/scripts/media_lane_supervisor.py --status
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_lane_resources import (  # noqa: E402
    FileLock,
    available_mb,
    default_whisper_threads,
    deprioritise,
    wait_for_memory,
)

DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "distil-large-v3")
DEFAULT_ANALYSIS_MODEL = os.environ.get("MEDIA_LANE_ANALYSIS_MODEL", "qwen-gpu")
DEFAULT_MODEL_PATH = os.environ.get("MEDIA_LANE_MODEL_PATH", "qwen/qwen3.5-9b")
DEFAULT_MEMORY_FLOOR = int(os.environ.get("MEDIA_LANE_MEMORY_FLOOR_MB", "2500"))
DEFAULT_IDLE_MINS = int(os.environ.get("MEDIA_LANE_IDLE_MINS", "30"))
DEFAULT_WHISPER_HOURS = float(os.environ.get("MEDIA_LANE_WHISPER_HOURS", "2"))
DEFAULT_SUMMARY_HOURS = float(os.environ.get("MEDIA_LANE_SUMMARY_HOURS", "2"))
DEFAULT_ANALYSIS_HOURS = float(os.environ.get("MEDIA_LANE_ANALYSIS_HOURS", "2"))
DEFAULT_YT_HOURS = float(os.environ.get("MEDIA_LANE_YT_HOURS", "1"))
DEFAULT_YT_WHISPER = int(os.environ.get("MEDIA_LANE_YT_WHISPER", "0"))
DEFAULT_CHUNK = int(os.environ.get("MEDIA_LANE_WHISPER_CHUNK", "2"))
RECEIPT_PATH = ROOT / "_system" / "data" / "lane_receipts" / "media-analysis.json"
STATE_PATH = ROOT / "tmp" / "media_lane_state.json"
LOCK_PATH = ROOT / "tmp" / "media_lane.lock"
LOG_PATH = ROOT / "tmp" / "media_lane_supervisor.log"

_stop = False


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"[{_stamp()}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def install_stop_handlers() -> None:
    def _handler(signum, _frame):
        global _stop
        _stop = True
        log(f"stop requested (signal {signum}); finishing current phase")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(doc: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def write_receipt(*, ready: bool, phase: str, extra: dict | None = None) -> None:
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "lane": "media-analysis",
        "host": "mac-media-lane",
        "model": DEFAULT_ANALYSIS_MODEL,
        "model_ready": bool(ready),
        "phase": phase,
        "probed_at": _stamp(),
        "available_mb": available_mb(),
    }
    if extra:
        payload.update(extra)
    RECEIPT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_python(args: list[str], *, env: dict | None = None) -> int:
    cmd = [sys.executable, "-u", *args]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged["PYTHONUNBUFFERED"] = "1"
    log("exec: " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=merged,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        try:
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line if line.endswith("\n") else line + "\n")
        except OSError:
            pass
        if _stop:
            proc.send_signal(signal.SIGTERM)
            break
    return proc.wait(timeout=1800)


def json_status(script: str, *extra: str) -> dict:
    try:
        out = subprocess.check_output(
            [sys.executable, str(SCRIPTS / script), "--status", *extra],
            cwd=str(ROOT),
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out.strip(), "error": "unparseable status"}


def whisper_pending() -> int:
    doc = json_status("whisper_backfill_daemon.py")
    if "error" in doc and "pending" not in doc:
        return -1
    return int(doc.get("pending") or 0)


def analysis_remaining(script: str) -> int:
    doc = json_status(script)
    if "error" in doc and "remaining" not in doc:
        return -1
    return int(doc.get("remaining") or 0)


def reconcile_whisper_orphans() -> None:
    """Queue catalogued audio episodes that have no transcript or queue row.

    Runs every cycle, not only inside the Whisper phase: otherwise orphans
    stay invisible while the backlog happens to read empty.
    """
    try:
        out = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "fetch_podcast_transcript.py"),
                "--reconcile-whisper-orphans",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        doc = json.loads(out.stdout or "{}")
        queued = int(doc.get("queued") or 0)
        if queued:
            log(f"whisper orphan reconcile queued {queued} episode(s)")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        log(f"whisper orphan reconcile failed: {exc}; continuing")


def reader_summary_remaining() -> int:
    doc = json_status("summarize_podcast_episode.py")
    if "error" in doc and "remaining_model" not in doc and "remaining" not in doc:
        return -1
    return int(doc.get("remaining_model", doc.get("remaining", 0)) or 0)


def find_lms() -> Path | None:
    home = Path.home()
    candidates = [
        home / ".lmstudio" / "bin" / "lms",
        home / "Library" / "Application Support" / "LM Studio" / "lms",
        Path("/opt/homebrew/bin/lms"),
        Path("/usr/local/bin/lms"),
    ]
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def model_ready(model: str) -> bool:
    probe = SCRIPTS / "llm_ready.py"
    if not probe.exists():
        log(f"readiness probe missing at {probe}")
        return False
    code = subprocess.call(
        [sys.executable, str(probe), "--model", model],
        cwd=str(ROOT),
    )
    return code == 0


def ensure_model(model: str, model_path: str, context_length: int) -> bool:
    if model_ready(model):
        write_receipt(ready=True, phase="model-ready")
        return True
    lms = find_lms()
    if lms is None:
        log("lms CLI not found; start LM Studio and load the model, or install the CLI")
        write_receipt(ready=False, phase="model-missing-cli")
        return False
    log(f"loading {model_path} as {model} (ctx={context_length} parallel=1)")
    # --gpu max uses Metal on Apple Silicon. If an older lms rejects the flag,
    # retry without it rather than failing the whole lane.
    base = [
        str(lms), "load", model_path,
        "--identifier", model,
        "-c", str(context_length),
        "--parallel", "1",
        "-y",
    ]
    try:
        result = subprocess.run(base + ["--gpu", "max"], cwd=str(ROOT), timeout=600)
        if result.returncode != 0:
            subprocess.run(base, cwd=str(ROOT), timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"lms load failed: {exc}")
        write_receipt(ready=False, phase="model-load-failed")
        return False
    ok = model_ready(model)
    write_receipt(ready=ok, phase="model-ready" if ok else "model-not-ready")
    return ok


def youtube_due(state: dict, min_hours: float = 20.0) -> bool:
    last = state.get("last_youtube_at")
    if not last:
        return True
    try:
        then = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    age_h = (datetime.now(timezone.utc) - then).total_seconds() / 3600.0
    return age_h >= min_hours


_active_floor_mb = DEFAULT_MEMORY_FLOOR


def phase_whisper(*, threads: int, chunk: int, hours: float, push: bool) -> int:
    wait_for_memory(_active_floor_mb, log=log, stop_flag=lambda: _stop)
    if _stop:
        return 0
    # Catalogued episodes with audio but no transcript/queue row are invisible
    # to the daemon until they are reconciled into its backlog.
    reconcile = run_python([str(SCRIPTS / "fetch_podcast_transcript.py"), "--reconcile-whisper-orphans"])
    if reconcile != 0:
        log(f"whisper orphan reconcile exited code={reconcile}; continuing")
    if _stop:
        return 0
    env = {
        "WHISPER_MODEL": DEFAULT_MODEL,
        "WHISPER_THREADS": str(threads),
    }
    args = [
        str(SCRIPTS / "whisper_backfill_daemon.py"),
        "--hours", str(hours),
        "--chunk", str(chunk),
        "--push-every-minutes", "15",
    ]
    if not push:
        args.append("--no-push")
    return run_python(args, env=env)


def phase_youtube(*, hours: float, whisper: int, push: bool) -> int:
    wait_for_memory(_active_floor_mb, log=log, stop_flag=lambda: _stop)
    if _stop:
        return 0
    args = [
        str(SCRIPTS / "youtube_lane.py"),
        "--hours", str(hours),
        "--whisper", str(whisper),
    ]
    if not push:
        args.append("--no-push")
    return run_python(args)


def phase_reader_summary(*, model: str, hours: float, push: bool) -> int:
    wait_for_memory(_active_floor_mb, log=log, stop_flag=lambda: _stop)
    if _stop:
        return 0
    args = [
        str(SCRIPTS / "summarize_podcast_episode.py"),
        "--llm",
        "--model", model,
        "--hours", str(hours),
        "--push-every-minutes", "15",
    ]
    if push:
        args.append("--push")
    return run_python(args)


def phase_publish_podcast(*, push: bool) -> int:
    script = SCRIPTS / "publish_podcast_dashboard.py"
    if not script.exists():
        log("publish_podcast_dashboard.py missing; reader summaries will publish with the next dashboard build")
        return 0
    wait_for_memory(_active_floor_mb, log=log, stop_flag=lambda: _stop)
    if _stop:
        return 0
    args = [str(script)]
    if push:
        args.append("--push")
    return run_python(args)


def phase_analysis(script: str, *, model: str, hours: float, push: bool) -> int:
    wait_for_memory(_active_floor_mb, log=log, stop_flag=lambda: _stop)
    if _stop:
        return 0
    args = [
        str(SCRIPTS / script),
        "--model", model,
        "--hours", str(hours),
        "--push-every-minutes", "15",
    ]
    # Whisper is idle in this phase by construction. Podcast batch understands
    # --share-with-whisper; video batch takes --max-wait-minutes 0.
    if script.endswith("analyze_podcast_batch.py"):
        args.append("--share-with-whisper")
    else:
        args.extend(["--max-wait-minutes", "0"])
    if not push:
        args.append("--no-push")
    return run_python(args)


def status_snapshot() -> dict:
    return {
        "available_mb": available_mb(),
        "whisper_pending": whisper_pending(),
        "reader_summary_remaining": reader_summary_remaining(),
        "podcast_analysis_remaining": analysis_remaining("analyze_podcast_batch.py"),
        "video_analysis_remaining": analysis_remaining("analyze_video_batch.py"),
        "receipt": str(RECEIPT_PATH),
        "lock": str(LOCK_PATH),
        "defaults": {
            "whisper_model": DEFAULT_MODEL,
            "whisper_threads": default_whisper_threads(),
            "analysis_model": DEFAULT_ANALYSIS_MODEL,
            "memory_floor_mb": DEFAULT_MEMORY_FLOOR,
            "idle_mins": DEFAULT_IDLE_MINS,
        },
    }


def run_forever(args: argparse.Namespace) -> int:
    global _active_floor_mb
    install_stop_handlers()
    _active_floor_mb = int(args.memory_floor)
    prio = deprioritise(args.nice)
    threads = args.threads if args.threads > 0 else default_whisper_threads()
    log(
        f"media lane start: nice={prio} threads={threads} "
        f"floor={args.memory_floor}MB model={args.model} repo={ROOT}"
    )

    lock = FileLock(LOCK_PATH)
    if not lock.acquire(blocking=False):
        log("another media lane holds the lock; exiting")
        return 0

    reader_turn = True
    whisper_turn = True
    backoff = args.min_backoff
    try:
        while not _stop:
            # Rotate log softly.
            try:
                if LOG_PATH.exists() and LOG_PATH.stat().st_size > args.max_log_mb * 1024 * 1024:
                    LOG_PATH.replace(Path(str(LOG_PATH) + ".1"))
            except OSError:
                pass

            wait_for_memory(args.memory_floor, log=log, stop_flag=lambda: _stop)
            if _stop:
                break

            reconcile_whisper_orphans()
            pending = whisper_pending()
            if pending < 0:
                log(f"could not read whisper backlog; retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, args.max_backoff)
                continue

            # Whisper goes first, but in bounded windows: after each window
            # the analysis phases get their turn, so a large transcription
            # backlog cannot starve reader summaries for days.
            if pending > 0 and whisper_turn:
                log(f"phase=whisper ({pending} pending)")
                code = phase_whisper(
                    threads=threads,
                    chunk=args.chunk,
                    hours=args.whisper_hours,
                    push=not args.no_push,
                )
                log(f"whisper phase exited code={code}")
                whisper_turn = False
                backoff = args.min_backoff if code == 0 else min(backoff * 2, args.max_backoff)
                continue

            state = load_state()
            if youtube_due(state) and not _stop:
                yt_whisper = args.yt_whisper
                log(f"phase=youtube (hours={args.yt_hours} whisper={yt_whisper})")
                code = phase_youtube(
                    hours=args.yt_hours,
                    whisper=yt_whisper,
                    push=not args.no_push,
                )
                state["last_youtube_at"] = _stamp()
                state["last_youtube_code"] = code
                save_state(state)
                log(f"youtube phase exited code={code}")
                # Fall through to analysis in the same loop iteration only when
                # whisper is still empty; otherwise the next iteration will
                # prefer transcription again.

            if not ensure_model(args.model, args.model_path, args.context_length):
                log(f"model not ready; retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, args.max_backoff)
                continue

            reader_left = reader_summary_remaining()
            video_left = analysis_remaining("analyze_video_batch.py")
            pod_left = analysis_remaining("analyze_podcast_batch.py")
            if reader_left < 0 and video_left < 0 and pod_left < 0:
                log(f"could not read analysis status; retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, args.max_backoff)
                continue

            if reader_left > 0 and (video_left <= 0 or reader_turn):
                log(f"phase=reader-summary ({reader_left} remaining)")
                code = phase_reader_summary(
                    model=args.model,
                    hours=args.summary_hours,
                    push=not args.no_push,
                )
                log(f"reader-summary phase exited code={code}")
                publish_code = phase_publish_podcast(push=not args.no_push)
                log(f"podcast publish exited code={publish_code}")
                reader_turn = False
                whisper_turn = True
                backoff = args.min_backoff if code == 0 else min(backoff * 2, args.max_backoff)
                continue

            if video_left > 0:
                log(f"phase=video-analysis ({video_left} remaining)")
                code = phase_analysis(
                    "analyze_video_batch.py",
                    model=args.model,
                    hours=args.analysis_hours,
                    push=not args.no_push,
                )
                log(f"video analysis exited code={code}")
                reader_turn = True
                whisper_turn = True
                backoff = args.min_backoff
                continue

            if pod_left > 0:
                log(f"phase=podcast-analysis ({pod_left} remaining)")
                code = phase_analysis(
                    "analyze_podcast_batch.py",
                    model=args.model,
                    hours=args.analysis_hours,
                    push=not args.no_push,
                )
                log(f"podcast analysis exited code={code}")
                whisper_turn = True
                backoff = args.min_backoff
                continue

            if pending > 0:
                # Nothing else is waiting; spend the window transcribing.
                log(f"phase=whisper ({pending} pending)")
                code = phase_whisper(
                    threads=threads,
                    chunk=args.chunk,
                    hours=args.whisper_hours,
                    push=not args.no_push,
                )
                log(f"whisper phase exited code={code}")
                whisper_turn = False
                backoff = args.min_backoff if code == 0 else min(backoff * 2, args.max_backoff)
                continue

            if args.exit_when_empty:
                log("all queues empty; exiting")
                break
            log(f"all queues empty; idle {args.idle_mins}m")
            write_receipt(ready=True, phase="idle", extra={
                "whisper_pending": 0,
                "reader_summary_remaining": 0,
                "podcast_remaining": 0,
                "video_remaining": 0,
            })
            for _ in range(args.idle_mins * 60):
                if _stop:
                    break
                time.sleep(1)
            backoff = args.min_backoff
    finally:
        lock.release()
        log("media lane exit")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--status", action="store_true", help="Print queue snapshot and exit.")
    p.add_argument("--once", action="store_true", help="One phase cycle then exit (testing).")
    p.add_argument("--exit-when-empty", action="store_true")
    p.add_argument("--no-push", action="store_true")
    p.add_argument("--model", default=DEFAULT_ANALYSIS_MODEL)
    p.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    p.add_argument("--context-length", type=int, default=16384)
    p.add_argument("--threads", type=int, default=0, help="Whisper CPU threads (0 = auto cap).")
    p.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
    p.add_argument("--nice", type=int, default=15)
    p.add_argument("--memory-floor", type=int, default=DEFAULT_MEMORY_FLOOR)
    p.add_argument("--whisper-hours", type=float, default=DEFAULT_WHISPER_HOURS)
    p.add_argument("--summary-hours", type=float, default=DEFAULT_SUMMARY_HOURS)
    p.add_argument("--analysis-hours", type=float, default=DEFAULT_ANALYSIS_HOURS)
    p.add_argument("--yt-hours", type=float, default=DEFAULT_YT_HOURS)
    p.add_argument("--yt-whisper", type=int, default=DEFAULT_YT_WHISPER,
                   help="Videos to Whisper per YouTube pass. 0 queues only.")
    p.add_argument("--idle-mins", type=int, default=DEFAULT_IDLE_MINS)
    p.add_argument("--min-backoff", type=int, default=120)
    p.add_argument("--max-backoff", type=int, default=1800)
    p.add_argument("--max-log-mb", type=int, default=32)
    args = p.parse_args()

    if args.status:
        print(json.dumps(status_snapshot(), indent=2))
        return 0

    if args.once:
        args.exit_when_empty = True
        # Cap one cycle: whisper hours small.
        args.whisper_hours = min(args.whisper_hours, 0.05)
        args.summary_hours = min(args.summary_hours, 0.05)
        args.analysis_hours = min(args.analysis_hours, 0.05)
        args.yt_hours = min(args.yt_hours, 0.05)
        args.idle_mins = 0

    return run_forever(args)


if __name__ == "__main__":
    raise SystemExit(main())
