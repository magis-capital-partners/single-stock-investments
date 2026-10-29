from decimal import Decimal

import pytest

from _system.trading.sleeves.strategy_ownership import OwnershipRegistry, reference_owner, annotate_lots
from _system.trading.sleeves.realized import normalize_event, build_history
from _system.trading.sleeves.tests.test_realized import trade, sibling_report, history
from _system.trading.portfolio_hub.flex_ingest import build_account_snapshot
from _system.trading.sleeves.flex_positions import parse_flex_positions
from _system.trading.sleeves.classify_positions import classify_positions


def event(tx="open", ref="ETF_LS|PAIR|fill", **kw):
    return {"account": "TEST", "event_id": tx, "transaction_id": tx, "trade_id": "trade-" + tx,
            "conid": "101", "model": "", "order_ref": ref, "sec_type": "STK", "trade_date": "2026-10-01",
            "quantity": "10", "report_id": "source-sha", **kw}


def registry(*events):
    return OwnershipRegistry.build(list(events) or [event()], account="TEST", through="2026-10-26")


@pytest.mark.parametrize("ref", ["ETF_LS|B4|x", "B5P|x", "ETF_LS|MANUAL|BUY|x"])
def test_only_executed_references_prove_ls(ref):
    assert reference_owner(ref)["owner"] == "excluded"
    assert reference_owner("proposed " + ref) is None


def test_opening_ls_survives_human_exit_and_id_domains_do_not_collide():
    reg = registry(event(), event("human", "MICHAEL_SLEEVE", trade_id="open"))
    assert reg.resolve(account="TEST", conid="101", transaction_id="open", closing_ref="MICHAEL_SLEEVE")["owner"] == "excluded"
    assert reg.resolve(account="TEST", conid="101", trade_id="open")["owner"] == "michael"
    assert reg.resolve(account="TEST", conid="999", transaction_id="open") is None
    assert reg.resolve(account="TEST", conid="101", model="other", transaction_id="open") is None
    with pytest.raises(ValueError, match="account mismatch"):
        reg.resolve(account="OTHER", conid="101")


def test_unknown_shared_lot_reviews_but_predating_algo_is_residual():
    reg = registry(event(), event("old", "", trade_date="2025-01-01"), event("unknown", ""))
    assert reg.resolve(account="TEST", conid="101", transaction_id="unknown")["owner"] == "unallocated"
    assert reg.resolve(account="TEST", conid="101", transaction_id="old") is None
    assert reg.resolve(account="TEST", conid="101")["owner"] == "unallocated"
    assert reg.resolve(account="TEST", conid="101", closing_ref="MICHAEL_SLEEVE")["owner"] == "unallocated"


def test_canceled_opening_and_cross_strategy_exit_require_review():
    reg = registry(event("human", "MICHAEL_SLEEVE"), event("cancel", "", event_type="TradeCancel", cancel_transaction_id="human"))
    assert reg.resolve(account="TEST", conid="101", transaction_id="human")["owner"] == "unallocated"
    reg = registry(event("human", "MICHAEL_SLEEVE"))
    assert reg.resolve(account="TEST", conid="101", transaction_id="human", closing_ref="ETF_LS|EXIT")["reason"] == "cross_strategy_close"


def test_documented_option_overlay_is_distinct_from_algorithmic_options():
    assert reference_owner("ETF_LS|MANUAL|SELLPUT|ABC|20261030|100P|2026-10-01|att1", "OPT")["owner"] == "drew"
    assert reference_owner("ETF_LS|AUTO|OPTION|x", "OPT")["owner"] == "excluded"


def test_closed_hifo_lots_split_ls_and_human_without_altering_broker_pnl(tmp_path):
    rows = [("Trade", trade(transactionID="open-ls", tradeID="tls", openCloseIndicator="O", fifoPnlRealized="0", orderReference="ETF_LS|PAIR", tradeDate="20261001")),
            ("Trade", trade(transactionID="open-m", tradeID="tm", openCloseIndicator="O", fifoPnlRealized="0", orderReference="MICHAEL_SLEEVE", tradeDate="20261002")),
            ("Trade", trade(dateTime="20261023;100000", fifoPnlRealized="30")),
            ("Lot", trade(transactionID="open-ls", tradeID="", dateTime="20261023;100000", quantity="4", fifoPnlRealized="10", levelOfDetail="CLOSED_LOT")),
            ("Lot", trade(transactionID="open-m", tradeID="", dateTime="20261023;100000", quantity="6", fifoPnlRealized="20", levelOfDetail="CLOSED_LOT"))]
    result = history(sibling_report(tmp_path, rows))
    assert [(r["owner"], r["realized_native"]) for r in result["records"]] == [("excluded", "10"), ("michael", "20")]
    assert sum(Decimal(r["realized_native"]) for r in result["records"]) == 30
    assert len({r["ownership_version"] for r in result["records"]}) == 1


def test_registry_roundtrip_immutability_and_session_checks(tmp_path):
    reg = registry()
    path = tmp_path / "current.json"
    reg.save(path)
    assert OwnershipRegistry.load(path, account="TEST", through="2026-10-26").version == reg.version
    with pytest.raises(ValueError, match="session"):
        OwnershipRegistry.load(path, through="2026-10-27")
    assert (tmp_path / f"ownership-{reg.version}.json").exists()
    prepared = OwnershipRegistry.load(path).payload["prepared_at"]
    registry().save(path)
    assert OwnershipRegistry.load(path).payload["prepared_at"] == prepared


