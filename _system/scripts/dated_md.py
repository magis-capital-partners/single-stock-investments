"""Helpers for dated markdown files (deep_dive_YYYY-MM-DD.md, adversarial_*, etc.)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

DATED_MD_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.md$")


def filename_date(path: Path) -> datetime | None:
    m = DATED_MD_RE.search(path.name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)


def dated_md_sort_key(path: Path) -> tuple[datetime, datetime]:
    """Primary: YYYY-MM-DD in filename. Tiebreak: mtime (same-day rewrites only)."""
    name_dt = filename_date(path)
    if name_dt is None:
        name_dt = datetime.min.replace(tzinfo=timezone.utc)
    mtime_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (name_dt, mtime_dt)


def latest_dated_md(research: Path, prefix: str) -> Path | None:
    files = list(research.glob(f"{prefix}_*.md"))
    if not files:
        return None
    return max(files, key=dated_md_sort_key)


def dated_md_label(path: Path) -> str:
    name_dt = filename_date(path)
    if name_dt:
        return name_dt.strftime("%Y-%m-%d")
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
