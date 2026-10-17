"""RSI-4 uncertainty, timestamp, unit-conversion and publication invariants."""
import copy
import json
from datetime import datetime

import pytest

from reverse_splits.coverage_data import (NY, calibrate_chart, parse_chart, repair_events,
                                          validate_chart_url, CoverageStore)
from reverse_splits.coverage_research import (assumed_cost_curve, deterministic_access,
                                              estimate_ratings, financing_estimate,
                                              framework_packet, announcement_plan,
                                              public_borrow_proxies)
from reverse_splits.coverage_research import collateral_scenarios, scenario_snapshot
from reverse_splits.coverage_research import baseline_comparison
from reverse_splits.net_edge_v3 import Account, BorrowHistory, StudyPolicy, dated_borrow


def snap(key, issuer, day, *, score=None, signals=None):
    return {"key": key, "ticker": "TEST", "issuer": issuer, "cik": issuer.removeprefix("cik/"),
            "database_ticker": "TEST", "known_at": day+"T12:00:00+00:00", "screen_rating": score,
            "fundamental": {"signals": signals or {}, "status": "scored" if score is not None else "missing",
                            "balances": {}, "flows": {}, "evidence": []},
            "source_url": "https://www.sec.gov/example", "data_assumptions": [], "identity_assumed": False}


def test_estimated_financials_cannot_see_future_or_same_issuer():
    first = snap("first", "cik/1", "2020-01-01", signals={"cash_burn": {"score": .2}})
    same = snap("same", "cik/1", "2020-01-02")
    other = snap("other", "cik/2", "2020-01-02")
    future = snap("future", "cik/3", "2022-01-01", score=100, signals={"cash_burn": {"score": 1.}})
    data = {s["key"]: s for s in (first, same, other, future)}
    estimate_ratings(data)
    assert same["imputed_signals"]["cash_burn"] == {"value": .5, "prior_other_issuers": 0, "basis": "neutral_prior"}
    assert other["imputed_signals"]["cash_burn"] == {"value": .2, "prior_other_issuers": 1, "basis": "earlier_other_issuer_median"}
    assert other["reported_screen_rating"] is None
    assert other["modeled_conviction"] < other["screen_rating"]
    # Same-time observations cannot train each other in either insertion order.
    assert other["imputed_signals"]["leverage"]["prior_other_issuers"] == 0


def test_reported_scores_are_preserved_without_filling_missing_balances():
    s = snap("x", "cik/1", "2020-01-01", score=83, signals={"cash_burn": {"score": 1.}})
    estimate_ratings({"x": s})
    assert s["screen_rating"] == s["reported_screen_rating"] == 83
    assert s["fundamental"]["balances"] == {}
    assert s["rating_basis"] == "reported_financial_signals"


def test_identity_needs_a_company_name_not_just_a_current_symbol():
    base = {"event_id": "a", "ticker": "OLD", "issuer": "unresolved_symbol/OLD", "company": "Different Business",
            "ratio": .1, "ex_date": "2020-01-02", "available_at": "2020-01-01T00:00:00-05:00", "verification": "structured_corporate_action"}
    issuers = [{"cik": "1", "name": "Other Inc", "primary_ticker": "OLD"}]
    result, _, _ = repair_events([base], [], issuers)
    assert not result[0].get("cik")
    result, _, _ = repair_events([{**base, "company": "Other Inc Common Stock"}], [], issuers)
    assert result[0]["cik"] == "1"
    assert result[0]["assumptions"] == ["identity_exact_company_name_current_registry"]


def test_recover_dated_primary_schedule_and_keep_effective_clock_separate():
    e = {"event_id": "a", "ticker": "T", "issuer": "cik/1", "cik": "1", "ratio": .1,
         "ex_date": "2020-01-03", "available_at": None, "verification": "candidate_requires_verification"}
    d = {"eligible": 1, "cik": "1", "scheduled": "2020-01-03", "ratio": .1,
         "available_at": "2020-01-02T00:00:00-05:00", "accession": "a", "filed_at": "2020-01-01"}
    result, _, counts = repair_events([e], [d], [])
    assert result[0]["available_at"] == d["available_at"]
    assert result[0]["assumptions"] == []
    assert counts["primary_action_repairs"] == 1
    result, _, _ = repair_events([{**e, "verification": "structured_corporate_action"}], [], [])
    assert result[0]["clock_basis"] == "assumed_observable_by_effective_day_close"
    assert "effective_date_clock_proxy" in result[0]["assumptions"]


