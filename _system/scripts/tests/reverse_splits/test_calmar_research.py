from dataclasses import replace

import pytest

from reverse_splits.calmar_research import (
    identifier, neighborhood, path_metrics, period_metrics, ranked, search_policies, summarize,
)
from reverse_splits.net_edge_v3 import Account, StudyPolicy
from reverse_splits.net_edge_study import simulate
from reverse_splits.calmar_validation import robust_failures
from reverse_splits.calmar_extension import RECENT, extended_neighborhood, model_id, summarize_window
from reverse_splits.net_edge_v3 import size_position
from test_rs_net_edge_v3 import SESSIONS, Store, portfolio_candidate


def test_calmar_uses_calendar_cagr_and_every_daily_drawdown():
    rows = [{"date": "2020-01-02", "equity": 110.},
            {"date": "2020-06-02", "equity": 88.},
            {"date": "2021-01-01", "equity": 121.}]
    stats = path_metrics(rows, 100., "2020-01-01", "2021-01-01")
    cagr = 1.21**(365.25/366)-1
    assert stats["max_drawdown"] == pytest.approx(.2)
    assert stats["cagr"] == pytest.approx(cagr)
    assert stats["calmar"] == pytest.approx(cagr/.2)


def test_idle_or_drawdown_free_paths_do_not_win_with_infinity():
    stats = path_metrics([{"date": "2021-01-01", "equity": 100.}], 100., "2020-01-01", "2021-01-01")
    assert stats["calmar"] is None
    assert not ranked([dict(id="cash", sample_qualified=False, trades=0, **stats)])


def test_first_day_loss_is_measured_from_starting_cash():
    stats = path_metrics([{"date": "2021-01-01", "equity": 90.}], 100., "2020-01-01", "2021-01-01")
    assert stats["max_drawdown"] == pytest.approx(.1)
    assert stats["calmar"] < 0


@pytest.mark.parametrize("values", [[0], [float("nan")], [-1]])
def test_invalid_or_bankrupt_equity_cannot_rank(values):
    assert path_metrics([{"date": "2021-01-01", "equity": values[0]}], 100., "2020-01-01", "2021-01-01")["calmar"] is None


def test_duplicate_or_unordered_equity_dates_are_rejected():
    rows = [{"date": "2021-01-01", "equity": 100.}]*2
    with pytest.raises(ValueError): path_metrics(rows, 100., "2020-01-01", "2021-01-01")


def test_period_return_starts_from_previous_balance_including_idle_days():
    rows = [{"date": "2020-12-31", "equity": 110.}, {"date": "2021-12-31", "equity": 121.}]
    result = period_metrics(rows, 100., "2021-01-01", "2021-12-31")
    assert result["initial_equity"] == 110.
    assert result["total_return"] == pytest.approx(.1)


def test_predeclared_search_has_640_unique_trials_and_keeps_costs_fixed():
    policies = list(search_policies(StudyPolicy()))
    assert len(policies) == 80
    ids = {identifier(replace(p, fundamental_floor=f), v) for p in policies
           for f in (40., 60., 80., 90.) for v in ("fundamental", "net_edge")}
    assert len(ids) == 640
    assert all(p.assumed_annual_borrow == .5 and p.confidence == .9 for p in policies)


def test_sparse_winner_is_reported_but_not_sample_qualified():
    result = {"performance_valid": True, "funding_valid": True, "trade_ledger": [
        {"issuer": "a", "entry_day": "2020-01-02", "net_pnl": 10.}],
        "daily_equity_curve": [{"date": "2018-05-01", "equity": 99.}, {"date": "2026-10-13", "equity": 110.}],
        "costs": {}, "unresolved_admitted_names": 0, "open_positions": 0, "skipped": {}}
    row = summarize(result, StudyPolicy(), "net_edge", 100.)
    assert row["calmar"] > 0 and not row["sample_qualified"]
    assert ranked([row]) and not ranked([row], qualified=True)


def test_neighborhood_requires_one_adjacent_parameter_change():
    def row(floor, hold):
        p = replace(StudyPolicy(), fundamental_floor=floor, sessions=hold)
        return dict(id=identifier(p, "net_edge"), variant="net_edge", policy=p.__dict__, calmar=.5)
    center, adjacent, distant, two_changes = row(60., 5), row(80., 5), row(90., 5), row(80., 10)
    out = neighborhood(center, [center, adjacent, distant, two_changes])
    assert out["ids"] == [adjacent["id"]]


def test_daily_export_reserves_terminal_settlement_liability_and_preserves_default():
    p = StudyPolicy(sessions=1)
    account = Account(equity=1e6)
    evidence = {"borrow": [], "executions": []}
    ordinary = simulate([portfolio_candidate(p)], p, account, SESSIONS, Store(), evidence, variant="baseline")
    full = simulate([portfolio_candidate(p)], p, account, SESSIONS, Store(), evidence, variant="baseline", keep_daily=True)
    assert full["net_pnl"] == ordinary["net_pnl"]
    assert full["daily_equity_curve"][-1]["equity"] == full["ending_equity"]
    assert "daily_equity_curve" not in ordinary


