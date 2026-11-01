"""Offline tests for the public 13F book writer. No network."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_managers_json  # noqa: E402
import check_holdings_confidentiality as guard  # noqa: E402
import ingest_13f  # noqa: E402


def test_sec_names_match_ignores_punctuation_and_case():
    assert build_managers_json.names_match("AKRE CAPITAL MANAGEMENT LLC", "Akre Capital Management, LLC")
    assert not build_managers_json.names_match("Baron Capital", "Baron Financial Group LLC")


def test_a_partial_match_needs_the_sec_name_and_a_rare_word():
    assert build_managers_json.plausible_name_ok(
        "Engine Capital", "Engine Capital Management, LP", "Engine Capital Management, LP"
    )
    assert build_managers_json.plausible_name_ok(
        "Polen Capital", "POLEN CAPITAL MANAGEMENT LLC", "POLEN CAPITAL MANAGEMENT LLC"
    )
    assert build_managers_json.plausible_name_ok(
        "Hel Ved Capital", "Hel Ved Capital Management Ltd", "Hel Ved Capital Management Ltd"
    )
    assert build_managers_json.plausible_name_ok(
        "YCM (Yacktman)", "YACKTMAN ASSET MANAGEMENT LP", "YACKTMAN ASSET MANAGEMENT LP"
    )
    assert build_managers_json.plausible_name_ok(
        "Ancora (Bellator/Catalyst/Merlin)", "Ancora Advisors LLC", "Ancora Advisors LLC"
    )
    assert build_managers_json.plausible_name_ok(
        "Fairfax Financial", "FAIRFAX FINANCIAL HOLDINGS LTD/ CAN", "FAIRFAX FINANCIAL HOLDINGS LTD/ CAN"
    )
    assert build_managers_json.plausible_name_ok(
        "Absoluto Partners",
        "Absoluto Partners Gestao de Recursos Ltda",
        "Absoluto Partners Gestao de Recursos Ltda",
    )
    assert not build_managers_json.plausible_name_ok(
        "Armor Capital", "ARMOR ADVISORS, L.L.C.", "ARMOR ADVISORS, L.L.C."
    )
    assert not build_managers_json.plausible_name_ok(
        "HCM (Hidden )", "Hidden Lake Asset Management LP", "Hidden Lake Asset Management LP"
    )
    assert not build_managers_json.plausible_name_ok(
        "Greenlight Capital", "Greenlight Masters, LLC", "Greenlight Masters, LLC"
    )
    assert not build_managers_json.plausible_name_ok(
        "Engine Capital", "Someone Else LP", "Engine Capital Management, LP"
    )


def test_efts_pick_keeps_one_firm_and_drops_a_different_legal_name():
    pershing = {
        "_source": {
            "ciks": ["1336528"],
            "display_names": ["PERSHING SQUARE CAPITAL MANAGEMENT, L.P.  (CIK 0001336528)"],
        }
    }
    picked = build_managers_json.pick_efts_cik("Pershing Square Capital Management", [pershing, pershing])
    assert picked == ("0001336528", "PERSHING SQUARE CAPITAL MANAGEMENT, L.P.")
    masters = {
        "_source": {
            "ciks": ["1449674"],
            "display_names": ["Greenlight Masters, LLC (CIK 0001449674)"],
        }
    }
    assert build_managers_json.pick_efts_cik("Greenlight Capital", [masters]) is None
    other = {
        "_source": {
            "ciks": ["0000000002"],
            "display_names": ["PERSHING SQUARE CAPITAL MANAGEMENT, L.P. (CIK 0000000002)"],
        }
    }
    assert build_managers_json.pick_efts_cik("Pershing Square Capital Management", [pershing, other]) is None


def test_a_notice_does_not_copy_a_different_firm():
    assert ingest_13f.notice_member_shares_name("Robotti & Company Advisors", "ROBERT ROBOTTI")
    assert not ingest_13f.notice_member_shares_name("MIG Capital", "EXCHANGE TRADED CONCEPTS, LLC")
    assert not ingest_13f.notice_member_shares_name("MIG Capital", "")


def test_operational_notes_stay_on_the_review_list():
    managers = [{"cik": "0001425649", "manager_id": "mig-capital"}, {"cik": "0001494311", "manager_id": "greenstone"}]
    review = build_managers_json.attach_operational_review(managers, [])
    reasons = {item["cik"]: item["reason"] for item in review}
    assert reasons["0001425649"] == "latest_own_book_before_2026Q2"
    assert reasons["0001494311"] == "latest_own_book_before_2026Q2"
    assert any("Exchange Traded Concepts" in item["detail"] for item in review)


def test_display_name_drops_a_parenthetical_sleeve():
    assert build_managers_json.public_display_name("Akre Capital Management (Akre Focus Fund)", "AKRE") == "Akre Capital Management"


def test_position_file_keeps_shares_and_context_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_13f, "POSITIONS", tmp_path)
    manager = {"manager_id": "example", "display_name": "Example Capital", "cik": "0000000001"}
    built = {
        "quarter": "2026Q2",
        "period_end": "2026-06-30",
        "filing_date": "2026-08-12",
        "accession": "0000000001-26-000001",
        "source_url": "https://www.sec.gov/example.xml",
        "rows": [
            {
                "cusip": "478160104",
                "issuer": "JOHNSON & JOHNSON",
                "title_of_class": "COM",
                "sh_prn": "SH",
                "put_call": None,
                "shares": 25,
                "value_usd": 5000,
                "discretion": "SOLE",
            }
        ],
    }
    rows = ingest_13f.position_rows(manager, built, {"478160104": "JNJ"}, {"JNJ": "Johnson & Johnson"})
    path = tmp_path / "2026Q2" / "example.csv"
    ingest_13f.write_positions(path, rows)
    loaded = ingest_13f.read_positions(path)
    assert loaded[0]["shares"] == 25
    assert loaded[0]["ssi_ticker"] == "JNJ"
    assert loaded[0]["in_base_irr"] == "False"
    assert loaded[0]["quarter"] == "2026Q2"


def test_a_first_book_is_not_marked_all_new(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_13f, "POSITIONS", tmp_path / "positions")
    manager = {"manager_id": "example", "display_name": "Example"}
    rows = [{"cusip": "478160104", "shares": 10, "put_call": None, "sh_prn": "SH", "issuer": "JNJ", "ticker": "JNJ", "ssi_ticker": "JNJ", "value_usd": 1, "filed_at": "2026-08-12"}]
    assert ingest_13f.diff_book(manager, rows, "2026Q2", "2026-06-30") == []


def test_alerts_skip_old_filings_and_small_moves():
    changes = [
        {"manager_name": "Akre", "ssi_ticker": "JNJ", "change_type": "new", "filed_at": "2026-08-12", "shares_delta_pct": None},
        {"manager_name": "Akre", "ssi_ticker": "XOM", "change_type": "add", "filed_at": "2026-10-16", "shares_delta_pct": 10},
        {"manager_name": "Akre", "ssi_ticker": "CVX", "change_type": "trim", "filed_at": "2026-10-16", "shares_delta_pct": -30},
        {"manager_name": "Akre", "ssi_ticker": "ZZZZ", "change_type": "exit", "filed_at": "2026-10-16", "shares_delta_pct": -100},
    ]
    lines = ingest_13f.alert_lines(changes, {"JNJ", "XOM", "CVX"}, today="2026-10-18", window_days=10)
    assert lines == ["Akre: -30.0% CVX"]


def test_confidentiality_guard_rejects_letter_provenance_and_licensed_names(tmp_path):
    root = tmp_path
    path = root / "_system" / "reference" / "market-data" / "ownership"
    path.mkdir(parents=True)
    (path / "managers.json").write_text(
        json.dumps({"managers": [{"manager_id": "a", "roles": ["letters"], "display_name": "A"}]}) + "\n",
        encoding="utf-8",
    )
    issues = guard.scan(root)
    assert any("letters" in item for item in issues)
    folder = root / "_system" / "reference" / "market-data" / "ownership" / "13f"
    folder.mkdir()
    (folder / "tikr_export.csv").write_text("x", encoding="utf-8")
    assert any("tikr" in item for item in guard.scan(root))


def test_a_plain_manager_keeps_the_ssi_book_and_new_positions():
    universe = {"JNJ"}
    changes = [
        {"ssi_ticker": "JNJ", "ticker": "JNJ", "change_type": "trim", "shares_delta_pct": -4},
        {"ssi_ticker": "", "ticker": "UBER", "change_type": "add", "shares_delta_pct": 20},
        {"ssi_ticker": "", "ticker": "META", "change_type": "new", "shares_delta_pct": None},
        {"ssi_ticker": "", "ticker": "X", "change_type": "exit", "shares_delta_pct": -100},
    ]
    kept = ingest_13f.reported_changes({"roles": ["active"]}, changes, universe, 5)
    assert [row["ticker"] for row in kept] == ["JNJ", "META"]


def test_watchlist_reports_the_whole_book_at_the_threshold():
    universe = {"JNJ"}
    changes = [
        {"ssi_ticker": "JNJ", "ticker": "JNJ", "change_type": "trim", "shares_delta_pct": -4},
        {"ssi_ticker": "", "ticker": "UBER", "change_type": "add", "shares_delta_pct": 5},
        {"ssi_ticker": "", "ticker": "META", "change_type": "new", "shares_delta_pct": None},
        {"ssi_ticker": "", "ticker": "X", "change_type": "exit", "shares_delta_pct": -100},
        {"ssi_ticker": "", "ticker": "Y", "change_type": "trim", "shares_delta_pct": -4.9},
    ]
    kept = ingest_13f.reported_changes({"roles": ["active", "watchlist"]}, changes, universe, 5)
    assert [row["ticker"] for row in kept] == ["UBER", "META", "X"]


def test_watchlist_threshold_defaults_to_five_percent():
    assert ingest_13f.watchlist_threshold_pct({}) == 5
    assert ingest_13f.watchlist_threshold_pct({"watchlist_share_change_pct": 8}) == 8
    assert ingest_13f.watchlist_threshold_pct({"watchlist_share_change_pct": 8}, 3) == 3


def test_a_successor_cik_does_not_replace_quarters_the_old_filer_still_reported():
    """Pershing Square Inc. filed its own small book before the LP's Q2 2026 notice."""
    history = [{"cik": "0001336528", "name": "Pershing Square Capital Management, L.P.", "through": "2026-08-14"}]
    filings = [
        {"cik": "0001336528", "form": "13F-HR", "report_date": "2026-03-31", "filing_date": "2026-05-15", "accession": "old-q1"},
        {"cik": "0001336528", "form": "13F-NT", "report_date": "2026-06-30", "filing_date": "2026-08-14", "accession": "old-q2-notice"},
        {"cik": "0002026053", "form": "13F-HR", "report_date": "2026-03-31", "filing_date": "2026-05-15", "accession": "new-q1"},
        {"cik": "0002026053", "form": "13F-HR", "report_date": "2026-06-30", "filing_date": "2026-08-14", "accession": "new-q2"},
        {"cik": "0002026053", "form": "13F-HR", "report_date": "2026-09-30", "filing_date": "2026-11-14", "accession": "new-q3"},
        {"cik": "0001336528", "form": "13F-HR", "report_date": "2026-09-30", "filing_date": "2026-11-14", "accession": "old-after-through"},
    ]
    kept = ingest_13f.select_successor_filings(filings, "0002026053", history)
    assert [row["accession"] for row in kept] == ["old-q1", "old-q2-notice", "new-q2", "new-q3"]
    from thirteenf_period import periods_for_fund

    groups = periods_for_fund(kept, 4)
    assert [group[-1]["accession"] for group in groups] == ["old-q1", "new-q2", "new-q3"]


def test_workflow_runs_the_registry_ingest():
    text = Path(__file__).resolve().parents[3].joinpath(".github/workflows/data-pipeline.yml").read_text(encoding="utf-8")
    assert 'python _system/scripts/ingest_13f.py --periods "${THIRTEEN_F_PERIODS:-2}" --alerts' in text
    assert '"29 13 * * *") thirteen_f=true; thirteen_f_periods=2' in text
    assert '"29 18 21 2,5,8,11 *") thirteen_f=true; thirteen_f_periods=12' in text
