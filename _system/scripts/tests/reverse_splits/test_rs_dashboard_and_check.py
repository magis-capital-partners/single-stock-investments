"""The dashboard feed is built from the ledger alone, and the checker is loud about the right things."""
from __future__ import annotations

import json
import shutil
import subprocess
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
    assert counts["announcement_issuers_last_90_days"] == 3
    assert counts["repeat_issuers"] == 1
    # Additive keys: where the events came from and how many still need review.
    assert counts["events_by_source"] == {"yfinance": 2, "edgar_search": 1}
    assert counts["events_by_status"] == {"seeded": 2, "edgar_candidate": 1}
    assert counts["events_needs_review"] == 1
    assert counts["events_distinct"] == 3 and counts["duplicate_event_rows"] == 0
    assert counts["first_ex_date"] == "2024-03-01" and counts["last_ex_date"] == "2026-10-20"
    assert counts["upcoming_effective"] == 2


def test_recent_announcements_are_windowed_sorted_and_linked(fixture_ledger):
    recent = builder.build(today=TODAY, ledger_dir=fixture_ledger)["recent_announcements"]
    assert [r["ticker"] for r in recent] == ["FFF", "CCC", "DDD"]
    ccc = recent[1]
    assert ccc["ratio"] == 0.1 and ccc["announced_ex_date"] == "2026-10-15" and ccc["outcome"] == "announced_only"
    assert ccc["url"] == "https://www.sec.gov/Archives/edgar/data/3/000100000026000003/"
    assert ccc["source"] == "edgar_search" or ccc["source"] is None
    assert recent[2]["company"] is None and recent[2]["outcome"] == "cancelled"
    assert ccc["ex_date_status"] == "scheduled" and ccc["phrase_hit"] is False and ccc["filings_in_window"] == 1
    assert recent[2]["ex_date_status"] == "cancelled"
    assert recent[0]["phrase_hit"] is False  # a mention is labelled Mention, not a phrase hit


def _append_announcements(ledger, rows):
    paths = ledger_paths(ledger)
    existing = [json.loads(line) for line in paths["announcements"].read_text(encoding="utf-8").splitlines()]
    write_jsonl(paths["announcements"], existing + rows, sparse=True)


def _append_events(ledger, rows):
    paths = ledger_paths(ledger)
    existing = [json.loads(line) for line in paths["events"].read_text(encoding="utf-8").splitlines()]
    write_jsonl(paths["events"], existing + rows)


def _announcement(ticker, cik, day, **extra):
    return {"ticker": ticker, "cik": cik, "company": f"{ticker} Inc", "exchange": "Nasdaq", "exchange_class": "listed",
            "announce_date": day, "outcome": "announced_only", "date_quality": "filing_text",
            "accept_time": f"{day}T12:00:00.000Z", "accession": f"acc-{ticker}-{day}", "form": "8-K", **extra}


def test_recent_collapses_by_issuer_badges_phrase_hits_and_reads_past_dates_as_effective(fixture_ledger):
    _append_announcements(fixture_ledger, [
        # One issuer filing three times in the window collapses to its newest filing.
        _announcement("NXX", "0000000077", "2026-09-01", announced_ratio=0.1),
        _announcement("NXX", "0000000077", "2026-09-20"),
        _announcement("NXXW", "0000000077", "2026-10-05"),
        # A phrase hit: announced only, no ratio, no ex date.
        _announcement("PTC", "0000000088", "2026-10-06"),
        # The filing reports a date before itself: effective, not scheduled.
        _announcement("DXS", "0000000099", "2026-10-06", announced_ex_date="2026-05-07", announced_ratio=0.05),
    ])
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    recent = doc["recent_announcements"]
    nxx = [r for r in recent if r["cik"] == "0000000077"]
    assert len(nxx) == 1 and nxx[0]["ticker"] == "NXXW" and nxx[0]["announce_date"] == "2026-10-05"
    assert nxx[0]["filings_in_window"] == 3 and nxx[0]["phrase_hit"] is True
    ptc = next(r for r in recent if r["ticker"] == "PTC")
    assert ptc["phrase_hit"] is True and ptc["ex_date_status"] is None
    dxs = next(r for r in recent if r["ticker"] == "DXS")
    assert dxs["phrase_hit"] is False and dxs["ex_date_status"] == "effective" and dxs["ex_date_before_filing"] is True
    counts = doc["counts"]
    # The heading's count is the true 90-day total (filings and issuers), not the length of the list.
    assert counts["announcements_last_90_days"] == 8 and counts["announcement_issuers_last_90_days"] == 6
    assert len(recent) == 6


