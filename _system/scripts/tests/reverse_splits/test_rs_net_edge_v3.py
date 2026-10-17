"""Economic invariants: availability, execution, financing, carry and sizing."""
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from reverse_splits.net_edge import FRAMEWORKS
from reverse_splits.net_edge_evidence import (
    capitalization, filing_rating, import_records, monetary_facts, trailing_year,
)
from reverse_splits.net_edge_v3 import (
    Account, StudyPolicy, assessment, calibration, daily_exit, dated_borrow,
    expected_carry, loan_schedule, payoff_forecast, size_position, ssr_limit_fill,
)

SESSIONS = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16",
            "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]
CUTOFF = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def cited(**values):
    return {"known_at": "2026-10-14T12:00:00+00:00", "source_url": "https://www.sec.gov/example",
            "locator": "Note 3", **values}


def review(key, status="supported"):
    return cited(framework=key, status=status, mechanism="Documented financing mechanism",
                 contrary_evidence="Proceeds may extend runway", falsifier="No issuance before maturity")


def test_framework_contradiction_only_vetoes_selected_mechanism():
    rows = [review("accounting", "contradicted"), review("dilution_financing")]
    assert not assessment(rows, CUTOFF, selected_mechanisms=["dilution_financing"])["blocked"]
    assert assessment(rows, CUTOFF, selected_mechanisms=["accounting"])["blocked"]


def test_na_reviews_do_not_manufacture_thesis_and_unknown_routes_stay_unknown():
    result = assessment([review(k, "not_applicable") for k in FRAMEWORKS], CUTOFF)
    assert result["complete"] and not result["thesis_supported"]
    assert assessment([], CUTOFF)["missing"] == sorted(FRAMEWORKS)


def test_future_review_and_uncited_veto_cannot_change_past():
    rows = [review("cash_burn") | {"known_at": "2026-10-16T00:00:00+00:00"}]
    result = assessment(rows, CUTOFF, vetoes=[{"reason": "identity_mismatch"}])
    assert result["reviewed"] == 0 and not result["blocked"]


def test_borrow_indication_is_usable_forecast_evidence_but_never_approval():
    row = cited(issuer="cik/1", annual_rate=.5, shares=1000, kind="indication")
    assert dated_borrow([row], "cik/1", CUTOFF, max_age_hours=24.) == row
    assert dated_borrow([row], "cik/1", CUTOFF, approval=True, max_age_hours=24.) is None
    assert dated_borrow([row], "cik/2", CUTOFF, max_age_hours=24.) is None


def test_entry_approval_has_own_fresh_clock():
    old = cited(issuer="cik/1", annual_rate=.5, shares=1000, kind="approval", approved=True, reference="ref")
    fresh = old | {"known_at": "2026-10-15T11:00:00+00:00"}
    future = fresh | {"known_at": "2026-10-15T13:00:00+00:00"}
    assert dated_borrow([old, fresh, future], "cik/1", CUTOFF, approval=True) == fresh


def test_friday_return_settlement_bills_weekend_and_daily_rate_changes():
    loan = loan_schedule("2026-10-15", "2026-10-16", 2., .5, SESSIONS,
                         daily_rates={"2026-10-17": 1.})
    assert loan["billed_calendar_days"] == 3
    assert loan["fraction"] == pytest.approx(3*(.5+1+.5)/360/2)


def test_bank_holidays_are_not_exchange_settlement_days():
    from reverse_splits.net_edge_v3 import settlement_day
    days = ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14"]
    loan = loan_schedule("2026-10-08", "2026-10-09", 10., .5, days)
    assert loan["billed_calendar_days"] == 4 and loan["exit_settlement"] == "2026-10-13"
    assert str(settlement_day("2026-11-10", ["2026-11-10", "2026-11-11", "2026-11-12"])) == "2026-11-12"
    # When Veterans Day falls on Saturday, Friday is a normal settlement day.
    assert str(settlement_day("2023-11-08", ["2023-11-08", "2023-11-09", "2023-11-10", "2023-11-13"])) == "2023-11-10"
    assert str(settlement_day("2025-01-08", ["2025-01-08", "2025-01-10", "2025-01-13"])) == "2025-01-09"


