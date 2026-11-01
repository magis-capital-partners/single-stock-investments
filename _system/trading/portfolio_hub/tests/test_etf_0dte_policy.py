"""etf-0dte in the hub: owner-custody policy, the ledger's lots, and the ticket guard.

etf-0dte is spx-0dte's SPY / QQQ 0DTE executors (clients 50/51, watchdogs
130/131). Their options, and the shares an assignment delivers overnight, sit in
this account but belong to no hub owner: the hub never sizes, rebalances or
tickets against them.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from _system.trading.portfolio_hub import ledger as ledger_module
from _system.trading.portfolio_hub.allocation_policy import (
    classify_policy_position,
    etf_0dte_ticket_refusal,
    load_etf_0dte_expected_delivery,
)
from _system.trading.portfolio_hub.ledger import PortfolioLedger

from .test_ledger import snapshot

ALIAS = "paper-primary"
LETF = {"SPY", "QQQ", "AAPL"}   # the committed universe snapshot lists SPY and QQQ


@pytest.fixture()
def ledger(tmp_path):
    result = PortfolioLedger(tmp_path / "portfolio.db")
    result.migrate()
    yield result
    result.close()


def _position(base, conid, symbol, quantity, *, sec_type="STK", local=None):
    unit = "contracts" if sec_type == "OPT" else "shares"
    return {
        **base, "conid": conid, "symbol": symbol, "local_symbol": local or symbol, "sec_type": sec_type,
        "quantity_unit": unit, "quantity": str(quantity), "market_value": "1", "market_value_native": "1",
        "market_value_base": "1",
    }


def _book(*rows):
    payload = snapshot()
    base = payload["positions"][0]
    payload["positions"] = [_position(base, *row[:3], **(row[3] if len(row) > 3 else {})) for row in rows]
    return payload


def _lots(ledger, conid):
    projection = ledger.allocation_projection(ALIAS)
    return sorted(
        (row["owner"], row["strategy"], row["bucket"], row["quantity_decimal"])
        for row in projection["allocations"] if row["conid"] == conid
    )


def _forecast(monkeypatch, shares):
    monkeypatch.setattr(ledger_module, "load_etf_0dte_expected_delivery", lambda alias, as_of=None: shares)
    monkeypatch.setattr(ledger_module, "load_ls_universe", lambda: set(LETF))


# ------------------------------------------------------------------- policy

def test_policy_routes_etf_0dte_options_and_shares_to_no_owner():
    def policy(row, forecast=None):
        return classify_policy_position(row, ls_symbols=LETF, drew_symbols={"SPY"}, etf_0dte_delivery=forecast)

    # IB API row; Flex row (OCC in symbol, no underlying); QQQ.
    for row in (
        {"symbol": "SPY", "local_symbol": "SPY   261027P00570000", "sec_type": "OPT"},
        {"symbol": "SPY   261027P00570000", "local_symbol": "SPY   261027P00570000", "sec_type": "OPT"},
        {"symbol": "QQQ   261027C00500000", "sec_type": "OPT"},
    ):
        got = policy(row)
        assert (got.owner, got.strategy, got.bucket, got.reason) == (
            "unallocated", "etf_0dte", "etf_0dte", "etf_0dte_option_exclusion",
        ), row

    unattributed = policy({"symbol": "QQQ", "local_symbol": "QQQ", "sec_type": "STK", "quantity_decimal": "200"})
    assert (unattributed.owner, unattributed.strategy, unattributed.bucket, unattributed.reason) == (
        "unallocated", "etf_0dte", "etf_0dte_delivery_unattributed", "etf_0dte_unattributed_shares",
    )
    delivered = policy({"symbol": "SPY", "sec_type": "STK", "quantity_decimal": "-100"}, {"SPY": -100})
    assert (delivered.owner, delivered.bucket, delivered.reason) == (
        "unallocated", "etf_0dte_delivery", "etf_0dte_expected_delivery",
    )
    # Neighbours are untouched: SPX stays SPX's, an LS name stays LS's.
    assert policy({"symbol": "SPX", "local_symbol": "SPXW  260817P05000000", "sec_type": "OPT"}).strategy == "spx_0dte"
    assert policy({"symbol": "AAPL", "sec_type": "STK", "quantity_decimal": "4"}).strategy == "letf"


# ------------------------------------------------------------------- ledger

def test_ledger_puts_etf_0dte_lots_outside_both_books(ledger, monkeypatch):
    _forecast(monkeypatch, {"SPY": -100})
    snapshot_id = ledger.ingest_account_snapshot(_book(
        (1, "CSU", 12),
        (2, "SPY", -100),
        (3, "QQQ", 200),
        (4, "SPY", -2, {"sec_type": "OPT", "local": "SPY   261027P00570000"}),
    ))
    assert _lots(ledger, 2) == [("unallocated", "etf_0dte", "etf_0dte_delivery", "-100")]
    assert _lots(ledger, 3) == [("unallocated", "etf_0dte", "etf_0dte_delivery_unattributed", "200")]
    assert _lots(ledger, 4) == [("unallocated", "etf_0dte", "etf_0dte", "-2")]
    notes = {row["conid"]: row["note"] for row in ledger.allocation_projection(ALIAS)["allocations"]}
    assert notes[2] == "etf_0dte_expected_delivery:expected_delivery"
    assert notes[3] == "etf_0dte_unattributed_shares:no_forecast"
    assert [row["symbol"] for row in ledger.latest_portfolio(ALIAS, "michael")["positions"]] == ["CSU"]
    assert ledger.latest_portfolio(ALIAS, "drew")["positions"] == []
    assert ledger.reconcile_allocations(snapshot_id) == []


def test_an_explicit_lot_is_a_known_holding_and_only_the_rest_is_etf_0dte(ledger, monkeypatch):
    _forecast(monkeypatch, {"SPY": 100})
    snapshot_id = ledger.ingest_account_snapshot(_book((2, "SPY", 650)))
    ledger.add_allocation(
        account_alias=ALIAS, conid=2, owner="michael", strategy="single_stock",
        quantity="500", effective_at="2026-08-17T13:00:00Z",
    )
    assert _lots(ledger, 2) == [
        ("michael", "single_stock", None, "500"),
        ("unallocated", "etf_0dte", "etf_0dte_delivery", "100"),
        ("unallocated", "etf_0dte", "etf_0dte_delivery_unattributed", "50"),
    ]
    ids = [row["allocation_id"] for row in ledger.allocation_projection(ALIAS)["allocations"]]
    assert len(ids) == len(set(ids))
    assert ledger.reconcile_allocations(snapshot_id, Decimal("0")) == []
    michael = ledger.latest_portfolio(ALIAS, "michael")["positions"]
    assert [(row["symbol"], row["quantity_decimal"]) for row in michael] == [("SPY", "500")]


def test_a_delivery_netted_into_a_known_holding_is_still_attributed(ledger, monkeypatch):
    # Michael holds 500; an assigned call delivers -100; the account shows 400.
    _forecast(monkeypatch, {"SPY": -100})
    snapshot_id = ledger.ingest_account_snapshot(_book((2, "SPY", 400)))
    ledger.add_allocation(
        account_alias=ALIAS, conid=2, owner="michael", strategy="single_stock",
        quantity="500", effective_at="2026-08-17T13:00:00Z",
    )
    assert _lots(ledger, 2) == [
        ("michael", "single_stock", None, "500"),
        ("unallocated", "etf_0dte", "etf_0dte_delivery", "-100"),
    ]
    assert ledger.reconcile_allocations(snapshot_id, Decimal("0")) == []


def test_an_owner_lot_on_an_etf_0dte_option_is_ended_like_spx(ledger, monkeypatch):
    _forecast(monkeypatch, None)
    snapshot_id = ledger.ingest_account_snapshot(_book((4, "SPY", -2, {"sec_type": "OPT", "local": "SPY   261027P00570000"})))
    ledger.add_allocation(
        account_alias=ALIAS, conid=4, owner="drew", strategy="single_stock",
        quantity="-2", effective_at="2026-08-17T13:00:00Z",
    )
    assert _lots(ledger, 4) == [("unallocated", "etf_0dte", "etf_0dte", "-2")]
    assert ledger.reconcile_allocations(snapshot_id, Decimal("0")) == []


def test_hub_forecast_is_read_from_the_environment_on_the_new_york_date(tmp_path, monkeypatch):
    def write(session, shares, account="U805366"):
        path = tmp_path / "spy" / session / f"expected_delivery_{account}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"written_at": "x", "shares": shares}), encoding="utf-8")

    monkeypatch.delenv("ETF_0DTE_LIVE_DIR", raising=False)
    monkeypatch.delenv("ETF_0DTE_ACCOUNT", raising=False)
    assert load_etf_0dte_expected_delivery("U805366", as_of="2026-10-28T01:30:00Z") is None

    write("2026-10-27", {"SPY": -100})
    write("2026-10-28", {"SPY": 300})
    monkeypatch.setenv("ETF_0DTE_LIVE_DIR", str(tmp_path))
    # 01:30 UTC on the 28th is 21:30 on the 27th in New York: the 28th has not happened.
    assert load_etf_0dte_expected_delivery("U805366", as_of="2026-10-28T01:30:00Z") == {"SPY": -100.0}
    assert load_etf_0dte_expected_delivery("U805366", as_of="2026-10-28T14:00:00Z") == {"SPY": 300.0}
    assert load_etf_0dte_expected_delivery("primary", as_of="2026-10-28T14:00:00Z") is None
    monkeypatch.setenv("ETF_0DTE_ACCOUNT", "U805366")
    assert load_etf_0dte_expected_delivery("primary", as_of="2026-10-28T14:00:00Z") == {"SPY": 300.0}


# ------------------------------------------------------------- ticket guard

@pytest.mark.parametrize("identity", [
    {"symbol": "SPY", "sec_type": "STK", "local_symbol": "SPY"},
    {"symbol": "QQQ", "sec_type": "STK", "local_symbol": "QQQ"},
    {"symbol": "SPY", "sec_type": "OPT", "local_symbol": "SPY   261027C00580000", "trading_class": "SPY"},
    {"symbol": "QQQ", "sec_type": "OPT", "local_symbol": "QQQ   271217P00400000", "trading_class": "QQQ"},
])
def test_ticket_guard_refuses_every_spy_and_qqq_contract(identity):
    reason = etf_0dte_ticket_refusal(identity)
    assert reason and "etf-0dte" in reason and identity["symbol"] in reason


@pytest.mark.parametrize("identity", [
    {"symbol": "CSU", "sec_type": "STK", "local_symbol": "CSU"},
    {"symbol": "SPYG", "sec_type": "STK", "local_symbol": "SPYG"},
    {"symbol": "QQQM", "sec_type": "STK", "local_symbol": "QQQM"},
    {"symbol": "XSP", "sec_type": "OPT", "local_symbol": "XSP   270129P00540000", "trading_class": "XSP"},
    {"symbol": "SPX", "sec_type": "OPT", "local_symbol": "SPXW  260817P05000000", "trading_class": "SPXW"},
])
def test_ticket_guard_passes_everything_else(identity):
    assert etf_0dte_ticket_refusal(identity) is None
