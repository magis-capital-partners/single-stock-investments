"""reverse-split in the hub: owner-custody policy, the ledger's lots, the Flex
snapshot, and the ticket guard. Mirrors test_etf_0dte_policy.py.

reverse-split (RS) shorts small-cap stock in this account (client 60, watchdog
140 reserved, orderRef RSLIVE|) and names its positions in a symbol-claims
file. Before these rules an RS short was Michael's residual book, his
authoritative lot, and a hub BUY -- including a reduce-only short_framework
cover, which passes against any short in the account -- could net against it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from _system.trading.portfolio_hub import ledger as ledger_module
from _system.trading.portfolio_hub.allocation_policy import (
    classify_policy_position,
    load_rs_symbol_claims,
    reverse_split_ticket_refusal,
)
from _system.trading.portfolio_hub.command_poller import OrderCommandLoop
from _system.trading.portfolio_hub.flex_ingest import build_account_snapshot
from _system.trading.portfolio_hub.ledger import PortfolioLedger
from _system.trading.portfolio_hub.orders import GuardedOrderService
from _system.trading.portfolio_hub.paper import PaperOrderBroker
from _system.trading.sleeves import symbol_claims as sc
from _system.trading.sleeves.strategy_ownership import OwnershipRegistry
from _system.trading.sleeves.symbol_claims import SCHEMA, SymbolClaims, load_symbol_claims

from .test_contract_resolution import _Channel, _RecordingService
from .test_etf_0dte_policy import ALIAS, _book, _lots

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
LETF = {"SPY", "QQQ", "TSLA", "NVDA", "AMZN", "AAPL"}


def write_claims(directory, claims):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "reverse-split.json"
    path.write_text(json.dumps({
        "schema": SCHEMA, "system": "reverse-split", "account": "U805366",
        "generated_at": "2026-11-18T14:59:00Z",
        "claims": {symbol: {"conid": conid, "sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z",
                            "release_after": None} for symbol, conid in claims.items()},
    }), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for name in ("IB_ACCOUNT_SYMBOL_CLAIMS_DIR", "IB_ACCOUNT_SYMBOL_CLAIMS_LAST_GOOD_DIR",
                 "IB_ACCOUNT_SYMBOL_CLAIMS_ACCOUNT", "IBKR_ACCOUNT_ID", "SLEEVE_OWNERSHIP_REGISTRY",
                 "SLEEVE_OWNERSHIP_REQUIRED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sc, "DEFAULT_CLAIMS_DIR", "/nonexistent/ib-account-claims")
    sc._LAST_GOOD.clear()
    yield
    sc._LAST_GOOD.clear()


@pytest.fixture()
def rs(tmp_path) -> SymbolClaims:
    write_claims(tmp_path / "claims", {"ABCD": 11, "WXYZ": 12})
    return load_symbol_claims(directory=tmp_path / "claims").at(NOW)


@pytest.fixture()
def broken(tmp_path) -> SymbolClaims:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "reverse-split.json").write_text("{", encoding="utf-8")
    return load_symbol_claims(directory=tmp_path / "broken").at(NOW)


@pytest.fixture()
def ledger(tmp_path):
    result = PortfolioLedger(tmp_path / "portfolio.db")
    result.migrate()
    yield result
    result.close()


def _claims(monkeypatch, claims):
    monkeypatch.setattr(ledger_module, "load_rs_symbol_claims", lambda **kw: claims)
    monkeypatch.setattr(ledger_module, "load_etf_0dte_expected_delivery", lambda alias, as_of=None: None)
    monkeypatch.setattr(ledger_module, "load_ls_universe", lambda: set(LETF))


# ------------------------------------------------------------------- policy

def test_policy_routes_rs_stamps_and_claims_to_no_owner(rs):
    def policy(row, claims=rs):
        return classify_policy_position(row, ls_symbols=LETF, drew_symbols={"ABCD"}, rs_claims=claims)

    for row, reason in (
        ({"conid": 11, "symbol": "ABCD", "sec_type": "STK", "quantity_decimal": "-500"}, "reverse_split_symbol_claim"),
        ({"conid": 99, "symbol": "WXYZ", "sec_type": "STK", "quantity_decimal": "-10"}, "reverse_split_symbol_claim"),
        ({"conid": 5, "symbol": "AAPL", "sec_type": "STK", "order_ref": "RSLIVE|ENTRY|AAPL|1"}, "reverse_split_order_reference"),
    ):
        got = policy(row)
        assert (got.owner, got.strategy, got.bucket, got.reason) == ("unallocated", "reverse_split", "reverse_split", reason), row
    # Without the claims it was Drew's (a Drew symbol) -- and Michael's when untagged.
    assert policy({"conid": 11, "symbol": "ABCD", "sec_type": "STK"}, None).owner == "drew"
    # A claim beats a broker-matched owner on the same conid.
    evidence = {"owner": "michael", "strategy": "single_stock", "reason": "broker_matched_opening_order_reference"}
    assert policy({"conid": 11, "symbol": "ABCD", "sec_type": "STK", "_ownership": evidence}).strategy == "reverse_split"
    # RS opening evidence after the claim is gone.
    rs_evidence = {"owner": "excluded", "strategy": "reverse_split", "reason": "broker_matched_opening_order_reference"}
    got = policy({"conid": 13, "symbol": "OLDX", "sec_type": "STK", "_ownership": rs_evidence})
    assert (got.owner, got.strategy, got.bucket) == ("unallocated", "reverse_split", "reverse_split")
    # Neighbours are untouched.
    assert policy({"conid": 7, "symbol": "CSU", "sec_type": "STK", "quantity_decimal": "12"}).owner == "michael"
    assert policy({"conid": 8, "symbol": "AAPL", "sec_type": "STK"}).strategy == "letf"
    assert policy({"conid": 9, "symbol": "SPY", "local_symbol": "SPY   261027P00570000", "sec_type": "OPT"}).strategy == "etf_0dte"


def test_unreadable_claims_make_an_unproven_short_an_ownership_review(broken):
    def policy(row):
        return classify_policy_position(row, ls_symbols=LETF, rs_claims=broken)

    got = policy({"conid": 31, "symbol": "NEWX", "sec_type": "STK", "quantity_decimal": "-100"})
    assert (got.owner, got.strategy, got.bucket, got.reason) == (
        "unallocated", "ownership_review", "reverse_split_unverified", "reverse_split_claims_unreadable")
    assert policy({"conid": 7, "symbol": "CSU", "sec_type": "STK", "quantity_decimal": "12"}).owner == "michael"
    evidence = {"owner": "michael", "strategy": "single_stock", "reason": "broker_matched_opening_order_reference"}
    proven = policy({"conid": 31, "symbol": "NEWX", "sec_type": "STK", "quantity_decimal": "-100", "_ownership": evidence})
    assert proven.owner == "michael"


def test_hub_claims_are_read_from_the_environment_at_the_snapshot_moment(tmp_path, monkeypatch):
    assert load_rs_symbol_claims().status == "not_configured"
    path = write_claims(tmp_path / "claims", {"ABCD": 11})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["claims"]["ABCD"]["release_after"] = "2026-11-18T15:05:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("IB_ACCOUNT_SYMBOL_CLAIMS_DIR", str(tmp_path / "claims"))
    assert load_rs_symbol_claims(session_date="2026-11-17").position_match({"conid": 11, "secType": "STK"})
    assert load_rs_symbol_claims(as_of="2026-11-18T16:00:00Z").position_match({"conid": 11, "secType": "STK"}) is None


# ------------------------------------------------------------------- ledger

def test_ledger_puts_rs_lots_outside_both_books(ledger, monkeypatch, rs):
    _claims(monkeypatch, rs)
    snapshot_id = ledger.ingest_account_snapshot(_book((1, "CSU", 12), (11, "ABCD", -500), (12, "WXYZ", -300)))
    assert _lots(ledger, 11) == [("unallocated", "reverse_split", "reverse_split", "-500")]
    assert _lots(ledger, 12) == [("unallocated", "reverse_split", "reverse_split", "-300")]
    notes = {row["conid"]: row["note"] for row in ledger.allocation_projection(ALIAS)["allocations"]}
    assert notes[11] == "reverse_split_symbol_claim"
    assert [row["symbol"] for row in ledger.latest_portfolio(ALIAS, "michael")["positions"]] == ["CSU"]
    assert ledger.latest_portfolio(ALIAS, "drew")["positions"] == []
    assert ledger.reconcile_allocations(snapshot_id) == []


def test_without_claims_the_same_short_was_michaels_authoritative_lot(ledger, monkeypatch):
    _claims(monkeypatch, None)
    ledger.ingest_account_snapshot(_book((11, "ABCD", -500)))
    assert _lots(ledger, 11) == [("michael", "single_stock", None, "-500")]


def test_an_owner_lot_on_an_rs_claimed_conid_is_ended(ledger, monkeypatch, rs):
    _claims(monkeypatch, rs)
    snapshot_id = ledger.ingest_account_snapshot(_book((11, "ABCD", -500)))
    ledger.add_allocation(
        account_alias=ALIAS, conid=11, owner="michael", strategy="single_stock",
        quantity="-200", effective_at="2026-08-17T13:00:00Z",
    )
    assert _lots(ledger, 11) == [("unallocated", "reverse_split", "reverse_split", "-500")]
    assert ledger.latest_portfolio(ALIAS, "michael")["positions"] == []
    assert ledger.reconcile_allocations(snapshot_id, Decimal("0")) == []


def test_unreadable_claims_quarantine_the_unproven_remainder_and_keep_known_lots(ledger, monkeypatch, broken):
    _claims(monkeypatch, broken)
    snapshot_id = ledger.ingest_account_snapshot(_book((1, "CSU", 12), (31, "NEWX", -300)))
    ledger.add_allocation(
        account_alias=ALIAS, conid=31, owner="michael", strategy="single_stock",
        quantity="-100", effective_at="2026-08-17T13:00:00Z",
    )
    assert _lots(ledger, 31) == [
        ("michael", "single_stock", None, "-100"),
        ("unallocated", "ownership_review", "reverse_split_unverified", "-200"),
    ]
    assert _lots(ledger, 1) == [("michael", "single_stock", None, "12")]
    assert ledger.reconcile_allocations(snapshot_id, Decimal("0")) == []


# --------------------------------------------------------------------- flex

FLEX = """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse><FlexStatements count="1">
 <FlexStatement accountId="U805366" fromDate="20261117" toDate="20261117" period="LastBusinessDay">
  <OpenPositions>
   <OpenPosition accountId="U805366" currency="USD" fxRateToBase="1" assetCategory="STK" symbol="CSU"
     conid="7" position="12" markPrice="100" positionValue="1200" costBasisMoney="1000" fifoPnlUnrealized="200"
     originatingTransactionID="m1" openDateTime="20261001;100000" reportDate="20261117" model=""/>
   <OpenPosition accountId="U805366" currency="USD" fxRateToBase="1" assetCategory="STK" symbol="ABCD"
     conid="11" position="-500" markPrice="3" positionValue="-1500" costBasisMoney="-1600" fifoPnlUnrealized="100"
     originatingTransactionID="r1" openDateTime="20261117;100000" reportDate="20261117" model=""/>
   <OpenPosition accountId="U805366" currency="USD" fxRateToBase="1" assetCategory="STK" symbol="NEWX"
     conid="31" position="-200" markPrice="2" positionValue="-400" costBasisMoney="-450" fifoPnlUnrealized="50"
     originatingTransactionID="r2" openDateTime="20261117;110000" reportDate="20261117" model=""/>
  </OpenPositions>
  <EquitySummaryByReportDateInBase reportDate="20261117" currency="USD" total="100000"/>
 </FlexStatement>
