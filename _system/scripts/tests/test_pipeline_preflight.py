"""The news preflight may skip only a run that would duplicate the last one."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pipeline_preflight as preflight  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def test_feed_built_at_reads_build_time(tmp_path: Path) -> None:
    feed = tmp_path / "portfolio_news.json"
    feed.write_text(json.dumps({"build_time": "2026-10-16T10:30:00Z", "items": []}), encoding="utf-8")
    assert preflight.feed_built_at(feed) == datetime(2026, 10, 16, 10, 30, tzinfo=timezone.utc)


def test_decide_news_skips_only_a_fresh_duplicate() -> None:
    fresh = NOW - timedelta(hours=1)
    stale = NOW - timedelta(hours=8)
    assert preflight.decide_news(fresh, now=NOW)[0] is False
    assert preflight.decide_news(stale, now=NOW)[0] is True


def test_decide_news_fails_open() -> None:
    assert preflight.decide_news(None, now=NOW)[0] is True
    future = NOW + timedelta(hours=1)
    assert preflight.decide_news(future, now=NOW)[0] is True
