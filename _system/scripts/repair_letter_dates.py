#!/usr/bin/env python3
"""Repair bad letter dates/quarters in vault insights and rebuild downstream artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from fund_registry import (  # noqa: E402
    letter_date_overrides,
    parse_letter_date_with_confidence,
    quarter_from_path,
    resolve_quarter,
    sanity_year,
)
from vault_paths import letters_root  # noqa: E402

LETTERS_ROOT = letters_root()
INSIGHTS_PATH = LETTERS_ROOT / "insights.json"


def repair_letter_record(letter: dict, text: str | None = None) -> bool:
    source = letter.get("source_file") or letter.get("path") or ""
    path = Path(str(source).replace("\\", "/"))
    if not path.parts:
        return False
    stem = path.stem
    folder_q = None
    for part in path.parts:
        if part.upper().startswith("20") and "Q" in part.upper():
            folder_q = part.upper()
            break
    stored_q = letter.get("quarter")
    quarter_hint = folder_q
    if stored_q:
        try:
            stored_year = int(str(stored_q)[:4])
        except ValueError:
            stored_year = None
        if stored_year is not None and sanity_year(stored_year) is not None:
            quarter_hint = stored_q
        elif not quarter_hint:
            quarter_hint = stored_q
    iso, date_source, date_confidence = parse_letter_date_with_confidence(
        stem, text, quarter_hint, overrides=letter_date_overrides()
    )
    if iso and sanity_year(int(iso[:4])) is None:
        iso, date_source, date_confidence = parse_letter_date_with_confidence(
            stem, text, folder_q, overrides=letter_date_overrides()
        )
    if not iso and folder_q:
        return False
    new_quarter = resolve_quarter(path, stem, iso, date_source or "none")
    changed = False
    if iso and letter.get("letter_date") != iso:
        letter["letter_date"] = iso
        letter["date_source"] = date_source
        letter["date_confidence"] = date_confidence
        changed = True
    if new_quarter and letter.get("quarter") != new_quarter:
        letter["quarter"] = new_quarter
        changed = True
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write repaired insights (default when not dry-run)")
    args = parser.parse_args()
    apply = args.apply or not args.dry_run
    if not INSIGHTS_PATH.exists():
        print(f"Missing {INSIGHTS_PATH}")
        return 1
    payload = json.loads(INSIGHTS_PATH.read_text(encoding="utf-8"))
    letters = payload.get("letters") or []
    fixed = 0
    bad_before = sum(
        1
        for letter in letters
        if letter.get("quarter") and sanity_year(int(str(letter.get("quarter"))[:4])) is None
    )
    for letter in letters:
        if repair_letter_record(letter):
            fixed += 1
    bad_after = sum(
        1
        for letter in letters
        if letter.get("quarter") and sanity_year(int(str(letter.get("quarter"))[:4])) is None
    )
    print(f"Repaired {fixed} letter records ({bad_before} bad quarters -> {bad_after})")
    if apply and fixed:
        payload["letters"] = letters
        payload["repaired_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        INSIGHTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
