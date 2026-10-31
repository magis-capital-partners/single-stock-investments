"""Public archive, identity, provenance and historical selection contracts."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discover_public_funds as public_funds
import global_disclosures as disclosures
import investor_history as archive
import investor_history_checkpoint as checkpoint
import investor_universe as universe
import ownership_common as ownership
import stage_investor_history as staging
from thirteenf_core import merge_filings
from thirteenf_legacy import parse_legacy_document


def test_historical_filer_alias_keeps_the_current_manager_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "ARCHIVE", tmp_path / "archive")
    registry = tmp_path / "managers.json"
    registry.write_text(json.dumps({"managers": [{
        "manager_id": "pershing-square",
        "display_name": "Pershing Square Capital Management",
        "sec_name": "PERSHING SQUARE INC.",
        "cik": "0002026053",
        "cik_history": [{"cik": "0001336528"}],
        "roles": ["active"],
        "book": "full",
    }]}), encoding="utf-8")
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps({"managers": [{
        "firm": "Pershing Square Capital Management", "name": "Bill Ackman",
    }]}), encoding="utf-8")
    corpus = tmp_path / "insights.json"
    corpus.write_text(json.dumps({"letters": [{
        "fund_id": "pershing", "fund": "Pershing Square Capital Management",
        "letter_eligible": True, "document_type": "investor_letter",
    }]}), encoding="utf-8")
    result = universe.compile_universe(
        registry_path=registry, roster_path=roster, corpus_path=corpus,
        aliases_path=tmp_path / "aliases.json",
        catalog={"PERSHING SQUARE CAPITAL MANAGEMENT, L.P.": {"0001336528"}},
    )
    published = json.loads(registry.read_text())["managers"]
    assert len(published) == len(result["managers"]) == 1
    assert published[0]["cik"] == "0002026053"
    assert archive.cik_map(published) == {
        "1336528": "pershing-square", "2026053": "pershing-square",
    }
    assert result["source_ids"]["pershing"] == "pershing-square"


def test_archived_publishers_survive_corpus_rotation_without_reviving_rejected_ciks():
    from refresh_investor_history import retain_archived_identities

    current = {
        "managers": [{"manager_id": "new", "cik": "1"}],
        "source_ids": {"renamed": "new"},
    }
    previous = {
        "managers": [
            {"manager_id": "old", "cik": None},
            {"manager_id": "rejected", "cik": "2"},
        ],
        "source_ids": {"historic": "old", "renamed": "old", "bad": "rejected"},
    }
    result = retain_archived_identities(current, previous)
    assert {m["manager_id"] for m in result["managers"]} == {"old", "new"}
    assert result["source_ids"] == {"historic": "old", "renamed": "new"}


def test_retained_letter_identity_follows_an_explicit_source_correction():
    from refresh_investor_history import current_disclosure_identity

    universe = {"source_ids": {"fund": "correct"}}
    old = {"manager_id": "old", "vehicle_id": "fund", "source_kind": "fund_disclosure"}
    assert current_disclosure_identity(old, universe)["manager_id"] == "correct"
    nport = {**old, "source_kind": "nport"}
    assert current_disclosure_identity(nport, universe)["manager_id"] == "old"


def test_unchanged_originals_and_books_do_not_rewrite_archive_pages(tmp_path):
    db = archive.connect(tmp_path / "a.sqlite")
    meta = {"accession": "a", "manager_id": "example", "cik": "1", "form": "13F-HR"}
    rows = [{"cusip": "037833100", "value_usd": 100, "shares": 1}]
    archive.store_filing(db, meta, rows)
    archive.store_raw_documents(db, "a", {"raw_info_bytes": b"immutable original"})
    changes = db.total_changes
    archive.store_filing(db, dict(meta), list(rows))
    archive.store_raw_documents(db, "a", {"raw_info_bytes": b"immutable original"})
    assert db.total_changes == changes
    archive.store_filing(db, meta, [{**rows[0], "shares": 2}])
    assert archive.filing_rows(db, "a")[0]["shares"] == 2
    assert db.total_changes > changes


def test_zero_asset_registered_fund_report_is_explicitly_empty():
    result = disclosures.parse_nport(
        b"""<nport><genInfo>
    <repPdDate>2021-06-30</repPdDate><seriesId>S1</seriesId><seriesName>Unfunded Fund</seriesName>
    </genInfo><fundInfo><totAssets>0.0000</totAssets><netAssets>0.0000</netAssets></fundInfo></nport>""",
        "example",
        source_url="https://www.sec.gov/example.xml",
    )
    assert result["positions"] == []
    assert not result["partial"]


def test_foreign_currency_attributes_upgrade_from_preserved_xml_without_http(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(disclosures, "ARCHIVE", tmp_path)
    raw = b"""<nport><genInfo><repPdDate>2021-06-30</repPdDate><seriesId>S1</seriesId><seriesName>Global Fund</seriesName></genInfo><invstOrSecs><invstOrSec><name>Foreign Company</name><balance>1000</balance><currencyConditional curCd="HKD" exchangeRt="7.8"/><valUSD>5000</valUSD><pctVal>3</pctVal></invstOrSec></invstOrSecs></nport>"""
    source = tmp_path / "source.xml"
    source.write_bytes(raw)
    url = "https://www.sec.gov/example.xml"
    disclosures.public_document(url, source)
    snapshot = disclosures.parse_nport(raw, "example", source_url=url)
    assert snapshot["positions"][0]["currency"] == "HKD"
    snapshot.pop("parser_version")
    snapshot["positions"][0]["currency"] = ""
    monkeypatch.setattr(
        disclosures,
        "get_bytes",
        lambda *_: pytest.fail("Upgrades must use the pinned originals"),
    )
    disclosures.upgrade_nport_snapshots([snapshot], tmp_path / "public-cache.sqlite")
    assert snapshot["positions"][0]["currency"] == "HKD"
    assert snapshot["parser_version"] == disclosures.NPORT_PARSER_VERSION
    snapshot.pop("parser_version")
    snapshot["vehicle_id"] = "different-fund"
    with pytest.raises(ValueError, match="identity mismatch"):
        disclosures.upgrade_nport_snapshots(
            [snapshot], tmp_path / "public-cache.sqlite"
        )


def test_letter_allocations_and_financial_abbreviations_are_not_stock_holdings():
    rows = disclosures.extract_document_positions("""Top 10 holdings
    United States 47%
    United Kingdom 22%
    Countries(a) 13%
    Liabilities (Net)(b) 5%
    Information Technology 4%
    Foreign Company PLC 3%
    We hold an investment whose net asset value (NAV) increased.
    """)
    assert len(rows) == 1
    assert rows[0]["issuer"] == "Foreign Company PLC"
    assert rows[0]["weight_pct"] == 3


def test_public_boundary_checks_fields_without_treating_fund_names_as_field_names():
    from check_holdings_confidentiality import _json_issues

    path = Path("directory_index.json")
    assert not _json_issues(path, {"manager_id": "letter"})
    assert _json_issues(path, {"nested": {"letter_source": "private"}})


def test_missing_required_letters_cannot_publish_a_reduced_universe(
    tmp_path, monkeypatch
):
    import refresh_investor_history as refresh

    def unexpected_network():
        raise AssertionError("Required inputs must be checked before any refresh")

    monkeypatch.setattr(refresh.investor_universe, "fetch_roster", unexpected_network)
    with pytest.raises(
        FileNotFoundError, match="retain the previous complete snapshot"
    ):
        refresh.refresh(corpus=tmp_path / "missing.json")


def test_letter_holdings_table_has_no_arbitrary_row_limit():
    text = "Top 70 holdings\n" + "\n".join(f"Issuer {i} PLC 1%" for i in range(70))
    assert len(disclosures.extract_document_positions(text)) == 70


def test_sec_client_retries_a_temporary_internal_server_error(monkeypatch):
    from urllib.error import HTTPError

    import sec_client

    attempts = []

    def response(request, **kwargs):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise HTTPError(request.full_url, 500, "Temporary failure", {}, None)
        return io.BytesIO(b"complete public document")

    monkeypatch.setattr(sec_client.urllib.request, "urlopen", response)
    monkeypatch.setattr(sec_client.time, "sleep", lambda _: None)
    client = sec_client.SecClient(min_interval=0, max_attempts=2)
    assert (
        client.get_bytes("https://www.sec.gov/example.xml")
        == b"complete public document"
    )
    assert len(attempts) == 2


def test_legacy_preserves_classes_options_and_principal_amounts():
    raw = b"""CONFORMED PERIOD OF REPORT: 20001231