def test_future_emergency_closure_is_not_known_by_an_earlier_cost_plan():
    from reverse_splits.net_edge_v3 import planning_sessions
    calendar = ("2025-01-08", "2025-01-10", "2025-01-13")
    assert "2025-01-09" in planning_sessions(calendar, "2024-12-20T12:00:00+00:00")
    assert "2025-01-09" not in planning_sessions(calendar, "2025-01-02T12:00:00+00:00")


def test_intraday_and_explicit_preborrow_minimum_are_distinct():
    assert loan_schedule("2026-10-15", "2026-10-15", 2., .5, SESSIONS)["fraction"] == 0
    billed = loan_schedule("2026-10-15", "2026-10-15", 2., .5, SESSIONS, minimum_days=1, preborrow_fee_per_share=.01)
    assert billed["fraction"] == pytest.approx((3*.5/360+.01)/2)


def test_collateral_rounds_nominal_price_after_split_and_adjusts_quantity():
    loan = loan_schedule("2026-10-15", "2026-10-16", 2., .5, SESSIONS,
                         daily_prices={d: 40. for d in ["2026-10-16", "2026-10-17", "2026-10-18"]},
                         daily_share_factors={d: .05 for d in ["2026-10-16", "2026-10-17", "2026-10-18"]})
    assert loan["fraction"] == pytest.approx(.05*41*.5/360*3/2)


def test_forecast_averages_each_holding_scenario_on_current_calendar():
    p = StudyPolicy()
    out = expected_carry([{"hold_sessions": 0}, {"hold_sessions": 1}], "2026-10-15", 10., .5, SESSIONS, p)
    assert out["expected_billed_days"] == 1.5
    assert out["fraction"] == pytest.approx(11*.5/360/10*1.5)


def fact(value, start, end, filed="2026-08-01"):
    return {"val": value, "start": start, "end": end, "filed": filed, "form": "10-Q"}


def test_ttm_requires_matching_fiscal_start_and_preserves_provenance():
    rows = [fact(100, "2025-01-01", "2025-12-31"), fact(30, "2025-01-01", "2025-06-30"), fact(40, "2026-01-01", "2026-06-30")]
    value = trailing_year(rows, "2026-06-30")
    assert value["value"] == 110 and len(value["evidence"]) == 3
    rows[1]["start"] = "2025-04-01"
    assert trailing_year(rows, "2026-06-30") is None


def test_future_restated_companyfacts_and_mixed_currency_are_excluded():
    raw = {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {
        "USD": [fact(100, "2025-01-01", "2025-12-31"), fact(1000, "2025-01-01", "2025-12-31", "2026-11-01")],
        "EUR": [fact(500, "2025-01-01", "2025-12-31")]}}}}}
    metrics, currency = monetary_facts(raw, "2026-10-15T12:00:00+00:00")
    assert all(r["filed"] < "2026-10-15" for r in metrics["revenues"])
    assert len({r["unit"] for r in metrics["revenues"]}) == 1
    assert currency in {"USD", "EUR"}
    assert all(r["val"] != 1000 for r in metrics["revenues"])


def test_utc_date_rollover_does_not_expose_a_later_eastern_filing():
    from reverse_splits.net_edge_clock import available
    cutoff = datetime.fromisoformat("2026-10-15T02:00:00+00:00")  # Oct 14, 10pm Eastern
    assert not available({"known_at": "2026-10-14"}, cutoff)
    assert available({"known_at": "2026-10-13"}, cutoff)
    raw = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [fact(99, "2026-01-01", "2026-06-30", "2026-10-14")]}}}}}
    assert monetary_facts(raw, cutoff.isoformat())[0]["revenues"] == []


