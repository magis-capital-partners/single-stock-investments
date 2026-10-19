#!/usr/bin/env python3
"""Has the media analysis lane read anything lately?

The podcast and video analysers ran on this workstation, not in CI, and when
they stopped on 2026-09-11 nothing noticed for fourteen days. Every existing
signal said healthy the whole time, because every existing signal was a count
of things *collected*:

    episodes    4,609 -> 4,627      (+18)
    transcripts 4,063 -> 4,222     (+159)
    videos         90 ->     95      (+5)
    analysed      429 ->    429       (0)

The scheduled task read "Running" while holding a deleted script. The model
server answered on its port while no client was connected to it. The YouTube
lane exited 0 daily. A growing corpus that attributes less is the failure mode
this repo keeps rediscovering, so the check has to key off the one number that
can fall while everything else rises.

STALL, NOT LEVEL. A low analysed fraction is a backlog, which is ordinary and
self-correcting. What is not ordinary is that fraction's numerator standing
still while work remains. So this stores the last value and the day it last
moved, and complains about elapsed time rather than about a ratio. A lane that
is merely slow keeps resetting its own clock; only a lane that is *stopped*
trips it.

The state file is written whenever the count moves, so a fresh clone or a
deleted state file re-baselines to today rather than firing immediately -- the
opposite of a ratchet baselined on a bulk-write day, which records the most
flattering moment available and then cliffs.

Usage:
  python _system/scripts/check_media_analysis_freshness.py
  python _system/scripts/check_media_analysis_freshness.py --json
  python _system/scripts/check_media_analysis_freshness.py --update   # write state
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "dashboard" / "data" / "insights" / "manifest.json"
STATE = ROOT / "_system" / "data" / "media_analysis_ratchet.json"
RECEIPT = ROOT / "_system" / "data" / "lane_receipts" / "media-analysis.json"

# Generous on purpose. The analyser has managed ~23 items on a bad day and 115
# on a good one; either resets the clock. Four days of no movement at all means
# the lane is not running, which is the only thing this is trying to catch.
STALL_DAYS = 4

# Which source_health rows carry an analysis stage, and what the backlog is
# measured against. Nothing else on the row is a depth signal.
SOURCES = {
    "podcasts": "transcript_count",
    "videos": "items",
}

# Neither analyser runs in CI. Both are workstation scheduled tasks. The
# Research Watchdog only notices that the analysed count stopped moving.
# See install_local_lane_tasks.ps1 and analysis_supervisor.ps1.
LANE_CHECK = {
    "podcasts": (
        "podcast analysis",
        "This lane does not run in CI. On the workstation, check scheduled task "
        "'SSI Podcast Analysis' (analysis_supervisor.ps1 runs analyze_podcast_batch.py) "
        "and `lms ps` for the local model. Last-result and the task log are on that machine.",
    ),
    "videos": (
        "video analysis",
        "This lane does not run in CI. On the workstation, the same scheduled task "
        "'SSI Podcast Analysis' drains videos (analyze_video_batch.py), and "
        "youtube_lane.py publishes the catalog. Last-result and the task log are on that machine.",
    ),
}


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def observe(manifest: dict) -> dict[str, dict]:
    """Current depth per source, skipping any the manifest does not describe."""
    health = manifest.get("source_health") or {}
    out: dict[str, dict] = {}
    for name, corpus_key in SOURCES.items():
        row = health.get(name)
        if not isinstance(row, dict):
            continue
        analysed = _int(row.get("with_analysis"))
        if analysed is None:
            # Written by build_insights.py. Absent means an old manifest or a
            # rebuild that dropped it -- report it rather than reading it as
            # zero, which would look like a total collapse.
            out[name] = {"analysed": None, "corpus": _int(row.get(corpus_key))}
            continue
        item = {"analysed": analysed, "corpus": _int(row.get(corpus_key))}
        if name == "podcasts" and row.get("with_reader_summary") is not None:
            item["reader_summaries"] = _int(row.get("with_reader_summary"))
            item["reader_corpus"] = _int(row.get("items") or row.get("episode_count"))
        out[name] = item
    return out


def evaluate(
    observed: dict[str, dict],
    state: dict,
    *,
    today: date,
    stall_days: int = STALL_DAYS,
) -> tuple[list[str], dict]:
    """Return (problems, next_state). Pure, so the tests can move the clock."""
    problems: list[str] = []
    previous = state.get("sources") or {}
    nxt: dict[str, dict] = {}

    for name, now in sorted(observed.items()):
        analysed, corpus = now["analysed"], now["corpus"]
        was = previous.get(name) or {}

        # Reader summaries have their own stall clock.  Claims can keep
        # moving while every new episode remains unreadable, and vice versa.
        reader_next = None
        reader_value = _int(now.get("reader_summaries"))
        reader_corpus = _int(now.get("reader_corpus"))
        if reader_value is not None and reader_corpus is not None:
            prior_reader = was.get("reader") if isinstance(was.get("reader"), dict) else {}
            prior_value = _int(prior_reader.get("reader_summaries"))
            prior_change = prior_reader.get("last_change_at")
            if prior_value is None or reader_value != prior_value or not prior_change:
                reader_next = {
                    "reader_summaries": reader_value,
                    "reader_corpus": reader_corpus,
                    "last_change_at": today.isoformat(),
                }
            else:
                reader_next = {
                    "reader_summaries": reader_value,
                    "reader_corpus": reader_corpus,
                    "last_change_at": prior_change,
                }
                backlog = reader_corpus - reader_value
                if backlog > 0:
                    try:
                        stalled = (today - date.fromisoformat(str(prior_change))).days
                    except ValueError:
                        stalled = 0
                    if stalled >= stall_days:
                        problems.append(
                            f"{name}: reader-summary lane is stale. summaries stuck at "
                            f"{reader_value} for {stalled} days (last moved {prior_change}) "
                            f"with {backlog} episodes lacking a reader summary. "
                            "Check media_lane_supervisor.py phase=reader-summary and "
                            "summarize_podcast_episode.py --status on the Mac lane."
                        )

        if analysed is None:
            problems.append(
                f"{name}: source_health has no with_analysis field; "
                "build_insights.py should be writing it"
            )
            nxt[name] = was or {}
            if reader_next is not None:
                nxt[name]["reader"] = reader_next
            continue

        last_value = _int(was.get("analysed"))
        last_change = was.get("last_change_at")

        if last_value is None or analysed != last_value or not last_change:
            # Moved, or nothing to compare against yet. Re-baseline to today.
            nxt[name] = {
                "analysed": analysed,
                "corpus": corpus,
                "last_change_at": today.isoformat(),
            }
            if reader_next is not None:
                nxt[name]["reader"] = reader_next
            continue

        nxt[name] = {"analysed": analysed, "corpus": corpus, "last_change_at": last_change}
        if reader_next is not None:
            nxt[name]["reader"] = reader_next
        backlog = (corpus - analysed) if corpus is not None else None
        if not backlog or backlog <= 0:
            continue  # nothing left to read; standing still is correct
        try:
            stalled = (today - date.fromisoformat(str(last_change))).days
        except ValueError:
            continue
        if stalled >= stall_days:
            lane, where = LANE_CHECK.get(name, (name, "Check the workstation analyser; it does not run in CI."))
            problems.append(
                f"{name}: {lane} lane is stale. analysed stuck at {analysed} "
                f"for {stalled} days (last moved {last_change}) "
                f"with {backlog} unanalysed of {corpus}. {where}"
            )

    return problems, {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "sources": nxt}


def _day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def evaluate_receipt(
    receipt: dict | None,
    state: dict,
    *,
    today: date,
    stall_days: int = STALL_DAYS,
    count_stalled: bool = False,
) -> tuple[list[str], dict]:
    """The local analyser writes a receipt. A missing one starts a clock.

    The clock is not a failure by itself. It becomes one when the analysed
    count is also stuck, so a lane that starts reading again goes quiet even
    if this machine has not committed a receipt yet. A receipt that says the
    model is ready clears the clock.
    """
    prior = state.get("receipt") if isinstance(state.get("receipt"), dict) else {}
    if receipt and receipt.get("model_ready") is True:
        return [], {
            "model_ready": True,
            "probed_at": receipt.get("probed_at"),
            "absent_since": None,
        }

    absent_since = prior.get("absent_since")
    if receipt and receipt.get("model_ready") is False:
        probed = _day(str(receipt.get("probed_at") or ""))
        # A failing probe is the same fact as no probe: the lane is not reading.
        if probed is not None and not absent_since:
            absent_since = probed.isoformat()

    if not absent_since:
        return [], {"model_ready": False, "absent_since": today.isoformat()}

    nxt = {"model_ready": False, "absent_since": absent_since, "probed_at": (receipt or {}).get("probed_at")}
    started = _day(str(absent_since))
    if started is None or not count_stalled:
        return [], nxt
    stalled = (today - started).days
    if stalled < stall_days:
        return [], nxt
    return [
        f"media-analysis lane is stale: no ready model receipt since {absent_since} "
        f"({stalled} days; last ready probe none) and the analysed count is stuck. "
        "Podcast and video analysis run on the workstation, not in CI. "
        "Check scheduled task 'SSI Podcast Analysis' (analysis_supervisor.ps1, `lms ps`) "
        "or Mac Mini LaunchAgent com.magis.ssi.media-lane "
        "(media_lane_supervisor.py / install_mac_media_lane.sh) and youtube_lane.py. "
        "See _system/scripts/install_local_lane_tasks.ps1."
    ], nxt


def note_observed_counts(manifest: dict, *, today: date | None = None) -> bool:
    """Move the stall clock when a rebuild changes how many items were read.

    The insights shard writer calls this and commits the file with the
    manifest. The watchdog only reads it. A rebuild that does not change the
    analysed count leaves the clock where it is, so a stuck lane stays stuck.
    """
    observed = observe(manifest if isinstance(manifest, dict) else {})
    if not observed:
        return False
    state = load_json(STATE)
    _, nxt = evaluate(observed, state, today=today or date.today())
    nxt["receipt"] = state.get("receipt") if isinstance(state.get("receipt"), dict) else {}
    if state.get("sources") == nxt.get("sources") and state.get("receipt") == nxt.get("receipt"):
        return False
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(nxt, indent=2) + "\n", encoding="utf-8")
    return True


def check(*, today: date | None = None, stall_days: int = STALL_DAYS):
    manifest = load_json(MANIFEST)
    observed = observe(manifest)
    state = load_json(STATE)
    today = today or date.today()
    problems, nxt = evaluate(observed, state, today=today, stall_days=stall_days)
    receipt = load_json(RECEIPT) or None
    receipt_problems, receipt_state = evaluate_receipt(
        receipt, state, today=today, stall_days=stall_days, count_stalled=bool(problems),
    )
    problems.extend(receipt_problems)
    nxt["receipt"] = receipt_state
    return observed, problems, nxt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--update", action="store_true",
                    help="persist the new baseline (the daily lane passes this)")
    ap.add_argument("--stall-days", type=int, default=STALL_DAYS)
    args = ap.parse_args()

    observed, problems, nxt = check(stall_days=args.stall_days)

    if args.update:
        previous = load_json(STATE)
        moved = previous.get("sources") != nxt.get("sources") or previous.get("receipt") != nxt.get("receipt")
        if moved:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(nxt, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"observed": observed, "problems": problems}, indent=2))
    else:
        for name, row in sorted(observed.items()):
            analysed, corpus = row["analysed"], row["corpus"]
            shown = "?" if analysed is None else analysed
            print(f"{name}: analysed {shown} of {corpus if corpus is not None else '?'}")
            if row.get("reader_summaries") is not None:
                print(
                    f"{name}: reader summaries {row['reader_summaries']} of "
                    f"{row.get('reader_corpus') if row.get('reader_corpus') is not None else '?'}"
                )
        for msg in problems:
            print(f"WARN: {msg}")
            # The Actions log otherwise shows only "exit code 1". Name the lane,
            # when it last moved, and the workstation task to check.
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::error title=Media analysis lane stale::{msg}")
        if not problems:
            print("OK: media analysis has moved within the stall window")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
