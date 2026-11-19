"""Shadow-only evaluation when halt/SSR state is unknown (owner 2026-11-19, option B).

No intraday source today can say "SSR clear", so every strict eligibility check
fails. In SHADOW only, the later gates still run and are recorded as a
conditional would-be entry. A known halt or restriction still refuses, an armed
executor refuses exactly as before, and nothing is ever transmitted on it.
No socket, Gateway or vendor is contacted.
"""

import asyncio
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
from _system.trading.tests.test_rs_shadow_report import build, ready

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
    assert row["fully_gated"] is False
    assert (row["cik"], row["action_id"], row["action_day"]) == (
        "12345", "issuer1:2026-11-25:10", "2026-11-25")
    assert row["published_at"] == "2026-11-18T14:59:00Z"
    # The borrow used is a public indication: never an allocation, and the
    # successful WhatIf above proves no borrow.
    assert row["borrow_indication"]["locate_approved"] is False
    assert row["borrow_indication"]["available_shares"] == 10000
    assert {"quote", "borrow", "margin"} <= set(counting.calls)
    # Recorded once: the next cycles do not repeat quote, borrow or WhatIf.
    before = list(counting.calls)
    for _ in range(3):
        assert run(box.engine.enter(signal(), box.broker.snap, NOW)) is None
    assert counting.calls == before
    assert len(events(box.journal, "shadow_entry_conditional")) == 1


def test_a_second_publisher_record_of_the_same_action_is_not_a_second_record(box):
    shadow(box)
    counting = Counting(box.broker)
    box.engine.broker = counting
    assert run(box.engine.enter(signal(), box.broker.snap, NOW)) is None
    before = list(counting.calls)
    assert run(box.engine.enter(signal(id="prn:two"), box.broker.snap, NOW)) is None
    assert counting.calls == before
    assert len(events(box.journal, "shadow_entry_conditional")) == 1
    # A different action of the same issuer is a new opportunity.
    assert run(box.engine.enter(signal(id="x", action_id="issuer1:2027-02-01:5"),
                                box.broker.snap, NOW)) is None
    assert len(events(box.journal, "shadow_entry_conditional")) == 2


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


# ---- shadow report (rs_shadow_report.v2) --------------------------------
# Opportunities come only from fully gated shadow_entry events. Conditional
# entries are a separate, non-gating block and never touch readiness.

def _add(path, kind, payload, at="2026-11-18T15:10:00+00:00"):
    j = Journal(path, "p", "RSLIVE|")
    j.event(at, kind, payload)
    j.close()


COND = {"id": "c1", "ticker": "ABC", "shares": 400, "limit": 2.0,
        "reason": "shadow journal: entries are never transmitted",
        "initial_margin": 800, "maintenance_margin": 700, "fully_gated": False,
        "eligibility_unknown": ["halted", "ssr"], "eligibility_missing": [],
        "cik": "444", "action_id": "c-a1", "conid": 444, "synthetic_control": False,
        "published_at": "2026-11-18T15:09:00+00:00", "first_seen_at": "2026-11-18T15:09:10+00:00"}


def test_conditional_entries_never_make_a_quiet_run_ready(tmp_path):
    path = build(tmp_path / "s.sqlite", entries=None)
    for n, cik in enumerate(("444", "555", "666")):  # 3 issuers, enough if they counted
        _add(path, "shadow_entry_conditional", {**COND, "id": "c%d" % n, "cik": cik,
                                                "action_id": "c-a%d" % n},
             at=("2026-11-17T15:10:00+00:00" if n == 0 else "2026-11-18T15:1%d:00+00:00" % n))
    r = ready(tmp_path, path)
    assert r["checks"]["opportunities"] == 0 and r["ready_for_arm_review"] is False
    assert "enough_opportunities" in r["failed_checks"]
    c = r["conditional"]
    assert c["counts_toward_readiness"] is False and c["would_be_entries"] == 3
    assert c["issuers"] == 3 and c["sessions"] == 2
    assert c["unknown_inputs"] == {"halted": 3, "ssr": 3}
    assert c["downstream_gates_exercised"] is True
    assert "downstream_gates_exercised" not in r["checks"]
    assert r["sessions"][1]["conditional_entries"][0]["id"] == "c1"


def test_conditional_entries_leave_a_ready_report_unchanged(tmp_path):
    plain = ready(tmp_path, build(tmp_path / "a.sqlite"))
    path = build(tmp_path / "b.sqlite")
    _add(path, "shadow_entry_conditional", COND)
    mixed = ready(tmp_path, path)
    assert plain["ready_for_arm_review"] is mixed["ready_for_arm_review"] is True
    assert plain["checks"] == mixed["checks"]
    assert plain["conditional"]["would_be_entries"] == 0
    assert plain["conditional"]["downstream_gates_exercised"] is True  # full entries ran them
    quiet = ready(tmp_path, build(tmp_path / "c.sqlite", entries=None))
    assert quiet["conditional"]["downstream_gates_exercised"] is False


def test_conditional_dedup_matches_the_opportunity_rules(tmp_path):
    path = build(tmp_path / "s.sqlite", entries=None)
    _add(path, "shadow_entry_conditional", COND)
    _add(path, "shadow_entry_conditional", {**COND, "id": "other-publisher"})        # duplicate
    _add(path, "shadow_entry_conditional", {**COND, "id": "synthetic-control:q",
                                            "action_id": "q", "cik": "777"})        # control
    _add(path, "shadow_entry_conditional", {**COND, "id": "late", "action_id": "c-late",
                                            "published_at": "2026-11-18T13:00:00+00:00"})
    _add(path, "shadow_entry_conditional", {**COND, "id": "c2", "action_id": "c-a2"})
    r = shadow_report(path, min_sessions=2)
    assert r["conditional"]["would_be_entries"] == 2 and r["conditional"]["issuers"] == 1
    assert r["conditional"]["excluded_entries"] == {
        "duplicate_issuer_action": 1, "synthetic_control": 1, "catch_up_announcement": 1}


def test_a_fully_gated_entry_supersedes_its_conditional_record(tmp_path):
    path = build(tmp_path / "s.sqlite")  # full entries for (111, a1), (222, a2), (333, a3)
    _add(path, "shadow_entry_conditional", {**COND, "cik": "111", "action_id": "a1",
                                            "published_at": "2026-11-17T15:00:00+00:00",
                                            "first_seen_at": "2026-11-17T15:00:00+00:00"},
         at="2026-11-17T15:01:00+00:00")
    r = shadow_report(path, min_sessions=2)
    assert r["checks"]["opportunities"] == 3 and r["conditional"]["would_be_entries"] == 0
    assert r["conditional"]["excluded_entries"] == {"has_fully_gated_entry": 1}