def test_missing_debt_stays_unknown_and_ifrs_ratios_need_no_fx_conversion():
    from reverse_splits.fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    raw = {"cik": 1, "facts": {"ifrs-full": {}}}
    for tag, value in [("ProfitLoss", -5), ("NetCashFlowsFromUsedInOperatingActivities", -10)]:
        raw["facts"]["ifrs-full"][tag] = {"units": {"EUR": [fact(value, "2025-07-01", "2026-06-30")]}}
    for tag, value in [("Assets", 100), ("CashAndCashEquivalents", 5), ("Equity", 20)]:
        raw["facts"]["ifrs-full"][tag] = {"units": {"EUR": [{"val": value, "end": "2026-06-30", "filed": "2026-08-01", "form": "20-F"}]}}
    out = filing_rating(raw, "2026-10-15T00:00:00+00:00", screen, expected_cik="1")
    assert out["currency"] == "EUR" and "leverage" not in out["signals"]
    assert out["score"] is None  # Two mechanisms do not become three by filling missing debt with zero.


def test_financing_proceeds_can_offset_ownership_dilution():
    record = cited(shares_before=100, common_equity_value_before=1000,
                   basis="same_split_basis_claims_and_proceeds_reconciled",
                   scenarios=[{"probability": 1., "incremental_shares": 100, "net_proceeds_to_common": 1000}])
    out = capitalization(record, CUTOFF.isoformat())
    assert out["scenarios"][0]["ownership_dilution"] == .5
    assert out["expected_value_change"] == 0
    with pytest.raises(ValueError): capitalization(record | {"scenarios": [{"probability": .5}]}, CUTOFF.isoformat())


def test_import_batch_is_atomic_idempotent_and_rejects_fake_approval(tmp_path):
    path, output = tmp_path/"input.jsonl", tmp_path/"borrow.jsonl"
    good = cited(kind="indication", issuer="cik/1", annual_rate=.5, shares=100)
    path.write_text(json.dumps(good)+"\n"+json.dumps(good))
    assert import_records(path, output, "borrow")["imported"] == 1
    assert import_records(path, output, "borrow")["imported"] == 0
    path.write_text(json.dumps(good)+"\n"+json.dumps(good | {"kind": "approval", "approved": False}))
    with pytest.raises(ValueError): import_records(path, output, "borrow")
    assert len(output.read_text().splitlines()) == 1


def quote(t=0, **values):
    return {"kind": "quote", "timestamp": t, "known_at": t, "bid": 10., "ask": 10.02,
            "nbbo_verified": True, "is_trading": "Y", **values}


def trade(t, size, **values):
    return {"kind": "trade", "timestamp": t, "known_at": t, "price": 10.01,
            "size": size, "aggressor": "buy", "regular_trade": True, **values}


def test_ssr_quotes_alone_never_fill_and_queue_must_be_consumed():
    assert ssr_limit_fill([quote(), quote(1)], 0, 10)["shares"] == 0
    out = ssr_limit_fill([quote(), trade(1, 15), trade(2, 10)], 0, 10, queue_ahead=15)
    assert out["status"] == "filled" and out["price"] == pytest.approx(10.01)


@pytest.mark.parametrize("record", [trade(1, 100, price=10.), trade(1, 100, aggressor="sell"),
                                    trade(1, 100, regular_trade=False), trade(1, 100, known_at=2), trade(901, 100)])
def test_ssr_cannot_fill_on_ineligible_print_or_after_timeout(record):
    assert ssr_limit_fill([quote(), record], 0, 10)["shares"] == 0


def test_ssr_needs_fresh_national_quote_and_cancels_when_bid_reaches_limit():
    assert ssr_limit_fill([quote(nbbo_verified=False), trade(1, 100)], 0, 10)["shares"] == 0
    assert ssr_limit_fill([quote(), trade(20, 100)], 0, 10)["shares"] == 0
    assert ssr_limit_fill([quote(), quote(1, bid=10.01), trade(2, 100)], 0, 10)["status"] == "cancelled_price_test"
    assert ssr_limit_fill([quote(is_trading="N"), trade(1, 100)], 0, 10)["shares"] == 0


