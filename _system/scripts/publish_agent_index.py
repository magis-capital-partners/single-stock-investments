#!/usr/bin/env python3
"""Publish the agent index manifest at ``_system/data/agent_index_manifest.json``.

The SQLite hybrid index itself is disposable and gitignored; this manifest is
the committed, versioned pointer to it: content hashes of every input store,
row counts, the exact rebuild command, and the CI artifact name that carries
the prebuilt database (``.github/workflows/agent-index.yml``). A fresh cloud
agent verifies the manifest hash, downloads the artifact when available, or
rebuilds deterministically with the recorded command.

Usage:
  python _system/scripts/publish_agent_index.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from atomic_io import attach_envelope, semantic_text_sha256, write_json_if_changed  # noqa: E402

OUT = ROOT / "_system" / "data" / "agent_index_manifest.json"
INPUTS = (
    "_system/data/claims.jsonl",
    "_system/data/chunks.jsonl",
    "_system/data/catalog/documents.jsonl",
    "dashboard/data/portfolio_summary.json",
    "dashboard/data/research_manifest.json",
)


def _file_meta(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    if not path.is_file():
        return {"path": rel, "present": False}
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = sum(1 for line in text.splitlines() if line.strip()) if rel.endswith(".jsonl") else None
    meta: dict[str, Any] = {"path": rel, "present": True, "sha256": f"sha256:{semantic_text_sha256(text)}", "bytes": path.stat().st_size}
    if lines is not None:
        meta["rows"] = lines
    return meta


def build_manifest(*, root: Path = ROOT) -> dict[str, Any]:
    shard_dir = root / "dashboard" / "data" / "agent_shards"
    pack_dir = root / "dashboard" / "data" / "context_packs"
    payload: dict[str, Any] = {
        "schema_version": "magis.agent_index_manifest.v1",
        "description": "Versioned pointer to the disposable SQLite hybrid search index and every committed agent store it is built from.",
        "index": {
            "sqlite_path": "_system/cache/agent_search.sqlite",
            "gitignored": True,
            "rebuild_command": "python _system/scripts/agent_search.py --build --include-filing-text",
            "ci_artifact": "agent-search-index (see .github/workflows/agent-index.yml)",
            "engine": "SQLite FTS5 BM25 reranked by 256-dim hashing-embedding cosine (0.6/0.4 hybrid)",
        },
        "stores": [_file_meta(root, rel) for rel in INPUTS],
        "counts": {
            "agent_shards": len(list(shard_dir.glob("*.json"))) if shard_dir.is_dir() else 0,
            "context_packs": len(list(pack_dir.glob("*.md"))) if pack_dir.is_dir() else 0,
            "schemas": len(list((root / "_system" / "schemas").glob("*.schema.json"))),
        },
        "entry_points": ["AGENT_INDEX.md", "llms.txt", "_system/scripts/agent_mcp_server.py"],
        "legacy_monoliths_do_not_load": [
            {"path": "dashboard/data/kpi_trends.json", "use_instead": "dashboard/data/kpi_summary.json + L1 shard kpi_series"},
            {"path": "dashboard/data/document_registry.json", "use_instead": "_system/data/catalog/documents.jsonl (cross-store catalog)"},
            {"path": "dashboard/data/document_catalog.json", "use_instead": "dashboard/data/document_catalog_summary.json + catalog JSONL"},
            {"path": "dashboard/data/research_memory.json", "use_instead": "_system/data/claims.jsonl + _system/data/memory_index.json"},
            {"path": "_system/memory/MEMORY.md", "use_instead": "_system/data/memory_index.json (load one shard, not the whole file)"},
        ],
        "canonical_returns_note": "valuation.json returns block (percent_per_year) is canonical; legacy results/implied_return/results_lawrence_legacy fields are reference-only for older consumers.",
    }
    return attach_envelope(payload, feed_id="agent-index-manifest", row_count=sum(int(s.get("rows") or 0) for s in payload["stores"]))


def main(argv: list[str] | None = None) -> int:
    manifest = build_manifest()
    changed = write_json_if_changed(OUT, manifest)
    print(f"OK agent index manifest: stores={len(manifest['stores'])} counts={manifest['counts']} written={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
