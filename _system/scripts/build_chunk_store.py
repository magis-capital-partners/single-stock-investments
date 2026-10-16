#!/usr/bin/env python3
"""Build the committed chunk store at ``_system/data/chunks.jsonl``.

Chunks the curated research layer (latest deep dive per ticker, canonical
filing digest, thesis card text, and MEMORY.md sections) into roughly
800-token pieces with ticker, kind, section, and source path so agents can
retrieve cited evidence instead of loading whole reports. Raw filing
``_text/`` extracts are indexed only in the disposable SQLite hybrid index
(see ``agent_search.py --include-filing-text``), not committed as JSONL.

Usage:
  python _system/scripts/build_chunk_store.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import estimate_tokens, validate  # noqa: E402
from atomic_io import attach_envelope, write_json_if_changed, write_text_if_changed  # noqa: E402
from build_ticker_latest import build_latest  # noqa: E402

OUT_JSONL = ROOT / "_system" / "data" / "chunks.jsonl"
OUT_SUMMARY = ROOT / "_system" / "data" / "chunks_summary.json"
CHUNK_CHARS = 3200
OVERLAP_CHARS = 200

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def chunk_text(text: str) -> list[tuple[str | None, str]]:
    """Split markdown by heading, then by size with a small overlap."""
    sections: list[tuple[str | None, str]] = []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        sections = [(None, text)]
    else:
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            sections.append((match.group(2).strip(), text[match.start():end]))
    chunks: list[tuple[str | None, str]] = []
    for section, body in sections:
        body = body.strip()
        if len(body) < 120:
            continue
        start = 0
        while start < len(body):
            piece = body[start:start + CHUNK_CHARS].strip()
            if len(piece) >= 120:
                chunks.append((section, piece))
            start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks


def _add_file(rows: list[dict[str, Any]], *, ticker: str, kind: str, path: Path, root: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    rel = path.relative_to(root).as_posix()
    for section, piece in chunk_text(text):
        digest = hashlib.sha256(f"{rel}|{section}|{piece[:200]}".encode("utf-8")).hexdigest()
        row: dict[str, Any] = {
            "chunk_id": f"sha256:{digest[:24]}",
            "ticker": ticker,
            "kind": kind,
            "source_path": rel,
            "section": section,
            "text": piece,
            "token_estimate": estimate_tokens(piece),
        }
        row = {k: v for k, v in row.items() if v is not None}
        errors = validate(row, "chunk")
        if errors:
            raise ValueError(f"invalid chunk {row.get('chunk_id')}: {errors}")
        rows.append(row)


def build_chunks(*, root: Path = ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for research in sorted(root.glob("*/research")):
        ticker = research.parent.name
        latest = build_latest(ticker, root=root) or {}
        artifacts = latest.get("artifacts") or {}
        for key, kind in (("deep_dive", "deep_dive"), ("filing_digest", "filing_digest")):
            artifact = artifacts.get(key)
            if artifact and artifact.get("path"):
                _add_file(rows, ticker=ticker, kind=kind, path=root / artifact["path"], root=root)
        card_path = research / "thesis_card.json"
        if card_path.is_file():
            try:
                card = json.loads(card_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                card = {}
            text = "\n\n".join(str(card.get(k) or "") for k in ("thesis", "why_market_wrong"))
            if len(text.strip()) >= 120:
                digest = hashlib.sha256(f"{ticker}|thesis|{text[:200]}".encode("utf-8")).hexdigest()
                rows.append({
                    "chunk_id": f"sha256:{digest[:24]}",
                    "ticker": ticker,
                    "kind": "thesis",
                    "source_path": card_path.relative_to(root).as_posix(),
                    "text": text.strip(),
                    "token_estimate": estimate_tokens(text),
                })
    for mem_rel in ("_system/memory/MEMORY.md",):
        mem_path = root / mem_rel
        if mem_path.is_file():
            _add_file(rows, ticker="", kind="memory", path=mem_path, root=root)
    rows.sort(key=lambda r: (str(r.get("ticker")), str(r.get("kind")), str(r.get("chunk_id"))))
    return rows


def main(argv: list[str] | None = None) -> int:
    rows = build_chunks()
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    changed = write_text_if_changed(OUT_JSONL, text)
    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[str(row["kind"])] = by_kind.get(str(row["kind"]), 0) + 1
    summary = attach_envelope(
        {
            "schema_version": "magis.chunks_summary.v1",
            "description": "Curated-layer chunks (latest deep dive, filing digest, thesis, memory). Raw filing text is indexed in the SQLite hybrid index only.",
            "chunks_jsonl_path": "_system/data/chunks.jsonl",
            "by_kind": by_kind,
            "total_token_estimate": sum(int(r.get("token_estimate") or 0) for r in rows),
        },
        feed_id="agent-chunks",
        row_count=len(rows),
    )
    write_json_if_changed(OUT_SUMMARY, summary)
    print(f"OK chunk store: chunks={len(rows)} by_kind={by_kind} written={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
