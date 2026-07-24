#!/usr/bin/env python3
"""Refresh officer_directory.json from seeded rows + optional filing snippets.

Full DEF14A/20-F harvest is incremental; this script merges manual seeds and
preserves existing officers while allowing --seed-only runs for CI.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OFFICER_PATH = ROOT / "_system" / "reference" / "podcasts" / "officer_directory.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {"officers": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"officers": []}
    except json.JSONDecodeError:
        return {"officers": []}


def merge_officers(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for row in existing + incoming:
        key = f"{(row.get('person_name') or '').lower()}|{(row.get('ticker') or '').upper()}"
        if not row.get("person_name"):
            continue
        prev = by_key.get(key, {})
        merged = {**prev, **row}
        # union aliases/titles
        aliases = list(
            dict.fromkeys((prev.get("name_aliases") or []) + (row.get("name_aliases") or []))
        )
        titles = list(dict.fromkeys((prev.get("titles") or []) + (row.get("titles") or [])))
        companies = list(
            dict.fromkeys((prev.get("company_aliases") or []) + (row.get("company_aliases") or []))
        )
        merged["name_aliases"] = aliases
        merged["titles"] = titles
        merged["company_aliases"] = companies
        by_key[key] = merged
    return sorted(by_key.values(), key=lambda r: (r.get("ticker") or "", r.get("person_name") or ""))


def build(*, seed_only: bool = True) -> dict:
    doc = load_json(OFFICER_PATH)
    officers = list(doc.get("officers") or [])
    # Placeholder for future filing harvest when seed_only is False
    if not seed_only:
        # Intentionally no-op network harvest here; Vicki/filing pipelines can append later.
        pass
    merged = merge_officers(officers, [])
    out = {
        "schema_version": 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "notes": doc.get("notes")
        or "Person ↔ company ↔ ticker. Refresh via build_officer_directory.py.",
        "officers": merged,
    }
    OFFICER_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--full", action="store_true", help="Reserved for filing harvest expansion")
    args = p.parse_args()
    out = build(seed_only=not args.full)
    print(f"officers={len(out.get('officers') or [])} -> {OFFICER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
