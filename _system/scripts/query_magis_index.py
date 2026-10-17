#!/usr/bin/env python3
"""Query the disposable local SQLite FTS5 index (``_system/cache/magis_index.sqlite``).

Auto-builds the index if it does not exist yet. Returns compact JSON hits in
milliseconds so agents (Grok Bot, Cursor, Claude) can search across all tickers,
theses, memory beliefs, and cross-store documents without scanning the repo tree.

Usage:
  python _system/scripts/query_magis_index.py --query "royalty deficit"
  python _system/scripts/query_magis_index.py --query "10-K" --ticker TPL --kind document
"""
from __future__ import annotations

import argparse
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

from build_local_search_index import DEFAULT_DB, build_index  # noqa: E402


def _sanitize_fts_query(raw: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9._-]+", raw)
    if not tokens:
        return '""'
    return " AND ".join(f'"{t}"' for t in tokens)


def query_index(
    query: str,
    *,
    ticker: str | None = None,
    kind: str | None = None,
    limit: int = 15,
    db_path: Path = DEFAULT_DB,
    root: Path = ROOT,
) -> dict[str, Any]:
    if not db_path.is_file():
        build_index(db_path, root=root)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        fts_q = _sanitize_fts_query(query)
        sql = """
            SELECT
                kind,
                ref_id,
                ticker,
                title,
                snippet(search_fts, 4, '[', ']', '...', 24) AS snippet,
                path,
                bm25(search_fts) AS score
            FROM search_fts
            WHERE search_fts MATCH ?
        """
        params: list[Any] = [fts_q]
        if ticker:
            sql += " AND UPPER(ticker) = UPPER(?)"
            params.append(ticker.strip())
        if kind:
            sql += " AND LOWER(kind) = LOWER(?)"
            params.append(kind.strip())
        sql += " ORDER BY score LIMIT ?"
        params.append(int(limit))

        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return {
            "query": query,
            "fts_query": fts_q,
            "ticker_filter": ticker,
            "kind_filter": kind,
            "count": len(rows),
            "hits": rows,
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--query", "-q", required=True, help="Search terms")
    parser.add_argument("--ticker", "-t", default=None, help="Optional ticker filter")
    parser.add_argument("--kind", "-k", choices=["document", "ticker", "memory"], default=None)
    parser.add_argument("--limit", "-n", type=int, default=15)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)
    result = query_index(
        args.query,
        ticker=args.ticker,
        kind=args.kind,
        limit=args.limit,
        db_path=args.db,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