def test_duplicate_sources_and_ineligible_instruments_cannot_inflate_trade_universe():
    e = {"event_id": "a", "ticker": "T", "issuer": "cik/1", "cik": "1", "ratio": .1,
         "ex_date": "2020-01-03", "available_at": "2020-01-02T00:00:00-05:00", "verification": "structured_corporate_action"}
    rows, rejected, _ = repair_events([e, {**e, "event_id": "b"}, {**e, "event_id": "c", "company": "Test ETF"}], [], [])
    assert len(rows) == 1
    assert {r["reason"] for r in rejected} == {"duplicate_issuer_action", "instrument_outside_common_equity_sleeve"}


def test_public_chart_reconstructs_split_units_without_synthetic_bars():
    t = int(datetime(2020, 1, 2, 10, tzinfo=NY).timestamp())
    raw = json.dumps({"chart": {"result": [{"meta": {"symbol": "T"}, "timestamp": [t, t+86400],
        "indicators": {"quote": [{"open": [20., None], "high": [22., None], "low": [18., None], "close": [20., None], "volume": [100, None]}]},
        "events": {"splits": {"s": {"date": t+86400, "numerator": 1, "denominator": 10}}}}]}}).encode()
    bars, _, _ = parse_chart(raw, "T")
    assert bars["2020-01-02"]["close"] == 2
    assert bars["2020-01-02"]["volume"] == 1000
    assert "2020-01-03" not in bars
    assert parse_chart(raw, "WRONG")[2] == "public_chart_symbol_mismatch"


def test_unit_calibration_handles_already_nominal_segments_and_rejects_conflicts():
    bars = {f"2020-01-0{i}": {"open": 2., "high": 2., "low": 2., "close": 2., "volume": 1000., "_future_split_factor": .1} for i in (2, 3, 4)}
    nominal = {d: {"close": 20.} for d in bars}
    calibrated, _, status = calibrate_chart(copy.deepcopy(bars), [], nominal)
    assert calibrated["2020-01-02"]["close"] == 20
    assert calibrated["2020-01-02"]["volume"] == 100
    assert status["unit_validation"] == "split_segments_overlap_checked"
    conflict = {d: {"close": 200.} for d in bars}
    assert calibrate_chart(bars, [], conflict)[2]["status"] == "public_nominal_units_conflict"


@pytest.mark.parametrize("url", ["https://query1.finance.yahoo.com/v8/finance/chart/T?apikey=x",
                                  "https://other.example/v8/finance/chart/T", "https://user:pass@query1.finance.yahoo.com/v8/finance/chart/T"])
def test_free_chart_collector_rejects_credentials_and_unapproved_endpoints(url):
    with pytest.raises(ValueError): validate_chart_url(url)


class Store:
    def factor(self, *_): return 1.
    def prior(self, *_): return [{"date": "2020-01-01", "close": 10., "volume": 10000}]


def test_financing_includes_proceeds_and_reverse_split_has_no_dilution():
    s = snap("x", "cik/1", "2020-01-02", score=70)
    s["price"] = 10
    s["fundamental"].update(currency="USD", balances={"cash": 0, "shares": 100}, flows={"cfo": -100})
    f = financing_estimate(s, Store())
    assert f["reverse_split_economic_dilution"] == 0
    assert sum(r["probability"] for r in f["scenarios"]) == pytest.approx(1)
    r = f["scenarios"][1]
    assert r["net_proceeds"] == pytest.approx(50)
    assert r["per_share_value_change"] > -r["issuance_fraction"]/(1+r["issuance_fraction"])
    assert f["added_to_forecast_return"] is False


def test_framework_packet_has_all_routes_without_manufacturing_research_or_fraud():
    s = snap("x", "cik/1", "2020-01-02", score=70)
    estimate_ratings({"x": s})
    packet = framework_packet(s, [], Store())
    assert len(packet["frameworks"]) == 27
    assert packet["completed_underwriting"] is False
    fraud = next(r for r in packet["frameworks"] if r["framework"] == "fraud_bad_actors")
    assert fraud["status"] == "unresolved_no_allegation"
    assert not any(r["positive_edge_added"] for r in packet["frameworks"])