def test_daily_bracket_takes_adverse_bound_and_gap_is_not_capped():
    bars = [{"date": "2026-10-15", "open": 10., "high": 13., "low": 8., "close": 9.}]
    out = daily_exit(bars, 10., StudyPolicy(sessions=1))
    assert out["exit_price"] == 12 and out["reason"] == "stop_bar_bound"
    bars[0].update(open=15., high=16., close=14.)
    assert daily_exit(bars, 10., StudyPolicy(sessions=1))["exit_price"] == 15.


def test_unpriced_or_truncated_paths_remain_unresolved():
    assert daily_exit([], 10., StudyPolicy())["status"] == "unresolved_price_path"
    assert daily_exit([{"date": "2026-10-15"}], 10., StudyPolicy())["status"] == "unresolved_price_path"


def donors(policy):
    return [{"issuer": f"cik/{i}", "screen_rating": 80., "ratio": .1, "policy_hash": policy.fingerprint(),
             "gross_return": .1 if i % 2 else .08, "exit_at": "2026-10-01T20:00:00+00:00", "hold_sessions": 1} for i in range(30)]


def test_prior_only_issuer_holdout_and_bootstrap_are_reproducible():
    p = StudyPolicy()
    s = {"issuer": "cik/0", "known_at": CUTOFF.isoformat(), "screen_rating": 80., "ratio": .1}
    rows = donors(p)
    rows += [rows[0] | {"issuer": "future", "exit_at": "2026-10-16T00:00:00+00:00", "gross_return": 10}]
    out = payoff_forecast(s, rows, p)
    assert out["donors"] == 29 and "future" not in out["training_issuers"]
    assert out["gross_edge"] < out["unshrunk_gross_edge"]
    assert out == payoff_forecast(s, rows, p)
    assert out["gross_lower_bound"] <= out["gross_edge"]


def test_joint_size_search_does_not_use_a_tiny_order_cost_as_universal_veto():
    p = StudyPolicy(assumed_annual_borrow=0.)
    f = {"status": "estimated", "gross_edge": .015, "gross_lower_bound": .012,
         "holding_scenarios": [{"hold_sessions": 0}], "gross": {"variance": .02}}
    curve = [{"notional": 10000, "round_trip": .002, "uncertainty": 0., "issuers": 30}]
    small = size_position(f, curve, 10., "2026-10-15", 0., SESSIONS, p, Account(), adv=1e8)
    large = size_position(f, curve, 10., "2026-10-15", 0., SESSIONS, p, Account(equity=1000000.), adv=1e8)
    assert small["shares"] == 0 and large["shares"] > 0
    assert large["notional"]*large["stress_fraction"] <= 5000
    assert large["expected_commission"] == pytest.approx(2*max(1, large["shares"]*.005)/large["notional"])


def test_capacity_inventory_and_existing_positions_bind_size():
    p = StudyPolicy()
    f = {"status": "estimated", "gross_edge": .5, "gross_lower_bound": .4,
         "holding_scenarios": [{"hold_sessions": 0}], "gross": {"variance": .01}}
    curve = [{"notional": 10000, "round_trip": .001}]
    a = Account(equity=1000000.)
    out = size_position(f, curve, 10., "2026-10-15", .5, SESSIONS, p, a, adv=1e8, inventory=15)
    assert 0 < out["shares"] <= 15
    none = size_position(f, curve, 10., "2026-10-15", .5, SESSIONS, p, a, adv=1e8, used_stress=20000)
    assert none["shares"] == 0


def test_already_explored_history_is_never_relabelled_untouched_validation():
    out = calibration([{"prediction": .1, "realized": .05, "announcement": "2026-10-01"}], "2026-10-16")
    assert out["status"] == "historical_diagnostic_only" and out["prospective_observations"] == 0