</FlexStatements></FlexQueryResponse>
"""


@pytest.fixture()
def flex(tmp_path, monkeypatch):
    path = tmp_path / "flex_positions.xml"
    path.write_text(FLEX, encoding="utf-8")
    from _system.trading.portfolio_hub import flex_ingest

    monkeypatch.setattr(flex_ingest, "load_ls_universe", lambda: set(LETF))
    monkeypatch.setattr(flex_ingest, "load_drew_symbols", lambda: set())
    return path


def _registry(tmp_path, monkeypatch):
    def event(tx, ref, conid):
        return {"account": "U805366", "event_id": tx, "transaction_id": tx, "trade_id": "t-" + tx, "conid": conid,
                "model": "", "order_ref": ref, "sec_type": "STK", "trade_date": "2026-11-17", "quantity": "1",
                "report_id": "sha"}

    registry = OwnershipRegistry.build(
        [event("m1", "MAGIS|single_stock|michael|u1", "7"), event("r1", "RSLIVE|ENTRY|ABCD|1", "11")],
        account="U805366", through="2026-11-17",
    )
    path = tmp_path / "ownership-current.json"
    registry.save(path)
    monkeypatch.setenv("SLEEVE_OWNERSHIP_REGISTRY", str(path))


def _owners(snapshot):
    return {(a["conid"], a["owner"], a["strategy"]) for a in snapshot["completeness"]["ownership"]["allocations"]}


def test_a_host_without_claims_publishes_exactly_what_it_did_before(flex):
    snapshot = build_account_snapshot(flex, account_alias="U805366")
    assert "symbol_claims" not in snapshot["completeness"]
    assert "warnings" not in snapshot["completeness"]


def test_flex_ownership_attributes_rs_lots_and_carries_the_claims(tmp_path, monkeypatch, flex, rs, ledger):
    _registry(tmp_path, monkeypatch)
    snapshot = build_account_snapshot(flex, account_alias="U805366", rs_claims=rs)
    assert _owners(snapshot) == {
        (7, "michael", "single_stock"),
        (11, "unallocated", "reverse_split"),      # claimed, and its opening was RSLIVE|
        (31, "michael", "single_stock"),            # an unclaimed short with no evidence: Michael's residual
    }
    carried = snapshot["completeness"]["symbol_claims"]["reverse-split"]
    assert (carried["status"], carried["source"]) == ("ok", "file")
    assert [c["symbol"] for c in carried["claims"]] == ["ABCD", "WXYZ"]
    # Republishing the same statement with the same claims is the same snapshot.
    assert build_account_snapshot(flex, account_alias="U805366", rs_claims=rs) == snapshot
    ledger.ingest_account_snapshot(snapshot)
    assert [p["symbol"] for p in ledger.latest_portfolio("U805366", "michael")["positions"]] == ["CSU", "NEWX"]


def test_flex_without_a_registry_reaches_the_ledger_policy_with_the_same_answer(tmp_path, monkeypatch, flex, rs, ledger):
    snapshot = build_account_snapshot(flex, account_alias="U805366", rs_claims=rs)
    assert "ownership" not in snapshot["completeness"]
    _claims(monkeypatch, rs)
    ledger.ingest_account_snapshot(snapshot)
    assert _lots_for(ledger, "U805366", 11) == [("unallocated", "reverse_split", "reverse_split", "-500")]


def _lots_for(ledger, alias, conid):
    return sorted((row["owner"], row["strategy"], row["bucket"], row["quantity_decimal"])
                  for row in ledger.allocation_projection(alias)["allocations"] if row["conid"] == conid)


def test_flex_with_unreadable_claims_warns_and_quarantines(tmp_path, monkeypatch, flex):
    _registry(tmp_path, monkeypatch)
    claims_dir = tmp_path / "claims"
    path = write_claims(claims_dir, {"ABCD": 11})
    load_symbol_claims(directory=claims_dir, last_good_dir=tmp_path / "cache")   # a good read is remembered
    path.write_text("{", encoding="utf-8")
    sc._LAST_GOOD.clear()                                                          # a new process
    stale = load_symbol_claims(directory=claims_dir, last_good_dir=tmp_path / "cache")
    snapshot = build_account_snapshot(flex, account_alias="U805366", rs_claims=stale)
    assert _owners(snapshot) == {
        (7, "michael", "single_stock"),
        (11, "unallocated", "reverse_split"),
        (31, "unallocated", "ownership_review"),
    }
    carried = snapshot["completeness"]["symbol_claims"]["reverse-split"]
    assert (carried["status"], carried["source"]) == ("error", "last_good")
    assert any("symbol claims unreadable" in w and "last good copy" in w for w in snapshot["completeness"]["warnings"])


# ------------------------------------------------------------- ticket guard

@pytest.mark.parametrize("identity", [
    {"conid": 11, "symbol": "ABCD", "sec_type": "STK", "local_symbol": "ABCD"},
    {"conid": 777, "symbol": "ABCD", "sec_type": "STK", "local_symbol": "ABCD"},       # new conid, same name
    {"conid": 12, "symbol": "RENAMED", "sec_type": "STK", "local_symbol": "RENAMED"},  # same conid, new name
    {"conid": 900, "symbol": "ABCD", "sec_type": "OPT", "local_symbol": "ABCD  261218P00005000", "trading_class": "ABCD"},
])
def test_ticket_guard_refuses_every_rs_claimed_contract(identity, rs):
    reason = reverse_split_ticket_refusal(identity, rs)
    assert reason and "reverse-split" in reason


@pytest.mark.parametrize("identity", [
    {"conid": 7, "symbol": "CSU", "sec_type": "STK", "local_symbol": "CSU"},
    {"conid": 8, "symbol": "ABCDE", "sec_type": "STK", "local_symbol": "ABCDE"},
    {"conid": 9, "symbol": "MSFT", "sec_type": "OPT", "local_symbol": "MSFT  261120C00400000", "trading_class": "MSFT"},
])
def test_ticket_guard_passes_everything_else(identity, rs):
    assert reverse_split_ticket_refusal(identity, rs) is None


def test_ticket_guard_refuses_everything_while_the_claims_are_unreadable(broken):
    reason = reverse_split_ticket_refusal({"conid": 7, "symbol": "CSU", "sec_type": "STK"}, broken)
    assert reason and "unreadable" in reason


def _row(**overrides):
    base = {"request_id": "r1", "conid": 11, "symbol": "ABCD", "sec_type": "STK", "action": "BUY",
            "quantity_decimal": "10", "limit_price_decimal": "5.00", "owner": "michael",
            "strategy": "single_stock", "mode": "dry_run", "tif": "DAY", "state": "requested"}
    return {**base, **overrides}


def _quotes(conid):
    return {"bid": "4.99", "ask": "5.01", "min_tick": "0.01", "current_position": "-500"}


ABCD = {11: {"symbol": "ABCD", "sec_type": "STK", "local_symbol": "ABCD", "exchange": "SMART", "currency": "USD"}}


@pytest.mark.parametrize("row", [
    _row(action="BUY"),
    _row(action="SELL"),
    # reduce-only BUY cover: passes the reduce-only check against RS's -500.
    _row(action="BUY", strategy="short_framework", rationale="binding"),
    _row(conid=900, sec_type="OPT"),
])
def test_an_rs_claimed_ticket_is_refused_before_anything_is_drafted(row, rs):
    contracts = {**ABCD, 900: {"symbol": "ABCD", "sec_type": "OPT", "local_symbol": "ABCD  261218P00005000",
                               "trading_class": "ABCD", "strike": 5.0, "right": "P", "expiry": "20261218",
                               "multiplier": "100"}}
    service = _RecordingService(PaperOrderBroker(_quotes, contracts=contracts))
    channel = _Channel(requests=[row])
    OrderCommandLoop(service, channel, account_alias="U805366", options_enabled=True,
                     symbol_claims=lambda: rs).tick()
    assert service.created == []
    [(_, update)] = channel.published
    assert update["state"] == "rejected" and "claimed by reverse-split" in update["reject_reason"]


def test_every_ticket_is_refused_while_the_claims_are_unreadable(broken):
    service = _RecordingService(PaperOrderBroker(_quotes))
    channel = _Channel(requests=[_row(conid=7, symbol="CSU")])
    OrderCommandLoop(service, channel, account_alias="U805366", symbol_claims=lambda: broken).tick()
    assert service.created == []
    [(_, update)] = channel.published
    assert update["state"] == "rejected" and "unreadable" in update["reject_reason"]


def test_a_claim_made_after_the_preview_stops_the_submit(tmp_path, rs):
    ledger = PortfolioLedger(tmp_path / "orders.db")
    ledger.migrate()
    try:
        service = GuardedOrderService(ledger, PaperOrderBroker(_quotes, contracts=ABCD), "s" * 32)
        current = {"claims": SymbolClaims(system="reverse-split", status="not_configured")}

        def loop(channel):
            return OrderCommandLoop(service, channel, account_alias="U805366", symbol_claims=lambda: current["claims"])

        def preview():
            channel = _Channel(requests=[_row()])
            loop(channel).tick()
            update = channel.published[-1][1]
            assert update["state"] == "previewed", update
            return update

        def approve(update):
            channel = _Channel(requests=[_row(state="approved", intent_uuid=update["intent_uuid"],
                                              approved_fingerprint=update["contract_fingerprint"])])
            loop(channel).tick()
            return channel.published[-1][1]

        # Control: unclaimed, the dry-run ticket is acknowledged.
        assert approve(preview())["state"] == "acknowledged"

        # RS claims ABCD inside the approval window.
        update = preview()
        current["claims"] = rs
        result = approve(update)
        assert result["state"] == "rejected" and "claimed by reverse-split" in result["reject_reason"]
        order = service.get(update["intent_uuid"])
        assert order["state"] == "Rejected"
        event = ledger.connection.execute(
            "SELECT event_type FROM order_events WHERE intent_uuid=? ORDER BY rowid DESC LIMIT 1",
            (update["intent_uuid"],)).fetchone()
        assert event["event_type"] == "reverse_split_symbol_claim"
    finally:
        ledger.close()
