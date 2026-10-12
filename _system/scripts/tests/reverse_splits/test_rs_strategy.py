"""Meaningful invariants: no invented readiness and capital survives stated stress."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import hashlib
import json

import pytest

from reverse_splits.strategy import GATES, RULES, decisions, evaluate, handoff, policy, portfolio_stress, record_decision, triage

NOW = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)


def lead():
    return {"ticker": "TEST", "cik": "1", "announcement_date": "2026-10-08",
            "announced_ex_date": "2026-10-14", "announcement_url": "https://www.sec.gov/example",
            "fundamental": {"as_of": "2026-10-09", "score": 75, "source": "raw_companyfacts",
            "historical_eligible": True, "evidence_count": 4, "latest_period": "2026-06-30"}}


def inputs():
    from reverse_splits.research_lens import LENSES
    return {"ticker": "TEST", "as_of": "2026-10-09", "equity": 50000, "price": 10,
        "target_price": 5, "adv": 1000000, "fee_annual": 1, "round_trip_cost_fraction": .02,
        "locate_shares": 1000, "locate_at": (NOW-timedelta(hours=1)).isoformat(),
        "quote_at": (NOW-timedelta(minutes=2)).isoformat(), "borrow_reference": "PAPER-123",
        "identity_verified": True, "ssr_checked": True, "portfolio_reconciled": True,
        "catalyst": "Dated contractual funding deadline; target reconciled to common equity",
        "catalyst_date": "2026-10-12", "reason": "Test-only complete evidence", "decision": "review",
        "lens_reviews": [{"lens_id": l["id"], "status": "supported", "known_at": "2026-10-08",
                         "source_url": "https://www.sec.gov/example", "locator": "Item 1",
                         "mechanism": "Test mechanism", "contradictory_evidence": "Test recovery case",
                         "falsifier": "Test measurable falsifier"} for l in LENSES]}


def test_ready_requires_all_gates_and_unknown_is_not_zero_grade():
    p = inputs()
    ready = evaluate(lead(), p, NOW)
    assert ready["status"] == "paper_ready"
    assert ready["research_quality"] == 100
    p["lens_reviews"][0]["known_at"] = "2026-10-10"
    blocked = evaluate(lead(), p, NOW)
    assert blocked["status"] == "review_required"
    assert blocked["research_quality"] is None


def test_published_gate_catalog_matches_the_gates_evaluate_checks():
    evaluated = [g["id"] for g in evaluate(lead(), inputs(), NOW)["gates"]]
    assert [g["id"] for g in GATES] == evaluated
    assert all(g["label"] and g["requires"] for g in GATES)
    assert policy()["parameters"] == RULES
    assert policy()["rules_hash"] == hashlib.sha256(json.dumps(RULES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.mark.parametrize("change", [
    {"identity_verified": False}, {"portfolio_reconciled": False}, {"ssr_checked": False},
    {"locate_at": "2026-10-09"}, {"quote_at": (NOW-timedelta(minutes=16)).isoformat()},
    {"target_price": 8}, {"locate_shares": 0}, {"existing_names": 3}, {"fee_annual": 10},
])
def test_missing_or_unaffordable_execution_blocks_ready(change):
    p=inputs();p.update(change)
    assert evaluate(lead(), p, NOW)["status"] != "paper_ready"


def test_old_announcement_and_already_effective_split_never_become_fresh():
    old=lead();old["announcement_date"]="2024-01-01"
    assert not next(g for g in evaluate(old, inputs(), NOW)["gates"] if g["id"]=="announcement")["pass"]
    done=lead();done["announced_ex_date"]="2026-10-09"
    assert evaluate(done, inputs(), NOW)["status"] != "paper_ready"
    after_split=inputs();after_split["catalyst_date"]="2026-10-14"
    assert evaluate(lead(),after_split,NOW)["status"] != "paper_ready"


def test_raw_vintage_and_period_freshness_are_mandatory():
    s=lead()["fundamental"]
    assert triage(s, "2026-10-09")["eligible"]
    for changes in [{"source":"ssi_latest_revision_cache"}, {"score":59}, {"evidence_count":2}, {"latest_period":"2025-12-31"}]:
        assert not triage({**s,**changes}, "2026-10-09")["eligible"]


def test_joint_loss_and_low_price_margin_constrain_whole_shares():
    p=inputs();p.update(price=1.01,target_price=.50,existing_sleeve_stress_loss=940,existing_margin=37000)
    r=evaluate(lead(),p,NOW)["sizing"]
    assert r["shares"] == int(r["shares"])
    assert r["stress_loss"] <= 250
    assert r["joint_stress_loss"] <= 1000
    assert r["stressed_position_margin"]+37000 <= r["remaining_equity_after_joint_stress"]-10000
    p["existing_sleeve_stress_loss"]=1000
    assert evaluate(lead(),p,NOW)["sizing"]["shares"] == 0


def test_losses_outside_sleeve_reduce_available_account_margin():
    p=inputs();p.update(existing_margin=39000,other_account_stress_loss=1000)
    assert evaluate(lead(),p,NOW)["sizing"]["shares"]==0


def test_contradiction_blocks_despite_high_deterioration():
    p=inputs();p["lens_reviews"][1]["status"]="contradicted"
    r=evaluate(lead(),p,NOW)
    assert r["research_quality"] < 100
    assert r["status"] != "paper_ready"


def test_six_documented_lenses_without_operating_mechanism_still_block():
    p=inputs()
    for r in p["lens_reviews"]:
        if r["lens_id"] in {"cash_and_financing","operating_impairment"}:
            r["status"]="unresolved"
    assert evaluate(lead(),p,NOW)["status"] != "paper_ready"


def test_saved_snapshot_and_corrections_are_append_only(tmp_path):
    cfg=SimpleNamespace(data_dir=tmp_path)
    p=inputs()
    original=record_decision(cfg,lead(),p,NOW)
    p.update(reason="New evidence",supersedes=original["id"],decision="pass")
    revised=record_decision(cfg,lead(),p,NOW+timedelta(minutes=1))
    rows=decisions(cfg)
    assert len(rows)==2 and rows[-1]["reason"]=="Test-only complete evidence"
    assert revised["previous_hash"]==original["record_hash"]
    assert revised["supersedes"]==original["id"]
    for row in rows:
        expected=row.pop("record_hash")
        actual=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        assert actual==expected
    p.update(supersedes="missing")
    with pytest.raises(ValueError):record_decision(cfg,lead(),p,NOW)
    assert len(decisions(cfg))==2
    export=handoff(cfg,{"policy":policy(),"portfolio_contract":{}})
    assert export["performance"]["net_twr"] is None
    assert export["performance"]["closed_paper_trades"] == 0


def test_decisions_db_path_on_the_config_is_honoured(tmp_path):
    cfg=SimpleNamespace(data_dir=tmp_path/"ignored", decisions_db_path=tmp_path/"local"/"strategy_decisions.sqlite")
    record_decision(cfg,lead(),inputs(),NOW)
    assert (tmp_path/"local"/"strategy_decisions.sqlite").exists()
    assert not (tmp_path/"ignored").exists()
    assert len(decisions(cfg))==1


def test_historical_decision_cannot_claim_prospective_readiness(tmp_path):
    cfg=SimpleNamespace(data_dir=tmp_path)
    l=lead();l["fundamental"]["as_of"]="2026-10-08"
    p=inputs();p.update(as_of="2026-10-08",decision="paper_ready")
    with pytest.raises(ValueError):record_decision(cfg,l,p,NOW)
    p["decision"]="pass"
    assert record_decision(cfg,l,p,NOW)["prospective"] is False


@pytest.mark.parametrize("field,value",[("equity",float("nan")),("price",-1),("existing_names",1.5),("fee_annual",float("inf"))])
def test_invalid_financial_inputs_fail(field,value):
    p=inputs();p[field]=value
    with pytest.raises(ValueError):evaluate(lead(),p,NOW)


def test_portfolio_squeeze_can_worsen_risk_despite_lower_net_exposure():
    r=portfolio_stress({"equity":100000,"long_notional":50000,"other_short_notional":10000,"sleeve_notional":1000})
    assert r["net_exposure"]==.39
    scenario=r["scenarios"][-1]
    assert scenario["combined_pnl"]==scenario["base_pnl"]-2000
    assert scenario["combined_return"]==scenario["combined_pnl"]/100000
