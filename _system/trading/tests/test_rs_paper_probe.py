"""Read-only paper probe tests; no socket, Gateway or vendor is ever contacted."""

import asyncio
import json
import socket
from types import SimpleNamespace

import pytest

from _system.trading.rs_paper_executor import __main__ as cli
from _system.trading.rs_paper_executor import probe as probe_module
from _system.trading.rs_paper_executor.policy import Policy
from _system.trading.rs_paper_executor.probe import (
    listener_processes,
    probe,
    require_local_ib_listener,
)
from _system.trading.rs_paper_executor.safety import PaperEndpoint, SafetyError

NOW = "2026-11-18T15:00:00+00:00"
ENDPOINT = PaperEndpoint("DU000000", 171, 4002)
POLICY = Policy(spx_reserve=1, cash_buffer=1, daily_loss_limit=1)  # synthetic


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect

    def forbidden(*args, **kwargs):
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


class Broker:
    """Paper adapter double. Any submit/cancel attempt fails the test."""

    def __init__(self, *, data_type=1, warning="", qualified=1001, accounts=("DU000000",)):
        self.connected = self.closed = False
        self.data_type, self.warning, self.qualified = data_type, warning, qualified
        self.ib = SimpleNamespace(managedAccounts=lambda: list(accounts))
        self.tickers, self.components, self.previews = {}, {}, []

    def now(self):
        return NOW

    async def connect(self):
        self.connected = True

    async def snapshot(self):
        return {"at": NOW, "account": "DU000000", "complete": True, "nav": 1e6,
                "available_funds": 9e5, "excess_liquidity": 9e5, "positions": {},
                "orders": [], "executions": []}

    async def qualify(self, signal):
        if signal["expected_conid"] != self.qualified:
            raise SafetyError("qualified stock does not match reviewed contract ID")
        return {"conid": self.qualified, "ticker": signal["ticker"]}

    async def quote(self, conid):
        self.tickers[conid] = SimpleNamespace(shortableShares=5000, halted=0)
        clocks = {k: NOW for k in ("bid_at", "ask_at", "bid_size_at", "ask_size_at",
                                   "shortable_at")}
        self.components[conid] = clocks
        return {"conid": conid, "bid": 2.5, "ask": 2.51, "bid_size": 300,
                "ask_size": 400, "market_data_type": self.data_type,
                "size_units": "shares", **clocks}

    async def margin(self, conid, shares, price):
        self.previews.append((conid, shares, price))
        return {"at": NOW, "account": "DU000000", "what_if": True,
                "initial_change": 10.0, "maintenance_change": 9.0,
                "initial_after": 10.0, "maintenance_after": 9.0,
                "warning": self.warning}

    async def submit(self, intent):
        raise AssertionError("probe must never submit")

    async def cancel(self, row):
        raise AssertionError("probe must never cancel")

    def close(self):
        self.closed = True


def go(broker, lookup=lambda port: ["java"], **kwargs):
    return asyncio.run(probe(ENDPOINT, POLICY, broker, lookup=lookup, **kwargs))


@pytest.mark.parametrize("names", [[], ["ssh"], ["sshd"], ["java", "ssh"],
                                   ["plink"], ["python"]])
def test_forwarded_or_unknown_listener_refuses_before_connect(names):
    b = Broker()
    with pytest.raises(SafetyError):
        go(b, lookup=lambda port: names, symbol="ABC", conid=1001)
    assert not b.connected


@pytest.mark.parametrize("names", [["java"], ["ibgateway"], ["tws"], ["javaw.exe"]])
def test_local_ib_listener_names_accepted(names):
    assert require_local_ib_listener(4002, lambda port: names) == names


