"""The summary window waits out a model reload instead of ending on the first refusal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import llm_local


def test_retry_after_outage_stops_when_the_window_is_over():
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert llm_local.retry_after_outage(RuntimeError("connection refused"), past, sleep_seconds=0) is False
    assert llm_local.retry_after_outage(RuntimeError("connection refused"), None, sleep_seconds=0) is False


def test_retry_after_outage_forgets_the_stale_server(monkeypatch):
    llm_local._RESOLVED["http://localhost:1234/v1"] = "http://127.0.0.1:9/v1"
    monkeypatch.setattr(llm_local.time, "sleep", lambda _seconds: None)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert llm_local.retry_after_outage(RuntimeError("connection refused"), future, sleep_seconds=0) is True
    assert llm_local._RESOLVED == {}
