from datetime import datetime, timezone

import pytest
from reverse_splits.net_edge import (
    FRAMEWORKS,
    EdgePolicy,
    carry,
    conviction,
    dilution,
    distribution,
    forecast,
    framework_assessment,
    size_fraction,
)

SESSIONS = ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15",
            "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
CUTOFF = datetime(2026, 10, 15, 14, tzinfo=timezone.utc)


def test_carry_uses_settled_calendar_days_not_fractional_session():
    same = carry("2026-10-15", "2026-10-15", 2.01, .5, SESSIONS)
    assert same["fraction"] == 0
    minimum = carry("2026-10-15", "2026-10-15", 2.01, .5, SESSIONS, minimum_days=1)
    assert minimum["fraction"] == pytest.approx(3 * .5 / 360 / 2.01)
    # Thursday sale settles Friday; Friday cover settles Monday: three days.
    weekend = carry("2026-10-15", "2026-10-16", 2.01, .5, SESSIONS)
    assert weekend["billed_calendar_days"] == 3
    assert weekend["fraction"] == pytest.approx(3 * minimum["fraction"])


def test_settlement_transition_and_holidays():
    calendar = ["2024-05-22", "2024-05-23", "2024-05-24", "2024-05-28", "2024-05-29", "2024-05-30", "2024-05-31"]
    fee = carry("2024-05-23", "2024-05-24", 10, 1, calendar)
    assert fee["entry_settlement"] == "2024-05-28"
    assert fee["exit_settlement"] == "2024-05-29"
    # Friday T+2 and Tuesday T+1 both settle Wednesday, even across the holiday.
    assert carry("2024-05-24", "2024-05-28", 10, 1, calendar)["billed_calendar_days"] == 0
    assert carry("2024-05-28", "2024-05-29", 10, 1, calendar)["entry_settlement"] == "2024-05-29"


def test_daily_borrow_rates_and_collateral_do_not_compound():
    result = carry("2026-10-15", "2026-10-16", 10, .5, SESSIONS,
                   daily_prices={"2026-10-17": 20}, daily_rates={"2026-10-18": 1.})
    expected = (11 * .5 + 21 * .5 + 11 * 1.) / 360 / 10
    assert result["fraction"] == pytest.approx(expected)
    with pytest.raises(ValueError):
        carry("2026-10-16", "2026-10-15", 10, .5, SESSIONS)


def dilution_record(**values):
    return {"known_at": "2026-10-14T14:00:00Z", "source_url": "https://www.sec.gov/filing", "locator": "offering terms",
            "shares_before": 100, "incremental_shares": 100,
            "common_equity_value_before": 1000, "net_proceeds_to_common": 0, **values}


def test_actual_dilution_reconciles_cash_proceeds_and_ignores_split_mechanics():
    discounted = dilution(dilution_record(), CUTOFF)
    assert discounted["ownership_dilution"] == .5
    assert discounted["per_share_value_change"] == -.5
    fair = dilution(dilution_record(net_proceeds_to_common=1000), CUTOFF)
    assert fair["ownership_dilution"] == .5
    assert fair["per_share_value_change"] == 0
    assert fair["mechanical_split_dilution"] == 0
    assert dilution(None, CUTOFF)["ownership_dilution"] is None
    assert dilution(dilution_record(known_at="2026-10-16T14:00:00Z"), CUTOFF)["status"] == "unavailable"


def review(framework, **changes):
    return {"framework": framework, "known_at": "2026-10-14T14:00:00Z", "source_url": "https://www.sec.gov/filing",
            "locator": "p.4", "mechanism": "Cash burn requires refinancing", "contrary_evidence": "Financing could improve",
            "falsifier": "Positive recurring cash flow", "status": "supported", **changes}


def test_all_framework_routes_need_dated_evidence_and_falsifiers():
    reviews = [review(f) for f in FRAMEWORKS]
    assert framework_assessment(reviews, CUTOFF)["complete"]
    reviews[0] = review(FRAMEWORKS[0], known_at="2026-10-16T00:00:00Z")
    result = framework_assessment(reviews, CUTOFF)
    assert not result["complete"]
    assert FRAMEWORKS[0] in result["missing"]
    reviews[0] = review(FRAMEWORKS[0], falsifier="")
    assert not framework_assessment(reviews, CUTOFF)["complete"]
    assert not framework_assessment([review(f, status="not_applicable") for f in FRAMEWORKS], CUTOFF)["complete"]