def test_recent_list_is_capped_but_the_count_is_not(fixture_ledger, monkeypatch):
    monkeypatch.setattr(builder, "MAX_RECENT", 2)
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    assert len(doc["recent_announcements"]) == 2 and doc["counts"]["announcements_last_90_days"] == 3


def test_upcoming_uses_events_and_parsed_schedules_but_never_cancellations(fixture_ledger):
    upcoming = builder.build(today=TODAY, ledger_dir=fixture_ledger)["upcoming_effective"]
    assert [(r["ticker"], r["ex_date"], r["basis"]) for r in upcoming] == [("CCC", "2026-10-15", "announcement"), ("AAA", "2026-10-20", "event")]
    event = upcoming[1]
    assert event["ratio"] == 0.05 and event["split_from"] == 20.0 and event["cohort"] == "second"
    assert event["url"] == "https://www.sec.gov/Archives/edgar/data/1/000100000026000001/"
    assert all(r["ticker"] != "DDD" for r in upcoming)


def test_upcoming_never_lists_a_mention(fixture_ledger):
    _append_announcements(fixture_ledger, [
        _announcement("CELU", "0000000055", "2026-10-02", announced_ex_date="2026-12-20", outcome="mention"),
        _announcement("HAIN", "0000000056", "2026-10-03", announced_ex_date="2026-11-01"),
    ])
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    tickers = [r["ticker"] for r in doc["upcoming_effective"]]
    assert "CELU" not in tickers and "HAIN" in tickers
    assert doc["counts"]["upcoming_effective"] == len(tickers) == 3


def test_repeat_splitters_group_by_issuer(fixture_ledger):
    repeat = builder.build(today=TODAY, ledger_dir=fixture_ledger)["repeat_splitters"]
    assert len(repeat) == 1
    assert repeat[0]["ticker"] == "AAA" and repeat[0]["prior_rs_count"] == 1
    assert repeat[0]["last_ex_date"] == "2026-10-20" and repeat[0]["cohort"] == "second"
    assert repeat[0]["duplicates_merged"] == 0 and repeat[0]["cik_source"] == "event" and repeat[0]["ratio_flag"] is None


def _event(ticker, cik, ex_date, ratio, **extra):
    return {
        "ticker": ticker, "cik": cik, "company": f"{ticker} Corp", "exchange": "Nasdaq", "exchange_class": "listed",
        "split_from": round(1 / ratio, 6), "split_to": 1.0, "ratio": ratio, "first_proxy_date": None, "announce_date": None,
        "vote_date": None, "ratio_set_date": None, "effective_date": ex_date, "ex_date": ex_date, "prior_rs_count": 0,
        "cohort": "first", "status": "seeded", "confidence": 0.5, "needs_review": 0, "source": "yfinance", "outcome": "effective",
        "vote_path": None, "accept_time": None, "announced_ex_date": None, "announced_ratio": None, "jump_status": None,
        "jump_observed": None, "date_quality": "filing_text", "accession": None, "form": None,
        "created_at": "2026-10-09 03:14:38", "updated_at": "2026-10-09 04:04:43", **extra,
    }


def test_the_same_split_recorded_twice_counts_once(fixture_ledger):
    _append_events(fixture_ledger, [
        # ALM: one consolidation on adjacent days, tagged first then "second" by the ledger.
        _event("ALM", "0000000101", "2025-07-07", 0.6667),
        _event("ALM", "0000000101", "2025-07-08", 0.6667, prior_rs_count=1, cohort="second"),
        # VJET/VTAK: one CIK, two tickers, same day, plus a real earlier split.
        _event("VTAK", "0000000102", "2024-07-15", 0.125, source="databento_price_jump", date_quality=None),
        _event("VJET", "0000000102", "2026-10-05", 0.1, prior_rs_count=1, cohort="second"),
        _event("VTAK", "0000000102", "2026-10-05", 0.1, prior_rs_count=2, cohort="third_plus"),
        # BNRG/BRNX: the EDGAR row wins over the yfinance twin three days later and keeps its listing.
        _event("BRNX", "0000000103", "2023-12-04", 0.1),
        _event("BNRG", "0000000103", "2025-06-17", 0.2, source="edgar_search", exchange_class="unknown", prior_rs_count=1, cohort="second"),
        _event("BRNX", "0000000103", "2025-06-20", 0.2, prior_rs_count=2, cohort="third_plus"),
        # Two real splits ten days apart but at different ratios stay two.
        _event("TWO", "0000000104", "2025-01-02", 0.1),
        _event("TWO", "0000000104", "2025-01-10", 0.02, prior_rs_count=1, cohort="second", announced_ratio=0.5),
    ])
    _append_announcements(fixture_ledger, [_announcement("VJET", "0000000102", "2026-09-25")])
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    counts = doc["counts"]
    assert counts["events"] == 13 and counts["duplicate_event_rows"] == 3 and counts["events_distinct"] == 10
    by_cik = {r["cik"]: r for r in doc["repeat_splitters"]}
    assert "0000000101" not in by_cik, "ALM split once; a duplicate row is not a repeat"
    vjet = by_cik["0000000102"]
    assert vjet["ticker"] == "VJET" and vjet["prior_rs_count"] == 1 and vjet["cohort"] == "second" and vjet["duplicates_merged"] == 1
    bnrg = by_cik["0000000103"]
    assert bnrg["ticker"] == "BNRG" and bnrg["last_ex_date"] == "2025-06-17" and bnrg["prior_rs_count"] == 1
    assert bnrg["last_source"] == "edgar_search" and bnrg["exchange_class"] == "listed"
    two = by_cik["0000000104"]
    assert two["prior_rs_count"] == 1 and two["duplicates_merged"] == 0 and two["ratio_flag"] == "disagrees_with_announced"
    # AAA, VJET, BNRG and TWO: four issuers with a second distinct split.
    assert counts["repeat_issuers"] == 4


