#!/usr/bin/env python3
"""Aggregate unpromoted [PROPOSED ...] memories and corrections into one review.

Weekly knowledge-compounding loop: daily logs accumulate [PROPOSED MUNGER] /
[PROPOSED PABRAI] / [PROPOSED STAHL] / [PROPOSED MOI] / [PROPOSED COMPANY]
bullets that pile up unless a human promotes them. This script rolls the
trailing window into a single digest in _system/reviews/pending/ so the human
filter reviews one file instead of scanning every daily log.

It never writes _system/memory/MEMORY.md (human-quality-filter rule).

Usage:
  python _system/scripts/build_memory_digest.py --date 2026-07-20
  python _system/scripts/build_memory_digest.py --date 2026-07-20 --days 7 --write
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
DAILY_DIR = ROOT / "_system" / "memory" / "daily"
MEMORY_PATH = ROOT / "_system" / "memory" / "MEMORY.md"
CORRECTIONS_PATH = ROOT / "_system" / "memory" / "corrections.md"
PENDING_DIR = ROOT / "_system" / "reviews" / "pending"

PROPOSED_RE = re.compile(r"^\s*[-*]\s*\[PROPOSED(?:\s+([A-Z]+))?\]\s*(.+)$")
GROUP_ORDER = ["COMPANY", "MUNGER", "PABRAI", "STAHL", "MOI", "GENERAL"]


def window_dates(end: date, days: int) -> list[date]:
    return [end - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`]", "", text)).strip().lower()


def collect_proposals(dates: list[date]) -> dict[str, list[tuple[str, str]]]:
    """Group -> [(day, bullet)] from daily logs, in chronological order."""
    grouped: dict[str, list[tuple[str, str]]] = {group: [] for group in GROUP_ORDER}
    for day in dates:
        path = DAILY_DIR / f"{day.isoformat()}.md"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = PROPOSED_RE.match(line)
            if not match:
                continue
            tag = match.group(1) or "GENERAL"
            if tag == "MEMORY":
                tag = "GENERAL"
            group = tag if tag in GROUP_ORDER else "GENERAL"
            grouped[group].append((day.isoformat(), match.group(2).strip()))
    return grouped


def drop_promoted(grouped: dict[str, list[tuple[str, str]]]) -> tuple[dict[str, list[tuple[str, str]]], int]:
    """Drop bullets whose text already lives in MEMORY.md (human promoted)."""
    try:
        promoted = normalize(MEMORY_PATH.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        promoted = ""
    dropped = 0
    filtered: dict[str, list[tuple[str, str]]] = {}
    for group, rows in grouped.items():
        kept = []
        for day, bullet in rows:
            if promoted and normalize(bullet)[:120] in promoted:
                dropped += 1
            else:
                kept.append((day, bullet))
        filtered[group] = kept
    return filtered, dropped


def collect_corrections(dates: list[date]) -> list[str]:
    """Correction table rows within the window (Date | Ticker | ... format)."""
    try:
        lines = CORRECTIONS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    valid = {day.isoformat() for day in dates}
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] in valid:
            rows.append("| " + " | ".join(cells) + " |")
    return rows


def render_digest(end: date, days: int) -> tuple[str, int]:
    dates = window_dates(end, days)
    grouped, promoted_count = drop_promoted(collect_proposals(dates))
    corrections = collect_corrections(dates)
    total = sum(len(rows) for rows in grouped.values())

    out = [
        f"# Memory digest — week ending {end.isoformat()}",
        "",
        f"Window: {dates[0].isoformat()} to {end.isoformat()} "
        f"({total} unpromoted proposals, {len(corrections)} corrections"
        + (f", {promoted_count} already promoted and skipped" if promoted_count else "")
        + ")",
        "",
        "Human filter workflow: discuss, promote approved bullets into",
        "`_system/memory/MEMORY.md` genius sections, log rejections in",
        "`_system/memory/corrections.md`, then move this file to",
        "`_system/reviews/approved/`.",
        "",
    ]
    labels = {
        "COMPANY": "Company-specific",
        "MUNGER": "Charlie Munger",
        "PABRAI": "Mohnish Pabrai",
        "STAHL": "Murray Stahl",
        "MOI": "MOI / idea generation",
        "GENERAL": "Untagged proposals",
    }
    for group in GROUP_ORDER:
        rows = grouped[group]
        if not rows:
            continue
        out += [f"## {labels[group]} ({len(rows)})", ""]
        for day, bullet in rows:
            out.append(f"- ({day}) {bullet}")
        out.append("")

    out += ["## Corrections in window", ""]
    if corrections:
        out += ["| Date | Ticker | Error | Correction | Source |", "|---|---|---|---|---|"]
        out += corrections
    else:
        out.append("None logged.")
    out.append("")
    return "\n".join(out), total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Digest end date YYYY-MM-DD (default today)")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
    parser.add_argument("--write", action="store_true", help="Write the pending review file")
    args = parser.parse_args()
    end = date.fromisoformat(args.date) if args.date else date.today()

    digest, total = render_digest(end, args.days)
    if not args.write:
        print(digest)
        return 0
    if total == 0:
        print(f"No unpromoted proposals in the {args.days}-day window; digest not written.")
        return 0
    out = PENDING_DIR / f"memory_digest_{end.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(digest, encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT).as_posix()} ({total} proposals)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
