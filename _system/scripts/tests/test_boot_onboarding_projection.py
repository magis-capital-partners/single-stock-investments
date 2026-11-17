"""The boot row retains its badge; the complete onboarding record stays lazy."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_dashboard_shards as shards


def test_onboarding_detail_survives_full_ticker_shard_without_boot_duplication(tmp_path):
    original = {"ticker": "TEST", "onboard": {"phase": "downloading", "updated": "2026-11-17T18:00:00Z", "error": None, "download_detail": "complete source inventory", "deep_dive_pending": True}}
    before = copy.deepcopy(original)
    boot = shards.slim_ticker_row(original)
    assert boot["onboard"] == {"phase": "downloading"}
    assert original == before
    shards.write_ticker_shards({"tickers": [original]}, tmp_path)
    complete = json.loads((tmp_path / "tickers/TEST.json").read_text())
    assert complete == before
    assert {**boot, **complete}["onboard"] == before["onboard"]


@pytest.mark.parametrize("phase", ["complete", "queued", "failed", "", None])
def test_boot_preserves_the_exact_onboarding_badge_value(phase):
    row = {"ticker": "TEST", "onboard": {"phase": phase, "error": "detail only"}}
    assert shards.slim_ticker_row(row)["onboard"] == {"phase": phase}


def test_unrecorded_phase_is_not_invented():
    assert shards.slim_ticker_row({"ticker": "TEST", "onboard": {"updated": "2026-11-17"}})["onboard"] == {}


@pytest.mark.parametrize("value", [None, "unavailable", []])
def test_non_mapping_onboarding_values_are_preserved(value):
    assert shards.slim_ticker_row({"ticker": "TEST", "onboard": value})["onboard"] == value
