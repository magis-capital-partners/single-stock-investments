"""Regression coverage for the stock Summary publication."""

import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock_summary import (
    SCHEMA,
    add_verified_close,
    audit,
    combine_captures,
    expected_sessions,
    price_capture,
    price_record,
    short_excerpt,
)


def capture(points, **extra):
    return {
        "points": points,
        "currency": "USD",
        "exchange": "NMS",
        "source": "https://quote.example/",
        "basis": "Split-adjusted daily close in trading currency",
        "scale": 1,
        **extra,
    }


def test_capture_uses_daily_granularity_and_exact_listing(tmp_path):
    asset = tmp_path / "capture.gz"
    data = {
        "symbol": "SNDK",
        "data": {
            "meta": {
                "symbol": "SNDK",
                "currency": "USD",
                "exchangeName": "NMS",
                "exchangeTimezoneName": "America/New_York",
                "dataGranularity": "1d",
            },
            "timestamp": [1740148200, 1740407400],
            "indicators": {"quote": [{"close": [5, 8]}]},
        },
    }

    def write():
        asset.write_bytes(gzip.compress(json.dumps(data).encode()))

    write()
    result = price_capture(asset, "SNDK", {"market": "US"}, "2025-02-24", {"first_session": "2025-02-24"})
    assert result["points"] == {"2025-02-24": 8}
    data["data"]["meta"]["dataGranularity"] = "1mo"
    write()
    assert price_capture(asset, "SNDK", {"market": "US"}, "2025-02-24", {}) is None
    data["data"]["meta"].update(dataGranularity="1d", symbol="OTHER")
    write()
    assert price_capture(asset, "SNDK", {"market": "US"}, "2025-02-24", {}) is None


def test_verified_split_adjusts_existing_history_and_close_matches_previous_session():
    old = capture({"2026-11-16": 800, "2026-11-17": 808, "2026-11-18": 816})
    new = capture(
        {"2026-11-16": 100, "2026-11-17": 101, "2026-11-18": 102, "2026-11-19": 94.395},
        verified_split={"factor": 8, "date": "2026-11-20"},
    )
    latest = capture({"2026-11-20": 79.24}, previous_close=94.395)
    both = combine_captures(old, add_verified_close(new, latest))
    assert both["points"] == {**new["points"], "2026-11-20": 79.24}
    assert not both.get("issue")
    assert add_verified_close(new, {**latest, "previous_close": 111}) is new
    assert "issue" in combine_captures(old, {**new, "verified_split": None})


def test_history_remains_visible_while_awaiting_new_closes():
    price = price_record(capture({"2026-11-18": 11, "2026-11-19": 10}), "2026-11-22", {}, {})
    assert price["expected_last"] == "2026-11-20"
    assert price["status"] == "stale"
    assert len(price["points"]) == 2
    end = price_record(
        capture({"2026-11-18": 11, "2026-11-19": 10}), "2026-11-22", {"ended": "2026-11-19"}, {}
    )
    assert end["status"] == "ended"
    assert expected_sessions("LSE", "2026-11-18", "2026-11-22")[0] == "2026-11-20"


def test_profile_short_excerpt_keeps_initials_and_limits_quotations():
    assert short_excerpt(
        "Arthur J. Gallagher & Co. provides insurance brokerage and risk management services."
    ) == ("Arthur J. Gallagher & Co. provides insurance brokerage and risk management services.")
    assert len(short_excerpt(" ".join(["example"] * 40)).removesuffix(" …").split()) == 24


def test_registry_requires_coverage_and_counts_alias_once():
    doc = {
        "schema": SCHEMA,
        "as_of": "2026-11-22",
        "registered": ["ECHO", "SATS"],
        "aliases": {"SATS": "ECHO"},
        "listings": {
            "ECHO": {
                "ticker": "ECHO",
                "description": {"status": "source_needed"},
                "price": {"status": "unavailable", "reason": "Source required"},
            }
        },
    }
    report = audit(doc)
    assert report["counts"]["prices"] == {"unavailable": 1}
    doc["registered"].append("NEW")
    with pytest.raises(ValueError, match="registry"):
        audit(doc)
