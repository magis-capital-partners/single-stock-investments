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
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "dashboard" / "data" / "insights" / "manifest.json"
STATE = ROOT / "_system" / "data" / "media_analysis_ratchet.json"

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
        out[name] = {"analysed": analysed, "corpus": _int(row.get(corpus_key))}
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

        if analysed is None:
            problems.append(
                f"{name}: source_health has no with_analysis field; "
                "build_insights.py should be writing it"
            )
            nxt[name] = was or {}
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
            continue

        nxt[name] = {"analysed": analysed, "corpus": corpus, "last_change_at": last_change}
        backlog = (corpus - analysed) if corpus is not None else None
        if not backlog or backlog <= 0:
            continue  # nothing left to read; standing still is correct
        try:
            stalled = (today - date.fromisoformat(str(last_change))).days
        except ValueError:
            continue
        if stalled >= stall_days:
            problems.append(
                f"{name}: analysed stuck at {analysed} for {stalled} days "
                f"with {backlog} unanalysed of {corpus} - the analysis lane is "
                "not running (check the SSI Podcast Analysis task and `lms ps`)"
            )

    return problems, {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "sources": nxt}


def check(*, today: date | None = None, stall_days: int = STALL_DAYS):
    manifest = load_json(MANIFEST)
    observed = observe(manifest)
    problems, nxt = evaluate(
        observed, load_json(STATE), today=today or date.today(), stall_days=stall_days
    )
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
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(nxt, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"observed": observed, "problems": problems}, indent=2))
    else:
        for name, row in sorted(observed.items()):
            analysed, corpus = row["analysed"], row["corpus"]
            shown = "?" if analysed is None else analysed
            print(f"{name}: analysed {shown} of {corpus if corpus is not None else '?'}")
        for msg in problems:
            print(f"WARN: {msg}")
        if not problems:
            print("OK: media analysis has moved within the stall window")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
