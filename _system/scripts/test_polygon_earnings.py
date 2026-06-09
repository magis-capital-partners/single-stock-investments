#!/usr/bin/env python3
"""Tests for Polygon earnings access probe and cache preservation."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from polygon_earnings import (  # noqa: E402
    fetch_portfolio_earnings,
    merge_earnings_cache_payload,
    probe_earnings_access,
    resolve_earnings_events,
    save_earnings_cache,
)


def _sample_event(ticker: str = "ICE") -> dict:
    return {
        "portfolio_ticker": ticker,
        "polygon_ticker": ticker,
        "date": "2026-02-07",
        "verified": True,
        "reported": True,
    }


def test_probe_forbidden_on_both_bases():
    session = MagicMock()
    with patch("polygon_earnings.POLYGON_API_KEY", "test-key"):
        with patch(
            "polygon_earnings._polygon_request",
            side_effect=[(None, 403), (None, 403)],
        ) as mock_request:
            status = probe_earnings_access(session, probe_ticker="AAPL")
    assert status == "forbidden"
    assert mock_request.call_count == 2


def test_probe_ok_on_first_base():
    session = MagicMock()
    with patch("polygon_earnings.POLYGON_API_KEY", "test-key"):
        with patch(
            "polygon_earnings._polygon_request",
            return_value=({"results": []}, 200),
        ) as mock_request:
            status = probe_earnings_access(session, probe_ticker="AAPL")
    assert status == "ok"
    assert mock_request.call_count == 1


def test_forbidden_fetch_does_not_wipe_cache():
    existing = {
        "as_of": "2026-06-01T00:00:00Z",
        "events": [_sample_event()],
        "event_count": 1,
    }
    incoming = {
        "access_status": "forbidden",
        "fetch_skipped": True,
        "events": [],
        "event_count": 0,
    }
    merged = merge_earnings_cache_payload(existing, incoming)
    assert len(merged["events"]) == 1
    assert merged.get("cache_preserved") is True


def test_resolve_falls_back_to_cache():
    cache = {
        "as_of": "2026-06-01T00:00:00Z",
        "events": [_sample_event("META")],
    }
    payload = {
        "access_status": "forbidden",
        "fetch_skipped": True,
        "events": [],
    }
    events = resolve_earnings_events(payload, cache)
    assert len(events) == 1
    assert events[0]["portfolio_ticker"] == "META"


def test_ok_fetch_replaces_cache():
    existing = {
        "as_of": "2026-06-01T00:00:00Z",
        "events": [_sample_event("OLD")],
    }
    incoming = {
        "access_status": "ok",
        "fetch_skipped": False,
        "events": [_sample_event("NEW")],
        "event_count": 1,
    }
    merged = merge_earnings_cache_payload(existing, incoming)
    assert merged["events"][0]["portfolio_ticker"] == "NEW"
    assert merged.get("cache_preserved") is None


def test_fetch_portfolio_skips_ticker_loop_on_forbidden():
    with patch("polygon_earnings.POLYGON_API_KEY", "test-key"):
        with patch("polygon_earnings.probe_earnings_access", return_value="forbidden"):
            with patch("polygon_earnings.fetch_ticker_earnings") as mock_fetch:
                payload = fetch_portfolio_earnings()
    assert payload["access_status"] == "forbidden"
    assert payload["fetch_skipped"] is True
    mock_fetch.assert_not_called()


def test_save_earnings_cache_preserves_events():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cache_path = Path(tmp) / "earnings_calendar.json"
        original_path = save_earnings_cache.__globals__["EARNINGS_CACHE_PATH"]
        save_earnings_cache.__globals__["EARNINGS_CACHE_PATH"] = cache_path
        try:
            existing = {"events": [_sample_event()], "event_count": 1}
            incoming = {
                "access_status": "forbidden",
                "fetch_skipped": True,
                "events": [],
                "event_count": 0,
                "policy_version": 2,
            }
            save_earnings_cache(incoming, existing=existing)
            saved = cache_path.read_text(encoding="utf-8")
            assert '"portfolio_ticker": "ICE"' in saved
            assert '"cache_preserved": true' in saved
        finally:
            save_earnings_cache.__globals__["EARNINGS_CACHE_PATH"] = original_path


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("All polygon earnings tests passed.")