Form 13F Information Table Entry Total: 3
Form 13F Information Table Value Total: 150
<TABLE>
ALPHABET INC  CL A  02079K305  100  20 SH SOLE 20 0 0
ALPHABET INC  CL C  02079K107  40  10 SH CALL SOLE 10 0 0
EXAMPLE BOND  NOTE  123456789  10  1000 PRN SOLE 1000 0 0
</TABLE>"""
    rows, primary = parse_legacy_document(raw)
    assert primary["period_end"] == "2000-12-31"
    assert primary["table_entry_total"] == 3
    assert sum(r["value_usd"] for r in rows) == 150_000
    assert rows[1]["put_call"] == "CALL"
    assert rows[2]["sh_prn"] == "PRN"
    assert rows[0]["cusip"] != rows[1]["cusip"]


def test_legacy_unreadable_table_is_not_an_empty_portfolio():
    with pytest.raises(ValueError, match="requires review"):
        parse_legacy_document(b"<TABLE>unrecognized format</TABLE>")


def test_legacy_typed_identifier_wins_over_numeric_class_annotations():
    rows, _ = parse_legacy_document(b"""Table Entry Total: 3
    <TABLE>NAME  CLASS  CUSIP  VALUE  SHARES
    D FALCONBRIDGE LTD  NEW2005  306104100  5076  144815 SH DEFINED
    D LIBERTY MEDIA CORP SEE 53071MCOM  530718105  48245  5876395 SH DEFINED
    GABLES RESIDENTIAL TR  SH BN IN  362418105  18429  622600SHX 546350 0 76250
    S REPORT SUMMARY 3 DATA RECORDS 71750 0 OTHER MANAGERS
    </TABLE>""")
    assert [r["cusip"] for r in rows] == ["306104100", "530718105", "362418105"]
    assert [r["shares"] for r in rows] == [144815, 5876395, 622600]


def test_legacy_fixed_width_fields_recover_adjacent_large_amounts():
    rows, _ = parse_legacy_document(b"""Table Entry Total: 2
    <TABLE>NAME OF ISSUER TITLE OF CLASS CUSIP VALUE SHARES
