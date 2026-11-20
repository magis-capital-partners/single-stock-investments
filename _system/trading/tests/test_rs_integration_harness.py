"""Stage-6 harness logic against a simulated paper broker (no socket)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from _system.trading.rs_paper_executor.integration import run_integration
from _system.trading.rs_paper_executor.policy import Policy
from _system.trading.rs_paper_executor.safety import LiveEndpoint, PaperEndpoint, SafetyError
from _system.trading.tests.test_rs_paper_executor import (  # noqa: F401 (fixture)
    NOW,
    Broker,
    no_network,
    run,
)

ENDPOINT = PaperEndpoint("DU000000", 171, 4002)
POLICY = Policy(spx_reserve=1_000_000, cash_buffer=100_000, daily_loss_limit=2500)


class SimBroker(Broker):
    """Marketable orders fill in two partials over two snapshots; far orders rest;
    cancels confirm on the next snapshot; the clock advances with sleep."""

    def __init__(self):
        super().__init__()
        self.tickers = {1001: SimpleNamespace(shortableShares=50_000, halted=0)}
        self.pending_cancel, self.reconnects = [], 0
        self.ib = SimpleNamespace(disconnect=lambda: None, isConnected=lambda: True)

    def advance(self, seconds):
        at = datetime.fromisoformat(self.clock) + timedelta(seconds=seconds)
        self.clock = at.isoformat()

    async def connect(self):
        self.reconnects += 1

    async def quote(self, conid):
        q = await super().quote(conid)
        return {**q, **{k: self.clock for k in ("bid_at", "ask_at", "bid_size_at", "ask_size_at")}}

    async def margin(self, conid, shares, price):
        return {**(await super().margin(conid, shares, price)), "at": self.clock}

    async def cancel(self, row):
        await super().cancel(row)
        self.pending_cancel.append(row["ref"])

    async def snapshot(self):
        for i, row in enumerate(self.snap["orders"]):
            if row["state"] != "working":
                continue
            if row["ref"] in self.pending_cancel:
                row["state"] = "cancelled"
                continue
            marketable = (row["side"] == "SELL" and row["limit"] <= self.book["bid"]) or (
                row["side"] == "BUY" and row["limit"] >= self.book["ask"])
            if marketable:
                left = row["shares"] - row["filled"]
                self.execute(index=i, shares=max(1, left // 2) if row["filled"] == 0 else left,
                             exec_id=f"{row['ref']}:{row['filled']}")
        snap = await super().snapshot()
        snap["at"] = self.clock
        for e in snap["executions"]:
            e.setdefault("at", self.clock)
        return snap


def test_stage6_sequence_passes_on_a_well_behaved_paper_broker(tmp_path):
    b = SimBroker()

    async def sleep(seconds):
        b.advance(seconds)

    report = run(run_integration(ENDPOINT, POLICY, b, tmp_path / "t.integration.sqlite",
                                 symbol="TEST", conid=1001, sleep=sleep))
    failed = {k: v for k, v in report["steps"].items() if not v["pass"]}
    assert report["pass"], failed
    assert report["synthetic_control"] is True and report["paper_only"] is True
    assert report["steps"]["entry_fill"]["partial_fills"] >= 1
    assert report["steps"]["margin_rejection"]["orders_sent"] == 0
    assert b.reconnects == 1


def test_stage6_refuses_live_reused_or_misnamed_journal(tmp_path):
    with pytest.raises(SafetyError):
        run(run_integration(LiveEndpoint("U1234567", 60, 7496), POLICY, SimBroker(),
                            tmp_path / "t.integration.sqlite", symbol="TEST", conid=1001))
    with pytest.raises(SafetyError):
        run(run_integration(ENDPOINT, POLICY, SimBroker(), tmp_path / "state.sqlite",
                            symbol="TEST", conid=1001))
    existing = tmp_path / "old.integration.sqlite"
    existing.write_text("")
    with pytest.raises(SafetyError):
        run(run_integration(ENDPOINT, POLICY, SimBroker(), existing, symbol="TEST", conid=1001))


def test_stage6_reports_a_broker_that_never_confirms_cancel(tmp_path):
    b = SimBroker()

    async def never(row):
        b.cancelled.append(row)

    b.cancel = never

    async def sleep(seconds):
        b.advance(seconds)

    report = run(run_integration(ENDPOINT, POLICY, b, tmp_path / "t.integration.sqlite",
                                 symbol="TEST", conid=1001, sleep=sleep, timeout=40))
    assert report["steps"]["cancel_confirmed"]["pass"] is False and report["pass"] is False


from _system.trading.rs_paper_executor.integration import reference_price, run_mechanics  # noqa: E402


def delayed_broker():
    b = SimBroker()
    b.book["market_data_type"] = 3
    b.tickers[1001].last, b.tickers[1001].close = 10.0, 9.9
    b.ib.reqMarketDataType = lambda kind: setattr(b, "data_type", kind)
    return b


def test_mechanics_sequence_on_delayed_paper_data(tmp_path):
    b = delayed_broker()

    async def sleep(seconds):
        b.advance(seconds)

    report = run(run_mechanics(ENDPOINT, POLICY, b, tmp_path / "m.integration.sqlite",
                               symbol="TEST", conid=1001, shares=10, sleep=sleep))
    failed = {k: v for k, v in report["steps"].items() if not v["pass"]}
    assert report["pass"], failed
    assert report["mode"] == "mechanics_only" and b.data_type == 3
    assert report["reference"]["source"] == "delayed_mid"
    assert report["steps"]["delayed_quote_refused"]["reason"].startswith("live identified")
    assert report["steps"]["entry_fill"]["partial_fills"] == 1
    assert [(x["side"], x["shares"]) for x in b.sent] == [("SELL", 10), ("SELL", 1), ("BUY", 10)]


def test_reference_price_fallbacks():
    ticker = type("T", (), {"last": float("nan"), "close": 12.5})()
    assert reference_price({"bid": None, "ask": None}, ticker) == (12.5, "delayed_close")
    empty = type("T", (), {})()
    assert reference_price({}, empty, 20) == (20.0, "operator")
    with pytest.raises(SafetyError):
        reference_price({"bid": 0, "ask": 0}, empty)


@pytest.mark.parametrize("kwargs", [dict(shares=0), dict(shares=101)])
def test_mechanics_bounds(tmp_path, kwargs):
    with pytest.raises(SafetyError):
        run(run_mechanics(ENDPOINT, POLICY, delayed_broker(), tmp_path / "m.integration.sqlite",
                          symbol="TEST", conid=1001, **kwargs))
    with pytest.raises(SafetyError):
        run(run_mechanics(LiveEndpoint("U1234567", 60, 7496), POLICY, delayed_broker(),
                          tmp_path / "m2.integration.sqlite", symbol="TEST", conid=1001))
