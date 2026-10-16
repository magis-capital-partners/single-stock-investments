"""Tests for the agent data architecture (schemas, units, latest, packs, claims, chunks, search, MCP, proposals, eval)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import agent_mcp_server  # noqa: E402
import agent_proposals  # noqa: E402
import agent_schema  # noqa: E402
import agent_search  # noqa: E402
import build_agent_context  # noqa: E402
import build_chunk_store  # noqa: E402
import build_claim_store  # noqa: E402
import build_ticker_latest  # noqa: E402
import lint_agent_data  # noqa: E402
import normalize_return_units  # noqa: E402
import run_agent_eval  # noqa: E402


def test_schemas_exist_and_core_payloads_validate() -> None:
    for name in ("valuation", "thesis_card", "agent_shard", "ticker_latest", "claim", "chunk", "context_pack", "agent_proposal"):
        schema = agent_schema.load_schema(name)
        assert schema["type"] == "object"
    assert agent_schema.validate({"ticker": "GOOGL", "schema_version": "magis.valuation.v2", "returns": {"base_irr_pct": 0.12, "unit": "percent_per_year"}}, "valuation") == []


def test_canonical_returns_keeps_percent_unit_without_rescaling() -> None:
    # display "0.12%" proves sub-1 values are percent, not fractions.
    returns = agent_schema.canonical_returns(
        {"implied_return": {"base_pct": 0.12, "label": "7yr IRR", "display": "0.12% (total synthesis)"}, "results": {"base": {"return_pct": 0.5}}}
    )
    assert returns["base_irr_pct"] == 0.12
    assert returns["unit"] == "percent_per_year"


def test_latest_pointer_resolves_canonical_digest(tmp_path: Path) -> None:
    research = tmp_path / "SYNTH" / "research"
    evidence = research / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "filing_digest.md").write_text("# Digest\n\nCanonical body.\n", encoding="utf-8")
    (evidence / "filing_digest_2026-01-01.md").write_text("# Digest\n\nDated body.\n", encoding="utf-8")
    (research / "deep_dive_2026-01-02.md").write_text("# Dive\n\nBody.\n", encoding="utf-8")
    (research / "valuation.json").write_text(json.dumps({"ticker": "SYNTH", "as_of": "2026-01-02"}), encoding="utf-8")
    payload = build_ticker_latest.build_latest("SYNTH", root=tmp_path)
    assert payload is not None
    assert payload["artifacts"]["filing_digest"]["path"].endswith("filing_digest.md")
    assert payload["artifacts"]["deep_dive"]["date"] == "2026-01-02"
    assert payload["artifacts"]["filing_digest"]["sha256"].startswith("sha256:")


def test_normalize_and_lint_synthetic_ticker(tmp_path: Path) -> None:
    research = tmp_path / "SYNTH" / "research"
    (research / "evidence").mkdir(parents=True)
    (research / "evidence" / "filing_digest.md").write_text("# Digest\n\nBody.\n", encoding="utf-8")
    (research / "valuation.json").write_text(
        json.dumps({"ticker": "SYNTH", "as_of": "2026-01-02", "implied_return": {"base_pct": 12.5, "label": "7yr IRR", "display": "12.5% (base)"}, "results": {"base": {"return_pct": 12.5}}}),
        encoding="utf-8",
    )
    (research / "thesis_card.json").write_text(
        json.dumps({"ticker": "SYNTH", "schema_version": "1.0", "base_irr_pct": 12.5, "filing_digest": "SYNTH/research/evidence/filing_digest_2026-01-01.md"}),
        encoding="utf-8",
    )
    normalize_return_units.normalize_ticker("SYNTH", root=tmp_path)
    build_ticker_latest.write_latest("SYNTH", root=tmp_path)
    card = json.loads((research / "thesis_card.json").read_text(encoding="utf-8"))
    assert card["base_irr_unit"] == "percent_per_year"
    assert card["returns"]["base_irr_pct"] == 12.5
    assert card["filing_digest"].endswith("filing_digest.md")
    assert lint_agent_data.lint_ticker("SYNTH", root=tmp_path) == []


def test_context_pack_is_budgeted_and_lists_exclusions(tmp_path: Path) -> None:
    manifest = build_agent_context.write_pack("GOOGL", task="triage", root=ROOT)
    assert manifest["schema_version"] == "magis.context_pack.v1"
    assert manifest["token_estimate"] <= manifest["token_budget"] + 50
    assert manifest["excluded"]
    text = (ROOT / "dashboard" / "data" / "context_packs" / "GOOGL.md").read_text(encoding="utf-8")
    assert "## Returns (stable, percent per year)" in text
    assert "## Excluded from this pack" in text
    assert text.index("## Identity") < text.index("## Canonical pointers")


def test_claim_and_chunk_rows_validate() -> None:
    claims = build_claim_store.build_claims()
    assert len(claims) > 1000
    assert {c["status"] for c in claims} <= {"approved", "verified", "pending", "assumption"}
    assert all(c["source_path"] for c in claims)


def test_chunker_splits_by_heading() -> None:
    text = "# Title\n\n" + ("Pricing power compounds. " * 80) + "\n\n## Moat\n\n" + ("Widening moat evidence. " * 80)
    chunks = build_chunk_store.chunk_text(text)
    assert len(chunks) >= 2
    assert chunks[0][0] == "Title"


def test_hybrid_search_returns_cited_chunks(tmp_path: Path) -> None:
    db = tmp_path / "agent_search.sqlite"
    stats = agent_search.build_search_index(db, root=ROOT)
    assert stats["total"] > 100
    result = agent_search.search("Alphabet", ticker="GOOGL", limit=5, db_path=db, root=ROOT)
    assert result["count"] >= 1
    assert all(hit["source_path"] for hit in result["hits"])


def test_mcp_tools_are_read_only_and_functional() -> None:
    names = {tool["name"] for tool in agent_mcp_server.TOOLS}
    assert names == {"get_portfolio_summary", "get_ticker", "get_valuation", "get_claims", "search", "get_context_pack"}
    valuation = agent_mcp_server.call_tool("get_valuation", {"ticker": "GOOGL"})
    assert valuation["returns"]["unit"] == "percent_per_year"
    listing = agent_mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listing is not None and len(listing["result"]["tools"]) == 6


def test_proposal_validation_requires_existing_provenance(tmp_path: Path) -> None:
    good = {
        "agent": "test-agent",
        "kind": "claim",
        "ticker": "GOOGL",
        "summary": "Alphabet pricing power claim",
        "payload": {"statement": "Pricing power"},
        "provenance": {"source_paths": ["GOOGL/research/thesis_card.json"], "as_of": "2026-10-16"},
    }
    submitted = agent_proposals.submit(good, inbox=tmp_path / "inbox.jsonl", root=ROOT)
    assert submitted["status"] == "pending_human_review"
    bad = dict(good, provenance={"source_paths": ["NOPE/missing.json"]})
    assert agent_proposals.validate_proposal(bad, root=ROOT)


def test_golden_eval_passes_on_canonical_stores() -> None:
    golden = run_agent_eval.build_golden()
    assert len(golden["questions"]) == 30
    assert len({q["ticker"] for q in golden["questions"]}) == 10
    result = run_agent_eval.run_eval(golden=golden)
    assert result["pass"], result["failures"]
