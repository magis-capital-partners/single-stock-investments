"""Availability, selection, cost, and liability invariants for biotech research."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biotech_strategy import BASELINE, append_paper, available_rows, backtest, checksum, clinical_peer_momentum, percentile, portfolio_risk, register_protocol, score_rows, targets
from build_biotech_strategy import build


def protocol():
    p = copy.deepcopy(BASELINE)
    p["portfolio"].update(max_name_weight=0.5, max_names=2, selection_fraction=0.5)
    return p


def features():
    return [
        {"ticker": "AAA", "consensus_score": 90, "spend_value": 0.2,
         "known_at": "2026-01-01", "as_of": "2025-12-31", "identity_status": "verified"},
        {"ticker": "BBB", "consensus_score": 10, "spend_value": 2,
         "known_at": "2026-01-01", "as_of": "2025-12-31", "identity_status": "verified"},
    ]


def test_ties_and_missing_are_not_synthetic_zero_signals():
    assert percentile({"a": 5, "b": 5}) == {"a": 50, "b": 50}
    assert "c" not in percentile({"a": 0, "c": None})
    rows = score_rows([*features(), {"ticker": "MISSING", "consensus_score": 100}], protocol())
    assert rows[0]["ticker"] == "AAA"
    assert rows[-1]["strategy_score"] is None
    assert rows[-1]["missing_required"] == ["spend_value"]


def test_publication_day_and_future_revisions_cannot_select_a_past_portfolio():
    old, rejected = available_rows(features(), "2026-01-01", protocol())
    assert old == []
    assert len(rejected) == 2
    amended = [*features(), {**features()[1], "consensus_score": 1000, "known_at": "2026-03-01"}]
    before, _ = available_rows(amended, "2026-01-02", protocol())
    assert before[0]["ticker"] == "AAA"
    invalid, _ = available_rows([{**features()[0], "as_of": "2026-01-03"}], "2026-01-04", protocol())
    assert invalid == []


def test_individual_shorts_need_dated_availability_and_fees():
    rows = score_rows(features(), protocol())
    weights, abstentions = targets(rows, "long_short", protocol())
    assert weights == {"AAA": 0.5}
    assert abstentions[0]["ticker"] == "BBB"
    weights, _ = targets(rows, "long_short", protocol(), {"BBB": {"available": True, "apr": 0.1}})
    assert weights["BBB"] == -0.5


def test_entry_cannot_earn_the_same_day_return_and_costs_reduce_nav():
    marks = [{"date": "2026-01-02", "ticker": "AAA", "total_return": 0.8},
             {"date": "2026-01-03", "ticker": "AAA", "total_return": 0.1}]
    result = backtest(features(), marks, protocol())
    long = result["variants"][0]
    assert long["daily"][0]["gross_return"] == 0
    assert long["daily"][0]["return"] < 0
    assert long["daily"][1]["gross_return"] == pytest.approx(0.05)
    assert long["metrics"]["total_return"] < 0.05


def test_missing_exit_marks_retain_the_liability_and_withhold_complete_metrics():
    marks = [{"date": "2026-01-02", "ticker": "AAA", "total_return": 0},
             {"date": "2026-01-03", "ticker": "BBB", "total_return": 0.1}]
    result = backtest(features(), marks, protocol())
    long = result["variants"][0]
    assert long["daily"][1]["return"] is None
    assert "AAA" in long["daily"][1]["unpriced_liabilities"]
    assert long["metrics"]["status"] == "incomplete_marks"


def test_reproducible_protocol_and_idempotent_append_only_paper_events(tmp_path):
    path = tmp_path / "paper.jsonl"
    a = {"id": "first", "as_of": "2026-01-01"}
    assert append_paper(path, a)
    first_bytes = path.read_bytes()
    assert not append_paper(path, a)
    assert path.read_bytes() == first_bytes
    assert append_paper(path, {"id": "second", "as_of": "2026-01-02"})
    events = [json.loads(s) for s in path.read_text().splitlines()]
    assert events[1]["previous_sha256"] == checksum(events[0])


def test_empty_or_unverified_inputs_cannot_publish_fake_performance(tmp_path):
    doc = build(tmp_path, "2026-10-29")
    assert doc["summary"]["universe"] == 0
    assert doc["backtest"]["status"] == "awaiting_dated_inputs"
    assert doc["paper"]["positions"] == []
    assert doc["paper"]["total_return"] is None
    assert doc["paper"]["cash_weight"] == 1
    assert doc["authority"] == "research_and_paper_only"


def test_verified_dated_marks_can_start_a_simulated_paper_portfolio(tmp_path):
    observed = features()
    marks = [{"date": "2026-01-02", "ticker": t, "close": 10, "total_return": 0} for t in ["AAA", "BBB"]]
    doc = build(tmp_path, "2026-01-02", observations=observed, marks=marks, protocol=protocol())
    assert doc["paper"]["status"] == "simulated_rebalance"
    assert doc["paper"]["positions"][0]["ticker"] == "AAA"
    assert all(not row["observed_fill"] for row in doc["paper"]["positions"])


def test_registered_rules_cannot_change_under_the_same_identifier(tmp_path):
    path = tmp_path / "registry.json"
    register_protocol(path, protocol(), "2026-01-01")
    changed = protocol()
    changed["costs"]["one_way_bps"] = 0
    with pytest.raises(ValueError, match="Registered protocol changed"):
        register_protocol(path, changed, "2026-01-02")


def test_quarantined_rows_do_not_distort_eligible_percentiles():
    rows = score_rows([*features(), {"ticker": "BAD", "identity_status": "quarantined", "consensus_score": 1000, "spend_value": 0}], protocol())
    assert next(r for r in rows if r["ticker"] == "AAA")["strategy_score"] == 100
    assert next(r for r in rows if r["ticker"] == "BAD")["strategy_score"] is None


def test_each_required_factor_has_its_own_staleness_gate():
    row = {**features()[0], "factor_dates": {"spend_value": "2024-01-01"}}
    assert available_rows([row], "2026-01-02", protocol())[0] == []


def test_clinical_peers_exclude_own_returns_and_future_profiles():
    profiles = [{"ticker": t, "clinical_tags": ["oncology", "phase2"], "known_at": "2025-12-01"} for t in ["AAA", "BBB", "CCC", "DDD"]]
    profiles.append({"ticker": "FUTURE", "clinical_tags": ["oncology"], "known_at": "2026-03-01"})
    returns = [{"ticker": t, "return_12m": value, "end_date": "2025-12-31"} for t, value in [("AAA",1000),("BBB",.1),("CCC",.2),("DDD",.3),("FUTURE",9000)]]
    result = clinical_peer_momentum(profiles, returns, "2026-01-02")
    assert result["AAA"]["peer_momentum_12m"] == pytest.approx(.2)
    assert "AAA" not in result["AAA"]["peer_tickers"]
    assert "FUTURE" not in result


def test_paper_marks_existing_positions_without_losing_them_on_a_data_failure(tmp_path):
    ledger = tmp_path / "paper.jsonl"
    first = build(tmp_path, "2026-01-02", observations=features(), marks=[{"date":"2026-01-02","ticker":"AAA","close":10}], protocol=protocol())
    append_paper(ledger, first["paper"])
    second = build(tmp_path, "2026-01-05", marks=[{"date":"2026-01-05","ticker":"AAA","close":11}], protocol=protocol(), ledger=ledger)
    assert second["paper"]["status"] == "marked_existing_positions"
    assert second["paper"]["nav"] > first["paper"]["nav"]
    assert second["paper"]["orders"] == []
    missing = build(tmp_path, "2026-01-06", protocol=protocol(), ledger=ledger)
    assert missing["paper"]["status"] == "unpriced_open_positions"
    assert missing["paper"]["positions"] == first["paper"]["positions"]
    assert missing["paper"]["total_return"] is None


def test_paper_ledger_rejects_backdated_events(tmp_path):
    ledger = tmp_path / "paper.jsonl"
    append_paper(ledger, {"id":"new", "as_of":"2026-01-03"})
    with pytest.raises(ValueError, match="before the last"):
        append_paper(ledger, {"id":"old", "as_of":"2026-01-01"})


def test_paper_ledger_rejects_modified_prior_events(tmp_path):
    ledger = tmp_path / "paper.jsonl"
    append_paper(ledger, {"id":"first", "as_of":"2026-01-01", "cash":100})
    append_paper(ledger, {"id":"second", "as_of":"2026-01-02", "cash":100})
    ledger.write_text(ledger.read_text().replace('"cash": 100', '"cash": 999', 1))
    with pytest.raises(ValueError, match="hash chain"):
        append_paper(ledger, {"id":"third", "as_of":"2026-01-03"})


def test_liquidity_and_catalyst_gaps_remain_explicit_in_stress_report():
    risk = portfolio_risk(features(), {"AAA":.04,"BBB":-.04}, 100000, [])
    assert risk["status"] == "incomplete_inputs"
    assert risk["combined_tail_stress"] == pytest.approx(-.148)
    assert all("liquidity" in r["missing"] for r in risk["positions"])
