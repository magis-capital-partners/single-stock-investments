#!/usr/bin/env python3
"""Compile the disposable local SQLite FTS5 search index at ``_system/cache/magis_index.sqlite``.

Indexes:
  1. ``_system/data/catalog/documents.jsonl`` (cross-store documents: SSI, Drive, research-vault)
  2. ``{TICKER}/research/thesis_card.json`` and ``dashboard/data/agent_shards/{TICKER}.json``
  3. ``_system/memory/MEMORY.md`` and ``_system/memory-hub/research-equity/MEMORY.md``

The SQLite database is gitignored and rebuilt locally on demand in seconds.

Usage:
  python _system/scripts/build_local_search_index.py
  python _system/scripts/build_local_search_index.py --db /tmp/test_index.sqlite
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
DEFAULT_DB = ROOT / "_system" / "cache" / "magis_index.sqlite"
CATALOG_JSONL = ROOT / "_system" / "data" / "catalog" / "documents.jsonl"
AGENT_SHARDS_DIR = ROOT / "dashboard" / "data" / "agent_shards"


def build_index(db_path: Path = DEFAULT_DB, *, root: Path = ROOT) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute(
            """
            CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                sha256 TEXT,
                ticker TEXT,
                source_type TEXT,
                title TEXT,
                stores_json TEXT,
                ssi_pdf_path TEXT,
                text_extract_path TEXT,
                drive_web_view_link TEXT,
                modified_at TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE tickers (
                ticker TEXT PRIMARY KEY,
                company TEXT,
                book TEXT,
                stance TEXT,
                archetype TEXT,
                base_irr_pct REAL,
                thesis TEXT,
                why_market_wrong TEXT,
                agent_shard_path TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE search_fts USING fts5(
                kind,
                ref_id,
                ticker,
                title,
                body,
                path,
                tokenize='porter unicode61'
            );
            """
        )

        doc_count = 0
        catalog_path = root / "_system" / "data" / "catalog" / "documents.jsonl"
        if catalog_path.is_file():
            doc_rows: list[tuple[Any, ...]] = []
            fts_rows: list[tuple[Any, ...]] = []
            for line in catalog_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                doc_id = str(doc.get("document_id") or f"sha256:{doc.get('sha256')}")
                tk = str(doc.get("ticker") or "")
                title = str(doc.get("title") or "")
                stype = str(doc.get("source_type") or "pdf")
                stores = json.dumps(doc.get("stores") or [])
                ssi_p = doc.get("ssi_pdf_path")
                txt_p = doc.get("text_extract_path")
                drive_url = doc.get("drive_web_view_link")
                mod = doc.get("modified_at")
                doc_rows.append((doc_id, doc.get("sha256"), tk, stype, title, stores, ssi_p, txt_p, drive_url, mod))
                body_parts = [title, stype, tk, str(ssi_p or ""), str(doc.get("drive_folder_path") or "")]
                fts_rows.append(
                    (
                        "document",
                        doc_id,
                        tk,
                        title,
                        " ".join(p for p in body_parts if p),
                        str(txt_p or ssi_p or drive_url or ""),
                    )
                )
                doc_count += 1
            conn.executemany(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                doc_rows,
            )
            conn.executemany(
                "INSERT INTO search_fts (kind, ref_id, ticker, title, body, path) VALUES (?, ?, ?, ?, ?, ?)",
                fts_rows,
            )

        ticker_count = 0
        shards_dir = root / "dashboard" / "data" / "agent_shards"
        if shards_dir.is_dir():
            t_rows: list[tuple[Any, ...]] = []
            fts_t_rows: list[tuple[Any, ...]] = []
            for shard_file in sorted(shards_dir.glob("*.json")):
                try:
                    shard = json.loads(shard_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                tk = str(shard.get("ticker") or shard_file.stem)
                company = str(shard.get("company") or tk)
                book = str(shard.get("book") or "research_universe")
                tsum = shard.get("thesis_summary") or {}
                stance = str(tsum.get("stance") or "")
                arch = str(tsum.get("archetype") or "")
                irr = tsum.get("base_irr_pct")
                irr_val = float(irr) if isinstance(irr, (int, float)) else None
                thesis = str(tsum.get("thesis") or "")
                wrong = str(tsum.get("why_market_wrong") or "")
                rel_path = shard_file.relative_to(root).as_posix()
                t_rows.append((tk, company, book, stance, arch, irr_val, thesis, wrong, rel_path))
                assumptions_text = " ".join(
                    f"{a.get('input', '')}: {a.get('value', '')}" for a in (tsum.get("key_assumptions") or []) if isinstance(a, dict)
                )
                questions_text = " ".join(str(q) for q in (tsum.get("open_questions") or []))
                full_body = " ".join(p for p in (company, stance, arch, thesis, wrong, assumptions_text, questions_text) if p)
                fts_t_rows.append(("ticker", tk, tk, f"{tk} — {company}", full_body, rel_path))
                ticker_count += 1
            conn.executemany(
                "INSERT OR REPLACE INTO tickers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                t_rows,
            )
            conn.executemany(
                "INSERT INTO search_fts (kind, ref_id, ticker, title, body, path) VALUES (?, ?, ?, ?, ?, ?)",
                fts_t_rows,
            )

        memory_count = 0
        for mem_rel in ("_system/memory/MEMORY.md", "_system/memory-hub/research-equity/MEMORY.md"):
            mem_path = root / mem_rel
            if not mem_path.is_file():
                continue
            current_heading = mem_path.name
            section_lines: list[str] = []
            sec_idx = 0
            for raw_line in mem_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if raw_line.startswith("#"):
                    if section_lines:
                        sec_idx += 1
                        conn.execute(
                            "INSERT INTO search_fts (kind, ref_id, ticker, title, body, path) VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                "memory",
                                f"{mem_rel}#{sec_idx}",
                                "",
                                current_heading,
                                "\n".join(section_lines),
                                mem_rel,
                            ),
                        )
                        memory_count += 1
                        section_lines = []
                    current_heading = raw_line.lstrip("#").strip()
                elif raw_line.strip():
                    section_lines.append(raw_line.strip())
            if section_lines:
                sec_idx += 1
                conn.execute(
                    "INSERT INTO search_fts (kind, ref_id, ticker, title, body, path) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "memory",
                        f"{mem_rel}#{sec_idx}",
                        "",
                        current_heading,
                        "\n".join(section_lines),
                        mem_rel,
                    ),
                )
                memory_count += 1

        conn.commit()
    finally:
        conn.close()

    return {
        "documents": doc_count,
        "tickers": ticker_count,
        "memory_sections": memory_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    stats = build_index(args.db, root=args.root)
    print(
        f"Built SQLite FTS5 index at {args.db} "
        f"(documents={stats['documents']}, tickers={stats['tickers']}, memory_sections={stats['memory_sections']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
