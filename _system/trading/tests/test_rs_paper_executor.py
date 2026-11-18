"""Executable safety tests; no socket, Gateway or vendor is ever contacted."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
import socket
from types import SimpleNamespace

import pytest

from _system.trading.rs_paper_executor.engine import Executor
from _system.trading.rs_paper_executor.ibkr import (
    PaperIBKR,
    account_values,
    positions_for_account,
)
from _system.trading.rs_paper_executor.journal import Journal
from _system.trading.rs_paper_executor.policy import Calendar, Policy
from _system.trading.rs_paper_executor.safety import PaperEndpoint, SafetyError, number

NOW = "2026-11-18T15:00:00+00:00"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect

    def forbidden(*args, **kwargs):
        # Windows asyncio creates its own local wake-up socketpair. Only that
        # stdlib implementation may connect; all application sockets fail.
        import sys

        caller = sys._getframe(1).f_code
        if (
            caller.co_name in ("socketpair", "_fallback_socketpair")
            and caller.co_filename == socket.__file__
        ):
            return original(*args, **kwargs)
        raise AssertionError("test attempted a real socket connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def signal(**changes):
    result = dict(
        id="primary:one",
        action_id="issuer1:2026-11-25:10",
        cik="12345",
        ticker="TEST",
        expected_conid=1001,
        status="scheduled",
        ratio=10,
        action_day="2026-11-25",
        instrument_type="CS",
        currency="USD",
        identity_verified=True,
        conditions_resolved=True,
        source_sha256="a" * 64,
        published_at="2026-11-18T14:59:00Z",
        first_seen_at="2026-11-18T14:59:10Z",
        identity_known_at="2026-11-18T14:59:11Z",
        terms_known_at="2026-11-18T14:59:12Z",
        financial_known_at="2026-11-18T14:59:13Z",
        history_known_at="2026-11-18T14:59:14Z",
        ordinal_min=2,
        score=34,
        signal_count=5,
        period="2026-06-30",
    )
    return {**result, **changes}


class Broker:
    def __init__(self):
        self.clock = NOW
        self.sent, self.cancelled = [], []
        self.snap = dict(
            at=NOW,
            account="DU000000",
            complete=True,
            nav=10_000_000,
            available_funds=5_000_000,
            excess_liquidity=5_000_000,
            positions={},
            orders=[],
            executions=[],
        )
        self.book = dict(
            conid=1001,
            bid=10,
            ask=10.01,
            bid_size=10000,
            ask_size=10000,
            bid_at=NOW,
            ask_at=NOW,
            bid_size_at=NOW,
            ask_size_at=NOW,
            market_data_type=1,
            size_units="shares",
        )
        self.proof = dict(
            conid=1001,
            at=NOW,
            complete=True,
            source_verified=True,
            halted=False,
            ssr=False,
        )
        self.loan = dict(conid=1001, at=NOW, apr=0.5, available_shares=10000)
        self.preview = dict(
            at=NOW,
            account="DU000000",
            what_if=True,
            initial_change=10000,
            maintenance_change=10000,
            initial_after=20000,
            maintenance_after=20000,
            warning="",
        )
        self.fail_submit = False

    def now(self):
        return self.clock

    async def snapshot(self):
        return deepcopy(self.snap)

    async def qualify(self, s):
        return dict(conid=1001, ticker=s["ticker"], sec_type="STK", currency="USD")

    async def quote(self, conid):
        return deepcopy(self.book)

    async def eligibility(self, conid):
        return deepcopy(self.proof)

    async def borrow(self, conid):
        return deepcopy(self.loan)

    async def margin(self, conid, shares, price):
        return deepcopy(self.preview)

    async def submit(self, intent):
        self.sent.append(deepcopy(intent))
        if self.fail_submit:
            raise ConnectionError("ack lost after possible transmission")
        self.snap["orders"].append(
            {
                **intent,
                "client_id": 171,
                "state": "working",
                "filled": 0,
                "order_id": len(self.sent),
                "perm_id": 100 + len(self.sent),
            }
        )
        return dict(order_id=len(self.sent), perm_id=100 + len(self.sent))

    async def cancel(self, row):
        self.cancelled.append(deepcopy(row))

    def execute(self, index=0, shares=None, exec_id="fill1"):
        row = self.snap["orders"][index]
        qty = shares if shares is not None else row["shares"] - row["filled"]
        row["filled"] += qty
        row["state"] = "filled" if row["filled"] == row["shares"] else "working"
        delta = -qty if row["side"] == "SELL" else qty
        self.snap["positions"][1001] = self.snap["positions"].get(1001, 0) + delta
        self.snap["executions"].append(
            {
                **row,
                "shares": qty,
                "price": row["limit"],
                "exec_id": exec_id,
                "at": self.clock,
                "commission": 1,
            }
        )


@pytest.fixture
def setup(tmp_path):
    policy = Policy(spx_reserve=1_000_000, cash_buffer=100_000, daily_loss_limit=2500)
    journal = Journal(tmp_path / "paper.sqlite", policy.digest)
    broker = Broker()
    engine = Executor(PaperEndpoint("DU000000", 171, 4002), policy, journal, broker)
    yield engine, journal, broker
    journal.close()


def run(awaitable):
    return asyncio.run(awaitable)


def test_defaults_are_not_approved_capital():
    with pytest.raises(SafetyError):
        Policy().validate()


@pytest.mark.parametrize(
    "change",
    [
        dict(account="U123"),
        dict(host="ny4"),
        dict(port=7496),
        dict(port=4001),
        dict(mode="live"),
        dict(client_id=17),
        dict(client_id=50),
        dict(client_id=91),
        dict(client_id=0),
        dict(client_id=True),
    ],
)
def test_live_endpoints_and_production_ids_block_before_connect(change):
    with pytest.raises(SafetyError):
        replace(PaperEndpoint("DU000000", 171, 4002), **change).validate()


@pytest.mark.parametrize(
    "value", [None, "", "NaN", float("inf"), "1.7976931348623157E308", True]
)
def test_ib_unset_numbers_are_not_zero(value):
    with pytest.raises(SafetyError):
        number(value)


def test_second_writer_and_policy_change_rejected(tmp_path):
    file = tmp_path / "state.sqlite"
    one = Journal(file, "a")
    with pytest.raises(SafetyError):
        Journal(file, "a")
    one.close()
    with pytest.raises(SafetyError):
        Journal(file, "b")


def test_successful_margin_checked_entry_and_dedup(setup):
    e, j, b = setup
    ref = run(e.enter(signal(), b.snap, NOW))
    assert b.sent[0]["side"] == "SELL" and b.sent[0]["shares"] == 500
    assert j.rows("orders")[0]["ref"] == ref
    assert j.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    with pytest.raises(SafetyError):
        run(e.enter(signal(id="other-source"), b.snap, NOW))
    assert len(b.sent) == 1


@pytest.mark.parametrize(
    "change",
    [
        dict(score=None),
        dict(signal_count=2),
        dict(period="2025-09-30"),
        dict(ordinal_min=1),
        dict(status="authorization"),
        dict(identity_verified=False),
        dict(instrument_type="ADR"),
        dict(conditions_resolved=False),
        dict(published_at="2026-11-18T14:00:00Z"),
        dict(financial_known_at="2026-11-18T16:00:00Z"),
    ],
)
def test_original_clock_and_financial_gates(setup, change):
    e, _, b = setup
    with pytest.raises(SafetyError):
        run(e.enter(signal(**change), b.snap, NOW))
    assert not b.sent


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_change", "NaN"),
        ("maintenance_change", "1.7976931348623157E308"),
        ("initial_after", None),
        ("account", "DUOTHER"),
        ("what_if", False),
        ("warning", "insufficient"),
    ],
)
def test_margin_missing_sentinel_or_warning_never_places(setup, field, value):
    e, _, b = setup
    b.preview[field] = value
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


def test_margin_reserve_blocks_despite_large_nav(setup):
    e, _, b = setup
    b.snap["excess_liquidity"] = 1_105_000
    with pytest.raises(SafetyError, match="SPX reserve"):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


@pytest.mark.parametrize(
    "field,value",
    [
        ("market_data_type", 3),
        ("ask_at", "2026-11-18T14:58:00Z"),
        ("ask_size", 0),
        ("size_units", "lots"),
        ("ask", 12),
    ],
)
def test_quote_gates(setup, field, value):
    e, _, b = setup
    b.book[field] = value
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


@pytest.mark.parametrize(
    "field,value", [("halted", True), ("ssr", True), ("ssr", None), ("complete", False)]
)
def test_unknown_or_restricted_eligibility(setup, field, value):
    e, _, b = setup
    b.proof[field] = value
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


def test_partial_fills_duplicate_callbacks_and_scoped_cover(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    b.execute(shares=100)
    run(e.reconcile(NOW))
    run(e.reconcile(NOW))
    assert j.rows("positions")[0]["shares"] == 100
    assert len(j.rows("fills")) == 1
    j.set("kill", True)
    b.snap["orders"].append(
        dict(
            ref="SPX0DTE|FOREIGN",
            side="SELL",
            state="working",
            account="DU000000",
            client_id=17,
        )
    )
    run(e.protect(b.snap, NOW))
    assert [r["ref"] for r in b.cancelled] == [j.rows("orders")[0]["ref"]]
    assert len(b.sent) == 1  # never cover while entry cancellation is uncertain
    b.snap["orders"][0]["state"] = "cancelled"
    run(e.reconcile(NOW))
    run(e.protect(b.snap, NOW))
    assert b.sent[-1]["side"] == "BUY" and b.sent[-1]["shares"] == 100
    b.execute(index=2, exec_id="cover1")
    run(e.reconcile(NOW))
    assert j.rows("positions")[0]["shares"] == 0


def test_lost_ack_is_durable_and_not_retried(setup):
    e, j, b = setup
    b.fail_submit = True
    with pytest.raises(ConnectionError):
        run(e.enter(signal(), b.snap, NOW))
    assert j.rows("orders")[0]["state"] == "uncertain"
    run(e.tick([signal()], NOW))
    assert len(b.sent) == 1 and j.get("entry_halt")


def test_stop_and_daily_loss_cover_from_live_ask(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    b.execute()
    run(e.reconcile(NOW))
    b.book["ask"] = 16
    run(e.protect(b.snap, NOW))
    assert j.get("entry_halt") == "daily_loss_limit"
    assert b.sent[-1]["side"] == "BUY"


def test_foreign_broker_position_and_wrong_contract_rejected(setup):
    e, _, b = setup
    b.snap["positions"][1001] = 100
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    b.snap["positions"].clear()
    with pytest.raises(SafetyError):
        run(e.enter(signal(expected_conid=1002), b.snap, NOW))


def test_journal_failure_happens_before_submission(setup, monkeypatch):
    e, j, b = setup

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(j, "intent", fail)
    with pytest.raises(OSError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


def test_calendar_half_day_and_out_of_range():
    c = Calendar()
    assert c.exit_at("2026-11-27T15:00:00Z", 1) == "2026-11-27T17:59:00+00:00"
    with pytest.raises(SafetyError):
        c.exit_at("2030-01-02T15:00:00Z", 5)


def test_endpoint_rejects_live_managed_account_even_on_paper_port():
    e = PaperEndpoint("DU000000", 171, 4002)
    with pytest.raises(SafetyError):
        e.prove_session(["DU000000", "U123"], 171)


def test_paper_connect_checks_session_before_requests():
    class WrongIB:
        def __init__(self):
            self.client = SimpleNamespace(clientId=171)
            self.closed = False

        async def connectAsync(self, *args, **kwargs):
            pass

        def isConnected(self):
            return True

        def managedAccounts(self):
            return ["U123"]

        def disconnect(self):
            self.closed = True

    ib = WrongIB()
    broker = PaperIBKR(PaperEndpoint("DU000000", 171, 4002), lambda: {}, ib=ib)
    with pytest.raises(SafetyError):
        run(broker.connect())
    assert ib.closed


def test_position_error_completion_is_not_complete_snapshot():
    async def scenario():
        cancelled = []

        class Wrapper:
            def __init__(self):
                self._futures, self._results = {}, {}

            def startReq(self, req):
                f = asyncio.get_running_loop().create_future()
                self._futures[req] = f
                self._results[req] = []
                return f

            def _endReq(self, req):
                self._futures.pop(req).set_result(None)

            def positionMulti(self, *args):
                pass

            def positionMultiEnd(self, *args):
                pass

        w = Wrapper()

        def request(req, *args):
            w._endReq(req)  # ib_insync error path can complete a future
            w.positionMultiEnd(req)  # late end must not upgrade it

        ib = SimpleNamespace(
            wrapper=w,
            client=SimpleNamespace(
                getReqId=lambda: 1,
                reqPositionsMulti=request,
                cancelPositionsMulti=cancelled.append,
            ),
        )
        with pytest.raises(SafetyError):
            await positions_for_account(ib, "DU000000")
        assert cancelled == [1] and not w._futures and not w._results

    run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        ("apr", None),
        ("apr", 2),
        ("available_shares", 0),
        ("at", "2026-11-18T12:00:00Z"),
        ("conid", 999),
    ],
)
def test_borrow_is_quantity_rate_clock_and_identity_bound(setup, field, value):
    e, _, b = setup
    b.loan[field] = value
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


def advance(b, seconds):
    b.clock = (datetime.fromisoformat(b.clock) + timedelta(seconds=seconds)).isoformat()
    b.snap["at"] = b.clock
    b.proof["at"] = b.clock
    b.loan["at"] = b.clock
    b.preview["at"] = b.clock
    for field in ["bid_at", "ask_at", "bid_size_at", "ask_size_at"]:
        b.book[field] = b.clock


def test_entry_cancel_expiry_does_not_assume_confirmation(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    advance(b, 31)
    run(e.expire_orders(b.snap, b.clock))
    run(e.expire_orders(b.snap, b.clock))
    assert len(b.cancelled) == 1
    assert j.rows("orders")[0]["state"] == "working"
    advance(b, 31)
    run(e.expire_orders(b.snap, b.clock))
    assert j.get("entry_halt") == "cancellation_unconfirmed"


def test_unfilled_cover_is_cancelled_then_repriced_after_confirmation(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    b.execute()
    run(e.reconcile(NOW))
    j.set("kill", True)
    run(e.protect(b.snap, NOW))
    advance(b, 16)
    run(e.expire_orders(b.snap, b.clock))
    run(e.protect(b.snap, b.clock))
    assert b.cancelled[-1]["side"] == "BUY" and len(b.sent) == 2
    b.snap["orders"][1]["state"] = "cancelled"
    run(e.reconcile(b.clock))
    run(e.protect(b.snap, b.clock))
    assert len(b.sent) == 3 and b.sent[-1]["shares"] == 500
    assert b.sent[1]["ref"] != b.sent[2]["ref"]


def test_kill_during_margin_preview_never_places_entry(setup):
    e, j, b = setup

    async def preview(*args):
        j.set("kill", True)
        return b.preview

    b.margin = preview
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


def test_margin_delay_rechecks_original_publication_window(setup):
    e, _, b = setup

    async def preview(*args):
        advance(b, 901)
        return b.preview

    b.margin = preview
    with pytest.raises(SafetyError):
        run(e.enter(signal(), b.snap, NOW))
    assert not b.sent


def test_wrong_or_old_account_snapshot_is_not_margin_permission(setup):
    e, _, b = setup
    for changes in [
        dict(account="DU999"),
        dict(at="2026-11-18T12:00:00Z"),
        dict(complete=False),
    ]:
        with pytest.raises(SafetyError):
            run(e.enter(signal(), {**b.snap, **changes}, NOW))
    assert not b.sent


def test_decision_time_inputs_are_saved_before_submit(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    saved = json.loads(j.rows("orders")[0]["payload"])["signal"]
    assert saved["entry_evidence"]["quote"]["bid_size"] == 10000
    assert saved["entry_evidence"]["margin"]["what_if"] is True
    assert saved["entry_evidence"]["borrow"]["apr"] == 0.5


def test_recovery_imports_broker_fill_without_a_second_submission(tmp_path):
    p = Policy(spx_reserve=1_000_000, cash_buffer=100_000, daily_loss_limit=2500)
    file = tmp_path / "recovery.sqlite"
    j = Journal(file, p.digest)
    b = Broker()
    e = Executor(PaperEndpoint("DU000000", 171, 4002), p, j, b)
    run(e.enter(signal(), b.snap, NOW))
    j.close()
    b.execute()
    j = Journal(file, p.digest)
    try:
        recovered = Executor(e.endpoint, p, j, b)
        run(recovered.tick([signal()], NOW))
        assert len(b.sent) == 1 and j.rows("positions")[0]["shares"] == 500
    finally:
        j.close()


def test_closed_paper_borrow_estimate_is_not_erased(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    b.execute()
    run(e.reconcile(NOW))
    j.set("kill", True)
    run(e.protect(b.snap, NOW))
    b.execute(index=1, exec_id="cover1")
    run(e.reconcile(NOW))
    run(e.protect(b.snap, NOW))
    assert j.get("last_pnl") < -2  # spread + commission + retained modeled borrow


def test_missing_box_r_proposals_does_not_prevent_time_exit(setup):
    e, j, b = setup
    run(e.enter(signal(), b.snap, NOW))
    b.execute()
    run(e.reconcile(NOW))
    with j.db:
        j.db.execute("UPDATE positions SET exit_at=?", (NOW,))
    run(e.tick([], NOW))
    assert b.sent[-1]["side"] == "BUY"


def test_box_r_runtime_refuses_before_adapter_connect(monkeypatch):
    monkeypatch.setenv("RS_COLLECTOR_HOST", "lightsail")
    with pytest.raises(SafetyError, match="Box R"):
        run(PaperIBKR(PaperEndpoint("DU000000", 171, 4002), lambda: {}).connect())


def test_real_adapter_margin_builds_only_a_whatif_stock_sell(monkeypatch):
    import sys

    orders = []

    def limit_order(action, qty, price, **kwargs):
        x = SimpleNamespace(action=action, totalQuantity=qty, lmtPrice=price, **kwargs)
        orders.append(x)
        return x

    monkeypatch.setitem(
        sys.modules, "ib_insync", SimpleNamespace(LimitOrder=limit_order)
    )

    class IB:
        client = SimpleNamespace(clientId=171)

        def isConnected(self):
            return True

        def managedAccounts(self):
            return ["DU000000"]

        async def whatIfOrderAsync(self, contract, order):
            return SimpleNamespace(
                initMarginChange="123",
                maintMarginChange="124",
                initMarginAfter="200",
                maintMarginAfter="201",
                warningText="",
            )

    b = PaperIBKR(
        PaperEndpoint("DU000000", 171, 4002), lambda: {}, ib=IB(), clock=lambda: NOW
    )
    b.contracts[1001] = SimpleNamespace(conId=1001)
    preview = run(b.margin(1001, 73, 2.55))
    assert preview["initial_change"] == "123"
    assert (
        orders[0].action,
        orders[0].totalQuantity,
        orders[0].whatIf,
        orders[0].account,
    ) == ("SELL", 73, True, "DU000000")


def test_complete_positions_cancel_subscription_on_success():
    async def scenario():
        cancelled = []

        class Wrapper:
            def __init__(self):
                self._futures, self._results = {}, {}

            def startReq(self, req):
                f = asyncio.get_running_loop().create_future()
                self._futures[req] = f
                self._results[req] = []
                return f

            def _endReq(self, req):
                self._futures.pop(req).set_result(None)

            def positionMulti(self, *args):
                pass

            def positionMultiEnd(self, *args):
                pass

        w = Wrapper()

        def request(req, account, model):
            w.positionMulti(req, account, model, SimpleNamespace(conId=1001), -73, 2)
            w.positionMultiEnd(req)

        ib = SimpleNamespace(
            wrapper=w,
            client=SimpleNamespace(
                getReqId=lambda: 1,
                reqPositionsMulti=request,
                cancelPositionsMulti=cancelled.append,
            ),
        )
        assert await positions_for_account(ib, "DU000000") == {1001: -73}
        assert cancelled == [1] and not w._futures

    run(scenario())


def test_account_snapshot_cannot_reuse_missing_cached_margin():
    async def scenario():
        cancelled = []

        class Wrapper:
            def __init__(self):
                self._futures, self._results = {}, {}

            def startReq(self, req):
                f = asyncio.get_running_loop().create_future()
                self._futures[req] = f
                return f

            def _endReq(self, req):
                self._futures.pop(req).set_result(None)

            def accountSummary(self, *args):
                pass

        w = Wrapper()

        def request(req, group, tags):
            w.accountSummary(req, "DU000000", "NetLiquidation", "10000000", "USD")
            w._endReq(req)  # two mandatory account fields never arrived

        ib = SimpleNamespace(
            wrapper=w,
            client=SimpleNamespace(
                getReqId=lambda: 1,
                reqAccountSummary=request,
                cancelAccountSummary=cancelled.append,
            ),
        )
        with pytest.raises(SafetyError):
            await account_values(ib, "DU000000")
        assert cancelled == [1]

    run(scenario())


def test_inbox_uses_existing_box_r_snapshot_without_mutating_it():
    from _system.trading.rs_paper_executor.inbox import proposals

    candidate = {
        "id": "sec:one",
        "ticker": "TEST",
        "cik": "12345",
        "status": "scheduled",
        "checks": {"announcement": {"state": "pass"}, "repeat": {"state": "pass"}},
        "implementation_conditions": [],
        "source_urls": [{"sha256": "a" * 64}],
        "analyzed_at": "2026-11-18T14:59:20Z",
        "published_at": "2026-11-18T14:59:00Z",
        "first_seen_at": "2026-11-18T14:59:10Z",
        "ordinal_min": 2,
        "financials": {"score": 34, "signal_count": 5, "period": "2026-06-30"},
    }
    operations = {"generated_at": NOW, "candidates": [candidate]}
    original = deepcopy(operations)
    proof = {
        "identities": {
            "TEST": {
                "cik": "12345",
                "conid": 1001,
                "type": "CS",
                "currency": "USD",
                "verified": True,
                "at": "2026-11-18T14:59:30Z",
                "valid_until": "2026-11-18T21:00:00Z",
                "source_url": "https://example.invalid/verified-reference",
                "source_sha256": "b" * 64,
                "action_source_sha256": "a" * 64,
                "action_day": "2026-11-25",
                "ratio": 10,
                "conditions_resolved": True,
                "action_id": "canonical-action",
            }
        }
    }
    rows = proposals(operations, proof, NOW)
    assert len(rows) == 1 and rows[0]["expected_conid"] == 1001
    assert operations == original
    proof["identities"]["TEST"]["action_source_sha256"] = "c" * 64
    assert not proposals(operations, proof, NOW)
    with pytest.raises(SafetyError):
        proposals({**operations, "generated_at": "2026-11-18T13:00:00Z"}, proof, NOW)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.cloudflare.com/x",
        "https://evil.invalid/x",
        "https://api.cloudflare.com/wrong-path",
        "https://user@api.cloudflare.com/x",
    ],
)
def test_inbox_rejects_untrusted_hosts_before_network(url):
    from _system.trading.rs_paper_executor.inbox import read_https

    with pytest.raises(SafetyError):
        read_https(url, "not-a-token")


def test_cli_preflight_and_missing_connect_flag_open_no_socket(tmp_path, capsys):
    from _system.trading.rs_paper_executor.__main__ import main
    from dataclasses import asdict

    config = tmp_path / "paper.json"
    config.write_text(
        json.dumps(
            {
                "endpoint": asdict(PaperEndpoint("DU000000", 171, 4002)),
                "policy": asdict(
                    Policy(
                        spx_reserve=1_000_000, cash_buffer=100000, daily_loss_limit=2500
                    )
                ),
            }
        )
    )
    assert main(["preflight", "--config", str(config)]) == 0
    assert json.loads(capsys.readouterr().out)["connection_opened"] is False
    assert main(["run", "--config", str(config)]) == 2
    assert "no connection was opened" in capsys.readouterr().out


def test_notification_outbox_redacts_retries_and_never_loses_event(setup):
    from _system.trading.rs_paper_executor.notify import deliver_alerts

    _, j, _ = setup
    j.event(
        NOW, "entry_halt", {"account": "DO-NOT-SEND", "error": "SECRET-DO-NOT-SEND"}
    )
    calls = []

    def failed(url, body):
        raise OSError("network unavailable")

    with pytest.raises(OSError):
        deliver_alerts(j, "https://hooks.slack.com/services/test", NOW, post=failed)
    assert j.get("alert_cursor", 0) == 0
    later = (datetime.fromisoformat(NOW) + timedelta(seconds=61)).isoformat()
    deliver_alerts(
        j,
        "https://hooks.slack.com/services/test",
        later,
        post=lambda url, body: calls.append(body),
    )
    assert len(calls) == 1
    assert "DO-NOT-SEND" not in json.dumps(calls)
    assert j.get("alert_cursor") > 0
    with pytest.raises(SafetyError):
        deliver_alerts(j, "https://evil.invalid/services/test", later, post=failed)
