"""Resolve Letters/{YYYY Qn} folders by name under the Letters root.

Hard-coded quarter ids are a hint when two live folders share a canonical
name. A folder that is not a live child of Letters is never chosen over one
that is, so a trashed id cannot become the destination again.
"""
from __future__ import annotations

import re

CANONICAL_LETTERS_ID = "1z8P-tKj3lvWmx72bXUxJQ9BcUmKrhTg4"
# Live as of the 2026-10-25 Drive audit. Name resolution wins when these drift.
PREFERRED_LETTER_QUARTERS = {
    ("2026", "1"): "1QxQd4VhLv7HK1qa45izn80MMYFcS-gxg",
    ("2026", "2"): "1CtFKEdK0eTXZlY-t6bddds5rLSX5V7sO",
    ("2026", "3"): "1GcMdQfFSDMTAjmVQsjGPKb3dLOndqCiD",
}
# Previous 2026 Q3 folder. It is in the Drive trash and must not be a target.
STALE_LETTER_QUARTER_IDS = frozenset({"1wBnJHPU6-rCk4nz11JhvCL5y39rdV12W"})

QUARTER_ALIAS_RE = re.compile(r"^(\d{4})\s+([1-4])Q(?:\s+Letters)?$", re.I)
QUARTER_CANON_RE = re.compile(r"^(\d{4})\s+Q([1-4])$", re.I)


def parse_quarter_name(name: str) -> tuple[str, str] | None:
    text = (name or "").strip()
    match = QUARTER_CANON_RE.match(text) or QUARTER_ALIAS_RE.match(text)
    if not match:
        return None
    return match.group(1), match.group(2)


def canonical_letter_path(year: str, quarter: str) -> str:
    return f"Letters/{year} Q{quarter}"


def canonical_quarter_name(year: str, quarter: str) -> str:
    return f"{year} Q{quarter}"


def _child_count(folder: dict) -> int:
    try:
        return int(folder.get("_child_count") or 0)
    except (TypeError, ValueError):
        return 0


def choose_quarter_keeper(
    year: str,
    quarter: str,
    folders: list[dict],
    *,
    assume_under_letters: bool = False,
) -> dict | None:
    """Pick the live Letters/{YYYY Qn} folder from a duplicate group.

    ``assume_under_letters`` is for callers that already filtered to children
    of the Letters root and did not copy parent ids onto each row.
    """
    if not folders:
        return None
    canon = canonical_quarter_name(str(year), str(quarter))
    preferred = PREFERRED_LETTER_QUARTERS.get((str(year), str(quarter)))

    def under_letters(folder: dict) -> bool:
        parents = [p for p in (folder.get("parents") or []) if p]
        if CANONICAL_LETTERS_ID in parents:
            return True
        return bool(assume_under_letters and not parents)

    named = [
        folder
        for folder in folders
        if (folder.get("name") or "") == canon and under_letters(folder)
    ]
    if named:
        if preferred:
            for folder in named:
                if folder.get("id") == preferred:
                    return folder
        return max(named, key=_child_count)

    if preferred:
        for folder in folders:
            if folder.get("id") == preferred and folder.get("id") not in STALE_LETTER_QUARTER_IDS:
                return folder
    live = [folder for folder in folders if folder.get("id") not in STALE_LETTER_QUARTER_IDS]
    pool = live or list(folders)
    return max(pool, key=_child_count)
