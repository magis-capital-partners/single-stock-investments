"""Public feed ingestion, dated history and watchlist coverage contracts."""

import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import public_holdings as holdings
import global_disclosures as disclosures
from letter_holdings_tables import extract_tables


CSV = b"""Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,MoneyMarketFlag
11/02/2026,WAGN,RYSAS TI,BR123,Reysas Logistics,12345,10,123450,4.2%,3000000,
11/02/2026,WAGN,RYGYO TI,BR456,Reysas REIT,20000,12,240000,8.0%,3000000,
11/02/2026,WAGN,CAD,CASHCAD,Canadian Dollar,-10,1,-7,0.00%,3000000,Y
"""
SOURCE = {
    "kind": "filepoint_csv",
    "manager_id": "dalal-street",
    "vehicle_id": "WAGN",
    "vehicle_name": "Pabrai Wagons ETF",
    "ticker": "WAGN",
    "url": "https://example.org/holdings.csv",
}

REPORT_SOURCE = {
    "kind": "annual_report_pdf",
    "manager_id": "example-manager",
    "vehicle_id": "foreign-stakes",
    "vehicle_name": "Disclosed foreign equity stakes",
    "frequency": "annual",
    "section_pattern": r"investments\s+in\s+Japan",
    "country": "JP",
    "minimum_positions": 2,
    "url": "https://example.org/2025.pdf",
}
REPORT_TABLE = """Our investments in Japan are listed below.
(Dollars in millions) December 31, 2025
Company
Percentage of
Company Owned Cost Basis Market Value 2025 Dividends
Delta Corporation 10.8% $ 400 $ 1,200 $ 12
Continental & Co., Ltd. 9.7% 500 1,300 13
Total $ 900 $ 2,500 $ 25
Other narrative and unrelated figures follow.
"""

VALUATION_TABLE = """Portfolio Valuation
Example Global Fund, L.P.
June 30, 2023
MARKET UNIT TOTAL % OF ANNUAL %
UNITS SECURITY PRICE VALUE COST COST GAIN/LOSS ASSETS INCOME YIELD
CASH AND EQUIVALENTS- usd
Cash And Cash Equivalents 3,000 3,000 30.0 0 0.0
COMMON STOCKS- usd
100 Delta Logistics Class 3 50.00 5,000 20.00 2,000 3,000 50.0 10 0.2
200 Étoile Industries SA 10.00 2,000 5.00 1,000 1,000 20.0 10 0.5
7,000 3,000 4,000 70.0 20 0.3
TOTAL ASSETS 10,000 6,000 4,000 100.0 20 0.2
Performance Contribution by Security
Delta Logistics 40.0 99.5 10.0
"""


def test_quantity_first_valuations_preserve_all_dates_and_exclude_attribution():
    tables = extract_tables(VALUATION_TABLE + VALUATION_TABLE.replace("June 30", "July 31"))
    assert [table["period_end"] for table in tables] == ["2023-06-30", "2023-07-31"]
    assert all(table["vehicle_name"] == "Example Global Fund, L.P." for table in tables)
    first, second = tables[0]["positions"]
    assert first["issuer"] == "Delta Logistics Class 3"
    assert first["shares"] == 100
    assert first["value_usd"] == 5000
    assert first["weight_pct"] == 50
    assert first["weight_basis"] == "reported_fund_assets"
    assert second["issuer"] == "Étoile Industries SA"
    assert second["weight_pct"] == 20


def test_valuations_do_not_guess_usd_values_or_inconsistent_weights():
    assert not extract_tables(VALUATION_TABLE.replace("- usd", "- eur"))
    assert not extract_tables(VALUATION_TABLE.replace("TOTAL ASSETS", "INCOMPLETE TABLE"))
    (table,) = extract_tables(VALUATION_TABLE.replace("50.0 10", "9.0 10"))
    assert table["positions"][0]["weight_pct"] is None
    assert table["positions"][0]["shares"] == 100


def test_non_usd_equity_sections_cannot_inherit_usd_from_a_previous_section():
    text = VALUATION_TABLE.replace(
        "7,000 3,000 4,000 70.0 20 0.3",
        "PREFERRED STOCK (REG S)- eur\n300 Continental Limited 20.00 6,000 10.00 3,000 3,000 60.0 10 0.2"
    )
    (table,) = extract_tables(text)
    assert len(table["positions"]) == 2
    assert all(row["weight_pct"] is None for row in table["positions"])


def test_damaged_later_valuation_columns_cannot_erase_verified_names_and_quantities():
    text = VALUATION_TABLE.replace("20.00 2,000 3,000", "20.00 2,0 00 3, 000")
    (table,) = extract_tables(text)
    assert len(table["positions"]) == 2
    row = table["positions"][0]
    assert row["issuer"] == "Delta Logistics Class 3"
    assert row["shares"] == 100 and row["value_usd"] == 5000
    assert row["weight_pct"] is None


