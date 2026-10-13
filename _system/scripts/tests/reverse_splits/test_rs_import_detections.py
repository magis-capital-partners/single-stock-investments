"""Price-detected splits enter the ledger as review-needed rows, never as duplicates.

The filing's ratio wins only when it agrees with the printed jump; a detection
the rename join tied to an existing event, or one within ten days of a ledger
event of the same issuer, is that event and is skipped; cohorts are recomputed
per issuer touching only rows that change.
"""
from __future__ import annotations

from reverse_splits import import_detections as imp
from reverse_splits.db import init_db


def det(symbol, day, k=10, venue="XNAS"):
    return {"symbol": symbol, "day": day, "ratio_inferred": str(k), "listing_venue": venue}


def test_company_names_drop_tickers_and_cik():
    assert imp.company_from_entity("Callon Petroleum Co  (CPE)  (CIK 0000928022)") == "Callon Petroleum Co"
    assert imp.company_from_entity(None) is None


def test_the_filing_ratio_wins_only_when_it_agrees_with_prices():
    assert imp.choose_ratio(16, 0.05) == (0.05, True)                    # 1:20 filed, 16x printed: within 35%
    assert imp.choose_ratio(25, 0.5) == (0.04, False)                    # a proxy's 1-for-2 floor, 25x printed
    assert imp.choose_ratio(10, None) == (0.1, False)


def test_rows_carry_status_confidence_and_filing_fields():
    checks = {
        "confirm|AAA|2025-03-10": {"status": "filing_confirmed", "cik": "0000000001", "accession": "0000000001-25-000001",
                                   "form": "8-K", "entity": "Alpha Corp  (CIK 0000000001)"},
        "confirm|BBB|2025-03-11": {"status": "filing_confirmed", "cik": "0000000002", "accession": "0000000002-25-000002",
                                   "form": "8-K", "entity": "Beta Inc  (BBB)  (CIK 0000000002)"},
    }
    rows, skipped = imp.build_rows(
        [det("AAA", "2025-03-10", k=16), det("BBB", "2025-03-11", k=25, venue="XASE"), det("CCC", "2025-03-12")],
        checks, [], [], {"0000000001-25-000001": 0.05, "0000000002-25-000002": 0.5}, "2026-10-12 00:00:00")
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["status"] == "filing_ratio" and by["AAA"]["ratio"] == 0.05 and by["AAA"]["split_from"] == 20.0
    assert by["AAA"]["confidence"] == 0.5 and by["AAA"]["accession"] == "0000000001-25-000001" and by["AAA"]["company"] == "Alpha Corp"
    assert by["BBB"]["status"] == "filing_confirmed" and by["BBB"]["ratio"] == 0.04 and by["BBB"]["exchange"] == "NYSE American"
    assert by["CCC"]["status"] == "filing_not_found" and by["CCC"]["confidence"] == 0.3 and by["CCC"]["accession"] is None
    assert all(r["needs_review"] == 1 and r["source"] == "databento_price_jump" and r["date_quality"] is None
               and r["outcome"] == "effective" and r["exchange_class"] == "listed" for r in rows)
    assert skipped == {"rename_join": 0, "same_issuer_nearby": 0}


def test_renamed_and_same_issuer_events_are_not_duplicated():
    checks = {"confirm|NEW|2024-05-02": {"status": "filing_confirmed", "cik": "0000000009", "accession": "x", "form": "8-K"}}
    ledger = [{"ticker": "LATER", "ex_date": "2024-05-01", "cik": "0000000009"}]
    joins = [{"filing_time_symbol": "SLRX", "detected_day": "2022-10-17"}]
    rows, skipped = imp.build_rows([det("SLRX", "2022-10-17"), det("NEW", "2024-05-02")], checks, joins, ledger, {}, "now")
    assert rows == [] and skipped == {"rename_join": 1, "same_issuer_nearby": 1}


def test_tickers_use_the_ledger_spelling():
    rows, _ = imp.build_rows([det("BRK.B", "2025-01-02")], {}, [], [], {}, "now")
    assert rows[0]["ticker"] == "BRK-B"


def test_cohorts_are_recomputed_per_issuer_touching_only_changed_rows(tmp_path):
    conn = init_db(tmp_path / "t.db")
    for ticker, ex, cik, prior, cohort in [("AAA", "2023-01-05", "1", 0, "first"), ("AAA", "2021-06-01", "1", None, None),
                                           ("ZZZ", "2022-01-01", None, 0, "first")]:
        conn.execute("INSERT INTO reverse_splits (ticker, ex_date, cik, split_from, split_to, ratio, prior_rs_count, cohort, updated_at) "
                     "VALUES (?, ?, ?, 10, 1, 0.1, ?, ?, 'old')", (ticker, ex, cik, prior, cohort))
    conn.commit()
    assert imp.retag_cohorts(conn) == 2
    got = {(r["ticker"], r["ex_date"]): (r["prior_rs_count"], r["cohort"], r["updated_at"]) for r in
           conn.execute("SELECT ticker, ex_date, prior_rs_count, cohort, updated_at FROM reverse_splits")}
    assert got[("AAA", "2021-06-01")][:2] == (0, "first")
    assert got[("AAA", "2023-01-05")][:2] == (1, "second"), "an earlier split found later makes this one the second"
    assert got[("ZZZ", "2022-01-01")] == (0, "first", "old"), "unchanged rows keep their stamp"