def test_larger_orders_cost_more_and_cannot_remove_uncertainty():
    s = snap("x", "cik/1", "2020-01-02", score=70)
    s["assumption_reserve"] = .01
    o = {"entry_price": 10., "prior_adv": 10000., "entry_day": "2020-01-02"}
    curve = assumed_cost_curve(s, o, Store(), [], participation=.01)
    assert curve[-1]["round_trip"] > curve[0]["round_trip"]
    assert curve[0]["uncertainty"] > .01
    assert deterministic_access("x", 1)
    assert not deterministic_access("x", 0)
    assert deterministic_access("x", .5) == deterministic_access("x", .5)


def test_announcement_plan_uses_projected_known_split_units_and_ignores_actual_open():
    from dataclasses import replace
    from reverse_splits.net_edge_v3 import distribution
    s = snap("x", "cik/1", "2026-10-14", score=80)
    s.update(price=1., prior_dollar_adv=1e8, modeled_conviction=70)
    sessions = tuple(f"2026-10-{d}" for d in (12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28))
    f = {"status": "estimated", "gross_edge": .10, "gross_lower_bound": .08,
         "known_at": s["known_at"], "gross": distribution([.09, .11]), "gross_scenarios": [.09, .11],
         "holding_scenarios": [{"hold_sessions": 2}, {"hold_sessions": 2}]}
    c = {"snapshot": s, "outcome": {"entry_day": "2026-10-15", "entry_price": 99999.}, "forecast": f,
         "announcement_reference_price": 10., "announcement_split_factor": .1,
         "announcement_curve": [{"notional": 1e6, "round_trip": .005, "uncertainty": .001, "issuers": 25}]}
    p = replace(StudyPolicy(), minimum_billed_days=1)
    a = Account(name_stress_budget=.02)
    plan = announcement_plan(c, p, a, sessions, {"borrow": []}, variant="net_edge")
    assert plan["shares"] > 0
    assert plan["notional"] == plan["shares"]*10
    assert plan["projected_share_factor"] == .1
    assert plan["annual_borrow"] == .5
    assert plan["expected_billed_days"] >= 1
    c["outcome"]["entry_price"] = .001
    assert announcement_plan(c, p, a, sessions, {"borrow": []}, variant="net_edge") == plan


def test_public_borrow_proxies_never_become_account_approvals_or_actual_charges():
    doc = {"histories": {"T": {"source_url": "https://www.iborrowdesk.com/api/ticker/T", "source_sha256": "a"*64,
           "records": [{"known_at": "2026-10-14T04:00:00Z", "annual_rate": .5, "available_shares": 100}]}}}
    event = {"ticker": "T", "issuer": "cik/1"}
    records = public_borrow_proxies([event, event], doc)
    assert len(records) == 1
    assert records[0]["kind"] == "indication"
    assert records[0]["account_approval"] is False
    assert records[0]["assumed_historical_identity"] is True


def test_public_volume_repairs_partial_venues_but_preserves_prices_and_prior_cutoff(tmp_path):
    import sqlite3
    p = tmp_path/"prices.sqlite"
    con = sqlite3.connect(p)
    con.execute("create table prices_daily(ticker text,date text,open real,high real,low real,close real,volume real)")
    con.execute("create table price_provenance(ticker text,date text,nominal integer,volume_basis text)")
    con.executemany("insert into prices_daily values('T',?,10,11,9,10,100)", [("2026-10-14",), ("2026-10-15",)])
    con.executemany("insert into price_provenance values('T',?,1,?)", [("2026-10-14", "three_venues_not_consolidated"), ("2026-10-15", "consolidated")])
    con.commit(); con.close()
    public = {"T": {"2026-10-14": {"close": 10.1, "volume": 500}, "2026-10-15": {"close": 10.2, "volume": 10000000}}}
    store = CoverageStore(p, [], public, {})
    rows = store.prices("T")
    assert rows["2026-10-14"]["close"] == 10
    assert rows["2026-10-14"]["volume"] == 500
    assert rows["2026-10-15"]["volume"] == 100
    assert store.prior("T", "2026-10-15")[-1]["volume"] == 500
    assert store.volume_overrides == 1
    store.connection.close()


