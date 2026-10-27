#!/usr/bin/env python3
"""Hybrid BM25 + hashing-vector search over chunks, claims, and filing text.

Builds a disposable SQLite index at ``_system/cache/agent_search.sqlite``
(FTS5 BM25 candidates reranked by cosine similarity over deterministic
hashing embeddings, so no external model or API key is required). Results are
cited chunks with source paths, not bare file paths to load whole.

Usage:
  python _system/scripts/agent_search.py --build
  python _system/scripts/agent_search.py --build --include-filing-text
  python _system/scripts/agent_search.py --query "pricing power" --ticker GOOGL
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import cosine, hash_embedding  # noqa: E402
from build_chunk_store import chunk_text, stable_chunk_id  # noqa: E402

DEFAULT_DB = ROOT / "_system" / "cache" / "agent_search.sqlite"
CHUNKS_JSONL = ROOT / "_system" / "data" / "chunks.jsonl"
MAX_FILING_CHUNKS_PER_FILE = 40


def _is_private_snapshot(row: dict[str, Any]) -> bool:
    return row.get("private_snapshot") is True


def restored_private_rows(root: Path, public_path: Path) -> list[dict[str, Any]] | None:
    """Return the vault copy of a placeholder JSONL, or None when it is not available.

    Public checkouts of ``chunks.jsonl`` are a one-line metadata placeholder
    after the fund-letter migration. The curated rows stay in the private
    research vault. This reader is for a vault that is already on disk. The
    public agent-index artifact must not clone that vault: the repository is
    public, and the sqlite upload would republish the private text.
    """
    try:
        rel = public_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    manifest_path = root / "dashboard" / "private-assets.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = (manifest.get("repository_assets") or {}).get(rel) or {}
    digest = str(entry.get("private_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None
    from vault_paths import research_vault_root

    vault = research_vault_root()
    if vault is None:
        return None
    private = vault / "dashboard-private" / "objects" / digest
    if not private.is_file():
        return None
    payload = private.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise RuntimeError(f"Private chunk snapshot hash mismatch for {rel}")
    rows: list[dict[str, Any]] = []
    for line in payload.decode("utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict) and not _is_private_snapshot(row):
            rows.append(row)
    return rows


def iter_chunk_rows(chunks_path: Path, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    placeholder = False
    for line in chunks_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        if _is_private_snapshot(row):
            placeholder = True
            restored = restored_private_rows(root, chunks_path)
            if restored:
                rows.extend(restored)
            continue
        rows.append(row)
    if placeholder and not rows:
        print(
            "chunks.jsonl is a private snapshot placeholder; curated chunks are not in this checkout.",
            file=sys.stderr,
        )
    return rows


def chunk_row_id(row: dict[str, Any]) -> str | None:
    """Use a written chunk_id, or the chunk-store scheme when the row has text.

    A private-snapshot placeholder has neither an id nor text. It is not a chunk.
    """
    existing = row.get("chunk_id")
    if isinstance(existing, str) and existing.strip():
        return existing
    text = row.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    section = row.get("section")
    return stable_chunk_id(
        source_path=str(row.get("source_path") or ""),
        section=section if isinstance(section, str) else None,
        text=text,
        ticker=str(row.get("ticker") or ""),
        kind=str(row.get("kind") or ""),
    )


def _sanitize(raw: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9._-]+", raw)
    return " AND ".join(f'"{t}"' for t in tokens) if tokens else '""'


def build_search_index(db_path: Path = DEFAULT_DB, *, root: Path = ROOT, include_filing_text: bool = False) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute(
            "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, ticker TEXT, kind TEXT, source_path TEXT, section TEXT, text TEXT, embedding TEXT)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id, ticker, title, body, tokenize='porter unicode61')"
        )
        rows: list[tuple[Any, ...]] = []
        fts_rows: list[tuple[Any, ...]] = []

        def add(chunk_id: str, ticker: str, kind: str, source_path: str, section: str | None, text: str) -> None:
            rows.append((chunk_id, ticker, kind, source_path, section, text, json.dumps(hash_embedding(text))))
            fts_rows.append((chunk_id, ticker, section or kind, text))

        chunks_path = root / "_system" / "data" / "chunks.jsonl"
        chunk_count = 0
        derived_chunk_ids = 0
        if chunks_path.is_file():
            for row in iter_chunk_rows(chunks_path, root):
                had_id = isinstance(row.get("chunk_id"), str) and bool(str(row.get("chunk_id")).strip())
                chunk_id = chunk_row_id(row)
                if chunk_id is None:
                    continue
                if not had_id:
                    derived_chunk_ids += 1
                add(chunk_id, str(row.get("ticker") or ""), str(row.get("kind")), str(row.get("source_path") or ""), row.get("section"), str(row.get("text") or ""))
                chunk_count += 1

        filing_count = 0
        if include_filing_text:
            for text_path in sorted(root.glob("*/research/evidence/_text/*.txt")):
                ticker = text_path.parent.parent.parent.parent.name
                try:
                    text = text_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                rel = text_path.relative_to(root).as_posix()
                for section, piece in chunk_text(text)[:MAX_FILING_CHUNKS_PER_FILE]:
                    digest = hashlib.sha256(f"{rel}|{piece[:200]}".encode("utf-8")).hexdigest()
                    add(f"sha256:{digest[:24]}", ticker, "filing_text", rel, section, piece)
                    filing_count += 1

        conn.executemany("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany("INSERT INTO chunks_fts (chunk_id, ticker, title, body) VALUES (?, ?, ?, ?)", fts_rows)
        conn.commit()
    finally:
        conn.close()
    return {
        "chunks": chunk_count,
        "derived_chunk_ids": derived_chunk_ids,
        "filing_text_chunks": filing_count,
        "total": chunk_count + filing_count,
    }


def search(query: str, *, ticker: str | None = None, kind: str | None = None, limit: int = 10, db_path: Path = DEFAULT_DB, root: Path = ROOT) -> dict[str, Any]:
    if not db_path.is_file():
        build_search_index(db_path, root=root)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        sql = (
            "SELECT c.chunk_id, c.ticker, c.kind, c.source_path, c.section, c.text, c.embedding, "
            "bm25(chunks_fts) AS bm25 FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ?"
        )
        params: list[Any] = [_sanitize(query)]
        if ticker:
            sql += " AND UPPER(c.ticker) = UPPER(?)"
            params.append(ticker)
        if kind:
            sql += " AND LOWER(c.kind) = LOWER(?)"
            params.append(kind)
        sql += " ORDER BY bm25 LIMIT ?"
        params.append(max(limit * 5, 25))
        candidates = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    query_vec = hash_embedding(query)
    for row in candidates:
        try:
            vec = json.loads(row.pop("embedding") or "[]")
        except json.JSONDecodeError:
            vec = []
        vector_score = cosine(query_vec, vec) if vec else 0.0
        # BM25 is negative (lower is better); normalize into a hybrid score.
        bm25_component = 1.0 / (1.0 + abs(float(row.get("bm25") or 0.0)))
        row["score"] = round(0.6 * bm25_component + 0.4 * max(0.0, vector_score), 6)
        row["snippet"] = " ".join(str(row.get("text") or "").split())[:420]
        row.pop("text", None)
    candidates.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    return {"query": query, "ticker_filter": ticker, "kind_filter": kind, "count": len(candidates[:limit]), "hits": candidates[:limit]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--query", "-q", default=None)
    parser.add_argument("--ticker", "-t", default=None)
    parser.add_argument("--kind", "-k", default=None)
    parser.add_argument("--limit", "-n", type=int, default=10)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--include-filing-text", action="store_true")
    args = parser.parse_args(argv)
    if args.build:
        stats = build_search_index(args.db, include_filing_text=args.include_filing_text)
        print(f"Built agent search index at {args.db}: {stats}")
        return 0
    if not args.query:
        parser.error("--query required (or --build)")
    result = search(args.query, ticker=args.ticker, kind=args.kind, limit=args.limit, db_path=args.db)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
