"""Automerge lane selection for cursor, codex, and claude branches."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "classify_agent_pr_lane.py"
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "marvin-pr-automerge.yml"

SYSTEM_FIX = [
    ".github/workflows/falsifier-resolution.yml",
    ".github/workflows/marvin-pr-automerge.yml",
    "_system/scripts/classify_agent_pr_lane.py",
    "_system/scripts/tests/test_falsifier_promotion_gate.py",
    "_system/memory/triage_events.jsonl",
    "_system/memory/triage_ledger.json",
]


def load():
    spec = importlib.util.spec_from_file_location("classify_agent_pr_lane_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_cursor_system_fix_uses_the_code_lane():
    lane = load()
    assert lane.classify("cursor/falsifier-e7-disposition-45c2", SYSTEM_FIX) == "code"


def test_control_plane_research_files_are_not_a_ticker_packet():
    lane = load()
    assert lane.classify(
        "cursor/fix-control-plane",
        ["_system/research/falsifier_outcomes.jsonl"],
    ) == "code"


def test_ticker_research_without_a_manifest_stays_on_the_research_lane():
    lane = load()
    assert lane.classify(
        "cursor/amzn-review-1111",
        ["AMZN/research/deep_dive_2026-10-02.md"],
    ) == "research"


def test_a_mixed_diff_that_touches_ticker_research_stays_on_the_research_lane():
    lane = load()
    assert lane.classify(
        "cursor/fix-1111",
        SYSTEM_FIX + ["ETHA/research/deep_dive_2026-10-02.md"],
    ) == "research"


def test_a_committee_packet_stays_on_the_research_lane():
    lane = load()
    assert lane.classify(
        "cursor/aaa-committee-1111",
        ["AAA/research/committee_work/2026-10-01/manifest.json"],
    ) == "research"


def test_a_manifest_stays_on_the_research_lane():
    lane = load()
    assert lane.classify(
        "cursor/etha-1111",
        ["ETHA/research/research_agent_manifest.json"],
    ) == "research"


def test_codex_and_claude_stay_on_the_code_lane_even_with_ticker_research():
    lane = load()
    files = ["AMZN/research/deep_dive.md"]
    assert lane.classify("codex/fix", files) == "code"
    assert lane.classify("claude/fix", files) == "code"


def test_an_unprefixed_branch_is_not_an_agent_lane():
    assert load().classify("feature/foo", SYSTEM_FIX) == "none"


def test_the_research_gate_still_requires_provenance_artifacts():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "classify_agent_pr_lane.py" in text
    assert "Cursor agent PR must include research_agent_manifest.json or committee_work artifacts." in text
    assert "needs.resolve-pr.outputs.lane == 'research'" in text