def test_dated_accrual_cannot_be_an_entry_borrow_forecast():
    row = cited(issuer="cik/1", annual_rate=.9, shares=1000, kind="accrual")
    assert dated_borrow([row], "cik/1", CUTOFF, max_age_hours=24.) is None


def test_date_only_capitalization_import_does_not_skip_validation():
    from reverse_splits.net_edge_evidence import validate_import
    with pytest.raises(ValueError):
        validate_import(cited(event_id="x", known_at="2026-10-14", scenarios=[]), "capitalization")


def test_prospective_archive_is_immutable_and_never_backdated(tmp_path):
    from reverse_splits.net_edge_evidence import freeze_forecasts
    row = {"event_id": "x", "known_at": "2026-10-15T11:00:00+00:00", "entry_at": "2026-10-16T13:30:00+00:00",
           "policy": {"hold": 5}, "input_hashes": {"source": "abc"}, "forecast": {"status": "abstain", "reason": "missing_data"}}
    assert freeze_forecasts(tmp_path, [row], now=CUTOFF)["frozen"] == 1
    assert freeze_forecasts(tmp_path, [row | {"forecast": {"status": "abstain", "reason": "changed"}}], now=CUTOFF)["frozen"] == 0
    with pytest.raises(ValueError): freeze_forecasts(tmp_path, [row], now=datetime(2026, 10, 17, tzinfo=timezone.utc))


def portfolio_candidate(policy, complete=True):
    bars = [{"date": "2026-10-12", "open": 10., "high": 10.1, "low": 9., "close": 9.5}]
    o = daily_exit(bars, 10., policy)
    if not complete: o = {"status": "unresolved_price_path", "marks": []}
    o.update(entry_day="2026-10-12", entry_price=10., bars=bars, prior_adv=1e8)
    return {"snapshot": {"key": "x", "issuer": "cik/1", "ticker": "ABC", "database_ticker": "ABC", "screen_rating": 80.,
                         "framework": {"blocked": False, "complete": True, "thesis_supported": True},
                         "identity_verified": True, "profile_verified": True, "valuation_verified": True, "catalyst_verified": True,
                         "dilution": 0., "announcement_borrow": cited(issuer="cik/1", annual_rate=.5, shares=10000, kind="indication")},
            "outcome": o, "forecast": {"status": "estimated", "gross_edge": .5, "gross_lower_bound": .4,
            "holding_scenarios": [{"hold_sessions": 0}], "gross": {"variance": .01}}, "curve": [{"notional": 10000, "round_trip": .001}]}


class Store:
    def factor(self, *args): return 1.


def test_future_missing_price_cannot_exclude_an_eligible_entry():
    from reverse_splits.net_edge_study import simulate
    p = StudyPolicy(sessions=1)
    evidence = {"borrow": [], "executions": []}
    a = Account(equity=1e6)
    out = simulate([portfolio_candidate(p, complete=False)], p, a, SESSIONS, Store(), evidence, variant="net_edge")
    assert out["journal"][0]["shares"] > 0
    assert out["unresolved_admitted_names"] == 1 and out["open_positions"] == 1
    assert out["net_pnl"] is None and not out["performance_valid"]