def test_split_price_digits_are_repaired_only_when_market_value_confirms_them():
    text = VALUATION_TABLE.replace("Delta Logistics Class 3 50.00", "Delta Logistics 5 0.00")
    (table,) = extract_tables(text)
    assert table["positions"][0]["issuer"] == "Delta Logistics"


def test_annual_table_keeps_issuer_stakes_separate_from_unknown_fund_weights():
    period, rows = holdings.parse_report_table(REPORT_TABLE, REPORT_SOURCE)
    assert period == "2025-12-31"
    assert [row["issuer"] for row in rows] == [
        "Delta Corporation", "Continental & Co., Ltd."
    ]
    assert rows[0]["issuer_ownership_pct"] == 10.8
    assert rows[0]["value_usd"] == 1_200_000_000
    assert all(row["weight_pct"] is None and row["shares"] is None for row in rows)
    assert holdings.parse_report_table(
        REPORT_TABLE.replace("investments in Japan", "investments in America"), REPORT_SOURCE
    ) is None


@pytest.mark.parametrize("before,after", [
    ("December 31, 2025", ""),
    ("Dollars in millions", "Yen in millions"),
    ("$ 2,500", "$ 9,500"),
    ("10.8%", "110.8%"),
    ("Total $ 900 $ 2,500 $ 25", ""),
])
def test_unverified_annual_tables_are_rejected(before, after):
    with pytest.raises(ValueError):
        holdings.parse_report_table(REPORT_TABLE.replace(before, after), REPORT_SOURCE)


def test_html_error_page_is_not_treated_as_a_public_report():
    pytest.importorskip("pypdf")
    with pytest.raises(ValueError, match="could not be read as a PDF"):
        holdings.parse_public_report(b"<html>Access denied</html>", REPORT_SOURCE, observed_at="2026-11-01T00:00:00Z")


def test_annual_index_discovers_newest_report_without_using_a_future_quarter(tmp_path, monkeypatch):
    source = {
        **REPORT_SOURCE,
        "kind": "annual_report_family",
        "url": "https://example.org/reports.html",
        "first_year": 2025,
        "annual_link_pattern": r"(\d{4})ar/linksannual\d{2}\.html",
        "report_url_template": "https://example.org/{year}ar/{year}ar.pdf",
    }
    calls = []
    def fetch(item):
        calls.append(item["url"])
        if item["kind"] == "annual_report_family":
            return b'<a href="2024ar/linksannual24.html">old</a><a href="2025ar/linksannual25.html">annual</a><a href="2026q2.pdf">interim</a>'
        return b"pdf"
    def parse(raw, item, *, observed_at):
        assert item["report_year"] == 2025
        period, rows = holdings.parse_report_table(REPORT_TABLE, item)
        return [holdings.snapshot(item, period, rows, observed_at=observed_at, partial=True)]
    monkeypatch.setitem(holdings.PARSERS, "annual_report_pdf", parse)
    documents, review = holdings.collect([source], tmp_path, fetcher=fetch)
    assert not review and len(documents) == 1
    assert calls == ["https://example.org/reports.html", "https://example.org/2025ar/2025ar.pdf"]


def test_archived_registered_fund_original_can_be_upgraded_without_primary_cache(
    tmp_path,
):
    raw = b"<report><repPdDate>2026-06-30</repPdDate><seriesId>S1</seriesId><seriesName>Public Fund</seriesName><invstOrSecs><invstOrSec><name>Reysas</name><balance>100</balance><valUSD>42.87</valUSD><pctVal>1.2</pctVal><invCountry>TR</invCountry><curCd>TRY</curCd></invstOrSec></invstOrSecs></report>"
    sha = holdings.digest(raw)
    archive = tmp_path / "public"
    (archive / "raw").mkdir(parents=True)
    path = archive / "raw" / (sha + ".gz")
    path.write_bytes(gzip.compress(raw))
    document = {
        "manager_id": "pabrai",
        "vehicle_id": "S1",
        "period_end": "2026-06-30",
        "source_kind": "nport",
        "source_url": "https://www.sec.gov/original.xml",
        "source_sha256": sha,
        "parser_version": "old",
        "positions": [],
    }
    disclosures.upgrade_nport_snapshots(
        [document], tmp_path / "missing.sqlite", public_archive=archive
    )
    assert document["positions"][0]["country"] == "TR"
    assert document["positions"][0]["value_usd"] == 42.87
    document["parser_version"] = "old"
    path.write_bytes(gzip.compress(raw + b"corrupt"))
    with pytest.raises(ValueError, match="checksum"):
        disclosures.upgrade_nport_snapshots(
            [document], tmp_path / "missing.sqlite", public_archive=archive
        )