def test_future_review_revision_cannot_overwrite_prior_contradiction():
    reviews = [review(f) for f in FRAMEWORKS]
    reviews += [review("cash_burn", status="contradicted", known_at="2026-10-14T15:00:00Z"),
                review("cash_burn", status="supported", known_at="2026-10-16T15:00:00Z")]
    result = framework_assessment(reviews, CUTOFF)
    assert result["contradicted"] == ["cash_burn"]
    assert not result["complete"]


def test_deterioration_is_provisional_until_full_framework_exists():
    f = {"score": 80, "historical_eligible": True, "source": "raw_companyfacts", "evidence_count": 4,
         "latest_period": "2026-06-30"}
    assert conviction(f, [], CUTOFF)["rating"] is None
    assert conviction(f, [], CUTOFF)["screen_rating"] == 80
    assert conviction(f, [review(key) for key in FRAMEWORKS], CUTOFF)["rating"] == 88
    assert conviction({**f, "source": "ssi_latest_revision_cache"}, [], CUTOFF)["screen_rating"] is None


def snapshot():
    return {"known_at": "2026-10-15T14:00:00Z", "issuer": "cik/subject", "screen_rating": 70,
            "entry_day": "2026-10-15", "ratio": .1, "dilution": None}


def donor(i, p, **changes):
    return {"issuer": f"cik/{i}", "exit_at": "2026-10-14T20:00:00Z", "screen_rating": 70, "ratio": .1,
            "dilution": None, "gross_return": .1 if i % 2 else -.05, "hold_minutes": 60,
            "calendar_hold_days": 0, "hold_sessions": 0, "policy_hash": p.fingerprint(), **changes}


def test_forecast_excludes_future_outcomes_same_issuer_and_other_exit_policies():
    p = EdgePolicy(min_donors=3)
    donors = [donor(i, p) for i in range(4)]
    base = forecast(snapshot(), donors, p, 10, .5, SESSIONS, .01, .002)
    contaminated = donors + [donor(50, p, exit_at="2026-10-15T14:00:01Z", gross_return=-100),
                             donor(51, p, issuer="cik/subject", gross_return=-100),
                             donor(52, p, policy_hash="other", gross_return=-100)]
    assert forecast(snapshot(), contaminated, p, 10, .5, SESSIONS, .01, .002) == base
    assert base["gross_edge"] == pytest.approx(.025)
    assert base["net_edge"] == pytest.approx(.013)
    assert base["expected_hold_minutes"] == 60
    assert base["expected_borrow"] == 0


def test_repeated_issuers_cannot_satisfy_minimum_training_depth():
    p = EdgePolicy(min_donors=3)
    donors = [donor(i, p, issuer="same") for i in range(100)]
    assert forecast(snapshot(), donors, p, 10, .5, SESSIONS, 0, 0)["status"] == "insufficient_prior_issuers"


def test_expected_borrow_averages_exit_scenarios_before_net_edge():
    p = EdgePolicy(min_donors=2)
    donors = [donor(1, p, hold_sessions=0), donor(2, p, hold_sessions=1)]
    e = forecast(snapshot(), donors, p, 10, 1, SESSIONS, 0, 0)
    # Half same-day, half next-day cover (3 billed days across the weekend).
    assert e["expected_borrow"] == pytest.approx(.5 * 3 * 11 / 360 / 10)
    assert e["expected_billed_days"] == pytest.approx(1.5)
    assert e["net_edge"] == pytest.approx(e["gross_edge"] - e["expected_borrow"])
    friday = forecast({**snapshot(), "entry_day": "2026-10-16"}, donors, p, 10, 1, SESSIONS, 0, 0)
    assert friday["expected_billed_days"] == .5  # Monday/Tuesday settlement, not Friday/Monday.
    zero_rate = forecast(snapshot(), donors, p, 10, 0, SESSIONS, 0, 0)
    assert zero_rate["expected_billed_days"] == 1.5
    assert zero_rate["expected_borrow"] == 0


def test_skew_has_short_pnl_sign_and_sizing_rejects_negative_edge():
    assert distribution([-.1, -.1, -.1, .5])["skewness"] > 0
    assert distribution([.1, .1, .1, -.5])["skewness"] < 0
    assert distribution([1, 1])["skewness"] is None
    p = EdgePolicy()
    e = {"net_edge": -.01}
    assert size_fraction(e, 90, p) == 0
    e = {"net_edge": .1, "net": {"variance": .1}, "expected_borrow": .01}
    assert 0 < size_fraction(e, 90, p) <= p.max_name_stress_loss / (2 + .03)
    assert size_fraction(e, 0, p) == 0


