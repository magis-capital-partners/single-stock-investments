"""Tests for the Unified Data Architecture (atomic_io, L0/L1 shards, catalog, FTS5, compaction)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import atomic_io  # noqa: E402
import build_local_search_index  # noqa: E402
import compact_dated_artifacts  # noqa: E402
import query_magis_index  # noqa: E402


def test_semantic_text_sha256_ignores_volatile_dates(tmp_path: Path) -> None:
    doc_day1 = (
        "# Thematic context — TPL — 2026-10-15\n\n"
        "**Date:** 2026-10-15\n"
        "**Generated:** 2026-10-15T08:00:00Z\n\n"
        " Permian water royalties grew 24% YoY.\n"
    )
    doc_day2 = (
        "# Thematic context — TPL — 2026-10-16\n\n"
        "**Date:** 2026-10-16\n"
        "**Generated:** 2026-10-16T09:30:00Z\n\n"
        " Permian water royalties grew 24% YoY.\n"
    )
    doc_changed = (
        "# Thematic context — TPL — 2026-10-16\n\n"
        "**Date:** 2026-10-16\n\n"
        " Permian water royalties grew 31% YoY.\n"
    )
    assert atomic_io.semantic_text_sha256(doc_day1) == atomic_io.semantic_text_sha256(doc_day2)
    assert atomic_io.semantic_text_sha256(doc_day1) != atomic_io.semantic_text_sha256(doc_changed)

    target = tmp_path / "thematic_context.md"
    assert atomic_io.write_text_if_changed(target, doc_day1) is True
    assert atomic_io.write_text_if_changed(target, doc_day2) is False
    assert atomic_io.write_text_if_changed(target, doc_changed) is True


def test_write_json_if_changed_and_attach_envelope(tmp_path: Path) -> None:
    p1 = atomic_io.attach_envelope(
        {
            "schema_version": "test.v1",
            "generated_at": "2026-10-15T10:00:00Z",
            "items": [{"ticker": "TPL", "value": 100}],
        },
        feed_id="test-feed",
        as_of="2026-10-15",
        row_count=1,
    )
    assert p1["_envelope"]["schema_version"] == "magis.feed.v2"
    assert p1["_envelope"]["feed_id"] == "test-feed"
    assert p1["_envelope"]["health"]["status"] == "healthy"
    assert p1["_envelope"]["content_sha256"].startswith("sha256:")

    target = tmp_path / "feed.json"
    assert atomic_io.write_json_if_changed(target, p1) is True

    # Changing only timestamps / envelope must not trigger a rewrite
    p2 = atomic_io.attach_envelope(
        {
            "schema_version": "test.v1",
            "generated_at": "2026-10-16T12:00:00Z",
            "items": [{"ticker": "TPL", "value": 100}],
        },
        feed_id="test-feed",
        as_of="2026-10-16",
        row_count=1,
    )
    assert atomic_io.write_json_if_changed(target, p2) is False

    # Changing semantic data must trigger a rewrite
    p3 = atomic_io.attach_envelope(
        {
            "schema_version": "test.v1",
            "generated_at": "2026-10-16T12:00:00Z",
            "items": [{"ticker": "TPL", "value": 125}],
        },
        feed_id="test-feed",
        as_of="2026-10-16",
        row_count=1,
    )
    assert atomic_io.write_json_if_changed(target, p3) is True


def test_l0_summary_feeds_exist_and_respect_size_budget() -> None:
    l0_files = [
        "dashboard/data/portfolio_summary.json",
        "dashboard/data/research_manifest.json",
        "dashboard/data/kpi_summary.json",
        "dashboard/data/document_catalog_summary.json",
    ]
    for rel in l0_files:
        path = ROOT / rel
        assert path.is_file(), f"Missing L0 summary file: {rel}"
        size_bytes = path.stat().st_size
        assert size_bytes < 102_400, f"L0 file {rel} exceeds 100 KB budget ({size_bytes} bytes)"
        payload = json.loads(path.read_text(encoding="utf-8"))
        env = payload.get("_envelope")
        assert isinstance(env, dict), f"Missing _envelope in {rel}"
        assert env.get("schema_version") == "magis.feed.v2"
        assert env.get("health", {}).get("status") == "healthy"


def test_l1_agent_shards_and_canonical_evidence() -> None:
    for ticker in ("TPL", "GOOGL"):
        shard_path = ROOT / "dashboard" / "data" / "agent_shards" / f"{ticker}.json"
        assert shard_path.is_file(), f"Missing L1 agent shard for {ticker}"
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        assert shard.get("schema_version") == "magis.agent_shard.v1"
        assert shard.get("ticker") == ticker
        assert "_envelope" in shard
        assert "thesis_summary" in shard
        assert "l2_pointers" in shard

        # Canonical undated evidence files exist
        assert (ROOT / ticker / "research" / "evidence" / "thematic_context.md").is_file()
        assert (ROOT / ticker / "research" / "evidence" / "insider_signal.md").is_file()
        assert (ROOT / ticker / "research" / "evidence" / "filing_digest.md").is_file()
        assert (ROOT / ticker / "third-party-analyses" / "source_inventory.json").is_file()


def test_cross_store_document_catalog_jsonl() -> None:
    catalog_path = ROOT / "_system" / "data" / "catalog" / "documents.jsonl"
    assert catalog_path.is_file()
    lines = [ln for ln in catalog_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 8000
    first = json.loads(lines[0])
    assert first.get("document_id", "").startswith("sha256:")
    assert isinstance(first.get("sha256"), str) and len(first["sha256"]) == 64
    assert isinstance(first.get("stores"), list) and len(first["stores"]) >= 1


def test_compact_dated_artifacts_on_synthetic_dir(tmp_path: Path) -> None:
    tdir = tmp_path / "SYNTH"
    ev_dir = tdir / "research" / "evidence"
    ev_dir.mkdir(parents=True)

    (ev_dir / "insider_signal_2026-10-01.md").write_text(
        "# Insider signal — SYNTH\n\n**Date:** 2026-10-01\n\nNo open-market buys.\n",
        encoding="utf-8",
    )
    (ev_dir / "insider_signal_2026-10-02.md").write_text(
        "# Insider signal — SYNTH\n\n**Date:** 2026-10-02\n\nNo open-market buys.\n",
        encoding="utf-8",
    )
    (ev_dir / "insider_signal_2026-10-03.md").write_text(
        "# Insider signal — SYNTH\n\n**Date:** 2026-10-03\n\nCEO bought 10,000 shares.\n",
        encoding="utf-8",
    )

    stats = compact_dated_artifacts.compact_ticker("SYNTH", root=tmp_path, prune_redundant=True)
    assert stats["canonical_written"] == 1
    assert stats["pruned_count"] == 2
    assert (ev_dir / "insider_signal.md").is_file()
    assert (ev_dir / "insider_signal_2026-10-03.md").is_file()
    assert not (ev_dir / "insider_signal_2026-10-01.md").exists()


def test_local_fts5_search_index_queries() -> None:
    db_path = ROOT / "_system" / "cache" / "magis_index.sqlite"
    if not db_path.is_file():
        build_local_search_index.build_index(db_path)
    result = query_magis_index.query_index("water royalty", ticker="TPL", kind="ticker", limit=5, db_path=db_path)
    hits = result.get("hits") or []
    assert len(hits) >= 1
    assert hits[0]["ticker"] == "TPL"


def test_write_superseded_review_md_dedupes_and_caps(tmp_path: Path) -> None:
    pending = tmp_path / "_system" / "reviews" / "pending"
    p1 = atomic_io.write_superseded_review_md(
        pending, "event_triage", "2026-10-01", "# Event triage — 2026-10-01\n\n**Date:** 2026-10-01\n\nRow A\n", keep_latest=2
    )
    assert p1.name == "event_triage_2026-10-01.md"
    # Identical semantic content on next day returns previous file without creating a new one
    p2 = atomic_io.write_superseded_review_md(
        pending, "event_triage", "2026-10-02", "# Event triage — 2026-10-02\n\n**Date:** 2026-10-02\n\nRow A\n", keep_latest=2
    )
    assert p2 == p1
    assert not (pending / "event_triage_2026-10-02.md").exists()
    # Changed content on day 3 and day 4 caps at keep_latest=2
    atomic_io.write_superseded_review_md(
        pending, "event_triage", "2026-10-03", "# Event triage — 2026-10-03\n\nRow B\n", keep_latest=2
    )
    atomic_io.write_superseded_review_md(
        pending, "event_triage", "2026-10-04", "# Event triage — 2026-10-04\n\nRow C\n", keep_latest=2
    )
    files = sorted(p.name for p in pending.glob("event_triage_*.md"))
    assert files == ["event_triage_2026-10-03.md", "event_triage_2026-10-04.md"]


def test_guard_staged_changes_drops_redundant_dated_file(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path), check=True)
    tp = tmp_path / "SYNTH" / "third-party-analyses"
    tp.mkdir(parents=True)
    f1 = tp / "source_inventory_2026-10-01.md"
    f1.write_text("# Source inventory — SYNTH\n\n**Date:** 2026-10-01\n\nZero sources.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=str(tmp_path), check=True)

    f2 = tp / "source_inventory_2026-10-02.md"
    f2.write_text("# Source inventory — SYNTH\n\n**Date:** 2026-10-02\n\nZero sources.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)

    res = compact_dated_artifacts.guard_staged_changes(tmp_path)
    assert res["canonicalized"] == 1
    assert res["dropped_redundant"] == 1
    assert (tp / "source_inventory.md").is_file()
    assert not f2.exists()
