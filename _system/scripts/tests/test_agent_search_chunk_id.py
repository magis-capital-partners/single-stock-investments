"""Indexer identity for chunk rows that never received a chunk_id.

The agent-index workflow died on the public chunks.jsonl placeholder
(`private_snapshot: true`, no chunk_id) after the fund-letter migration.
Real curated rows already use sha256 ids. A content row that arrives
without one gets the same id the chunk store would have written.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import agent_search  # noqa: E402
import build_chunk_store  # noqa: E402

PASSAGE = "Fund letter passage on pricing power and reinvestment. " * 8
SOURCE = "_system/reference/superinvestor-letters/2024/example.txt"
SECTION = "Outlook"


def _expected_id(source: str, section: str, text: str) -> str:
    digest = hashlib.sha256(f"{source}|{section}|{text[:200]}".encode("utf-8")).hexdigest()
    return f"sha256:{digest[:24]}"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _ids(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return [row[0] for row in conn.execute("SELECT chunk_id FROM chunks ORDER BY chunk_id")]
    finally:
        conn.close()


def test_content_row_without_chunk_id_uses_chunk_store_scheme(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    row = {
        "ticker": "GOOGL",
        "kind": "fund_letter",
        "source_path": SOURCE,
        "section": SECTION,
        "text": PASSAGE,
    }
    _write_jsonl(root / "_system" / "data" / "chunks.jsonl", [row])
    expected = _expected_id(SOURCE, SECTION, PASSAGE)
    assert build_chunk_store.stable_chunk_id(source_path=SOURCE, section=SECTION, text=PASSAGE, ticker="GOOGL", kind="fund_letter") == expected

    db = tmp_path / "search.sqlite"
    stats = agent_search.build_search_index(db, root=root)
    assert stats["chunks"] == 1
    assert stats["derived_chunk_ids"] == 1
    assert _ids(db) == [expected]

    again = tmp_path / "search-again.sqlite"
    agent_search.build_search_index(again, root=root)
    assert _ids(again) == [expected]


def test_existing_chunk_id_is_kept() -> None:
    row = {"chunk_id": "sha256:0123456789abcdef01234567", "text": PASSAGE, "source_path": SOURCE, "section": SECTION}
    assert agent_search.chunk_row_id(row) == "sha256:0123456789abcdef01234567"


def test_private_snapshot_placeholder_is_not_a_chunk(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write_jsonl(
        root / "_system" / "data" / "chunks.jsonl",
        [{"private_snapshot": True, "source_shape": "array", "entry_count": 18303}],
    )
    db = tmp_path / "search.sqlite"
    stats = agent_search.build_search_index(db, root=root)
    assert stats["chunks"] == 0
    assert stats["derived_chunk_ids"] == 0
    assert _ids(db) == []


def test_private_snapshot_restores_vault_rows_with_their_ids(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    public = root / "_system" / "data" / "chunks.jsonl"
    _write_jsonl(public, [{"private_snapshot": True, "source_shape": "array", "entry_count": 1}])
    private_row = {
        "chunk_id": "sha256:abcdef0123456789abcdef01",
        "ticker": "GOOGL",
        "kind": "deep_dive",
        "source_path": "GOOGL/research/deep_dive.md",
        "section": "Moat",
        "text": PASSAGE,
    }
    payload = (json.dumps(private_row) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    vault = tmp_path / "vault"
    obj = vault / "dashboard-private" / "objects" / digest
    obj.parent.mkdir(parents=True)
    obj.write_bytes(payload)
    manifest = {"repository_assets": {"_system/data/chunks.jsonl": {"private_sha256": digest, "public_sha256": "unused"}}}
    (root / "dashboard").mkdir(parents=True)
    (root / "dashboard" / "private-assets.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_VAULT_ROOT", str(vault))

    db = tmp_path / "search.sqlite"
    stats = agent_search.build_search_index(db, root=root)
    assert stats["chunks"] == 1
    assert stats["derived_chunk_ids"] == 0
    assert _ids(db) == ["sha256:abcdef0123456789abcdef01"]