def test_complete_evidence_can_use_observed_fills_without_future_cover_gating_entry():
    from reverse_splits.net_edge_study import clock, simulate
    p = StudyPolicy(sessions=1)
    entry = datetime.fromisoformat(clock("2026-10-12", 9)).replace(minute=30)
    approval = cited(issuer="cik/1", kind="approval", approved=True, reference="locate", shares=10000,
                     annual_rate=.5, known_at=entry.isoformat())
    fill = cited(kind="fill", issuer="cik/1", event_id="x", policy_hash=p.fingerprint(), phase="entry",
                 timestamp=entry.timestamp(), known_at=entry.isoformat(), price=10., shares=10000, observed=True,
                 compliance_verified=True, order_reference="entry")
    cover_time = datetime.fromisoformat(clock("2026-10-12"))
    cover = fill | {"phase": "cover", "timestamp": cover_time.timestamp(), "known_at": cover_time.isoformat(), "price": 9., "order_reference": "cover"}
    evidence = {"borrow": [approval], "executions": [fill, cover]}
    out = simulate([portfolio_candidate(p)], p, Account(equity=1e6), SESSIONS, Store(), evidence, variant="strict")
    assert out["trades"] == 1 and out["observed_fills"] == 2
    evidence["executions"] = [fill]
    missing = simulate([portfolio_candidate(p)], p, Account(equity=1e6), SESSIONS, Store(), evidence, variant="strict")
    assert missing["journal"][0]["shares"] > 0 and missing["net_pnl"] is None


def test_joint_funding_failure_suppresses_performance():
    from reverse_splits.net_edge_study import simulate
    p = StudyPolicy(sessions=1)
    c = portfolio_candidate(p)
    c["outcome"]["bars"][0]["high"] = 1e6
    out = simulate([c], p, Account(equity=1e6), SESSIONS, Store(), {"borrow": [], "executions": []}, variant="baseline")
    assert not out["funding_valid"] and out["net_pnl"] is None


def test_known_reverse_split_reduces_nominal_cover_commission():
    p = StudyPolicy()
    f = {"status": "estimated", "gross_edge": .5, "gross_lower_bound": .4,
         "holding_scenarios": [{"hold_sessions": 1}], "gross": {"variance": .01}}
    a = Account(equity=1e6, commission_per_share=.1, commission_max_fraction=1., name_stress_budget=.02)
    curve = [{"notional": 10000, "round_trip": .001}]
    ordinary = size_position(f, curve, 1., "2026-10-15", 0., SESSIONS, p, a, adv=1e8, inventory=1000)
    split = size_position(f | {"known_splits": [{"date": "2026-10-16", "ratio": .05}]}, curve, 1., "2026-10-15", 0., SESSIONS, p, a, adv=1e8, inventory=1000)
    assert split["expected_commission"] < ordinary["expected_commission"]
    assert split["net_distribution"]["mean"] == pytest.approx(split["net_edge"])


def test_cash_adjustments_are_paid_once_even_on_entry_day():
    from reverse_splits.net_edge_study import simulate
    p, a = StudyPolicy(sessions=1), Account(equity=1e6)
    evidence = {"borrow": [], "executions": [], "cashflows": []}
    first = simulate([portfolio_candidate(p)], p, a, SESSIONS, Store(), evidence, variant="net_edge")
    evidence["cashflows"] = [{"event_id": "x", "value_date": "2026-10-12", "cost_per_entry_share": .1}]
    second = simulate([portfolio_candidate(p)], p, a, SESSIONS, Store(), evidence, variant="net_edge")
    assert first["net_pnl"]-second["net_pnl"] == pytest.approx(first["journal"][0]["shares"]*.1)
    assert first["trade_ledger"][0]["net_pnl"]-second["trade_ledger"][0]["net_pnl"] == pytest.approx(first["journal"][0]["shares"]*.1)


def test_recall_blocks_older_borrow_and_covers_on_next_available_open():
    from reverse_splits.net_edge_study import recalled_outcome
    p = StudyPolicy(sessions=5)
    c = portfolio_candidate(p, complete=False)
    c["outcome"]["bars"].append({"date": "2026-10-13", "open": 11., "close": 10.})
    recall = cited(issuer="cik/1", kind="recall", known_at="2026-10-12T18:00:00+00:00")
    out = recalled_outcome(c, [recall])["outcome"]
    assert out["exit_day"] == "2026-10-13" and out["exit_price"] == 11.
    old = cited(issuer="cik/1", kind="indication", known_at="2026-10-12T17:00:00+00:00", annual_rate=.5, shares=1000)
    assert dated_borrow([old, recall], "cik/1", datetime(2026, 10, 12, 19, tzinfo=timezone.utc)) is None