def test_listener_lookup_parses_ss_and_powershell():
    ss = ('LISTEN 0 50 127.0.0.1:4002 0.0.0.0:* users:(("java",pid=812,fd=33))\n')
    run = lambda *a, **k: SimpleNamespace(stdout=ss)
    assert listener_processes(4002, run=run, system="posix") == ["java"]
    ps = "ibgateway\r\nibgateway\r\n"
    run = lambda *a, **k: SimpleNamespace(stdout=ps)
    assert listener_processes(4002, run=run, system="nt") == ["ibgateway"]


def test_full_read_only_probe_passes_without_any_order():
    b = Broker()
    report = go(b, symbol="ABC", conid=1001, shares=1)
    assert report["pass"] and report["orders_transmitted"] == 0
    assert report["live_orders_allowed"] is False and report["synthetic"] is False
    assert set(report["checks"]) == {
        "listener_is_local_ib", "paper_session_identity", "positions_complete",
        "account_values", "contract_identity", "realtime_two_sided_quote",
        "paper_shortable_tick", "broker_halt_state", "whatif_margin"}
    assert b.previews == [(1001, 1, 2.5)] and b.closed


def test_delayed_data_fails_and_skips_whatif():
    b = Broker(data_type=3)
    report = go(b, symbol="ABC", conid=1001)
    assert not report["pass"]
    assert not report["checks"]["realtime_two_sided_quote"]["pass"]
    assert not report["checks"]["whatif_margin"]["pass"] and b.previews == []


def test_whatif_warning_fails():
    report = go(Broker(warning="margin deficit"), symbol="ABC", conid=1001)
    assert not report["checks"]["whatif_margin"]["pass"] and not report["pass"]


def test_wrong_conid_fails_identity_and_requests_nothing_else():
    b = Broker(qualified=2002)
    report = go(b, symbol="ABC", conid=1001)
    assert not report["checks"]["contract_identity"]["pass"]
    assert "realtime_two_sided_quote" not in report["checks"] and b.previews == []


@pytest.mark.parametrize("kwargs", [{"symbol": "ABC"}, {"conid": 1001},
                                    {"symbol": "ABC", "conid": 1001, "shares": 500}])
def test_bad_probe_arguments_refuse_before_connect(kwargs):
    b = Broker()
    with pytest.raises(SafetyError):
        go(b, **kwargs)
    assert not b.connected


def test_account_only_probe_without_symbol():
    report = go(Broker())
    assert report["pass"] and "whatif_margin" not in report["checks"]


def test_cli_probe_requires_connect_flag(tmp_path, capsys):
    config = {"endpoint": {"account": "DU000000", "client_id": 171, "host": "127.0.0.1",
                           "port": 4002, "mode": "paper",
                           "deployment_role": "isolated_paper_executor"},
              "policy": {"spx_reserve": 1, "cash_buffer": 1, "daily_loss_limit": 1}}
    path = tmp_path / "c.json"
    path.write_text(json.dumps(config))
    assert cli.main(["probe", "--config", str(path)]) == 2
    assert "--connect-paper is required" in capsys.readouterr().out


def test_run_checks_listener_before_connect(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe_module, "listener_processes", lambda port: ["ssh"])
    attempted = []

    async def connect(self):
        attempted.append(True)

    monkeypatch.setattr(cli.PaperIBKR, "connect", connect)
    config = {"endpoint": {"account": "DU000000", "client_id": 171, "host": "127.0.0.1",
                           "port": 4002, "mode": "paper",
                           "deployment_role": "isolated_paper_executor"},
              "policy": {"spx_reserve": 1, "cash_buffer": 1, "daily_loss_limit": 1}}
    (tmp_path / "c.json").write_text(json.dumps(config))
    (tmp_path / "e.json").write_text("{}")
    (tmp_path / "o.json").write_text("{}")
    code = cli.main(["run", "--config", str(tmp_path / "c.json"), "--connect-paper",
                     "--state", str(tmp_path / "s.sqlite"), "--evidence",
                     str(tmp_path / "e.json"), "--operations-file",
                     str(tmp_path / "o.json"), "--once"])
    assert code == 2 and not attempted
    assert "not served only by a local IB" in capsys.readouterr().out
