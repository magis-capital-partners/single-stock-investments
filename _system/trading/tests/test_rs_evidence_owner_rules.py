"""Owner rules of 2026-11-19 for the evidence producers. No socket is opened.

* Keep entries blocked where evidence is missing; name the exact field.
* Public borrow indications are not allocations; a WhatIf proves no borrow.
* Synthetic controls, catch-up announcements and duplicate publisher records
  are never opportunities.
"""

import json
from pathlib import Path

from _system.trading.rs_evidence import reviews as reviews_mod
from _system.trading.rs_evidence.__main__ import _status
from _system.trading.rs_evidence.gaps import entry_gaps
from _system.trading.rs_evidence.identity import build_identities, duplicate_records
from _system.trading.rs_evidence.reviews import Reviews
from _system.trading.rs_evidence.runner import Producers, load_config
from _system.trading.tests.test_rs_evidence_producers import (  # noqa: F401 (fixture)
    NOW,
    candidate,
    fake_fetchers,
    no_network,
    refs,
    review_row,
    status_bytes,
    write_config,
)

# ---- catch-up and date-only clocks --------------------------------------


def test_only_a_timestamped_first_record_can_verify():
    for clock, refusal in (("date_only_next_day", "publication_clock_date_only_next_day"),
                           ("unverified_archive", "publication_clock_unverified_archive"),
                           ("unknown", "publication_clock_unknown"),
                           (None, "publication_clock_missing"),
                           ("<script>", "publication_clock_missing")):
        rows, _ = build_identities({"candidates": [candidate(publication_clock=clock)]}, refs(),
                                   Reviews([review_row()]), NOW, terms_mode="owner_review")
        row = rows["TEST"]
        assert row["verified"] is False and refusal in row["refusals"], clock
        assert row["conditions_resolved"] is False
    rows, _ = build_identities({"candidates": [candidate()]}, refs(), Reviews([review_row()]),
                               NOW, terms_mode="owner_review")
    assert rows["TEST"]["verified"] is True and rows["TEST"]["publication_clock"] == "timestamp"


# ---- duplicate publisher records ----------------------------------------


def _pair(**later):
    first = candidate()
    second = candidate(id="prn:two", first_seen_at="2026-11-18T14:59:40Z",
                       published_at="2026-11-18T14:59:30Z",
                       source_urls=[{"url": "https://www.prnewswire.com/x", "sha256": "b" * 64}],
                       **later)
    return first, second


def test_a_later_record_of_the_same_action_gets_no_row():
    first, second = _pair()
    rows, report = build_identities({"candidates": [second, first]}, refs(),
                                    Reviews([review_row()]), NOW, terms_mode="owner_review")
    assert rows["TEST"]["action_id"] == "sec:one" and rows["TEST"]["verified"] is True
    (skip,) = [r for r in report if r.get("skipped") == "duplicate_publisher_record"]
    assert skip == {"ticker": "TEST", "skipped": "duplicate_publisher_record",
                    "candidate_id": "prn:two", "duplicate_of": "sec:one", "basis": "same_action_day"}


def test_a_duplicate_cannot_reopen_a_window_the_first_record_used():
    # The first record is older than the 1 h lookback: the duplicate still gets no row.
    first, second = _pair()
    first["first_seen_at"] = "2026-11-18T12:00:00Z"
    rows, report = build_identities({"candidates": [first, second]}, refs(), None, NOW,
                                    terms_mode="owner_review")
    assert rows == {} and report[0]["duplicate_of"] == "sec:one"


def test_a_new_action_day_is_a_new_action_and_unknown_days_are_conservative():
    first, second = _pair(effective_date="2027-02-01", legal_effective_date=None,
                          trading_date="2027-02-01")
    assert duplicate_records([first, second]) == {}
    first, second = _pair(effective_date=None, legal_effective_date=None, trading_date=None)
    assert duplicate_records([first, second]) == {"prn:two": ("sec:one", "action_day_unknown")}
    # Other issuers, unscheduled records and synthetic controls are never compared.
    assert duplicate_records([candidate(), candidate(id="z", cik="999")]) == {}
    assert duplicate_records([candidate(status="authorization"), candidate(id="z")]) == {}


def test_synthetic_controls_never_get_an_identity():
    for control in (candidate(id="synthetic-control:abc"), candidate(synthetic_control=True)):
        rows, report = build_identities({"candidates": [control]}, refs(),
                                        Reviews([review_row(candidate_id=control["id"])]), NOW,
                                        terms_mode="owner_review")
        assert rows == {} and report == [{"ticker": "TEST", "skipped": "synthetic_control"}]


# ---- exact missing fields -----------------------------------------------


def _evidence(tmp_path, *, review=True, status=None):
    config = load_config(write_config(tmp_path))
    if status is not None:
        Path(config["eligibility"]["market_status_file"]).write_bytes(status)
    if review:
        reviews_mod.append(config["reviews"], review_row())
    Producers(config, fake_fetchers(), in_session=lambda now: True).step(NOW)
    return config, json.loads(Path(config["evidence"]).read_text())


def test_gaps_name_every_missing_field_today(tmp_path):
    # Today's state: no review yet, no SSR or halt clearance source.
    _, evidence = _evidence(tmp_path, review=False)
    gaps = entry_gaps(evidence, NOW)
    test = gaps["names"]["TEST"]
    assert "identity.owner_review_required" in test["blocked_by"]
    assert {"identity.ratio", "identity.conditions_resolved"} <= set(test["blocked_by"])
    assert "eligibility.intraday_ssr_clearance_source_absent" in test["blocked_by"]
    assert not any(g.startswith("borrow.") for g in test["blocked_by"])  # borrow row present
    assert test["borrow_is_indication_not_allocation"] is True
    assert "whatif_margin" in test["not_checked_here"]
    assert gaps["unblocked_by_evidence"] == []


def test_gaps_clear_only_when_every_section_is_present_and_fresh(tmp_path):
    _, evidence = _evidence(tmp_path, status=status_bytes({"TEST": {"halted": False, "ssr": False}}))
    gaps = entry_gaps(evidence, NOW)
    assert gaps["names"]["TEST"]["blocked_by"] == [] and gaps["unblocked_by_evidence"] == ["TEST"]
    # 31 s later the eligibility row is stale; past 30 min the borrow row is too.
    assert "eligibility.stale_or_missing_at" in entry_gaps(
        evidence, "2026-11-18T15:00:31+00:00")["names"]["TEST"]["blocked_by"]
    later = entry_gaps(evidence, "2026-11-18T15:30:00+00:00")["names"]["TEST"]["blocked_by"]
    assert "borrow.stale_or_missing_at" in later
    del evidence["borrow"]["1001"]
    assert "borrow.row_absent" in entry_gaps(evidence, NOW)["names"]["TEST"]["blocked_by"]


def test_status_carries_the_gap_report(tmp_path):
    config, _ = _evidence(tmp_path, review=False)
    out = _status(config, NOW)
    assert "eligibility.intraday_ssr_clearance_source_absent" in out["entry_gaps"]["blocking_fields"]


def test_borrow_rows_never_claim_an_allocation(tmp_path):
    _, evidence = _evidence(tmp_path)
    for row in evidence["borrow"].values():
        assert row["availability_only"] is True and row["locate_approved"] is False
