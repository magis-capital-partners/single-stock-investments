from __future__ import annotations

import gzip
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from _system.trading.sleeves.realized import build_history, normalize_event, read_report
from _system.trading.sleeves.realized_cli import publication, window_chunks
from _system.trading.sleeves.realized_store import RealizedStore


def write_report(tmp_path, trades=(), *, lots=(), positions=(), summaries=(), actions=(),
                 start="20260101", end="20261026", generated="20261027;060000", name="report.xml", account="TEST", levels=True):
    root = ET.Element("FlexQueryResponse")
    statement = ET.SubElement(ET.SubElement(root, "FlexStatements"), "FlexStatement",
                              accountId=account, fromDate=start, toDate=end, whenGenerated=generated)
    if levels:
        section = ET.SubElement(statement, "Trades")
        for row in trades:
            ET.SubElement(section, "Trade", {**row, "levelOfDetail": row.get("levelOfDetail", "EXECUTION")})
        for row in lots:
            ET.SubElement(section, "Trade", {**row, "levelOfDetail": "CLOSED_LOT"})
    for section_name, tag, rows in (("OpenPositions", "OpenPosition", positions),
                                    ("FIFOPerformanceSummaryInBase", "FIFOPerformanceSummaryUnderlying", summaries),
                                    ("CorporateActions", "CorporateAction", actions)):
        if rows:
            section = ET.SubElement(statement, section_name)
            for row in rows:
                ET.SubElement(section, tag, row)
    path = tmp_path / name
    ET.ElementTree(root).write(path, encoding="utf-8")
    return path


def trade(**kwargs):
    return {"transactionID": "1", "tradeID": "t1", "conid": "101", "symbol": "TEST",
            "assetCategory": "STK", "currency": "USD", "quantity": "-10", "tradePrice": "12",
            "fifoPnlRealized": "19", "ibCommission": "-1", "tradeDate": "20261023",
            "settleDateTarget": "20261026", "openCloseIndicator": "C", **kwargs}


def history(path, **kwargs):
    report = read_report(path, account="TEST")
    report["has_executions"] = True
    return build_history([normalize_event(r, report) for r in report["events"]], report["lots"],
                         reports=[report], positions=report["positions"], ls_symbols=set(), blacklist=set(),
                         summaries=report["summaries"], **kwargs)


def test_reported_pnl_is_not_charged_commissions_twice(tmp_path):
    row = history(write_report(tmp_path, [trade()]))["records"][0]
    assert row["realized_usd"] == "19"
    assert row["owner"] == "michael"
    assert row["settlement_status"] == "date_reached"


def test_zero_profit_close_is_preserved_and_open_zero_profit_is_not(tmp_path):
    result = history(write_report(tmp_path, [trade(fifoPnlRealized="0"), trade(transactionID="2", openCloseIndicator="O", fifoPnlRealized="0")]))
    assert len(result["records"]) == 1


def test_nonzero_reported_realization_on_open_marked_record_is_preserved(tmp_path):
    row = history(write_report(tmp_path, [trade(openCloseIndicator="O")]))["records"][0]
    assert row["record_kind"] == "reported_realization"
    assert row["quantity"] is None
    assert row["realized_usd"] == "19"


def test_reversal_does_not_claim_entire_fill_is_closed_quantity(tmp_path):
    row = history(write_report(tmp_path, [trade(openCloseIndicator="C;O", quantity="-30")]))["records"][0]
    assert row["quantity"] is None


def test_shared_3905_is_not_assigned_without_broker_lot_evidence(tmp_path):
    row = history(write_report(tmp_path, [trade(symbol="3905.T")]))["records"][0]
    assert row["owner"] == "unallocated"


def test_hifo_broker_matches_split_shared_security_between_owners(tmp_path):
    path = write_report(tmp_path, [trade(symbol="3905.T", fifoPnlRealized="30")], lots=[
        {"tradeID": "t1", "openDateTime": "20260102;100000", "quantity": "-4", "fifoPnlRealized": "10"},
        {"tradeID": "t1", "openDateTime": "20260914;100000", "quantity": "-6", "fifoPnlRealized": "20"},
    ])
    rows = history(path)["records"]
    assert [(r["owner"], r["realized_usd"]) for r in rows] == [("michael", "10"), ("drew", "20")]
    assert all(r["lot_matched"] for r in rows)


def test_mismatching_lot_amounts_do_not_double_count_execution(tmp_path):
    result = history(write_report(tmp_path, [trade()], lots=[{"tradeID": "t1", "fifoPnlRealized": "999"}]))
    assert len(result["records"]) == 1
    assert result["records"][0]["realized_usd"] == "19"
    assert result["reconciliation"]["exceptions"][0]["reason"] == "closed_lot_pnl_mismatch"