<S>                      <C>            <C>       <C>      <C>      <C> <C>  <C>     <C>    <C>    <C>    <C>
BANK OF AMERICA CORP         COMMON     060505104   1805519137794296 SH      DEFINED   01   137794296
EXXON MOBIL CORP  COM  30231G102  1E+07 182550682 SH SOLE
    </TABLE>""")
    assert rows[0]["shares"] == 137794296
    assert rows[0]["value_usd"] == 1_805_519_000
    assert rows[1]["value_usd"] == 10_000_000_000


def test_legacy_discretion_preserves_as_filed_identifier_without_check_digit_repair():
    rows, _ = parse_legacy_document(b"""Table Entry Total: 1
    <TABLE>NAME  CUSIP  VALUE  SHARES
    MCI Worldcom Inc.  58268B106  8528 96304 Sole Sole
    </TABLE>""")
    assert rows[0]["cusip"] == "58268B106"
    assert rows[0]["shares"] == 96304


@pytest.mark.parametrize("identifier_first", [False, True])
def test_legacy_reordered_columns_follow_reported_header(identifier_first):
    heading = (
        "CUSIP SECURITY DESCRIPTION CLASS SHARES MV(*1000)"
        if identifier_first
        else "SECURITY DESCRIPTION CUSIP CLASS SHARES MV(*1000)"
    )
    line = (
        "000400101  ABC Bancorp  COM  84490 1083 SH Sole"
        if identifier_first
        else "ABC Bancorp  000400101  COM  84490 1083 SH Sole"
    )
    rows, _ = parse_legacy_document(
        f"Table Entry Total: 1\n<TABLE>{heading}\n{line}\n</TABLE>".encode()
    )
    assert rows[0]["issuer"] == "ABC Bancorp"
    assert rows[0]["cusip"] == "000400101"
    assert rows[0]["shares"] == 84490
    assert rows[0]["value_usd"] == 1_083_000


def test_partial_original_rows_remain_available_without_invented_portfolio_weights(
    tmp_path, monkeypatch
):
    db = archive.connect(tmp_path / "archive.sqlite")
    raw = b"""Table Entry Total: 2
    <TABLE>Name of Issuer  Title  CUSIP
    APPLE INC  COM  037833100  100  20 SH SOLE
    UNKNOWN  COM  123456789  99UNKNOWN
    </TABLE>"""
    with pytest.raises(ValueError) as failure:
        parse_legacy_document(raw)
    meta = {
        "accession": "a",
        "manager_id": "example",
        "form": "13F-HR",
        "period_end": "2000-03-31",
        "filed_at": "2000-05-01",
    }
    archive.store_parse_failure(db, meta, failure.value)
    assert archive.filing_rows(db, "a")[0]["cusip"] == "037833100"
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    archive.export(
        db, [{"manager_id": "example", "display_name": "Example"}], tmp_path / "site"
    )
    book = json.loads((tmp_path / "site/history/example/2000.json").read_text())[
        "quarters"
    ]["2000Q1"]
    assert book["partial"] and book["positions"][0]["weight_pct"] is None


def test_preserved_original_can_be_reparsed_without_the_download_cache(tmp_path):
    db = archive.connect(tmp_path / "archive.sqlite")
    raw = b"""CONFORMED PERIOD OF REPORT: 20000331
    Table Entry Total: 1
    <TABLE>CUSIP
    APPLE INC  COM  037833100  100  20 SH SOLE
    </TABLE>"""
    meta = {
        "accession": "a",
        "manager_id": "example",
        "form": "13F-HR",
        "period_end": "2000-03-31",
        "filed_at": "2000-05-01",
        "source_url": "https://www.sec.gov/original.txt",
    }
    archive.store_filing(db, meta, status="error", error="Old parser")
    archive.store_raw_documents(db, "a", {"raw_info_bytes": raw})
    assert archive.reparse_cached(db, tmp_path / "empty-cache") == 1
    assert (
        db.execute("SELECT status FROM filings WHERE accession='a'").fetchone()[0]
        == "loaded"
    )
    assert archive.filing_rows(db, "a")[0]["value_usd"] == 100000


def test_legacy_cover_dates_are_excluded_and_wrapped_spaced_cusip_is_parsed():
    raw = b"""CONFORMED PERIOD OF REPORT: 20010331
