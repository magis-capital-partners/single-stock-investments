#!/usr/bin/env python3
"""The bot path guard, and its agreement with docs/WRITE_MAP.md and the lane classifier."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import check_contributor_paths as guard  # noqa: E402
import classify_agent_pr_lane as lanes  # noqa: E402

GROK = "grok/special_situations/2026-10-12-mdt-mmed"


@pytest.mark.parametrize(
    "path",
    [
        "_system/data/desk_briefs/special_situations/2026-10-12.json",
        "_system/memory-hub/research-equity/daily/2026-10-12.md",
        "_system/memory-hub/research-equity/CONTEXT.md",
        "_system/data/separations/separation_registry.jsonl",
        "_system/data/separations/separation_amendments.jsonl",
        "_system/research/short-alpha/candidates.json",
        "_system/reference/activist-reports/short_scorecard/Fugazi.csv",
        "MDT/third-party-analyses/vic/vic_2026-10-12_note_ab12.md",
        "_system/reviews/pending/desk_note_2026-10-12.md",
        "_system/memory/daily/2026-10-12.md",
    ],
)
def test_allowlisted_paths_pass(path):
    ok, offending = guard.check(GROK, [path])
    assert ok, offending


@pytest.mark.parametrize(
    "path",
    [
        "_system/scripts/build_special_situations.py",
        ".github/workflows/data-pipeline.yml",
        "_system/memory/MEMORY.md",
        "_system/reviews/approved/x.md",
        "MDT/research/human_decision.json",
        "_system/frameworks/special_situation_lens.md",
        "_system/data/desk_briefs/schema.json",
        "_system/data/desk_briefs/special_situations/notes.json",
        "_system/data/separations/separation_flows.jsonl",
        "_system/memory-hub/research-equity/README.md",
        "dashboard/index.html",
        "MDT/research/valuation.json",
        "a/b/third-party-analyses/vic/deep.md",
    ],
)
def test_other_paths_hold_for_review(path):
    ok, offending = guard.check(GROK, [path])
    assert not ok
    assert offending == [path]


def test_mixed_pr_reports_only_offenders():
    ok, offending = guard.check(
        GROK,
        ["_system/data/desk_briefs/activism/2026-10-12.json", "_system/scripts/x.py"],
    )
    assert not ok
    assert offending == ["_system/scripts/x.py"]


def test_non_grok_branches_are_not_guarded_here():
    ok, offending = guard.check("cursor/some-research", ["_system/scripts/x.py"])
    assert ok and offending == []
    ok, offending = guard.check("feature/anything", ["CLAUDE.md"])
    assert ok


@pytest.mark.parametrize("ref", ["grok/x", "grok/special_situations/notadate-x", "grok/Desk/2026-10-12-x", "GROK/a/2026-10-12-x"])
def test_malformed_grok_branch_is_other(ref):
    assert guard.classify_branch(ref) == "other"


def test_classifier_routes_grok_data_prs_to_the_data_lane():
    assert lanes.classify(GROK, ["_system/data/desk_briefs/activism/2026-10-12.json"]) == "data"
    assert lanes.classify(GROK, ["_system/scripts/x.py"]) == "code"
    assert lanes.classify(GROK, []) == "code"
    assert lanes.classify("cursor/x", ["MDT/research/thesis.md"]) == "research"
    assert lanes.classify("feature/x", ["MDT/research/thesis.md"]) == "none"


def test_write_map_lists_every_allowlist_pattern():
    text = (ROOT / "docs" / "WRITE_MAP.md").read_text(encoding="utf-8")
    for pattern in guard.GROK_DATA_ALLOWLIST:
        # The doc writes <desk>/<YYYY-MM-DD> where the glob has */????-??-??
        prose = (
            pattern.replace("*/????-??-??.json", "<desk>/<YYYY-MM-DD>.json")
            .replace("????-??-??.md", "<YYYY-MM-DD>.md")
            .replace("*/third-party-analyses", "{TICKER}/third-party-analyses")
            .replace("short_scorecard/*", "short_scorecard/")
            .replace("pending/*.md", "pending/*.md")
        )
        assert prose in text, f"{pattern} ({prose}) missing from docs/WRITE_MAP.md"


def test_contributing_names_the_guard():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "check_contributor_paths.py" in text
    assert re.search(r"grok/<desk>/<yyyy-mm-dd>-<slug>", text)