def test_foreign_fx_is_exact_and_missing_fx_stays_unknown(tmp_path):
    rows = history(write_report(tmp_path, [trade(currency="JPY", fxRateToBase="0.0065", fifoPnlRealized="1000"),
        trade(transactionID="2", currency="CAD", fifoPnlRealized="5")]))["records"]
    assert rows[0]["realized_usd"] == "6.5000"
    assert rows[1]["realized_usd"] is None


@pytest.mark.parametrize("code", ["Ep", "A", "Ex"])
def test_option_booking_without_execution_id_is_retained(tmp_path, code):
    row = history(write_report(tmp_path, [trade(assetCategory="OPT", transactionType="BookTrade", notes=code,
                                               openCloseIndicator="", multiplier="100")]))["records"][0]
    assert row["is_close"]
    assert row["identified"]


def test_index_strategies_are_excluded_from_discretionary_results(tmp_path):
    report = read_report(write_report(tmp_path, [trade(symbol="SPXW 261023C06000000", underlyingSymbol="SPX", assetCategory="OPT")]), account="TEST")
    event = normalize_event(report["events"][0], report)
    result = build_history([event], [], reports=[report], positions=[], ls_symbols=set(), blacklist=set())
    assert result["records"][0]["owner"] == "excluded"


def test_cancel_reversal_nets_the_broker_reported_amounts(tmp_path):
    result = history(write_report(tmp_path, [trade(), trade(transactionID="2", tradeID="cancel", transactionType="TradeCancel",
        origTradeID="t1", openCloseIndicator="", fifoPnlRealized="-19")]))
    assert sum(float(r["realized_usd"]) for r in result["records"]) == 0
    assert all(r["record_kind"] == "cancellation_adjustment" for r in result["records"])
    assert all(r["quantity"] is None for r in result["records"])


def test_cancel_rebooking_can_retain_realization_on_original_tax_record(tmp_path):
    result = history(write_report(tmp_path, [trade(), trade(transactionID="2", tradeID="cancel", transactionType="TradeCancel",
        origTradeID="t1", openCloseIndicator="", fifoPnlRealized="0")]))
    assert result["records"][0]["realized_usd"] == "19"
    assert result["records"][0]["record_kind"] == "cancellation_adjustment"


def test_settlement_status_uses_statement_date_not_wall_clock(tmp_path):
    rows = history(write_report(tmp_path, [trade(settleDateTarget="20261027"), trade(transactionID="2", settleDateTarget="")]))["records"]
    assert [r["settlement_status"] for r in rows] == ["pending", "unknown"]


def test_retained_contract_is_visible_without_becoming_a_new_closed_lot(tmp_path):
    row = history(write_report(tmp_path, [trade()], positions=[{"conid": "101", "position": "5"}]))["records"][0]
    assert row["contract_held_now"]


def test_wrong_account_and_ambiguous_period_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="configured account"):
        read_report(write_report(tmp_path, account="OTHER"), account="TEST")
    with pytest.raises(ValueError, match="ambiguous"):
        read_report(write_report(tmp_path, start="01/02/2026", end="03/04/2026"), account="TEST")


def test_duplicate_replay_does_not_duplicate_events_and_sources_are_recoverable(tmp_path):
    store = RealizedStore(tmp_path / "state")
    path = write_report(tmp_path, [trade()])
    assert not store.ingest(path, account="TEST")["duplicate"]
    assert store.ingest(path, account="TEST")["duplicate"]
    assert store.db.execute("SELECT count(*) FROM realized_events").fetchone()[0] == 1
    archived = Path(store.db.execute("SELECT archive_path FROM realized_reports").fetchone()[0])
    assert gzip.decompress(archived.read_bytes()) == path.read_bytes()
    store.close()


def test_later_correction_changes_effective_result_and_retains_prior_revision(tmp_path):
    store = RealizedStore(tmp_path / "state")
    store.ingest(write_report(tmp_path, [trade()]), account="TEST")
    store.ingest(write_report(tmp_path, [trade(fifoPnlRealized="21")], generated="20261028;060000", name="later.xml"), account="TEST")
    result = store.build(account="TEST", ls_symbols=set(), blacklist=set())
    assert result["records"][0]["realized_usd"] == "21"
    assert store.db.execute("SELECT count(*) FROM realized_revisions").fetchone()[0] == 2
    store.close()


def test_supplement_does_not_retire_existing_executions(tmp_path):
    store = RealizedStore(tmp_path / "state")
    store.ingest(write_report(tmp_path, [trade()]), account="TEST")
    store.ingest(write_report(tmp_path, [], generated="20261028;060000", name="empty-detail.xml"), account="TEST", role="closed_lots")
    assert store.db.execute("SELECT count(*) FROM realized_events WHERE active=1").fetchone()[0] == 1
    store.ingest(write_report(tmp_path, [{"levelOfDetail": "SUMMARY", "symbol": "TEST"}], generated="20261029;060000", name="summary.xml"), account="TEST")
    assert store.db.execute("SELECT count(*) FROM realized_events WHERE active=1").fetchone()[0] == 1
    store.close()


