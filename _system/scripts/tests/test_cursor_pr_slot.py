"""One open Cursor pull request per ticker, including dirty and draft ones."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "cursor_pr_slot.py"


def load():
    spec = importlib.util.spec_from_file_location("cursor_pr_slot_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_dirty_pr_still_occupies_the_ticker_slot():
    slot = load()
    prs = [
        {"number": 3, "headRefName": "cursor/csco-old-aaaa", "title": "CSCO: falsifier", "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"},
        {"number": 4, "headRefName": "cursor/crwd-bbbb", "title": "CRWD: falsifier", "mergeable": "MERGEABLE"},
    ]
    matches = slot.open_prs_for_ticker(prs, "CSCO")
    assert [pr["number"] for pr in matches] == [3]
    assert slot.cursor_pr_count(prs) == 2


def test_a_ticker_substring_does_not_steal_another_ticker():
    slot = load()
    prs = [{"number": 9, "headRefName": "cursor/amzn-review-cccc", "title": "AMZN: runway", "mergeable": "MERGEABLE"}]
    assert slot.open_prs_for_ticker(prs, "AM") == []
    assert slot.pr_matches_ticker(prs[0], "AMZN")


def test_duplicates_are_every_other_open_pr_for_the_ticker():
    slot = load()
    prs = [
        {"number": 1, "headRefName": "cursor/asml-old", "title": "ASML: v5", "isDraft": True},
        {"number": 2, "headRefName": "cursor/asml-new", "title": "ASML: v6"},
    ]
    extras = slot.duplicates_of(prs, "ASML", 1)
    assert [pr["number"] for pr in extras] == [2]
