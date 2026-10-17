#!/usr/bin/env python3
"""Shard ``_system/memory/MEMORY.md`` into a searchable L0 memory index.

MEMORY.md stays the human-curated source of truth (agents never edit it).
This builder splits it by heading into ``_system/data/memory_shards/*.md``
plus ``_system/data/memory_index.json`` so an agent loads only the section
relevant to its task (genius model, company belief, portfolio context)
instead of the whole file on every run.

Usage:
  python _system/scripts/build_memory_index.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import estimate_tokens  # noqa: E402
from atomic_io import attach_envelope, write_json_if_changed, write_text_if_changed  # noqa: E402

MEMORY_PATH = ROOT / "_system" / "memory" / "MEMORY.md"
SHARD_DIR = ROOT / "_system" / "data" / "memory_shards"
INDEX_PATH = ROOT / "_system" / "data" / "memory_index.json"
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or fallback


def build_memory_index(*, root: Path = ROOT) -> dict[str, Any]:
    mem_path = root / "_system" / "memory" / "MEMORY.md"
    shard_dir = root / "_system" / "data" / "memory_shards"
    text = mem_path.read_text(encoding="utf-8", errors="ignore") if mem_path.is_file() else ""
    sections: list[tuple[str, str]] = []
    current_title = "preamble"
    current: list[str] = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) <= 2 and current and any(part.strip() for part in current):
            sections.append((current_title, "\n".join(current).strip()))
            current_title = match.group(2).strip()
            current = [line]
        elif match and len(match.group(1)) <= 2:
            current_title = match.group(2).strip()
            current = [line]
        else:
            current.append(line)
    if current and any(part.strip() for part in current):
        sections.append((current_title, "\n".join(current).strip()))

    shard_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for idx, (title, body) in enumerate(sections):
        filename = f"{idx:02d}-{_slug(title, f'section-{idx}')}.md"
        write_text_if_changed(shard_dir / filename, body.strip() + "\n")
        rows.append({
            "section": title,
            "shard": f"_system/data/memory_shards/{filename}",
            "token_estimate": estimate_tokens(body),
            "proposed_only": "[PROPOSED" in body,
        })
    payload: dict[str, Any] = {
        "schema_version": "magis.memory_index.v1",
        "description": "L0 index over MEMORY.md sections. Load one shard for the genius/company context a task needs; MEMORY.md remains the human-curated source.",
        "source": "_system/memory/MEMORY.md",
        "sections": rows,
    }
    return attach_envelope(payload, feed_id="memory-index", row_count=len(rows))


def main(argv: list[str] | None = None) -> int:
    payload = build_memory_index()
    write_json_if_changed(INDEX_PATH, payload)
    print(f"OK memory index: sections={len(payload['sections'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
