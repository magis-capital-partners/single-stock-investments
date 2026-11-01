"""Offline 13F parser, amendment, and map tests. No network."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thirteenf_core import (  # noqa: E402
    book_source_for_latest_period,
    other_managers_from_primary,
    aggregate_positions,
    bridge_local_listing,
    classify_change,
    cusip_entries_from_legacy,
    diff_positions,
    discover_dataset_urls,
    group_filings_by_period,
    manager_confidentiality_issues,
    merge_filings,
    normalize_info_rows,
    parse_form_idx,
    parse_info_table_xml,
    parse_primary_doc_xml,
    quarter_from_period,
    reconcile,
    structural_ticker,
    ticker_map,
    value_to_usd,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "13f"


def _xml(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_quarter_uses_period_not_a_may_filing_date():
    assert quarter_from_period("2026-03-31") == "2026Q1"
    assert quarter_from_period("06-30-2026") == "2026Q2"
    assert quarter_from_period("2026-05-13") == "2026Q2"
    # The mislabel was calling this on the filing date. Callers must pass the period.


def test_shares_are_read_from_nested_ssh_prnamt():
    raw = parse_info_table_xml(_xml("info_table_min.xml"))
    rows = normalize_info_rows(raw, filing_date="2026-08-14")
    assert rows[0]["shares"] == 10
    assert rows[0]["value_usd"] == 2000
    assert rows[2]["put_call"] == "PUT"
    assert rows[3]["sh_prn"] == "PRN"
    assert rows[3]["shares"] == 7000


def test_pre_2023_values_are_thousands():
    assert value_to_usd("15", "2022-11-14") == 15000
    assert value_to_usd("15", "2023-01-03") == 15
    assert value_to_usd("1,234", "2026-08-14") == 1234


def test_aggregate_splits_stock_options_and_principal():
    raw = parse_info_table_xml(_xml("info_table_min.xml"))
    rows = aggregate_positions(normalize_info_rows(raw, filing_date="2026-08-14"))
    by_key = {(row["cusip"], row["put_call"], row["sh_prn"]): row for row in rows}
    stock = by_key[("478160104", None, "SH")]
    assert stock["shares"] == 25
    assert stock["value_usd"] == 5000
    assert by_key[("478160104", "PUT", "SH")]["shares"] == 1
    assert by_key[("123456789", None, "PRN")]["shares"] == 7000
    assert len(rows) == 3


def test_primary_period_and_reconciliation():
    primary = parse_primary_doc_xml(_xml("primary_hr.xml"))
    assert primary["period_end"] == "2026-06-30"
    assert primary["quarter"] == "2026Q2"
    assert primary["confidential_omitted"] is False
    assert primary["table_entry_total"] == 4
    raw = parse_info_table_xml(_xml("info_table_min.xml"))
    rows = aggregate_positions(normalize_info_rows(raw, filing_date="2026-08-14"))
    report = reconcile(len(raw), rows, primary)
    assert report["rows_match"] is True
    assert report["value_match"] is True
    assert report["ok"] is True


def test_new_holdings_amendment_does_not_replace_the_book():
    original = aggregate_positions(
        normalize_info_rows(parse_info_table_xml(_xml("info_table_min.xml")), filing_date="2026-08-14")
    )
    added = aggregate_positions(
        normalize_info_rows(parse_info_table_xml(_xml("info_table_one.xml")), filing_date="2026-08-20")
    )
    merged = merge_filings(
        [
            {"form": "13F-HR", "rows": original, "amendment_type": None},
            {"form": "13F-HR/A", "rows": added, "amendment_type": "NEW HOLDINGS"},
            {"form": "13F-NT", "rows": [{"cusip": "000000000", "shares": 1, "value_usd": 1, "sh_prn": "SH", "put_call": None}]},
        ]
    )
    cusips = {row["cusip"] for row in merged}
    assert "478160104" in cusips
    assert "999999999" in cusips
    assert "000000000" not in cusips


def test_restatement_replaces_the_book():
    original = aggregate_positions(
        normalize_info_rows(parse_info_table_xml(_xml("info_table_min.xml")), filing_date="2026-08-14")
    )
    replacement = aggregate_positions(
        normalize_info_rows(parse_info_table_xml(_xml("info_table_one.xml")), filing_date="2026-08-20")
    )
    merged = merge_filings(
        [
            {"form": "13F-HR", "rows": original},
            {"form": "13F-HR/A", "rows": replacement, "amendment_type": "RESTATEMENT"},
        ]
    )
    assert {row["cusip"] for row in merged} == {"999999999"}


def test_notice_names_the_managers_who_file_the_book():
    managers = other_managers_from_primary(_xml("primary_notice.xml"))
    assert [row["cik"] for row in managers] == ["0000933478", "0000093478"]
    assert managers[0]["name"] == "Example Fiduciary"
    assert managers[0]["file_number"] == "028-11554"


def test_a_later_notice_is_not_filled_by_an_older_holdings_filing():
    filings = [
        {"form": "13F-NT", "report_date": "2026-06-30", "filing_date": "2026-08-13", "accession": "nt"},
        {"form": "13F-HR", "report_date": "2025-12-31", "filing_date": "2026-01-29", "accession": "old"},
    ]
    decision = book_source_for_latest_period(filings)
    assert decision["mode"] == "notice"
    assert decision["period"] == "2026-06-30"
    assert decision["notice"]["accession"] == "nt"
    assert decision["filings"] == []


def test_a_holdings_filing_for_the_latest_period_is_the_book():
    filings = [
        {"form": "13F-HR", "report_date": "2026-06-30", "filing_date": "2026-08-07", "accession": "hr"},
        {"form": "13F-NT", "report_date": "2026-06-30", "filing_date": "2026-08-01", "accession": "nt"},
    ]
    decision = book_source_for_latest_period(filings)
    assert decision["mode"] == "direct"
    assert [row["accession"] for row in decision["filings"]] == ["hr"]


def test_notice_and_confidential_cover_pages():
    notice = parse_primary_doc_xml(_xml("primary_notice.xml"))
    assert notice["submission_type"] == "13F-NT"
    assert notice["quarter"] == "2026Q2"
    confidential = parse_primary_doc_xml(_xml("primary_confidential.xml"))
    assert confidential["confidential_omitted"] is True
    assert confidential["quarter"] == "2026Q1"
    report = reconcile(1, [{"value_usd": 10}], confidential)
    assert report["may_be_incomplete"] is True


def test_period_groups_skip_notices_and_keep_amendments_with_the_original():
    filings = [
        {"form": "13F-NT", "report_date": "2026-06-30", "filing_date": "2026-08-14", "accession": "n"},
        {"form": "13F-HR", "report_date": "2026-03-31", "filing_date": "2026-05-13", "accession": "a"},
        {"form": "13F-HR", "report_date": "2026-06-30", "filing_date": "2026-08-12", "accession": "b"},
        {"form": "13F-HR/A", "report_date": "2026-06-30", "filing_date": "2026-08-20", "accession": "c"},
        {"form": "13F-HR", "report_date": "2025-12-31", "filing_date": "2026-02-14", "accession": "d"},
    ]
    groups = group_filings_by_period(filings, periods=2)
    assert [row[0]["report_date"] for row in groups] == ["2026-03-31", "2026-06-30"]
    assert [row["accession"] for row in groups[1]] == ["b", "c"]


def test_change_classification_and_diff():
    assert classify_change(10, None) == "new"
    assert classify_change(0, 5) == "exit"
    assert classify_change(100, 100) == "unchanged"
    assert classify_change(110, 100) == "add"
    assert classify_change(90, 100) == "trim"
    changes = diff_positions(
        [{"cusip": "478160104", "shares": 10, "value_usd": 20, "sh_prn": "SH", "put_call": None, "issuer": "JNJ"}],
        [{"cusip": "478160104", "shares": 25, "value_usd": 50, "sh_prn": "SH", "put_call": None, "issuer": "JNJ"},
         {"cusip": "111111111", "shares": 3, "value_usd": 3, "sh_prn": "SH", "put_call": None, "issuer": "GONE"}],
        manager_id="example",
        period="2026Q2",
        prior_period="2026Q1",
    )
    by_cusip = {row["cusip"]: row["change_type"] for row in changes}
    assert by_cusip["478160104"] == "trim"
    assert by_cusip["111111111"] == "exit"


def test_cusip_map_quarantines_structural_tickers_and_corrects_jnj():
    entries = cusip_entries_from_legacy(
        {"478160104": "ABMD.CVR", "110122108": "MRTX.CVR", "007903107": "AMD"}
    )
    assert entries["mappings"]["478160104"]["ticker"] == "JNJ"
    assert entries["mappings"]["478160104"]["source"] == "reviewed"
    assert "110122108" in entries["quarantine"]
    assert "110122108" not in ticker_map(entries["mappings"])
    assert ticker_map(entries["mappings"])["007903107"] == "AMD"
    assert structural_ticker("ABMD.CVR") is True
    assert structural_ticker("AMD") is False


def test_name_bridge_does_not_invent_a_cusip_writeback():
    names = {"8697.T": "Japan Exchange Group", "JNJ": "Johnson & Johnson"}
    assert bridge_local_listing("Japan Exchange Group ADR", None, names) == "8697.T"
    assert bridge_local_listing("Johnson & Johnson", "JNJ", names) == "JNJ"


def test_dataset_urls_come_from_the_listing_page():
    html = """
    <a href="/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip">a</a>
    <a href="/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip">b</a>
    """
    urls = discover_dataset_urls(html)
    assert urls[0].endswith("01jun2026-31aug2026_form13f.zip")
    assert urls[1].startswith("https://www.sec.gov/files/")


def test_form_index_parser_keeps_13f_rows():
    rows = parse_form_idx((FIX / "form_index_snippet.idx").read_text(encoding="utf-8"))
    assert [row["form"] for row in rows] == ["13F-HR", "13F-NT"]
    assert rows[0]["cik"] == "0001720792"


def test_manager_registry_rejects_letter_provenance_and_licensed_names():
    clean = {"managers": [{"manager_id": "akre", "display_name": "Akre Capital Management", "ciks": [{"cik": "0001112520"}], "roles": ["active"]}]}
    assert manager_confidentiality_issues(clean) == []
    dirty = {"managers": [{"manager_id": "akre", "roles": ["letters"], "email": "hidden"}]}
    issues = manager_confidentiality_issues(dirty)
    assert any("letters" in issue for issue in issues)
    assert any("email" in issue for issue in issues)


def test_amendment_cover_types():
    new = parse_primary_doc_xml(_xml("primary_new_holdings.xml"))
    assert new["amendment_type"] == "NEW HOLDINGS"
    assert new["is_amendment"] is True
    restated = parse_primary_doc_xml(_xml("primary_restatement.xml"))
    assert restated["amendment_type"] == "RESTATEMENT"


def test_data_pipeline_schedules_the_13f_check():
    workflow = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "data-pipeline.yml"
    text = workflow.read_text(encoding="utf-8")
    assert 'cron: "29 13 * * *"' in text
    assert '"29 13 * * *") thirteen_f=true' in text
    assert "name: Check 13F filings" in text
    lane = Path(__file__).resolve().parents[3] / "_system" / "graph" / "graph_sources.json"
    assert "data-pipeline-thirteen-f" in lane.read_text(encoding="utf-8")


def test_fixture_files_are_json_safe_examples():
    # Guards the fixture directory against accidentally dropping a licensed export in.
    for path in FIX.iterdir():
        assert "tikr" not in path.name.lower()
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
