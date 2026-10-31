"""Desk feed age: two business days, and warrant rows missing terms_status."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_desk_feed_age as age  # noqa: E402


def _write(root: Path, rel: str, doc: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_two_business_days_is_fresh_and_three_is_not(tmp_path: Path):
    # Thursday 2026-10-29. Tuesday 2026-10-27 is two NYSE sessions back.
    spec = age.FeedSpec("sample", "dashboard/data/sample.json", row_lists=(("rows", "as_of"),))
    fresh = {"generated_at": "2026-10-27T13:00:00Z", "rows": [{"as_of": "2026-10-27"}]}
    _write(tmp_path, spec.path, fresh)
    assert age.check_feed(spec, root=tmp_path, today=date(2026, 10, 29)) == []

    stale = {"generated_at": "2026-10-26T13:00:00Z", "rows": [{"as_of": "2026-10-26"}]}
    _write(tmp_path, spec.path, stale)
    flags = age.check_feed(spec, root=tmp_path, today=date(2026, 10, 29))
    assert any("generated_at" in flag and "3 business days" in flag for flag in flags)
    assert any("newest row" in flag for flag in flags)


def test_envelope_stamp_wins_over_generated_at(tmp_path: Path):
    spec = age.FeedSpec("sample", "dashboard/data/sample.json")
    _write(
        tmp_path,
        spec.path,
        {"generated_at": "2026-10-01T00:00:00Z", "_envelope": {"generated_at": "2026-10-29T00:00:00Z"}},
    )
    assert age.check_feed(spec, root=tmp_path, today=date(2026, 10, 29)) == []


def test_weekend_does_not_count(tmp_path: Path):
    # Monday 2026-10-26. Friday 2026-10-23 is one business day back.
    spec = age.FeedSpec("sample", "dashboard/data/sample.json")
    _write(tmp_path, spec.path, {"build_time": "2026-10-23T15:00:00Z"})
    assert age.check_feed(spec, root=tmp_path, today=date(2026, 10, 26)) == []


def test_missing_terms_status_is_flagged_and_unparsed_is_not(tmp_path: Path):
    spec = age.FEEDS["warrants"]
    _write(
        tmp_path,
        spec.path,
        {
            "generated_at": "2026-10-29T00:00:00Z",
            "events": [{"event_id": "e1", "filed_at": "2026-10-29", "terms_status": "unparsed"}],
            "rows": [{"warrant_id": "w1", "terms": {"strike": 1}}],
        },
    )
    flags = age.check_feed(spec, root=tmp_path, today=date(2026, 10, 29))
    assert any("missing terms_status" in flag and "w1" in flag for flag in flags)
    assert not any("e1" in flag for flag in flags)


def test_activist_feed_is_a_named_feed_the_activism_desk_can_call():
    assert "activist_feed" in age.DESK_FEEDS["activism"]
    assert "activist_feed" in age.DESK_FEEDS["special_situations"]
    assert age.FEEDS["activist_feed"].row_lists == (("feed", "report_date"),)


def test_catalog_without_a_stamp_uses_the_summary(tmp_path: Path):
    spec = age.FEEDS["document_catalog"]
    _write(tmp_path, spec.path, {"private_snapshot": True})
    _write(
        tmp_path,
        spec.fallback_path,
        {"_envelope": {"generated_at": "2026-10-16T16:17:11Z", "health": {"status": "healthy"}}},
    )
    flags = age.check_feed(spec, root=tmp_path, today=date(2026, 10, 29))
    assert any("document_catalog_summary" in flag for flag in flags)
    assert any("business days" in flag for flag in flags)