def test_older_report_cannot_rewind_newer_effective_values(tmp_path):
    store = RealizedStore(tmp_path / "state")
    store.ingest(write_report(tmp_path, [trade(fifoPnlRealized="22")], generated="20261028;060000"), account="TEST")
    store.ingest(write_report(tmp_path, [trade()], name="old.xml"), account="TEST")
    assert store.build(account="TEST", ls_symbols=set(), blacklist=set())["records"][0]["realized_usd"] == "22"
    store.close()


def test_new_year_report_preserves_prior_year_history(tmp_path):
    store = RealizedStore(tmp_path / "state")
    store.ingest(write_report(tmp_path, [trade()]), account="TEST")
    store.ingest(write_report(tmp_path, [], start="20270101", end="20270104", generated="20270105;060000", name="newyear.xml"), account="TEST")
    assert len(store.build(account="TEST", ls_symbols=set(), blacklist=set())["records"]) == 1
    store.close()


def test_ownership_override_requires_auditable_evidence(tmp_path):
    store = RealizedStore(tmp_path / "state")
    with pytest.raises(ValueError, match="author"):
        store.assign({"owner": "drew", "account": "TEST", "record_id": "tx:1"})
    store.ingest(write_report(tmp_path, [trade(symbol="3905.T")]), account="TEST")
    store.assign({"owner": "drew", "account": "TEST", "record_id": "tx:1", "author": "test", "reason": "opening ticket evidence"})
    row = store.build(account="TEST", ls_symbols=set(), blacklist=set())["records"][0]
    assert row["owner"] == "drew" and row["confidence"] == "explicit_override"
    store.close()


def test_unlinked_corporate_action_is_retained_as_reconciliation_exception(tmp_path):
    store = RealizedStore(tmp_path / "state")
    store.ingest(write_report(tmp_path, [trade()], actions=[{"actionID": "a1", "type": "MERGER", "symbol": "OLD"}]), account="TEST")
    result = store.build(account="TEST", ls_symbols=set(), blacklist=set())
    assert result["reconciliation"]["unmatched_action_count"] == 1
    assert len(result["records"]) == 1
    store.close()


def test_publication_is_bounded_and_never_exports_excluded_strategy_rows(tmp_path):
    result = history(write_report(tmp_path, [trade()]))
    result["source_reports"] = []
    manifest, batches = publication(result)
    assert manifest["row_count"] == 1 and len(batches) == 1
    assert manifest["batch_hashes"]


def test_monthly_backfill_windows_cover_leap_year_without_gaps():
    chunks = list(window_chunks("2024-01-01", "2024-12-31"))
    assert len(chunks) == 12
    assert chunks[1] == ("2024-02-01", "2024-02-29")


def test_lot_quantities_must_conserve_closed_execution_quantity(tmp_path):
    result = history(write_report(tmp_path, [trade(symbol="3905.T")], lots=[
        {"tradeID": "t1", "openDateTime": "20260914;100000", "quantity": "-100", "fifoPnlRealized": "19"}]))
    assert result["records"][0]["owner"] == "unallocated"
    assert not result["records"][0]["lot_matched"]


def test_lot_record_identity_survives_detail_row_reordering(tmp_path):
    lots = [{"tradeID": "t1", "openDateTime": "20260102;100000", "quantity": "-4", "fifoPnlRealized": "10"},
            {"tradeID": "t1", "openDateTime": "20260914;100000", "quantity": "-6", "fifoPnlRealized": "9"}]
    first = history(write_report(tmp_path, [trade(symbol="3905.T")], lots=lots, name="first.xml"))
    second = history(write_report(tmp_path, [trade(symbol="3905.T")], lots=list(reversed(lots)), name="second.xml"))
    assert {r["record_id"]:r["owner"] for r in first["records"]} == {r["record_id"]:r["owner"] for r in second["records"]}


def test_later_universe_change_does_not_rewrite_old_ownership(tmp_path):
    store = RealizedStore(tmp_path / "state")
    store.ingest(write_report(tmp_path, [trade()]), account="TEST")
    first = store.build(account="TEST", ls_symbols=set(), blacklist=set())
    second = store.build(account="TEST", ls_symbols={"TEST"}, blacklist=set())
    assert first["records"][0]["owner"] == second["records"][0]["owner"] == "michael"
    store.close()


def test_execution_query_is_not_mistaken_for_supplemental_closed_lots(tmp_path):
    store = RealizedStore(tmp_path / "state")
    with pytest.raises(ValueError, match="executions only"):
        store.ingest(write_report(tmp_path, [trade()]), account="TEST", role="closed_lots")
    store.close()
