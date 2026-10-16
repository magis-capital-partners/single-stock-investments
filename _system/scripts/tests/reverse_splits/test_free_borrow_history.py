from datetime import datetime, timezone

import pytest

from _system.scripts.reverse_splits.free_borrow_history import daily_records, prior_proxy, validate_borrow_url


@pytest.mark.parametrize("url", [
    "https://www.iborrowdesk.com/api/ticker/BYND/export", "https://www.iborrowdesk.com/api/ticker/BYND?range=all",
    "https://www.iborrowdesk.com/api/history/BYND", "https://user:pass@www.iborrowdesk.com/api/ticker/BYND",
    "https://api.databento.com/v0/timeseries", "https://iborrowdesk.com.evil.test/api/ticker/BYND",
])
def test_free_window_client_rejects_paid_export_history_auth_and_other_destinations(url):
    with pytest.raises(ValueError): validate_borrow_url(url)


def response(rows):
    return {"symbol": "TEST", "country": "usa", "daily": rows}


def test_completed_daily_fee_waits_until_following_eastern_day_and_is_percent_scaled():
    rows = daily_records(response([{"date": "2026-07-07", "fee": 50., "available": 1000}]), "TEST",
                         datetime(2026, 7, 9, tzinfo=timezone.utc))
    assert rows[0]["annual_rate"] == .5
    assert rows[0]["known_at"] == "2026-07-08T04:00:00+00:00"
    assert not rows[0]["approval"]
    assert prior_proxy(rows, "2026-07-07T21:00:00Z") is None
    assert prior_proxy(rows, "2026-07-08T14:00:00Z") == rows[0]
    assert prior_proxy(rows, "2026-07-10T14:00:00Z") is None


def test_incomplete_current_day_and_older_than_free_year_are_excluded():
    now = datetime(2026, 7, 7, 16, tzinfo=timezone.utc)
    rows = [{"date": "2026-07-07", "fee": 50., "available": 1000},
            {"date": "2024-07-07", "fee": 10., "available": 1000}]
    assert daily_records(response(rows), "TEST", now) == []


def test_unknown_or_negative_fee_is_not_a_free_loan_or_zero_inventory():
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    rows = [{"date": "2026-07-07", "fee": None, "available": 1000},
            {"date": "2026-07-07", "fee": -.1, "available": 1000},
            {"date": "2026-07-07", "fee": 50., "available": None}]
    assert daily_records(response(rows), "TEST", now) == []


def test_public_symbol_and_market_must_match():
    with pytest.raises(ValueError, match="mismatch"):
        daily_records({"symbol": "OTHER", "country": "usa"}, "TEST", datetime.now(timezone.utc))