CONFIDENTIAL TREATMENT IS NO LONGER WARRANTED OR EXPIRED ON 20020515 1234 5678
Information Table Entry Total: 2
Information Table Value Total: 700617
[X] adds new holdings entries
<TABLE>
NAME OF ISSUER  TITLE OF CLASS  CUSIP  VALUE  SHARES
Costco Wholesale
Corp.              Com    22160K 10 5  664,777   16,937,000  X
Dover Corp.        Com    260003 10 8   35,840    1,000,000  X
</TABLE>"""
    rows, primary = parse_legacy_document(raw)
    assert [row["cusip"] for row in rows] == ["22160K105", "260003108"]
    assert rows[0]["issuer"] == "Costco Wholesale Corp."
    assert primary["amendment_type"] == "NEW HOLDINGS"
    assert primary["table_value_total_usd"] == 700617000


def test_legacy_html_paragraphs_within_cells_stay_in_the_same_row():
    rows, primary = parse_legacy_document(b"""<html><p>Table Entry Total: 1</p>
    <table><tr><td>Name of Issuer</td><td>Title of Class</td><td>CUSIP</td></tr>
    <tr><td><p>APPLE INC</p></td><td><p>COM</p></td><td>037833100</td>
    <td>100</td><td>20</td><td>SH</td></tr></table></html>""")
    assert len(rows) == 1
    assert rows[0]["issuer"] == "APPLE INC"
    assert rows[0]["value_usd"] == 100000
    assert primary["table_entry_total"] == 1


def test_secondary_zero_entry_cover_does_not_erase_the_main_report():
    rows, primary = parse_legacy_document(b"""Table Entry Total: 1
    Confidential Information has been omitted from the public Form 13F
    Other included manager: Table Entry Total: 0
    <TABLE>Name of Issuer  Class  CUSIP
    APPLE INC  COM  037833100  100  20 SH SOLE
    </TABLE>""")
    assert len(rows) == 1 and primary["table_entry_total"] == 1
    assert primary["confidential_omitted"]


def test_new_holdings_amendment_adds_omitted_rows_of_an_existing_cusip():
    rows = merge_filings(
        [
            {
                "form": "13F-HR",
                "rows": [
                    {"cusip": "1", "shares": 10, "value_usd": 100, "sh_prn": "SH"}
                ],
            },
            {
                "form": "13F-HR/A",
                "amendment_type": "NEW HOLDINGS",
                "rows": [{"cusip": "1", "shares": 2, "value_usd": 20, "sh_prn": "SH"}],
            },
        ]
    )
    assert len(rows) == 1 and rows[0]["shares"] == 12 and rows[0]["value_usd"] == 120


def test_legacy_issuer_word_is_not_a_cusip_and_trailing_decimal_is_valid():
    rows, _ = parse_legacy_document(b"""Table Entry Total: 2
    <TABLE>Name of Issuer  Title of Class  CUSIP
    FIFTH THIRD BANCOPCOM            316773100      739     20,000 SH X
    ANNALY CAPITAL MGMT  NOTE 4.00% 2/15  035710AA0  6067500.  6000  S None
    </TABLE>""")
    assert [row["cusip"] for row in rows] == ["316773100", "035710AA0"]
    assert rows[0]["value_usd"] == 739000
    assert rows[1]["sh_prn"] == "PRN"


def test_blank_legacy_market_value_is_preserved_as_unknown():
    rows, _ = parse_legacy_document(b"""Table Entry Total: 1
    <TABLE>NAME  CLASS  CUSIP  VALUE  SHARES
    AMERICA WEST HLDG CORP  CL B  023657208                 10 SH DEFINED
    </TABLE>""")
    assert len(rows) == 1 and rows[0]["shares"] == 10 and rows[0]["value_usd"] is None


def test_confidential_cover_is_unavailable_data_instead_of_a_parser_failure():
    rows, primary = parse_legacy_document(b"""CONFORMED PERIOD OF REPORT: 20120331
    Norges Bank has submitted its Form 13F pursuant to a request for confidential treatment.
    Table Entry Total: 2136
    Table Value Total: 125797751
    <TABLE>FORM 13F INFORMATIONAL TABLE</TABLE>""")
    assert rows == [] and primary["confidential_omitted"]


def test_full_restatement_supersedes_earlier_confidentiality_and_source_gaps(
    tmp_path, monkeypatch
):
    db = archive.connect(tmp_path / "archive.sqlite")
    archive.store_filing(
        db,
        {
            "accession": "a",
            "manager_id": "example",
            "form": "13F-HR",
            "period_end": "2000-03-31",
            "filed_at": "2000-05-01",
            "confidential_omitted": True,
        },
        status="confidential",
    )
    archive.store_filing(
        db,
        {
            "accession": "b",
            "manager_id": "example",
            "form": "13F-HR/A",
            "amendment_type": "RESTATEMENT",
            "period_end": "2000-03-31",
            "filed_at": "2001-05-01",
            "confidential_omitted": False,
        },
        [{"cusip": "1", "value_usd": 100, "shares": 1, "sh_prn": "SH"}],
    )
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    archive.export(
        db, [{"manager_id": "example", "display_name": "Example"}], tmp_path / "data"
    )
    book = json.loads((tmp_path / "data/history/example/2000.json").read_text())[
        "quarters"
    ]["2000Q1"]
    assert not book["partial"] and not book["confidential_omitted"]
    assert book["positions"][0]["weight_pct"] == 100
    assert len(book["filings"]) == 2


def test_legacy_fund_class_numbers_and_foreign_identifiers_are_preserved():
    rows, _ = parse_legacy_document(b"""Table Entry Total: 2
    <TABLE>NAME  CLASS  CUSIP  VALUE  SHARES
    ISHARES TR  S&P MIDCAP400  464287507  371  4619 SH DEFINED
    CHINA SHIPPING CONTAINER  COM  B018L76  7878 21651200 SH SOLE
    </TABLE>""")
    assert [row["cusip"] for row in rows] == ["464287507", "B018L76"]
    assert rows[0]["value_usd"] == 371000 and rows[1]["shares"] == 21651200


def test_public_document_survives_a_later_run_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(disclosures, "ARCHIVE", tmp_path)
    path = tmp_path / "original.xml"
    path.write_bytes(b"<edgarSubmission><original>public</original></edgarSubmission>")
    url = "https://www.sec.gov/Archives/example.xml"
    assert disclosures.public_document(url, path) == path.read_bytes()
    path.unlink()

    def fail(url):
        raise AssertionError("Preserved public XML must not be downloaded again")

    monkeypatch.setattr(disclosures, "get_bytes", fail)
    assert b"<original>public</original>" in disclosures.public_document(url, path)


@pytest.mark.parametrize(
    ("query", "expression"),
    [("Global Fund", '"Global Fund"'), (["S0001", "S0002"], '"S0001" OR "S0002"')],
)
def test_nport_queries_include_amendments_and_paginate(monkeypatch, query, expression):
    from urllib.parse import parse_qs, urlparse

    def search(url):
        parameters = parse_qs(urlparse(url).query)
        assert parameters["q"] == [expression]
        form = parameters["forms"][0]
        offset = int(parameters["from"][0])
        if offset:
            return {"hits": {"hits": [], "total": 1}}
        accession = "original" if form == "NPORT-P" else "amendment"
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "file_type": form,
                            "ciks": ["0000000001"],
                            "adsh": accession,
                            "file_date": "2020-02-01",
                        }
                    }
                ],
                "total": 1,
            }
        }

    monkeypatch.setattr(disclosures, "get_json", search)
    assert {row["form"] for row in disclosures.nport_filings("1", query)} == {
        "NPORT-P",
        "NPORT-P/A",
    }


def test_public_portfolio_collection_keeps_other_filings_after_one_bad_source(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(disclosures, "ARCHIVE", tmp_path)
    filings = [
        {
            "accession": key,
            "form": form,
            "filed_at": "2020-05-01",
            "url": "https://www.sec.gov/" + key,
        }
        for key, form in [("a", "NPORT-P"), ("b", "NPORT-P/A"), ("bad", "NPORT-P")]
    ]
    monkeypatch.setattr(disclosures, "nport_filings", lambda *args, **kwargs: filings)
    raw = b"""<edgarSubmission><repPdDate>2020-03-31</repPdDate><seriesId>S1</seriesId><seriesName>Global Fund</seriesName><invstOrSecs><invstOrSec><name>Foreign Company</name><curCd>HKD</curCd><valUSD>100</valUSD><pctVal>1</pctVal><invCountry>HK</invCountry></invstOrSec></invstOrSecs></edgarSubmission>"""
    monkeypatch.setattr(
        disclosures,
        "public_document",
        lambda url, path: b"bad XML" if url.endswith("/bad") else raw,
    )
    books, errors = disclosures.public_disclosures(
        [{"kind": "nport", "manager_id": "example", "cik": "1", "series_ids": ["S1"]}],
        workers=2,
    )
    assert [book["id"] for book in books] == ["a", "b"]
    assert len(errors) == 1 and errors[0]["accession"] == "bad"
    assert books[0]["positions"][0]["country"] == "HK"


def test_unknown_amendment_does_not_replace_the_original_book(tmp_path, monkeypatch):
    db = archive.connect(tmp_path / "archive.sqlite")
    manager = {"manager_id": "example", "display_name": "Example", "cik": "1"}
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    for accession, form, filed, value in [
        ("a", "13F-HR", "2000-02-01", 100),
        ("b", "13F-HR/A", "2000-03-01", 1),
    ]:
        archive.store_filing(
            db,
            {
                "accession": accession,
                "manager_id": "example",
                "form": form,
                "period_end": "1999-12-31",
                "filed_at": filed,
            },
            [{"cusip": accession, "value_usd": value, "shares": 1, "sh_prn": "SH"}],
        )
    archive.export(db, [manager], tmp_path / "site")
    book = json.loads((tmp_path / "site/history/example/1999.json").read_text())[
        "quarters"
    ]["1999Q4"]
    assert [row["cusip"] for row in book["positions"]] == ["a"]
    assert book["partial"]


def test_legacy_eight_character_cusip_and_dollar_cover_total():
    rows, primary = parse_legacy_document(b"""CONFORMED PERIOD OF REPORT: 19990331
