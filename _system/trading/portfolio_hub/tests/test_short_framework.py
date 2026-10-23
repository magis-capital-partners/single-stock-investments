from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from _system.trading.portfolio_hub import short_framework as guard
from _system.trading.portfolio_hub.orders import GuardedOrderService
from _system.trading.portfolio_hub.ledger import PortfolioLedger
from _system.trading.portfolio_hub.tests.test_orders import FakeBroker, approve, make_intent


def ticket():
    return {"strategy": "short_framework", "account_alias": "test-account", "conid": 101,
            "action": "SELL", "quantity": "10", "limit_price": "10", "mode": "paper",
            "tif": "DAY", "outside_rth": False, "reduce_only": False}


def verified():
    return {"valid": True, "account_reference": "test-account", "request": {
        "framework_decision_id": "a" * 64, "conid": 101, "action": "SELL", "quantity": "10",
        "limit_price": "10", "mode": "paper", "tif": "DAY", "outside_rth": False}}


@pytest.fixture()
def ledger(tmp_path):
    value = PortfolioLedger(tmp_path / "framework-orders.db")
    value.migrate()
    yield value
    value.close()


@pytest.fixture()
def framework_runtime(monkeypatch):
    monkeypatch.setattr(guard.shutil, "which", lambda name: "test-node")
    monkeypatch.delenv("SHORT_FRAMEWORK_NODE", raising=False)
    monkeypatch.setattr(guard.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(verified())))


def test_exact_private_binding_and_ticket(framework_runtime):
    guard.validate_framework_order(ticket(), "SF1:" + "a" * 64 + ":" + "b" * 64)


def test_missing_private_binding_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ValueError, match="private reviewed"):
        guard.validate_framework_order(ticket(), None)


@pytest.mark.parametrize("key,value", [("quantity", "11"), ("limit_price", "10.01"),
                                       ("mode", "live"), ("conid", 102), ("action", "BUY")])
def test_changed_ticket_fails(framework_runtime, key, value):
    with pytest.raises(ValueError, match="changed"):
        guard.validate_framework_order({**ticket(), key: value}, "SF1:" + "a" * 64 + ":" + "b" * 64)


def test_account_isolation(framework_runtime):
    with pytest.raises(ValueError, match="this account"):
        guard.validate_framework_order({**ticket(), "account_alias": "other"}, "SF1:" + "a" * 64 + ":" + "b" * 64)


def test_unavailable_node_fails_closed(monkeypatch):
    monkeypatch.delenv("SHORT_FRAMEWORK_NODE", raising=False)
    monkeypatch.setattr(guard.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="runtime unavailable"):
        guard.validate_framework_order(ticket(), "SF1:" + "a" * 64 + ":" + "b" * 64)


def test_expired_private_record_fails_closed(monkeypatch):
    monkeypatch.setattr(guard.shutil, "which", lambda name: "test-node")
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match="missing, expired"):
        guard.validate_framework_order(ticket(), "SF1:" + "a" * 64 + ":" + "b" * 64)


def test_nonframework_orders_do_not_invoke_node(monkeypatch):
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    guard.validate_framework_order({"strategy": "single_stock"}, None)


def test_service_rechecks_private_evidence_after_human_approval(ledger, monkeypatch):
    calls = []
    def check(row, binding, **kwargs):
        calls.append(binding)
        if len(calls) > 1:
            raise ValueError("borrow approval expired")
    monkeypatch.setattr(guard, "validate_framework_order", check)
    broker = FakeBroker()
    broker.quote = lambda conid: {"conid": conid, "bid": "9.99", "ask": "10.01",
                                 "as_of": datetime.now(timezone.utc).isoformat(),
                                 "current_position": "0", "min_tick": "0.01", "multiplier": "1"}
    service = GuardedOrderService(ledger, broker, "test-secret")
    intent = replace(make_intent(), strategy="short_framework", action="SELL", reduce_only=False)
    created = service.create(intent, framework_binding="test-binding")
    approved = approve(service, created)
    assert service.submit(approved["intent_uuid"])["state"] == "Rejected"
    assert len(calls) == 2
    assert broker.placed == []


def test_entry_requires_confirmed_flat_instrument(ledger, monkeypatch):
    monkeypatch.setattr(guard, "validate_framework_order", lambda *a, **k: None)
    service = GuardedOrderService(ledger, FakeBroker(), "test-secret")
    intent = replace(make_intent(), strategy="short_framework", action="SELL", reduce_only=False)
    created = service.create(intent, framework_binding="test-binding")
    assert service.preview(created["intent_uuid"])["state"] == "Rejected"