def test_fee_increase_reduces_edge_and_size():
    p = EdgePolicy(min_donors=2, minimum_billed_days=1)
    donors = [donor(i, p) for i in range(10)]
    low = forecast(snapshot(), donors, p, 10, .1, SESSIONS, 0, 0)
    high = forecast(snapshot(), donors, p, 10, 10, SESSIONS, 0, 0)
    assert high["net_edge"] < low["net_edge"]
    assert size_fraction(high, 80, p) <= size_fraction(low, 80, p)


def test_cost_forecast_matches_the_proposed_order_size_and_excludes_future_costs():
    from reverse_splits.net_edge_research import estimate
    p = EdgePolicy(min_donors=2)
    donors = [{**donor(i, p), "announcement_price": 10, "prior_dollar_adv": 10000,
               "costs": {125: .001, 500: .05, 1250: .5}} for i in range(4)]
    s = {**snapshot(), "price": 10, "prior_dollar_adv": 10000}
    small = estimate(s, donors, p, SESSIONS, 125)
    large = estimate(s, donors, p, SESSIONS, 1250)
    assert small["expected_slippage"] == .001
    assert large["expected_slippage"] == .5
    assert small["net_edge"] > 0 > large["net_edge"]
    future = {**donors[0], "issuer": "future", "exit_at": "2026-10-16T20:00:00Z", "costs": {125: 100, 500: 100, 1250: 100}}
    assert estimate(s, donors + [future], p, SESSIONS, 125) == small


def test_halted_profit_take_can_cover_at_a_loss_without_capping_the_fill():
    import numpy as np
    from reverse_splits.net_edge_research import exit_point
    t = datetime(2026, 10, 15, 14, tzinfo=timezone.utc).timestamp()
    path = {"ts": np.array([t, t + 1, t + 2, t + 3]), "mid": np.array([100, 100, 89, 150]),
            "bid": np.array([99, 99, 88, 149]), "ask": np.array([101, 101, 90, 151]),
            "bid_size": np.full(4, 100), "ask_size": np.full(4, 100),
            "tradable_quote": np.array([True, True, False, True]),
            "status_history": {"is_trading": {"ts": [t, t + 2, t + 3], "value": ["Y", "N", "Y"]}}}
    iso = lambda v: datetime.fromtimestamp(v, timezone.utc).isoformat()
    points = {"test": {"1/entry": {"fill_at": iso(t + .1), "decision_at": iso(t), "reference_mid": 100},
                       "1/close": {"decision_at": iso(t + 3)}}}
    result = exit_point({"key": "test"}, path, points, EdgePolicy())
    assert result["reason"] == "profit_take"
    assert result["exit_mid"] == 150
    assert result["queued_seconds"] == pytest.approx(1.)
    assert not result["missing_exit_quote"]


def test_replay_reconciles_costs_and_gives_negative_edge_zero_shares():
    from reverse_splits.net_edge_research import replay
    p = EdgePolicy(min_donors=2)
    rows = [{"key": "test", "ticker": "TEST", "issuer": "cik/test", "date": "2026-10-15", "adv": 200000, "dollar_adv": 200000}]
    snapshots = {"test": {"status": "frozen", "screen_rating": 70,
        "conviction": {"rating": None, "framework": {"contradicted": []}}}}
    outcomes = {"test": {"entry_blocked": False, "entry_mid": 1, "exit_mid": .9, "exit_at": "2026-10-15T20:00:00Z",
        "entry_book": None, "exit_book": None, "decision_book": None, "reason": "time", "hold_minutes": 100,
        "missing_exit_quote": True}}
    estimates = {"test": {"status": "estimated", "net_edge": .02, "gross_edge": .04, "net": {"variance": .04}, "expected_borrow": 0,
        "expected_commission": .001, "expected_slippage": .005, "annual_borrow": .5}}
    args = (rows, snapshots, outcomes, estimates, p, SESSIONS, ["2026-10-15", "2026-10-16"], "net_edge")
    result = replay(*args)
    assert result["trades"] == 1
    t = result["trade_ledger"][0]
    assert result["portfolio"]["net_pnl"] == pytest.approx(t["net"])
    assert t["net"] == pytest.approx(t["gross_pnl"] - t["borrow"] - t["slippage"] - t["commission"])
    assert t["estimated_fill"]
    estimates["test"]["net_edge"] = -.01
    result = replay(*args)
    assert result["trades"] == 0
    assert result["journal"][0]["shares"] == 0
    assert result["journal"][0]["reason"] == "nonpositive_net_edge"