def test_new_horizon_funds_are_discovered_and_every_workbook_row_is_retained(tmp_path):
    columns = [
        "Data as of:",
        "% Net Assets",
        "Name",
        "Ticker",
        "CUSIP",
        "Shares Held",
        "Market Value",
    ]
    values = [
        "11/02/26",
        "0.0311",
        "Singapore Exchange Ltd",
        "SGX SP",
        "6303866",
        "3,037,434",
        "$48,042,685",
    ]
    strings = columns + values
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    shared = (
        f'<sst xmlns="{namespace}">'
        + "".join(f"<si><t>{s}</t></si>" for s in strings)
        + "</sst>"
    )
    rows = "".join(
        "<row>"
        + "".join(
            f'<c r="{chr(65 + i)}{r + 1}" t="s"><v>{r * 7 + i}</v></c>'
            for i in range(7)
        )
        + "</row>"
        for r in range(2)
    )
    sheet = f'<worksheet xmlns="{namespace}"><sheetData>{rows}</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/sharedStrings.xml", shared)
        book.writestr("xl/worksheets/sheet1.xml", sheet)

    def fetch(source):
        if source["kind"] == "horizon_family":
            return b'<a href="https://horizonkinetics.com/products/etf/infl/">INFL</a><a href="https://horizonkinetics.com/products/etf/new/">NEW</a>'
        return buffer.getvalue()

    documents, review = holdings.collect(
        [
            {
                "kind": "horizon_family",
                "manager_id": "horizon-kinetics",
                "url": "https://horizonkinetics.com/products/etf/",
            }
        ],
        tmp_path,
        fetcher=fetch,
    )
    assert not review
    assert {d["vehicle_id"] for d in documents} == {
        "horizon-etf-INFL",
        "horizon-etf-NEW",
    }
    assert documents[0]["positions"][0]["weight_pct"] == pytest.approx(3.11)
    assert documents[0]["positions"][0]["ticker"] == "SGX SP"
    assert documents[0]["positions"][0]["value_usd"] == 48042685


def test_all_international_and_cash_lines_keep_actual_weights_and_dates():
    (book,) = holdings.parse_filepoint_csv(
        CSV, SOURCE, observed_at="2026-11-01T12:00:00Z"
    )
    assert book["period_end"] == "2026-11-02"
    assert [row["ticker"] for row in book["positions"]] == [
        "RYSAS TI",
        "RYGYO TI",
        "CAD",
    ]
    assert book["positions"][0]["shares"] == 12345
    assert book["positions"][0]["weight_pct"] == 4.2
    assert book["positions"][-1]["value_usd"] == -7
    assert all(row["weight_basis"] == "fund_net_assets" for row in book["positions"])


@pytest.mark.parametrize(
    "raw",
    [
        CSV.replace(b"11/02/2026,WAGN,RYGYO", b"11/03/2026,WAGN,RYGYO"),
        CSV.replace(b"WAGN", b"AKRE"),
        b"<html>Service unavailable</html>",
    ],
)
def test_wrong_vehicle_mixed_dates_or_error_page_are_never_portfolios(raw):
    with pytest.raises((ValueError, KeyError)):
        holdings.parse_filepoint_csv(raw, SOURCE, observed_at="2026-11-01T12:00:00Z")


def test_mutable_url_is_refetched_and_history_survives_failure(tmp_path):
    receipt = tmp_path / "receipt.json"
    first, review = holdings.collect(
        [SOURCE], tmp_path, fetcher=lambda _: CSV, observed_at="2026-11-02T12:00:00Z"
    )
    holdings.save(tmp_path, receipt, [], first, review)
    second, review = holdings.collect(
        [SOURCE],
        tmp_path,
        fetcher=lambda _: CSV.replace(b"11/02/2026", b"11/03/2026"),
        observed_at="2026-11-03T12:00:00Z",
    )
    previous = holdings.load(tmp_path, receipt)
    holdings.save(tmp_path, receipt, previous["disclosures"], second, review)
    assert len(holdings.load(tmp_path, receipt)["disclosures"]) == 2

    def broken(_):
        raise OSError("Publisher unavailable")

    current, review = holdings.collect([SOURCE], tmp_path, fetcher=broken)
    saved = holdings.save(
        tmp_path,
        receipt,
        holdings.load(tmp_path, receipt)["disclosures"],
        current,
        review,
    )
    assert len(saved["disclosures"]) == 2
    assert saved["review"][0]["reason"] == "Publisher unavailable"
    assert len(list((tmp_path / "raw").glob("*.gz"))) == 2
    pointer = json.loads(receipt.read_text())
    (tmp_path / "snapshots" / (pointer["identity"] + ".json.gz")).write_bytes(
        gzip.compress(b"{}")
    )
    with pytest.raises(ValueError, match="checksum"):
        holdings.load(tmp_path, receipt)