def test_distinct_events_prefers_filing_text_then_edgar_then_the_current_ticker():
    rows = [
        _event("OLD", "0000000200", "2026-01-05", 0.1),
        _event("NEW", "0000000200", "2026-01-05", 0.1),
        _event("PRC", "0000000200", "2026-01-06", 0.105, source="databento_price_jump", date_quality=None),
    ]
    kept, merged = builder.distinct_events(rows, {"cik:200": "NEW"})
    assert merged == 2 and len(kept) == 1 and kept[0]["ticker"] == "NEW"
    assert {m["ticker"] for m in kept[0]["merged"]} == {"OLD", "PRC"}
    kept, _ = builder.distinct_events(rows[:1] + [_event("EDG", "0000000200", "2026-01-09", 0.1, source="edgar_search")], {})
    assert kept[0]["ticker"] == "EDG"
    kept, merged = builder.distinct_events([_event("X", None, "2026-01-05", 0.1), _event("X", None, "2026-01-20", 0.1)], {})
    assert merged == 0 and len(kept) == 2, "eleven or more days apart is a second split"


def test_repeat_splitter_without_a_cik_is_matched_by_a_unique_ticker(fixture_ledger):
    _append_events(fixture_ledger, [
        _event("CYCN", None, "2023-05-16", 0.05, company=None),
        _event("CYCN", None, "2026-09-09", 0.0005, prior_rs_count=1, cohort="second", company=None),
    ])
    _append_announcements(fixture_ledger, [_announcement("CYCN", "0001755237", "2026-08-01", company="Korsana Biosciences, Inc.")])
    repeat = builder.build(today=TODAY, ledger_dir=fixture_ledger)["repeat_splitters"]
    cycn = next(r for r in repeat if r["ticker"] == "CYCN")
    assert cycn["cik"] == "0001755237" and cycn["cik_source"] == "announcement_ticker"
    assert cycn["company"] == "Korsana Biosciences, Inc."
    assert cycn["ratio_flag"] == "extreme"
    assert cycn["url"] == "https://www.sec.gov/edgar/browse/?CIK=1755237&owner=exclude"