def test_dated_universe_is_secondary_and_does_not_overwrite_confirmed_human():
    reg = OwnershipRegistry.build([event("human", "MICHAEL_SLEEVE")], account="TEST", through="2026-10-26",
        universes=[{"date": "2026-09-01", "symbols": ["SHARED"], "source_sha": "evidence"}])
    assert reg.resolve(account="TEST", conid="101", transaction_id="human", symbol="SHARED")["owner"] == "michael"
    assert reg.resolve(account="TEST", conid="101", opening_date="2026-08-01", symbol="SHARED") is None
    assert reg.resolve(account="TEST", conid="101", opening_date="2026-10-01", symbol="SHARED")["owner"] == "unallocated"


def test_timestamp_match_requires_unanimous_opening_evidence():
    reg = registry(event(trade_time="20261001;100000"))
    assert reg.resolve(account="TEST", conid="101", opening_time="20261001;100000")["owner"] == "excluded"
    reg = registry(event(trade_time="20261001;100000"), event("other", "", trade_time="20261001;100000"))
    assert reg.resolve(account="TEST", conid="101", opening_time="20261001;100000")["owner"] == "unallocated"


def test_later_missing_reference_cannot_erase_proven_ls_ownership():
    first = registry(event())
    later = OwnershipRegistry.build([event(ref="")], account="TEST", through="2026-10-27", previous=first)
    assert later.resolve(account="TEST", conid="101", transaction_id="open")["owner"] == "excluded"
    canceled = OwnershipRegistry.build([event(ref=""), event("cancel", "", event_type="TradeCancel", cancel_transaction_id="open")],
        account="TEST", through="2026-10-27", previous=first)
    assert canceled.resolve(account="TEST", conid="101", transaction_id="open")["owner"] == "unallocated"


def test_position_lots_conserve_costs_fx_and_shares_across_both_paths(tmp_path, monkeypatch):
    reg = registry(event(), event("human", "MICHAEL_SLEEVE"))
    registry_path = tmp_path / "registry.json"
    reg.save(registry_path)
    monkeypatch.setenv("SLEEVE_OWNERSHIP_REGISTRY", str(registry_path))
    path = tmp_path / "positions.xml"
    path.write_text('''<FlexQueryResponse><FlexStatements><FlexStatement accountId="TEST" fromDate="20261026" toDate="20261026">
      <OpenPositions>
      <OpenPosition accountId="TEST" conid="101" symbol="SHARED" assetCategory="STK" currency="EUR" position="4" costBasisMoney="20" positionValue="40" fifoPnlUnrealized="20" fxRateToBase="1.1" originatingTransactionID="open" openDateTime="20261001;100000" reportDate="20261026"/>
      <OpenPosition accountId="TEST" conid="101" symbol="SHARED" assetCategory="STK" currency="EUR" position="6" costBasisMoney="48" positionValue="60" fifoPnlUnrealized="12" fxRateToBase="1.1" originatingTransactionID="human" openDateTime="20261002;100000" reportDate="20261026"/>
      </OpenPositions><EquitySummaryByReportDateInBase reportDate="20261026" currency="USD" total="500"/>
    </FlexStatement></FlexStatements></FlexQueryResponse>''')
    snapshot = build_account_snapshot(path, account_alias="TEST")
    assert build_account_snapshot(path, account_alias="TEST") == snapshot
    parts = snapshot["completeness"]["ownership"]["allocations"]
    mike = next(p for p in parts if p["owner"] == "michael")
    assert mike["quantity_decimal"] == "6"
    assert mike["position"]["average_cost_native_decimal"] == "8"
    assert mike["position"]["market_value_base_decimal"] == "66.0"
    assert mike["position"]["unrealized_pnl_base_decimal"] == "13.2"
    assert sum(Decimal(p["quantity_decimal"]) for p in parts) == 10
    assert sum(Decimal(p["position"]["market_value_base_decimal"]) for p in parts) == 110
    legacy = classify_positions(annotate_lots(parse_flex_positions(path), reg, account="TEST"), blacklist_family=set(), etf_ls_symbols=set())
    assert [r["classification"]["bucket"] for r in legacy] == ["etf_ls", "michael"]


def test_missing_required_registry_never_uses_residual(monkeypatch):
    from _system.trading.sleeves.strategy_ownership import configured_registry
    monkeypatch.delenv("SLEEVE_OWNERSHIP_REGISTRY", raising=False)
    monkeypatch.setenv("SLEEVE_OWNERSHIP_REQUIRED", "1")
    with pytest.raises(ValueError, match="required ownership"):
        configured_registry()


def test_correction_audit_preserves_broker_economics(tmp_path):
    from copy import deepcopy
    from _system.trading.sleeves.ownership_audit import audit_changes
    from _system.trading.sleeves.tests.test_realized import write_report
    before = history(write_report(tmp_path, [trade()]))
    before["generation_id"] = "before"
    after = deepcopy(before)
    after["generation_id"] = "after"
    after["records"][0].update(owner="excluded", strategy="ls_algo", allocation_reason="opening_reference")
    assert audit_changes(before, after)["financial_amounts_unchanged"]
    assert audit_changes(before, after)["transitions"] == {"michael->excluded": 1}
    after["records"][0]["realized_usd"] = "12345"
    with pytest.raises(ValueError, match="financial amounts"):
        audit_changes(before, after)