def test_borrowing_uses_previous_day_collateral_and_projects_minimum_billing():
    from reverse_splits.net_edge_study import realized_loan
    sessions = tuple(f"2026-10-{d}" for d in (12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26))
    o = {"status": "daily_benchmark", "entry_day": "2026-10-14", "exit_day": "2026-10-15", "entry_price": 1.9,
         "marks": [{"date": "2026-10-14", "close": 2.}, {"date": "2026-10-15", "close": 100.}]}
    c = {"snapshot": {"database_ticker": "T", "issuer": "cik/1"}, "outcome": o}
    policy = StudyPolicy(minimum_billed_days=1)
    new = realized_loan(c, 100, .5, sessions, Store(), [], policy)
    assert new["total"] == pytest.approx(100*3*.5/360)
    projected = collateral_scenarios(copy.deepcopy(o), policy, sessions)
    assert projected["collateral_factors"] == [2/1.9]


def test_borrow_index_is_equivalent_and_scenario_copies_keep_index_references():
    from reverse_splits.net_edge import moment
    rows = [{"issuer": "cik/1", "known_at": "2026-10-14T12:00:00Z", "kind": "indication", "annual_rate": .5, "shares": 100},
            {"issuer": "cik/2", "known_at": "2026-10-14T12:00:00Z", "kind": "indication", "annual_rate": .8, "shares": 0}]
    indexed = BorrowHistory(rows)
    cutoff = moment("2026-10-14T13:00:00Z")
    assert dated_borrow(rows, "cik/1", cutoff) == dated_borrow(indexed, "cik/1", cutoff)
    changed = copy.deepcopy(indexed)
    changed[0]["annual_rate"] = 3
    assert dated_borrow(changed, "cik/1", cutoff)["annual_rate"] == 3
    assert indexed[0]["annual_rate"] == .5
    assert dated_borrow(indexed, "cik/3", cutoff) is None


def test_stale_announcement_borrow_cannot_evade_fallback_or_fee_stress():
    s = {"announcement_borrow": {"annual_rate": .01, "shares": 100}}
    assert scenario_snapshot(s, .5)["announcement_borrow"]["annual_rate"] == .5
    assert scenario_snapshot(s, 3.)["announcement_borrow"]["annual_rate"] == 3.
    s["announcement_borrow"]["annual_rate"] = 2.
    assert scenario_snapshot(s, .5)["announcement_borrow"]["annual_rate"] == 2.
    assert scenario_snapshot(s, 3.)["announcement_borrow"]["annual_rate"] == 12.
    assert s["announcement_borrow"]["annual_rate"] == 2.


def test_price_recovery_keeps_original_denominator_separate_from_new_scored_names():
    class Prices:
        def __init__(self, values): self.values = values
        def prices(self, ticker): return {"2026-10-13": {"open": self.values.get(ticker)}}
    original = {k: {"ticker": k, "database_ticker": k, "ex_date": "2026-10-12", "screen_rating": 70.}
                for k in ("priced", "recovered", "missing")}
    recovered = {"new": {"reported_screen_rating": 80., "identity_assumed": True, "cik": "1", "fundamental": {"status": "scored"}},
                 "unknown": {"reported_screen_rating": None, "identity_assumed": False, "cik": "", "fundamental": {"status": "raw_companyfacts_missing"}},
                 "no_file": {"reported_screen_rating": None, "identity_assumed": False, "cik": "2", "fundamental": {"status": "raw_companyfacts_missing"}}}
    comparison = baseline_comparison(original, recovered, Prices({"priced": 10}), Prices({"priced": 10, "recovered": 5, "new": 2}), ("2026-10-12", "2026-10-13"))
    recent = comparison["entry_prices"]["recent"]
    assert recent["original_scored_records"] == 3
    assert recent["original_missing_entry_records"] == 2
    assert recent["recovered_entry_records"] == recent["remaining_missing_entry_records"] == 1
    assert [r["key"] for r in recent["recovered_records"]] == ["recovered"]
    assert comparison["financials"]["current_reported_assumed_identity"] == 1
    assert comparison["financials"]["missing_issuer_identity"] == comparison["financials"]["identified_issuer_raw_file_missing"] == 1