def test_coverage_flags_a_class_that_is_mostly_a_to_d():
    listed = [_event(f"{letter}{i}", None, "2025-01-02", 0.1) for i, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")]
    otc = [_event(f"{'ABCD'[i % 4]}O{i}", None, "2025-01-02", 0.1, exchange_class="otc") for i in range(24)]
    otc.append(_event("ZOTC", None, "2025-01-02", 0.1, exchange_class="otc"))
    cover = builder.coverage(listed + otc)
    assert cover["skewed_classes"] == ["otc"] and cover["a_to_d_share"]["otc"] == 0.96
    assert cover["a_to_d_share"]["listed"] == round(4 / 26, 3) and cover["a_to_d_share"]["unknown"] is None
    assert cover["note"].startswith("OTC events are mostly tickers starting A-D") and "yfinance seed" in cover["note"]
    small = builder.coverage(otc[:5])
    assert small["skewed_classes"] == [] and small["note"] is None, "fewer than 20 events is too few to call"


def test_book_process_and_decisions_sections(fixture_ledger):
    doc = builder.build(today=TODAY, ledger_dir=fixture_ledger)
    book = doc["book"]
    assert book["latest_run"]["label"] == "fundamental_60" and book["latest_run"]["taken"] == 4
    assert book["latest_run"]["net_pnl"] == 140.72
    assert [r["label"] for r in book["latest_batch"]] == ["assumed_100_h5_effective", "fundamental_60"]
    assert book["latest_batch"][0]["net_pnl"] == -14286.0 and book["latest_batch"][0]["losses_over_50pct"] == 7
    assert book["run_count"] == 2 and book["authority"] == "none"
    assert any("locate" in limit.lower() for limit in book["honest_limits"])
    # The tile headlines the predeclared baseline, not the highest id; the superseded scenario says so.
    assert book["baseline_label"] == "assumed_100_h5_effective"
    assert book["headline_run"]["label"] == "assumed_100_h5_effective" and book["headline_run"]["net_pnl"] == -14286.0
    assert book["headline_run"]["baseline"] is True and book["headline_run"]["superseded"] is None
    superseded = {r["label"]: r["superseded"] for r in book["latest_batch"]}
    assert superseded["fundamental_60"] and "audit" in superseded["fundamental_60"] and superseded["assumed_100_h5_effective"] is None
    assert book["latest_run"]["superseded"] == superseded["fundamental_60"]
    assert book["batch_net_range"] == [-14286.0, -14286.0], "superseded and empty scenarios stay out of the range"
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
    assert doc["book"]["latest_run"] is None and doc["book"]["run_count"] == 0 and doc["book"]["headline_run"] is None
    assert doc["counts"]["first_ex_date"] is None and doc["coverage"]["note"] is None and "no completed events" in doc["definition"]
    assert doc["decisions_summary"] == {**doc["decisions_summary"], "count": 0, "latest_at": None}
    assert doc["health"]["status"] == "unhealthy"
    assert any("ledger_manifest.json missing" in p for p in doc["health"]["problems"])


def test_main_writes_the_feed_and_the_feed_is_valid_json(fixture_ledger, tmp_path):
    out = tmp_path / "reverse_splits.json"
    assert builder.main(["--ledger-dir", str(fixture_ledger), "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema_version"] == "reverse_splits.v1" and doc["counts"]["events"] == 3


# ------------------------------------------------------------------ viz
VIZ = ROOT / "dashboard" / "reverse-splits-viz.js"
NODE = shutil.which("node")
RENDER_JS = """
global.window = global;
require(%(viz)s);
const doc = JSON.parse(require('fs').readFileSync(%(doc)s, 'utf8'));
process.stdout.write(JSON.stringify({
  titled: ReverseSplitsViz.render(doc, { maxRecent: 1 }),
  bare: ReverseSplitsViz.render(doc, { hideTitle: true, maxRecent: 1 }),
}));
"""


@pytest.mark.skipif(not (VIZ.exists() and NODE), reason="dashboard JS or node absent")
def test_viz_reads_true_counts_badges_and_can_drop_its_own_title(fixture_ledger, tmp_path):
    _append_announcements(fixture_ledger, [
        _announcement("NXX", "0000000077", "2026-09-01"),
        _announcement("NXXW", "0000000077", "2026-10-05"),
        _announcement("DXS", "0000000099", "2026-10-06", announced_ex_date="2026-05-07", announced_ratio=0.05),
    ])
    doc_path = tmp_path / "doc.json"
    write_json(doc_path, builder.build(today=TODAY, ledger_dir=fixture_ledger))
    script = tmp_path / "render.js"
    script.write_text(RENDER_JS % {"viz": json.dumps(str(VIZ)), "doc": json.dumps(str(doc_path))}, encoding="utf-8")
    out = json.loads(subprocess.run([NODE, str(script)], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
    titled, bare = out["titled"], out["bare"]
    assert "<h2>Reverse splits</h2>" in titled and "<h2>" not in bare
    # The heading counts the 90-day filings and issuers, and the fold says it is part of the capped list.
    assert "(6 filings from 5 issuers in 90 days · showing newest 5, one row per issuer)" in bare
    assert "4 more of the newest 5" in bare and "more in the last 90 days" not in bare
    assert ">Phrase hit<" in bare and "2 filings in 90 days" in bare
    assert '2026-05-07</span> <span class="muted">effective</span>' in bare
    assert "<th>Exchange (current)</th>" in bare
    # Book tile: the baseline, with the superseded scenario badged in the table.
    assert "baseline · assumed_100_h5_effective · 124 trades" in bare and "-$14,286" in bare
    assert ">superseded<" in bare
    assert "NaN" not in bare and "undefined" not in bare


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
