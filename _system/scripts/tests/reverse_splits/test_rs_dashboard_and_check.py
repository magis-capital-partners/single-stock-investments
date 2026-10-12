"""The dashboard feed is built from the ledger alone, and the checker is loud about the right things."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

import build_reverse_splits_dashboard as builder
import check_reverse_splits as checker
from conftest import ROOT
from reverse_splits.ledger import ledger_paths, write_json, write_jsonl
from reverse_splits.strategy import GATES, RULES

TODAY = date(2026, 10, 11)


def test_payload_schema_and_authority_fields(fixture_ledger):
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    assert doc["schema_version"] == "reverse_splits.v1"
    assert doc["research_only"] is True and doc["in_base_irr"] is False and doc["authority"] == "none"
    assert doc["as_of"] == "2026-10-11" and doc["generated_at"].endswith("Z")
    assert doc["caption"] and doc["definition"]
    for key in ("counts", "recent_announcements", "upcoming_effective", "repeat_splitters", "book", "process", "decisions_summary", "health", "ledger"):
        assert key in doc, key
    assert doc["health"] == {"status": "healthy", "structural_errors": [], "problems": []}
    assert doc["ledger"]["path"] == "_system/data/reverse_splits/"


def test_counts_come_from_the_ledger_rows(fixture_ledger):
    counts = builder.build(today=TODAY, ledger_dir=fixture_ledger)["counts"]
    assert counts["events"] == 3 and counts["announcements"] == 4
    assert counts["by_cohort"] == {"first": 2, "second": 1, "third_plus": 0}
    assert counts["by_exchange_class"] == {"listed": 2, "otc": 1, "unknown": 0}
    assert counts["by_year"] == {"2024": 1, "2025": 1, "2026": 1}
    assert counts["announcements_by_outcome"] == {"announced_only": 2, "cancelled": 1, "mention": 1}
    assert counts["announcements_last_90_days"] == 3  # EEE on 2026-06-01 is outside the window
    assert counts["repeat_issuers"] == 1


def test_recent_announcements_are_windowed_sorted_and_linked(fixture_ledger):
    recent = builder.build(today=TODAY, ledger_dir=fixture_ledger)["recent_announcements"]
    assert [r["ticker"] for r in recent] == ["FFF", "CCC", "DDD"]
    ccc = recent[1]
    assert ccc["ratio"] == 0.1 and ccc["announced_ex_date"] == "2026-10-15" and ccc["outcome"] == "announced_only"
    assert ccc["url"] == "https://www.sec.gov/Archives/edgar/data/3/000100000026000003/"
    assert ccc["source"] == "edgar_search" or ccc["source"] is None
    assert recent[2]["company"] is None and recent[2]["outcome"] == "cancelled"


def test_upcoming_uses_events_and_parsed_schedules_but_never_cancellations(fixture_ledger):
    upcoming = builder.build(today=TODAY, ledger_dir=fixture_ledger)["upcoming_effective"]
    assert [(r["ticker"], r["ex_date"], r["basis"]) for r in upcoming] == [("CCC", "2026-10-15", "announcement"), ("AAA", "2026-10-20", "event")]
    event = upcoming[1]
    assert event["ratio"] == 0.05 and event["split_from"] == 20.0 and event["cohort"] == "second"
    assert event["url"] == "https://www.sec.gov/Archives/edgar/data/1/000100000026000001/"
    assert all(r["ticker"] != "DDD" for r in upcoming)


def test_repeat_splitters_group_by_issuer(fixture_ledger):
    repeat = builder.build(today=TODAY, ledger_dir=fixture_ledger)["repeat_splitters"]
    assert len(repeat) == 1
    assert repeat[0]["ticker"] == "AAA" and repeat[0]["prior_rs_count"] == 1
    assert repeat[0]["last_ex_date"] == "2026-10-20" and repeat[0]["cohort"] == "second"


def test_book_process_and_decisions_sections(fixture_ledger):
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    book = doc["book"]
    assert book["latest_run"]["label"] == "fundamental_60" and book["latest_run"]["taken"] == 4
    assert book["latest_run"]["net_pnl"] == 140.72
    assert [r["label"] for r in book["latest_batch"]] == ["assumed_100_h5_effective", "fundamental_60"]
    assert book["latest_batch"][0]["net_pnl"] == -14286.0 and book["latest_batch"][0]["losses_over_50pct"] == 7
    assert book["run_count"] == 2 and book["authority"] == "none"
    assert any("locate" in limit.lower() for limit in book["honest_limits"])
    process = doc["process"]
    assert process["version"] == "RSI-1.0" and process["rules"] == RULES
    assert [g["id"] for g in process["gates"]] == [g["id"] for g in GATES]
    assert process["policy"]["entry"] and process["validation"]
    assert process["doc"] == "_system/frameworks/reverse_split_short_process.md"
    summary = doc["decisions_summary"]
    assert summary["count"] == 2 and summary["by_decision"] == {"review": 1, "pass": 1}
    assert summary["tickers"] == ["DFLI", "NXGL"] and summary["chain_valid"] is True
    assert summary["latest_at"] == "2026-10-02T15:00:00+00:00"


def test_empty_ledger_builds_an_honest_empty_feed(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    doc = builder.build(today=TODAY, ledger_dir=empty)
    assert doc["counts"]["events"] == 0 and doc["recent_announcements"] == [] and doc["upcoming_effective"] == []
    assert doc["book"]["latest_run"] is None and doc["book"]["run_count"] == 0
    assert doc["decisions_summary"] == {**doc["decisions_summary"], "count": 0, "latest_at": None}
    assert doc["health"]["status"] == "unhealthy"
    assert any("ledger_manifest.json missing" in p for p in doc["health"]["problems"])


def test_main_writes_the_feed_and_the_feed_is_valid_json(fixture_ledger, tmp_path):
    out = tmp_path / "reverse_splits.json"
    assert builder.main(["--ledger-dir", str(fixture_ledger), "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema_version"] == "reverse_splits.v1" and doc["counts"]["events"] == 3


# ------------------------------------------------------------------ checker
def test_clean_fixture_has_no_structural_errors(fixture_ledger):
    assert checker.structural_errors(fixture_ledger) == []


def test_duplicate_event_key_is_a_structural_error(fixture_ledger):
    paths = ledger_paths(fixture_ledger)
    rows = [json.loads(line) for line in paths["events"].read_text(encoding="utf-8").splitlines()]
    rows.append(dict(rows[0]))
    write_jsonl(paths["events"], rows)
    errors = checker.structural_errors(fixture_ledger)
    assert any("duplicate event key" in e for e in errors)


def test_bad_json_line_and_bad_enums_are_reported_with_location(fixture_ledger):
    paths = ledger_paths(fixture_ledger)
    with paths["announcements"].open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    errors = checker.structural_errors(fixture_ledger)
    assert any("announcements.jsonl:5: invalid JSON" in e for e in errors)
    rows = [json.loads(line) for line in paths["events"].read_text(encoding="utf-8").splitlines()]
    rows[0]["exchange_class"] = "pink"
    rows[1]["cohort"] = "fourth"
    rows[2]["ex_date"] = "06/01/2025"
    write_jsonl(paths["events"], rows)
    errors = checker.structural_errors(fixture_ledger)
    assert any("events[0]: exchange_class" in e for e in errors)
    assert any("events[1]: cohort" in e for e in errors)
    assert any("events[2]: ex_date" in e for e in errors)


def test_broken_decision_chain_and_missing_manifest_are_structural_errors(fixture_ledger):
    paths = ledger_paths(fixture_ledger)
    rows = [json.loads(line) for line in paths["decisions"].read_text(encoding="utf-8").splitlines()]
    rows[0]["record"]["reason"] = "tampered"
    write_jsonl(paths["decisions"], rows)
    runs = [json.loads(line) for line in paths["book_runs"].read_text(encoding="utf-8").splitlines()]
    runs[0]["source_manifest_sha256"] = "f" * 64
    write_jsonl(paths["book_runs"], runs)
    errors = checker.structural_errors(fixture_ledger)
    assert any("decisions[0]: record_hash does not match" in e for e in errors)
    assert any("book_runs[0]: source manifest" in e for e in errors)


def test_health_flags_a_stale_ledger_and_a_stale_or_missing_feed(fixture_ledger, stale_fixture_ledger, tmp_path):
    fresh_feed = tmp_path / "fresh.json"
    builder.main(["--ledger-dir", str(fixture_ledger), "--out", str(fresh_feed)])
    report = checker.health(ledger_dir=fixture_ledger, dashboard_path=fresh_feed)
    assert report["status"] == "healthy" and report["problems"] == [] and report["structural_errors"] == []

    stale = checker.health(ledger_dir=stale_fixture_ledger, dashboard_path=fresh_feed)
    assert stale["status"] == "unhealthy" and any("ledger exported 11 days ago" in p for p in stale["problems"])

    missing = checker.health(ledger_dir=fixture_ledger, dashboard_path=tmp_path / "nope.json")
    assert missing["status"] == "unhealthy" and any("missing" in p for p in missing["problems"])

    old_feed = tmp_path / "old.json"
    write_json(old_feed, {"generated_at": (datetime.now(timezone.utc) - timedelta(hours=101)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    old = checker.health(ledger_dir=fixture_ledger, dashboard_path=old_feed)
    assert old["status"] == "unhealthy" and any("101h old" in p for p in old["problems"])

    built_in = checker.health(ledger_dir=fixture_ledger, check_dashboard=False)
    assert built_in["status"] == "healthy"


def test_main_exit_codes_follow_strict_and_warn_only(fixture_ledger, stale_fixture_ledger, tmp_path):
    feed = tmp_path / "feed.json"
    builder.main(["--ledger-dir", str(fixture_ledger), "--out", str(feed)])
    assert checker.main(["--strict", "--ledger-dir", str(fixture_ledger), "--dashboard", str(feed)]) == 0
    assert checker.main(["--ledger-dir", str(stale_fixture_ledger), "--dashboard", str(feed)]) == 0
    assert checker.main(["--strict", "--ledger-dir", str(stale_fixture_ledger), "--dashboard", str(feed)]) == 1
    assert checker.main(["--strict", "--warn-only", "--ledger-dir", str(stale_fixture_ledger), "--dashboard", str(feed)]) == 0
    paths = ledger_paths(fixture_ledger)
    rows = [json.loads(line) for line in paths["events"].read_text(encoding="utf-8").splitlines()]
    write_jsonl(paths["events"], rows + [dict(rows[0])])
    assert checker.main(["--ledger-dir", str(fixture_ledger), "--dashboard", str(feed)]) == 1
    assert checker.main(["--warn-only", "--ledger-dir", str(fixture_ledger), "--dashboard", str(feed)]) == 0


# ------------------------------------------------------------- real ledger
REAL_LEDGER = ROOT / "_system" / "data" / "reverse_splits"


@pytest.mark.skipif(not (REAL_LEDGER / "events.jsonl").exists(), reason="committed ledger not checked out")
def test_committed_ledger_is_structurally_valid_and_builds():
    assert checker.structural_errors(REAL_LEDGER) == []
    doc = builder.build(ledger_dir=REAL_LEDGER)
    assert doc["counts"]["events"] >= 600
    assert doc["counts"]["announcements"] >= 10000
    assert doc["decisions_summary"]["chain_valid"] is True
    assert len(doc["recent_announcements"]) <= 100 and len(doc["upcoming_effective"]) <= 50 and len(doc["repeat_splitters"]) <= 50
    for name in ("events", "announcements", "finra_short_interest", "book_runs", "book_source_manifests", "decisions"):
        size = (REAL_LEDGER / f"{name}.jsonl").stat().st_size
        assert size <= 10 * 1024 * 1024, f"{name}.jsonl is {size} bytes; nothing over 10 MB enters git"
    assert not (REAL_LEDGER / "local").exists() or (REAL_LEDGER / "local").is_dir()
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "_system/data/reverse_splits/local/" in gitignore