def test_sec_missing_cik_is_bound_independently_and_raw_bytes_preserved(tmp_path, monkeypatch):
    import io
    from reverse_splits.net_edge_evidence import digest, fetch_missing_companyfacts
    raw = json.dumps({"entityName": "Example Corp.", "facts": {}}).encode()
    identity = json.dumps({"cik": "0000000001", "name": "Example Corp.", "formerNames": []}).encode()
    responses = iter([raw, identity])
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kw: io.BytesIO(next(responses)))
    monkeypatch.setattr("time.sleep", lambda *args: None)
    result = fetch_missing_companyfacts(["1"], tmp_path/"missing", tmp_path/"cache", "test@example.com")
    path = tmp_path/"cache/CIK0000000001.json"
    assert result[0]["status"] == "downloaded" and path.read_bytes() == raw
    assert json.loads(path.with_name(path.name+".identity.json").read_text())["companyfacts_sha256"] == digest(path)


def test_ssr_can_use_fresh_quote_immediately_before_the_decision():
    assert ssr_limit_fill([quote(), trade(1, 100)], .5, 10)["status"] == "filled"


def test_observed_cover_uses_nominal_post_split_quantity_and_price():
    from reverse_splits.net_edge_study import clock, simulate
    p = StudyPolicy(sessions=5)
    c = portfolio_candidate(p)
    c["outcome"].update(status="daily_benchmark", exit_day="2026-10-13", exit_price=9., reason="time",
                        marks=[{"date": "2026-10-12", "close": 10.}])
    c["outcome"]["bars"].append({"date": "2026-10-13", "open": 9., "high": 9., "close": 9.})
    entry = datetime.fromisoformat(clock("2026-10-12", 9)).replace(minute=30)
    fill = cited(kind="fill", issuer="cik/1", event_id="x", policy_hash=p.fingerprint(), phase="entry", timestamp=entry.timestamp(), known_at=entry.isoformat(), price=10., shares=10000, observed=True, compliance_verified=True, order_reference="entry")
    cover_time = datetime.fromisoformat(clock("2026-10-13"))
    cover = fill | {"phase": "cover", "timestamp": cover_time.timestamp(), "known_at": cover_time.isoformat(), "price": 180., "shares": 1000, "order_reference": "cover"}
    approval = cited(issuer="cik/1", kind="approval", approved=True, reference="locate", shares=10000, annual_rate=0., known_at=entry.isoformat())
    class SplitStore:
        def factor(self, ticker, first, last): return .05 if last >= "2026-10-13" else 1.
    out = simulate([c], p, Account(equity=1e6), SESSIONS, SplitStore(), {"borrow": [approval], "executions": [fill, cover]}, variant="strict")
    assert out["trades"] == 1 and out["net_pnl"] > 0
    assert out["trade_ledger"][0]["net_pnl"] == pytest.approx(out["net_pnl"])


def test_prospective_outcomes_cannot_use_future_source_availability(tmp_path):
    from reverse_splits.net_edge_evidence import freeze_forecasts, record_outcomes
    row = {"event_id": "x", "known_at": "2026-10-14T11:00:00+00:00", "entry_at": "2026-10-15T11:30:00+00:00",
           "policy": {"sessions": 5}, "input_hashes": {"source": "abc"}, "forecast": {"status": "abstain", "reason": "missing"}}
    result = freeze_forecasts(tmp_path, [row], now=datetime(2026, 10, 15, 11, tzinfo=timezone.utc))
    forecast = json.loads(open(result["path"]).read())
    outcome = cited(forecast_sha256=forecast["record_sha256"], exit_at="2026-10-15T11:45:00+00:00", gross_return=.1, net_return=.09,
                    known_at="2026-10-16T00:00:00+00:00")
    with pytest.raises(ValueError): record_outcomes(tmp_path, [outcome], now=CUTOFF)
