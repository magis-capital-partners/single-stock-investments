"""Shadow-only evaluation when halt/SSR state is unknown (owner 2026-11-19, option B).

No intraday source today can say "SSR clear", so every strict eligibility check
fails. In SHADOW only, the later gates still run and are recorded as a
conditional would-be entry. A known halt or restriction still refuses, an armed
executor refuses exactly as before, and nothing is ever transmitted on it.
No socket, Gateway or vendor is contacted.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from _system.trading.rs_evidence.eligibility import build_eligibility
from _system.trading.rs_paper_executor.engine import Executor
from _system.trading.rs_paper_executor.ibkr import PaperIBKR
from _system.trading.rs_paper_executor.journal import Journal
from _system.trading.rs_paper_executor.safety import PaperEndpoint, SafetyError
from _system.trading.rs_paper_executor.shadow_report import shadow_report
from _system.trading.tests.test_rs_evidence_producers import halt_feed, restriction
from _system.trading.tests.test_rs_live_guards import (  # noqa: F401 (fixtures)
    events,
    live,
    no_network,
)
from _system.trading.tests.test_rs_paper_executor import NOW, Broker, run, signal
from _system.trading.tests.test_rs_shadow_report import build

UNKNOWN = dict(conid=1001, at=NOW, complete=False, source_verified=False,
               halted=None, ssr=None,
               missing=["halt_clearance_source_not_approved",
                        "intraday_ssr_clearance_source_absent"])


class Counting:
    """Wraps the fake broker and counts the calls that cost Gateway traffic."""

    def __init__(self, broker):
        self.inner, self.calls = broker, []
        for name in ("quote", "borrow", "margin"):
            setattr(self, name, self._wrap(name))

    def _wrap(self, name):
        async def call(*args):
            self.calls.append(name)
            return await getattr(self.inner, name)(*args)
        return call

    def __getattr__(self, name):
        return getattr(self.inner, name)


@pytest.fixture
def box(request):
    """The live-mode executor of test_rs_live_guards (client 60, arm file valid)."""
    return request.getfixturevalue("live")


def shadow(box):
    box.arm.unlink()
    box.broker.proof = dict(UNKNOWN)
    return box


# ---- the conditional path ------------------------------------------------

def test_unknown_ssr_in_shadow_runs_the_later_gates_and_records_once(box):
    shadow(box)
    counting = Counting(box.broker)
    box.engine.broker = counting
    assert run(box.engine.enter(signal(), box.broker.snap, NOW)) is None
    assert box.broker.sent == [] and box.journal.rows("orders") == []
    assert box.claims.held(NOW) == set()  # shadow never claims a name
    assert events(box.journal, "shadow_entry") == []
    (row,) = events(box.journal, "shadow_entry_conditional")
    assert row["eligibility_unknown"] == ["halted", "ssr"]
    assert row["eligibility_missing"] == UNKNOWN["missing"]
    assert row["reason"] == "arm file absent" and row["shares"] > 0
    assert row["initial_margin"] == 10000 and row["maintenance_margin"] == 10000
    assert {"quote", "borrow", "margin"} <= set(counting.calls)
    # Recorded once: the next cycles do not repeat quote, borrow or WhatIf.
    before = list(counting.calls)
    for _ in range(3):
        assert run(box.engine.enter(signal(), box.broker.snap, NOW)) is None
    assert counting.calls == before
    assert len(events(box.journal, "shadow_entry_conditional")) == 1


def test_armed_executor_refuses_unknown_ssr_exactly_as_before(box):
    box.broker.proof = dict(UNKNOWN)  # arm file present and valid
    with pytest.raises(SafetyError, match="fresh eligibility source required"):
        run(box.engine.enter(signal(), box.broker.snap, NOW))
    assert box.broker.sent == [] and box.journal.rows("orders") == []
    assert events(box.journal, "shadow_entry_conditional") == []


def test_an_arm_that_appears_mid_evaluation_still_never_transmits(box):
    shadow(box)
    answers = iter([(False, "arm file absent")] + [(True, "armed")] * 10)
    box.engine.transmit = lambda: next(answers)
    with pytest.raises(SafetyError, match="armed executor never enters"):
        run(box.engine.enter(signal(), box.broker.snap, NOW))
    assert box.broker.sent == [] and box.journal.rows("orders") == []
    assert box.claims.held(NOW) == set()


def test_paper_is_armed_so_unknown_ssr_refuses(tmp_path):
    from _system.trading.rs_paper_executor.policy import Policy

    policy = Policy(spx_reserve=1_000_000, cash_buffer=100_000, daily_loss_limit=2500)
    journal = Journal(tmp_path / "p.sqlite", policy.digest)
    broker = Broker()
    broker.proof = dict(UNKNOWN)
    engine = Executor(PaperEndpoint("DU000000", 171, 4002), policy, journal, broker)
    with pytest.raises(SafetyError, match="fresh eligibility source required"):
        run(engine.enter(signal(), broker.snap, NOW))
    assert broker.sent == []
    journal.close()


@pytest.mark.parametrize("change, match", [
    (dict(ssr=True), "restricted"),
    (dict(halted=True), "restricted"),
    (dict(halted=1), "restricted"),       # anything but None/False is not "unknown"
    (dict(ssr="yes"), "restricted"),
    (dict(at="2026-11-18T14:59:00+00:00"), "stale|age|old"),  # producers stopped
    (dict(conid=2002), "contract mismatch"),
])
def test_known_restriction_stale_or_foreign_proof_still_refuses(box, change, match):
    shadow(box)
    box.broker.proof.update(change)
    with pytest.raises(SafetyError, match=match):
        run(box.engine.enter(signal(), box.broker.snap, NOW))
    assert events(box.journal, "shadow_entry_conditional") == []
    assert box.broker.sent == []


def test_clear_proof_in_shadow_is_still_a_full_shadow_entry(box):
    box.arm.unlink()  # broker.proof stays complete and clear
    assert run(box.engine.enter(signal(), box.broker.snap, NOW)) is None
    assert len(events(box.journal, "shadow_entry")) == 1
    assert events(box.journal, "shadow_entry_conditional") == []


def test_later_gates_still_refuse_on_the_conditional_path(box):
    shadow(box)
    box.broker.loan["apr"] = 9.0  # borrow APR above policy
    with pytest.raises(SafetyError, match="borrow APR"):
        run(box.engine.enter(signal(), box.broker.snap, NOW))
    box.broker.loan["apr"] = 0.5
    box.broker.preview["what_if"] = False
    with pytest.raises(SafetyError, match="margin preview"):
        run(box.engine.enter(signal(), box.broker.snap, NOW))
    assert events(box.journal, "shadow_entry_conditional") == []


# ---- what the producers write, as the executor reads it ------------------

def _proof(rows, conid):
    evidence = {"eligibility": rows}
    broker = SimpleNamespace(evidence=lambda: evidence, tickers={})
    return asyncio.run(PaperIBKR.eligibility(broker, conid))


def _engine():
    return SimpleNamespace(policy=SimpleNamespace(evidence_age_seconds=30))


def test_producer_rows_label_unknowns_and_never_hide_a_restriction():
    # Default config: halt RSS does not clear, no SSR source.
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed())
    assert Executor.shadow_eligibility(_engine(), _proof(rows, 1001), NOW, 1001) == ["halted", "ssr"]
    # Owner-approved halt clearing: only SSR is unknown.
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed(), halt_feed_clears=True)
    assert Executor.shadow_eligibility(_engine(), _proof(rows, 1001), NOW, 1001) == ["ssr"]
    # ... but a cleared halt older than 30 s is labelled unknown, not clear.
    assert Executor.shadow_eligibility(
        _engine(), _proof(rows, 1001), "2026-11-18T15:00:25+00:00", 1001) == ["halted", "ssr"]
    # Rule 201 carry-in and a listed halt still refuse.
    rows, _ = build_eligibility({2001: "KRUS"}, NOW, halt_feed=halt_feed(),
                                restrictions=[restriction({"KRUS": "11/17/2026 3:59:00 PM"})])
    with pytest.raises(SafetyError, match="restricted"):
        Executor.shadow_eligibility(_engine(), _proof(rows, 2001), NOW, 2001)
    event = {"ticker": "TEST", "halt_at": "2026-11-18T14:58:00+00:00", "resume_at": None,
             "market": "NASDAQ", "reason": "T1"}
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed([event]))
    with pytest.raises(SafetyError, match="restricted"):
        Executor.shadow_eligibility(_engine(), _proof(rows, 1001), NOW, 1001)


def test_ib_halt_tick_still_refuses_a_conditional_entry():
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed())
    evidence = {"eligibility": rows}
    broker = SimpleNamespace(evidence=lambda: evidence, tickers={1001: SimpleNamespace(halted=2)})
    proof = asyncio.run(PaperIBKR.eligibility(broker, 1001))
    with pytest.raises(SafetyError, match="restricted"):
        Executor.shadow_eligibility(_engine(), proof, NOW, 1001)


# ---- shadow report -------------------------------------------------------

def _add(path, kind, payload, at="2026-11-18T15:10:00+00:00"):
    j = Journal(path, "p", "RSLIVE|")
    j.event(at, kind, payload)
    j.close()


COND = {"id": "c1", "ticker": "ABC", "shares": 400, "limit": 2.0, "reason": "arm file absent",
        "initial_margin": 800, "maintenance_margin": 700,
        "eligibility_unknown": ["halted", "ssr"], "eligibility_missing": []}


def test_report_counts_conditional_entries_apart_and_never_as_arm_ready(tmp_path):
    path = build(tmp_path / "s.sqlite", entry=False)
    _add(path, "shadow_entry_conditional", COND)
    r = shadow_report(path, min_sessions=2)
    assert r["would_be_entries"] == 0 and r["conditional_would_be_entries"] == 1
    assert r["conditional_unknown_inputs"] == {"halted": 1, "ssr": 1}
    assert r["checks"]["downstream_gates_exercised"] is True
    assert r["checks"]["enough_would_be_entries"] is False
    assert r["ready_for_arm_review"] is False and r["conditional_note"]
    assert r["sessions"][1]["conditional_entries"][0]["id"] == "c1"


def test_report_without_conditional_entries_is_unchanged(tmp_path):
    r = shadow_report(build(tmp_path / "s.sqlite"), min_sessions=2)
    assert r["ready_for_arm_review"] is True and r["conditional_would_be_entries"] == 0
    assert r["checks"]["downstream_gates_exercised"] is True and r["conditional_note"] is None
    r = shadow_report(build(tmp_path / "e.sqlite", entry=False), min_sessions=2)
    assert r["checks"]["downstream_gates_exercised"] is False


def test_a_proposal_with_a_full_entry_is_not_also_counted_conditional(tmp_path):
    path = build(tmp_path / "s.sqlite")  # full shadow entry for "s1"
    _add(path, "shadow_entry_conditional", {**COND, "id": "s1"}, at="2026-11-18T15:01:00+00:00")
    r = shadow_report(path, min_sessions=2)
    assert r["would_be_entries"] == 1 and r["conditional_would_be_entries"] == 0


def test_cli_report_carries_the_conditional_counts(tmp_path, capsys):
    from _system.trading.rs_paper_executor import __main__ as cli

    path = build(tmp_path / "s.sqlite", entry=False)
    _add(path, "shadow_entry_conditional", COND)
    config = tmp_path / "c.json"
    config.write_text(json.dumps({
        "endpoint": {"account": "DU000000", "client_id": 171, "port": 4002},
        "policy": {"spx_reserve": 1, "cash_buffer": 1, "daily_loss_limit": 1}}))
    assert cli.main(["shadow-report", "--config", str(config), "--state", str(path),
                     "--min-sessions", "2"]) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["conditional_would_be_entries"] == 1 and not out["ready_for_arm_review"]
    assert Path(path).exists()