def test_sequoia_uses_full_live_feed_not_fallback_top_ten():
    source = {**SOURCE, "kind": "filepoint_json", "post": {"fundID": "6604"}}
    raw = json.dumps(
        {
            "data": [
                {
                    "portfolioNumber": "6604",
                    "asOfDate": "2026-10-30T00:00:00",
                    "securityDescriptionLong": "Rolls-Royce",
                    "securityTicker": "RR/ LN",
                    "shares": 100,
                    "marketValueBase": 1234,
                    "netAssetsPercent": 0.1034,
                    "tradingCurrency": "GBP",
                    "country": "GB",
                }
            ]
        }
    ).encode()
    (book,) = holdings.parse_filepoint_json(
        raw, source, observed_at="2026-11-01T12:00:00Z"
    )
    assert book["period_end"] == "2026-10-30"
    (row,) = book["positions"]
    assert row["ticker"] == "RR/ LN"
    assert row["weight_pct"] == pytest.approx(10.34)
    assert row["currency"] == "GBP"
    with pytest.raises(ValueError, match="no live holdings"):
        holdings.parse_filepoint_json(
            b'{"data":[],"error":"timeout"}', source, observed_at="2026-11-01"
        )


def test_issuer_stakes_are_not_portfolio_weights_and_indirect_holders_are_ignored():
    source = {
        **SOURCE,
        "kind": "issuer_ownership",
        "issuer": "Reysas",
        "ticker": "RYSAS.IS",
        "owners": [
            {
                "names": ["PABRAI FUND 3"],
                "vehicle_id": "PIF3",
                "vehicle_name": "Pabrai Fund 3",
            }
        ],
    }
    table = {
        "itemKey": "kpy41_acc5_sermayede_dogrudan",
        "value": [
            {
                "shareholder": "PABRAI FUND 3",
                "shareInCapital": "299.509.209",
                "ratioInCapital": "14,98",
            },
            {
                "shareholder": "Unrelated fund",
                "shareInCapital": "100",
                "ratioInCapital": "2",
            },
        ],
    }
    flight = json.dumps([1, json.dumps(table, separators=(",", ":"))])
    raw = ("<script>self.__next_f.push(" + flight + ")</script>").encode()
    (book,) = holdings.parse_kap(raw, source, observed_at="2026-11-01T12:00:00Z")
    assert book["vehicle_id"] == "PIF3"
    assert book["period_end"] is None
    assert book["disclosed_at"] == "2026-11-01"
    (row,) = book["positions"]
    assert row["issuer_ownership_pct"] == 14.98
    assert row["nominal_capital_try"] == 299509209
    assert row["weight_pct"] is None
    assert row["shares"] is None


def test_dated_letter_valuation_table_retains_named_vehicle_not_letter_quarter():
    text = """Here are the largest holdings in FUND3 as of May 12, 2018:
FUND3's Largest Holdings
Shares
Held Cost
Market
Value Vintage Approx.
(millions) (millions) Return
Delta Logistics 23,000,000 $4.1 $28.2 2016 6.9x
Continental Industries 14,000,000 $11 $30.1 2015 2.7x
Total $58.3
"""
    (table,) = extract_tables(text)
    assert table["vehicle_name"] == "FUND3"
    assert table["period_end"] == "2018-05-12"
    assert [r["issuer"] for r in table["positions"]] == [
        "Delta Logistics",
        "Continental Industries",
    ]
    assert all(r["weight_pct"] is None for r in table["positions"])
    assert not extract_tables(text.replace("holdings", "performance attribution"))
    unicode_table = extract_tables(text.replace("Delta Logistics", "Étoile Industries"))[0]
    assert unicode_table["positions"][0]["issuer"] == "Étoile Industries"


def test_every_pr1282_manager_and_required_daily_vehicle_is_configured():
    root = Path(__file__).resolve().parents[3]
    required = json.loads(
        (root / "_system/reference/investors/required_managers.json").read_text()
    )["managers"]
    registry = json.loads(
        (root / "_system/reference/market-data/ownership/managers.json").read_text()
    )["managers"]
    actual = {m["manager_id"]: str(int(m["cik"])) for m in registry if m.get("cik")}
    assert all(actual.get(manager) == cik for manager, cik in required.items())
    sources = json.loads(holdings.SOURCES.read_text(encoding="utf-8"))["sources"]
    assert {
        "dalal-street",
        "akre-capital-management",
        "ruane-cunniff",
        "horizon-kinetics",
    } <= {s["manager_id"] for s in sources}
    assert {"RYSAS.IS", "RYGYO.IS"} <= {
        s.get("ticker") for s in sources if s["kind"] == "issuer_ownership"
    }