def test_replay_window_starts_flat_and_can_stop_new_entries_before_the_end():
    p = StudyPolicy(sessions=1)
    evidence = {"borrow": [], "executions": []}
    out = simulate([portfolio_candidate(p)], p, Account(equity=1e6), SESSIONS, Store(), evidence,
                   variant="baseline", keep_daily=True, start_day="2026-10-13", end_day="2026-10-20")
    assert out["trades"] == 0 and out["ending_equity"] == 1e6
    out = simulate([portfolio_candidate(p)], p, Account(equity=1e6), SESSIONS, Store(), evidence,
                   variant="baseline", start_day="2026-10-12", end_day="2026-10-20", entry_end_day="2026-10-11")
    assert out["trades"] == 0


def test_pm_screen_rejects_sparse_and_cost_sensitive_winners():
    row = {"qualification_failures": [], "calmar": 1., "last_three_years": {"cagr": .1},
           "neighborhood": {"rankable_neighbors": 4, "positive_neighbors": 3, "median_calmar": .4}}
    checks = {"cost_scenarios": {k: {"cagr": .01} for k in ("double_borrow", "double_slippage", "one_billed_day")},
              "separate_periods": [{"cagr": .1}, {"cagr": -.1}, {"cagr": .1}]}
    assert robust_failures(row, checks) == []
    checks["cost_scenarios"]["one_billed_day"]["cagr"] = -.01
    assert robust_failures(row, checks) == ["one_billed_day_not_positive"]
    row["qualification_failures"] = ["fewer_than_30_trades"]
    assert "fewer_than_30_trades" in robust_failures(row, checks)


def test_larger_name_budget_keeps_the_total_portfolio_stress_budget_binding():
    policy = StudyPolicy()
    forecast = {"status": "estimated", "gross_edge": .2, "gross_lower_bound": .15,
                "holding_scenarios": [{"hold_sessions": 0}], "gross": {"variance": .02}}
    curve = [{"notional": 1000., "round_trip": .001}]
    small = Account(equity=50000.)
    large = replace(small, name_stress_budget=.02)
    a = size_position(forecast, curve, 10., "2026-10-15", .5, SESSIONS, policy, small, adv=1e8)
    b = size_position(forecast, curve, 10., "2026-10-15", .5, SESSIONS, policy, large, adv=1e8)
    blocked = size_position(forecast, curve, 10., "2026-10-15", .5, SESSIONS, policy, large, adv=1e8, used_stress=850.)
    assert b["shares"] > a["shares"] > 0
    assert b["notional"]*b["stress_fraction"] <= 50000*.02
    assert blocked["shares"] == 0
    assert small.sleeve_stress_budget == large.sleeve_stress_budget == .02


def test_recent_replay_is_annualized_over_its_own_three_year_window():
    result = {"performance_valid": True, "funding_valid": True, "trade_ledger": [
        {"issuer": "a", "entry_day": "2024-01-02", "net_pnl": 10.}],
        "daily_equity_curve": [{"date": "2023-10-16", "equity": 99.}, {"date": "2026-10-13", "equity": 110.}],
        "costs": {}, "unresolved_admitted_names": 0, "open_positions": 0, "skipped": {}}
    row = summarize_window(result, StudyPolicy(), "net_edge", Account(equity=100.), RECENT)
    expected = path_metrics(result["daily_equity_curve"], 100., RECENT, "2026-10-13")
    assert row["cagr"] == expected["cagr"] and row["years"] < 3.01


def test_sizing_neighborhood_does_not_mix_two_simultaneous_changes():
    def row(floor, risk):
        p = replace(StudyPolicy(), fundamental_floor=floor)
        return dict(id=model_id(p, "net_edge", risk), variant="net_edge", policy=p.__dict__,
                    account={"name_stress_budget": risk}, calmar=.5)
    center, size_only, floor_only, both = row(60., .005), row(60., .01), row(80., .005), row(80., .01)
    out = extended_neighborhood(center, [center, size_only, floor_only, both])
    assert set(out["ids"]) == {size_only["id"], floor_only["id"]}


def test_publication_audit_rejects_a_sparse_trial_promoted_to_qualified(tmp_path):
    import hashlib
    import json
    from reverse_splits.calmar_validation import audit_publication
    from reverse_splits.ledger import write_json
    from reverse_splits.net_edge_evidence import digest
    write_json(tmp_path/"net_edge_research_v3.json", {"frozen": True})
    plan = {"portfolio_trials": 1, "bindings": {"research_summary_sha256": digest(tmp_path/"net_edge_research_v3.json")}}
    plan["signature"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    row = {"id": "one_trade", "trades": 1, "issuers": 1, "active_years": 1,
           "calmar": 2., "cagr": .2, "max_drawdown": .1, "sample_qualified": False,
           "qualification_failures": ["fewer_than_30_trades"]}
    doc = {"schema_version": "shorts_calmar_research.v1", "data_cost_usd": 0, "network_requests": 0,
           "authority": "none", "production_policy_changed": False, "strict_approvals_added": False,
           "plan": plan, "cases": [row], "ranked_ids": [row["id"]], "qualified_ranked_ids": [],
           "original_reproduction": [{"matched": True}],
           "validation": {"cases": {}, "passing_tested_ids": [], "paper_candidate": None}}
    write_json(tmp_path/"calmar_research.json", doc)
    assert not audit_publication(tmp_path)
    row["sample_qualified"] = True
    write_json(tmp_path/"calmar_research.json", doc)
    assert any("sample-qualified" in error for error in audit_publication(tmp_path))
