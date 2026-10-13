#!/usr/bin/env python3
"""Build ``dashboard/data/desk_briefs.json`` from the latest valid brief per desk.

Briefs arrive by pull request under ``_system/data/desk_briefs/<desk>/<date>.json``
(``_system/data/desk_briefs/README.md``). This joins the newest structurally valid
file for each desk into one payload for the Inbox: per-desk cards, a flat item list
with desk and owner, counts, and a health block. A brief older than seven days stays
listed with ``stale: true``; an invalid file is excluded and named in
``health.structural_errors``.

    python _system/scripts/build_desk_briefs.py
    python _system/scripts/build_desk_briefs.py --out /tmp/desk_briefs.json --now 2026-10-12T12:00:00Z
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, time, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_desk_briefs import (  # noqa: E402
    BRIEFS_DIR,
    DESK_LABELS,
    DESKS,
    REGISTRY_PATH,
    ROOT,
    SCHEMA_PATH,
    check_all,
)

SCHEMA_VERSION = "desk_briefs.v1"
DASHBOARD_PATH = ROOT / "dashboard" / "data" / "desk_briefs.json"
STALE_DAYS = 7
RESEARCH_ONLY = {"research_only": True, "in_base_irr": False, "authority": "none"}
CAPTION = (
    "Ranked output from the Magis desk bots, one brief per desk per day, filed by pull request and "
    "checked by schema. A brief is research only: it carries no authority, sizes nothing, and never "
    "enters a base IRR. The one number on each row is the dashboard's or the filing's, not the bot's."
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(value: object) -> datetime | None:
    """ISO datetimes with Z or an offset, or a bare date (read as 00:00Z)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hours_between(later: datetime, earlier: datetime) -> float:
    return round((later - earlier).total_seconds() / 3600.0, 1)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, newline="\n") as handle:
        handle.write(text)
        tmp = Path(handle.name)
    tmp.replace(path)


def latest_per_desk(briefs: list[dict]) -> dict[str, dict]:
    """Newest valid brief per desk by as_of, then by path (a later file name wins ties)."""
    chosen: dict[str, dict] = {}
    for record in briefs:
        if record["errors"] or not isinstance(record.get("payload"), dict):
            continue
        desk = record["payload"].get("desk")
        if desk not in DESKS:
            continue
        key = (record["payload"].get("as_of") or "", record["path"])
        current = chosen.get(desk)
        if current is None or key > (current["payload"].get("as_of") or "", current["path"]):
            chosen[desk] = record
    return chosen


def desk_entry(record: dict, *, now: datetime, root: Path, stale_days: int) -> tuple[dict, list[str]]:
    payload = record["payload"]
    as_of = date.fromisoformat(payload["as_of"])
    as_of_start = datetime.combine(as_of, time.min, tzinfo=timezone.utc)
    as_of_end = datetime.combine(as_of, time.max, tzinfo=timezone.utc)
    age_hours = max(0.0, hours_between(now, as_of_start))
    stale = age_hours > stale_days * 24
    problems: list[str] = []
    if stale:
        problems.append(f"{payload['desk']} brief is {age_hours / 24:.0f} days old ({payload['as_of']})")
    inputs = []
    for entry in payload.get("inputs_read") or []:
        generated = parse_stamp(entry.get("generated_at"))
        exists = (root / str(entry.get("path"))).exists()
        if not exists:
            problems.append(f"{payload['desk']} input missing: {entry.get('path')}")
        inputs.append(
            {
                "path": entry.get("path"),
                "generated_at": entry.get("generated_at"),
                "age_hours_at_read": max(0.0, hours_between(as_of_end, generated)) if generated else None,
                "exists": exists,
            }
        )
    items = []
    for item in payload.get("items") or []:
        items.append(
            {
                "ticker": item.get("ticker"),
                "headline": item.get("headline"),
                "one_number": item.get("one_number"),
                "lane": item.get("lane"),
                "evidence": [
                    {"kind": e.get("kind"), "ref": e.get("ref"), "url": e.get("url")} for e in item.get("evidence") or []
                ],
                "confidence": item.get("confidence"),
                "next": item.get("next"),
                "handoff": item.get("handoff"),
            }
        )
    entry = {
        "desk": payload["desk"],
        "desk_label": DESK_LABELS.get(payload["desk"], payload["desk"]),
        "owner": payload["owner"],
        "author": payload["author"],
        "as_of": payload["as_of"],
        "age_hours": age_hours,
        "stale": stale,
        "path": record["path"],
        "items": items,
        "inputs_read": inputs,
        "screens_empty": list(payload.get("screens_empty") or []),
        "notes": payload.get("notes"),
    }
    return entry, problems


def build(
    *,
    briefs_dir: Path = BRIEFS_DIR,
    registry_path: Path = REGISTRY_PATH,
    schema_path: Path = SCHEMA_PATH,
    root: Path = ROOT,
    now: datetime | None = None,
    stale_days: int = STALE_DAYS,
) -> dict:
    now = now or utc_now()
    report = check_all(
        briefs_dir=briefs_dir,
        registry_path=registry_path,
        schema_path=schema_path,
        root=root,
        today=now.date(),
    )
    chosen = latest_per_desk(report["briefs"])
    desks: list[dict] = []
    problems: list[str] = []
    for desk in DESKS:
        record = chosen.get(desk)
        if record is None:
            continue
        entry, entry_problems = desk_entry(record, now=now, root=root, stale_days=stale_days)
        desks.append(entry)
        problems.extend(entry_problems)
    items_flat = [
        {**item, "desk": d["desk"], "owner": d["owner"], "as_of": d["as_of"], "author": d["author"], "stale": d["stale"]}
        for d in desks
        for item in d["items"]
    ]
    structural_errors = list(report["errors"])
    status = "unhealthy" if structural_errors else ("degraded" if problems else "healthy")
    counts = {
        "briefs": len(desks),
        "items": len(items_flat),
        "files": report["files"],
        "by_desk": dict(Counter(item["desk"] for item in items_flat)),
        "by_owner": dict(Counter(item["owner"] for item in items_flat)),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": stamp(now),
        "caption": CAPTION,
        "desks": desks,
        "items_flat": items_flat,
        "desks_without_brief": [desk for desk in DESKS if desk not in chosen],
        "desk_labels": dict(DESK_LABELS),
        "counts": counts,
        "health": {
            "status": status,
            "structural_errors": structural_errors,
            "problems": problems,
            "warnings": list(report["warnings"]),
            "stale_days": stale_days,
            "checked_at": stamp(now),
        },
        **RESEARCH_ONLY,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help=f"default {DASHBOARD_PATH.relative_to(ROOT).as_posix()}")
    parser.add_argument("--briefs-dir", type=Path, default=BRIEFS_DIR)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--now", type=parse_stamp, default=None, help="override the clock, e.g. 2026-10-12T12:00:00Z (tests)")
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS)
    args = parser.parse_args(argv)
    payload = build(
        briefs_dir=args.briefs_dir,
        registry_path=args.registry,
        schema_path=args.schema,
        root=args.root,
        now=args.now,
        stale_days=args.stale_days,
    )
    target = args.out or DASHBOARD_PATH
    write_json(target, payload)
    c = payload["counts"]
    print(
        f"Wrote {target} briefs={c['briefs']} items={c['items']} files={c['files']} "
        f"without_brief={len(payload['desks_without_brief'])} health={payload['health']['status']}"
    )
    for line in payload["health"]["structural_errors"]:
        print(f"ERROR {line}")
    for line in payload["health"]["problems"]:
        print(f"WARN  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
