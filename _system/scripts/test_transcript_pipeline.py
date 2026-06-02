#!/usr/bin/env python3
"""Tests for transcript pipeline metadata and Polygon earnings verification."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from polygon_earnings import normalize_earnings_row, verified_display_events  # noqa: E402
from transcript_common import (  # noqa: E402
    is_transcript_candidate,
    manifest_has_period,
    parse_event_metadata,
)


def test_normalize_reported_earnings_verified():
    row = normalize_earnings_row(
        {
            "date": "2026-02-07",
            "fiscal_period": "Q4",
            "fiscal_year": 2025,
            "date_status": "confirmed",
            "actual_eps": 1.23,
        },
        portfolio_ticker="ICE",
        polygon_ticker="ICE",
    )
    assert row["verified"] is True
    assert row["reported"] is True
    assert row["verification_reason"] == "reported_actuals"


def test_normalize_projected_not_reported():
    row = normalize_earnings_row(
        {
            "date": "2026-08-01",
            "fiscal_period": "Q2",
            "date_status": "projected",
            "estimated_eps": 2.0,
        },
        portfolio_ticker="META",
        polygon_ticker="META",
    )
    assert row["reported"] is False
    assert row["verified"] is False


def test_confirmed_schedule_verified_not_reported():
    row = normalize_earnings_row(
        {
            "date": "2026-08-01",
            "fiscal_period": "Q2",
            "date_status": "confirmed",
        },
        portfolio_ticker="META",
        polygon_ticker="META",
    )
    assert row["reported"] is False
    assert row["verified"] is True
    assert row["verification_reason"] == "date_confirmed_scheduled"


def test_verified_display_excludes_unverified():
    events = [
        {"verified": True, "date": "2026-01-01"},
        {"verified": False, "date": "2026-02-01"},
    ]
    assert len(verified_display_events(events)) == 1


def test_transcript_url_detection():
    assert is_transcript_candidate("https://ir.example.com/CORRECTED-TRANSCRIPT-Q1.pdf")
    assert not is_transcript_candidate("https://ir.example.com/investor-deck.pdf")


def test_parse_corrected_transcript_metadata():
    meta = parse_event_metadata(
        "https://ir.ice.com/static-files/corrected-transcript-q4-2025.pdf",
        "CORRECTED-TRANSCRIPT-ICE-Q4-2025-Earnings-Call-7-February-2026.pdf",
    )
    assert meta["event_type"] == "earnings"
    assert meta["is_corrected"] is True
    assert meta["fiscal_period"] == "Q4"


def test_manifest_period_match():
    manifest = {
        "entries": [
            {"event_type": "earnings", "fiscal_period": "Q1", "fiscal_year": 2026, "call_date": "2026-05-06"},
        ]
    }
    assert manifest_has_period(manifest, "Q1", 2026, "2026-05-06")
    assert not manifest_has_period(manifest, "Q2", 2026, None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("All transcript pipeline tests passed.")