Form 13F Information Table Entry Total: 1
Form 13F Information Table Value Total: 5053000
APPLE COMPUTER  COM  03783310  5053  140600 SH SOLE 140600 0 0""")
    assert rows[0]["cusip"] == "03783310"
    assert rows[0]["raw_cusip"] == "03783310"
    assert primary["table_value_total_usd"] == 5053000


def test_full_discovery_follows_all_pages_and_preserves_amendments(monkeypatch):
    def block(accession, form="13F-HR"):
        return {
            "form": [form],
            "filingDate": ["2000-02-01"],
            "reportDate": ["1999-12-31"],
            "accessionNumber": [accession],
            "primaryDocument": ["a.txt"],
        }

    monkeypatch.setattr(
        ownership,
        "fetch_submissions",
        lambda cik: {
            "filings": {"recent": block("new"), "files": [{"name": "older.json"}]}
        },
    )
    monkeypatch.setattr(
        ownership, "sec_fetch_json", lambda url: block("old", "13F-E/A")
    )
    rows = ownership.list_13f_filings("1", limit=None, strict=True)
    assert {r["accession"] for r in rows} == {"new", "old"}

    def fail(url):
        raise TimeoutError("page unavailable")

    monkeypatch.setattr(ownership, "sec_fetch_json", fail)
    with pytest.raises(TimeoutError):
        ownership.list_13f_filings("1", limit=None, strict=True)


def make_zip(path, tables):
    with zipfile.ZipFile(path, "w") as zipped:
        for name, rows in tables.items():
            output = io.StringIO()
            writer = csv.DictWriter(
                output, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            zipped.writestr(name, output.getvalue())


def test_bulk_uses_reporting_period_and_historical_dollar_units(tmp_path):
    path = tmp_path / "bulk.zip"
    accession = "0000000001-13-000001"
    make_zip(
        path,
        {
            "SUBMISSION.tsv": [
                {
                    "ACCESSION_NUMBER": accession,
                    "CIK": "1",
                    "PERIODOFREPORT": "31-DEC-2012",
                    "FILING_DATE": "31-MAY-2013",
                    "SUBMISSIONTYPE": "13F-HR",
                }
            ],
            "COVERPAGE.tsv": [
                {
                    "ACCESSION_NUMBER": accession,
                    "REPORTCALENDARORQUARTER": "31-DEC-2012",
                    "FILINGMANAGER_NAME": "Example Capital",
                    "AMENDMENTTYPE": "",
                }
            ],
            "SUMMARYPAGE.tsv": [
                {
                    "ACCESSION_NUMBER": accession,
                    "TABLEENTRYTOTAL": "1",
                    "TABLEVALUETOTAL": "25",
                    "ISCONFIDENTIALOMITTED": "N",
                }
            ],
            "INFOTABLE.tsv": [
                {
                    "ACCESSION_NUMBER": accession,
                    "NAMEOFISSUER": "Untracked issuer",
                    "CUSIP": "123456789",
                    "VALUE": "25",
                    "SSHPRNAMT": "100",
                    "SSHPRNAMTTYPE": "SH",
                    "PUTCALL": "",
                }
            ],
        },
    )
    db = archive.connect(tmp_path / "a.sqlite")
    assert archive.ingest_bulk(db, path, [{"manager_id": "example", "cik": "1"}]) == 1
    filing = db.execute("select * from filings").fetchone()
    assert filing["period_end"] == "2012-12-31"
    assert filing["status"] == "loaded"
    assert archive.filing_rows(db, accession)[0]["value_usd"] == 25_000


def test_history_merges_new_holdings_but_keeps_each_as_filed_record(
    tmp_path, monkeypatch
):
    db = archive.connect(tmp_path / "a.sqlite")
    managers = [
        {"manager_id": "example", "display_name": "Example", "cik": "1"},
        {"manager_id": "nonfiler", "display_name": "Non filer"},
    ]
    for accession, form, amendment, rows in [
        (
            "a",
            "13F-HR",
            None,
            [{"cusip": "000000001", "shares": 10, "value_usd": 100, "sh_prn": "SH"}],
        ),
        (
            "b",
            "13F-HR/A",
            "NEW HOLDINGS",
            [{"cusip": "000000002", "shares": 5, "value_usd": 50, "sh_prn": "SH"}],
        ),
    ]:
        archive.store_filing(
            db,
            {
                "accession": accession,
                "manager_id": "example",
                "period_end": "2012-12-31",
                "filed_at": "2013-05-01",
                "form": form,
                "amendment_type": amendment,
            },
            rows,
        )
    archive.store_filing(
        db,
        {
            "accession": "later",
            "manager_id": "example",
            "period_end": "2026-06-30",
            "filed_at": "2026-08-01",
            "form": "13F-HR",
        },
        [],
    )
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: ([], {}))
    coverage = archive.export(db, managers, tmp_path / "data")
    book = json.loads((tmp_path / "data/history/example/2012.json").read_text())[
        "quarters"
    ]["2012Q4"]
    assert len(book["positions"]) == 2
    assert len(book["filings"]) == 2
    assert not coverage["complete"]  # Discovery has not yet exhausted EDGAR.
    index = json.loads((tmp_path / "data/directory_index.json").read_text())
    assert len(index["managers"]) == 2
    assert index["managers"][0]["history"][0]["quarter"] == "2012Q4"
    assert index["managers"][0]["history"][1]["positions"] == 0


def test_corrected_identity_cannot_inherit_an_old_filers_cached_book(
    tmp_path, monkeypatch
):
    db = archive.connect(tmp_path / "a.sqlite")
    managers = [
        {"manager_id": "example", "display_name": "Example", "cik": "1"},
        {"manager_id": "nonfiler", "display_name": "Non filer"},
    ]
    for accession, manager_id, cik in [
        ("good", "example", "1"),
        ("stale", "example", "2"),
        ("unlinked", "nonfiler", "3"),
    ]:
        archive.store_filing(
            db,
            {
                "accession": accession,
                "manager_id": manager_id,
                "cik": cik,
                "period_end": "2000-03-31",
                "filed_at": "2000-05-01",
                "form": "13F-HR",
            },
            [{"cusip": accession, "shares": 1, "value_usd": 1, "sh_prn": "SH"}],
        )
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: ([], {}))
    result = archive.export(db, managers, tmp_path / "data")
    assert result["filings"]["loaded"] == 1
    book = json.loads((tmp_path / "data/history/example/2000.json").read_text())[
        "quarters"
    ]["2000Q1"]
    assert [p["cusip"] for p in book["positions"]] == ["good"]
    index = json.loads((tmp_path / "data/directory_index.json").read_text())
    assert (
        next(m for m in index["managers"] if m["manager_id"] == "nonfiler")["history"]
        == []
    )
    assert db.execute("select count(*) from filings").fetchone()[0] == 3


def test_nport_keeps_fund_vehicle_currency_and_nav_denominator():
    xml = b"""<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><genInfo>
    <seriesId>S00001</seriesId><seriesName>Global Equity</seriesName><repPdDate>2020-03-31</repPdDate></genInfo>
    <invstOrSec><name>Tencent</name><title>Ordinary</title><cusip>000000000</cusip>
    <identifiers><isin value="KYG875721634"/><ticker value="0700.HK"/></identifiers>
    <balance>200</balance><units>NS</units><curCd>HKD</curCd><valUSD>10000</valUSD><pctVal>4.2</pctVal><invCountry>KY</invCountry></invstOrSec></edgarSubmission>"""
    parsed = disclosures.parse_nport(
        xml, "example", source_url="https://www.sec.gov/a.xml"
    )
    row = parsed["positions"][0]
    assert parsed["vehicle_id"] == "S00001"
    assert row["currency"] == "HKD"
    assert row["weight_basis"] == "fund_net_assets"
    assert row["isin"] == "KYG875721634"


def test_letters_include_untracked_foreign_holdings_and_exclude_discussion_and_exits():
    text = "Top ten holdings\nTencent (700 HK) 8.2%\nUnlisted Local Company 2.4%\nIndex return 14.5%\n"
    mentions = [
        {
            "ticker": "OWN",
            "action": "add",
            "commentary": "We own OWN as a long position.",
        },
        {
            "ticker": "OLD",
            "action": "exit",
            "commentary": "We exited our position in OLD.",
        },
        {
            "ticker": "PEER",
            "action": "discussed",
            "commentary": "The competitor PEER grew quickly.",
        },
    ]
    rows = disclosures.extract_document_positions(text, mentions)
    assert {r["ticker"] for r in rows} == {"OWN", "0700.HK", ""}
    assert (
        next(r for r in rows if r["ticker"] == "0700.HK")["weight_basis"]
        == "unspecified_disclosed_weight"
    )
    assert next(r for r in rows if r["ticker"] == "OWN")["weight_pct"] is None


def test_identity_does_not_merge_similarly_named_different_firms():
    catalog = {
        "Analog Century Management LP": {"0000000001"},
        "Century Management LLC": {"0000000002"},
    }
    assert universe.match_cik(["Century Management"], catalog) == (
        "0000000002",
        "Century Management LLC",
    )
    assert (
        universe.match_cik(
            ["Century Management"], {"Century Management LLC": {"1", "2"}}
        )
        is None
    )


def test_non_letters_never_expand_manager_universe(tmp_path):
    path = tmp_path / "insights.json"
    path.write_text(
        json.dumps(
            {
                "letters": [
                    {
                        "fund_id": "research",
                        "fund": "Broker Research",
                        "document_type": "sell_side_research",
                        "letter_eligible": False,
                    },
                    {
                        "fund_id": "real",
                        "fund": "Real Capital",
                        "document_type": "investor_letter",
                        "letter_eligible": True,
                    },
                ]
            }
        )
    )
    profiles = universe.eligible_profiles(path)
    assert len(profiles) == 1
    assert next(iter(profiles.values()))["name"] == "Real Capital"


def test_published_csv_requires_a_real_snapshot_date():
    source = {
        "columns": {"issuer": "Name", "weight_pct": "Weight"},
        "manager_id": "example",
        "vehicle_id": "fund",
        "vehicle_name": "Fund",
        "url": "https://fund.example/holdings.csv",
    }
    with pytest.raises(ValueError, match="as-of date"):
        disclosures.parse_holdings_csv(b"Name,Weight\nCompany,4.2\n", source)


def test_history_ui_contracts():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node runtime required")
    suite = Path(__file__).with_name("test_investor_history_ui.cjs")
    result = subprocess.run(
        [node, "--test", str(suite)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_durable_checkpoint_restores_a_live_wal_database_and_rejects_corruption(
    tmp_path,
):
    cache = tmp_path / "cache"
    db = archive.connect(cache / "archive.sqlite")
    archive.store_filing(
        db,
        {"accession": "a", "manager_id": "example", "period_end": "2000-12-31"},
        [{"cusip": "1", "shares": 2}],
    )
    (cache / "universe.json").write_text('{"managers":[]}')
    parts = tmp_path / "parts"
    manifest = checkpoint.pack(cache, parts, part_bytes=200)
    assert len(manifest["parts"]) > 1
    restored = tmp_path / "restored"
    assert checkpoint.restore(parts, restored)
    fake = "0" * 64
    shutil.copytree(parts / manifest["identity"], parts / fake)
    archive.write_json(parts / fake / "manifest.json", {**manifest, "identity": fake})
    with pytest.raises(ValueError, match="payload identity"):
        checkpoint.restore(parts, tmp_path / "tampered", identity=fake)
    with archive.connect(restored / "archive.sqlite") as other:
        assert other.execute("select count(*) from filings").fetchone()[0] == 1
        assert archive.filing_rows(other, "a")[0]["shares"] == 2
    file = checkpoint.part_path(parts, manifest, manifest["parts"][0])
    file.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        checkpoint.restore(parts, tmp_path / "broken")
    db.close()


def test_parallel_download_connections_close_after_transactions(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text('{"managers":[]}')
    monkeypatch.setattr(
        archive,
        "bulk_urls",
        lambda: ["https://www.sec.gov/a.zip", "https://www.sec.gov/b.zip"],
    )

    def fake_download(db, url):
        with db:
            db.execute(
                "INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?,?)",
                (url, "digest", 1, "loaded", None, archive.now()),
            )

    monkeypatch.setattr(archive, "download", fake_download)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "archive",
            "--download-only",
            "--workers",
            "2",
            "--database",
            str(tmp_path / "a.sqlite"),
            "--registry",
            str(registry),
        ],
    )
    assert archive.main() == 0
    with archive.connect(tmp_path / "a.sqlite") as db:
        assert db.execute("select count(*) from downloads").fetchone()[0] == 2


def test_checkpoint_reuses_unchanged_content_between_publications(tmp_path):
    cache = tmp_path / "cache"
    db = archive.connect(cache / "archive.sqlite")
    db.close()
    archive.write_json(cache / "universe.json", {"managers": []})
    first = checkpoint.pack(cache, tmp_path / "snapshots", part_bytes=1024)
    archive.write_json(cache / "disclosures.json", {"disclosures": []})
    second = checkpoint.pack(cache, tmp_path / "snapshots", part_bytes=1024)
    assert first["identity"] != second["identity"]
    a = {part["name"] for part in first["parts"]}
    b = {part["name"] for part in second["parts"]}
    assert a & b
    assert checkpoint.restore(
        tmp_path / "snapshots", tmp_path / "old", identity=first["identity"]
    )
    assert not (tmp_path / "old/disclosures.json").exists()


def test_parallel_history_workers_preserve_every_notice_and_close_databases(
    tmp_path, monkeypatch
):
    path = tmp_path / "archive.sqlite"
    monkeypatch.setattr(
        ownership,
        "list_13f_filings",
        lambda cik, **kwargs: [
            {
                "accession": "a" + cik,
                "form": "13F-NT",
                "report_date": "2000-03-31",
                "filing_date": "2000-05-01",
                "index_url": "https://www.sec.gov/" + cik,
            }
        ],
    )
    managers = [{"manager_id": "m" + str(i), "cik": str(i)} for i in range(1, 7)]
    assert archive.backfill_parallel(path, managers, workers=2) == 0
    db = archive.connect(path)
    assert (
        db.execute("SELECT count(*) FROM filings WHERE status='notice'").fetchone()[0]
        == 6
    )
    assert (
        db.execute("SELECT count(*) FROM discovery WHERE status='loaded'").fetchone()[0]
        == 6
    )
    db.execute("BEGIN EXCLUSIVE")
    db.rollback()
    db.close()


def test_deadline_cannot_hide_unvisited_accessions(tmp_path, monkeypatch):
    db = archive.connect(tmp_path / "archive.sqlite")
    monkeypatch.setattr(
        ownership,
        "list_13f_filings",
        lambda *args, **kwargs: [
            {
                "accession": str(i),
                "form": "13F-HR",
                "report_date": "2000-03-31",
                "filing_date": "2000-05-01",
                "index_url": "https://www.sec.gov/" + str(i),
            }
            for i in range(3)
        ],
    )
    times = iter([0, 2])
    monkeypatch.setattr(archive.time, "monotonic", lambda: next(times, 2))
    archive.backfill_filings(db, [{"manager_id": "example", "cik": "1"}], deadline=1)
    assert (
        db.execute("SELECT count(*) FROM filings WHERE status='discovered'").fetchone()[
            0
        ]
        == 3
    )


def test_cached_manager_does_not_hold_writer_during_the_next_network_request(
    tmp_path, monkeypatch
):
    db = archive.connect(tmp_path / "archive.sqlite")
    filing = {
        "accession": "a",
        "form": "13F-HR",
        "report_date": "2000-03-31",
        "filing_date": "2000-05-01",
        "index_url": "https://www.sec.gov/a",
    }
    archive.store_filing(db, {**filing, "manager_id": "example", "cik": "1"})

    def listing(cik, **kwargs):
        assert not db.in_transaction
        return [filing]

    monkeypatch.setattr(ownership, "list_13f_filings", listing)
    archive.backfill_filings(db, [{"manager_id": "example", "cik": "1"}])
    assert not db.in_transaction
    db.close()


def test_deployment_bundles_retain_distinct_historical_books_and_disclosures(
    tmp_path, monkeypatch
):
    data = tmp_path / "data"
    db = archive.connect(tmp_path / "archive.sqlite")
    manager = {"manager_id": "example", "display_name": "Example"}
    for year, value in [("2000", 100), ("2020", 200)]:
        archive.store_filing(
            db,
            {
                "accession": year,
                "manager_id": "example",
                "form": "13F-HR",
                "period_end": year + "-03-31",
                "filed_at": year + "-05-01",
            },
            [{"cusip": "1", "value_usd": value, "shares": 1, "sh_prn": "SH"}],
        )
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    archive.export(db, [manager], data)
    documents = [
        {
            "id": year,
            "manager_id": "example",
            "vehicle_id": "fund",
            "period_end": year + "-03-31",
            "positions": [{"ticker": "FOREIGN", "weight_pct": value}],
        }
        for year, value in [("2000", 1), ("2020", 2)]
    ]
    disclosures.publish(
        documents,
        {"managers": [manager]},
        data=data,
        preserve=False,
        save_archive=False,
    )
    staging.compact_history(data)
    staging.compact_disclosures(data)
    records = json.loads((data / "directory_index.json").read_text())["managers"][0][
        "history"
    ]
    assert records[0]["book_path"] == records[1]["book_path"]
    books = json.loads((data / records[0]["book_path"]).read_text())["quarters"]
    assert books["2000Q1"]["positions"][0]["value_usd"] == 100
    assert books["2020Q1"]["positions"][0]["value_usd"] == 200
    manifest = json.loads((data / "disclosures/example.json").read_text())
    assert manifest["quarters"]["2000Q1"] == manifest["quarters"]["2020Q1"]
    snapshots = json.loads((data / manifest["quarters"]["2000Q1"][0]).read_text())[
        "snapshots"
    ]
    assert {d["period_end"] for d in snapshots} == {"2000-03-31", "2020-03-31"}


def test_public_fund_discovery_requires_principal_adviser_and_keeps_dates(tmp_path):
    path = tmp_path / "ncen.zip"
    make_zip(
        path,
        {
            "SUBMISSION.tsv": [
                {
                    "ACCESSION_NUMBER": "a",
                    "CIK": "12",
                    "REPORT_ENDING_PERIOD": "2020-12-31",
                }
            ],
            "FUND_REPORTED_INFO.tsv": [
                {
                    "ACCESSION_NUMBER": "a",
                    "FUND_ID": "f",
                    "SERIES_ID": "S1",
                    "FUND_NAME": "Global Fund",
                }
            ],
            "ADVISER.tsv": [
                {
                    "FUND_ID": "f",
                    "ADVISER_TYPE": "Advisor",
                    "ADVISER_NAME": "Harris Associates L P",
                    "ADVISOR_START_DATE": "2019-01-01",
                    "ADVISOR_TERMINATED_DATE": "N/A",
                },
                {
                    "FUND_ID": "f",
                    "ADVISER_TYPE": "Subadvisor",
                    "ADVISER_NAME": "Other Capital",
                    "ADVISOR_START_DATE": "2018-01-01",
                    "ADVISOR_TERMINATED_DATE": "N/A",
                },
            ],
        },
    )
    rows = public_funds.discover_from_zip(
        path,
        [
            {"manager_id": "harris", "display_name": "Harris Associates L.P."},
            {"manager_id": "other", "display_name": "Other Capital"},
        ],
    )
    assert len(rows) == 1
    assert rows[0]["manager_id"] == "harris"
    assert rows[0]["series_id"] == "S1"
    assert rows[0]["appointment_start"] == "2019-01-01"
    assert rows[0]["appointment_end"] == ""


def test_pinned_deploy_restores_history_without_private_letter_evidence(
    tmp_path, monkeypatch
):
    cache = tmp_path / "original"
    db = archive.connect(cache / "archive.sqlite")
    manager = {"manager_id": "example", "display_name": "Example", "cik": "1"}
    archive.store_filing(
        db,
        {
            "accession": "a",
            "manager_id": "example",
            "cik": "1",
            "form": "13F-HR",
            "period_end": "1999-12-31",
            "filed_at": "2000-02-01",
        },
        [{"cusip": "1", "value_usd": 100, "shares": 2, "sh_prn": "SH"}],
    )
    db.close()
    archive.write_json(
        cache / "universe.json",
        {"managers": [manager], "source_ids": {"private-fund": "example"}},
    )
    archive.write_json(
        cache / "disclosures.json",
        {
            "disclosures": [
                {
                    "id": "doc",
                    "manager_id": "example",
                    "vehicle_id": "fund",
                    "source_ref": "private.txt",
                    "period_end": None,
                    "disclosed_at": "2020-01-01",
                    "quarter": "2020Q1",
                    "source_kind": "fund_disclosure",
                    "positions": [
                        {
                            "issuer": "Foreign Company",
                            "ticker": "1234.HK",
                            "evidence_quote": "private original quotation",
                        }
                    ],
                }
            ]
        },
    )
    vault = tmp_path / "vault"
    parts = vault / "dashboard-private/investor-history"
    manifest = checkpoint.pack(cache, parts)
    receipt = tmp_path / "receipt.json"
    archive.write_json(receipt, {"identity": manifest["identity"]})
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    result = staging.stage(
        tmp_path / "site", vault=vault, receipt=receipt, cache=tmp_path / "restored"
    )
    assert result["identity"] == manifest["identity"]
    generated = "".join(
        path.read_text(encoding="utf-8") for path in (tmp_path / "site").rglob("*.json")
    )
    assert "1999Q4" in generated and "1234.HK" in generated
    assert (
        "private original quotation" not in generated and "private.txt" not in generated
    )
    receipt.write_text('{"identity":"' + "0" * 64 + '"}')
    with pytest.raises(RuntimeError, match="missing"):
        staging.stage(
            tmp_path / "missing", vault=vault, receipt=receipt, cache=tmp_path / "new"
        )
