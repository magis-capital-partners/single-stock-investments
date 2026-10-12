"""As-of routing, evidence independence and unchanged strategy economics."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from reverse_splits.framework_plan import PATHS, furnace_drafts, plan, routes, summarize
from reverse_splits.strategy import decisions, evaluate, record_decision


def score():
    return {"as_of":"2026-10-11","source":"raw_companyfacts","historical_eligible":True,
            "score":75,"evidence_count":4,"latest_period":"2026-06-30",
            "signals":{"cash_burn":{"value":.5,"score":1},"leverage":{"value":.6,"score":1},
                       "accrual_ratio":{"value":.15,"score":1},"profit_without_cash":{"value":.7,"score":.7}},
            "evidence":[{"metric":"cash","period":"2026-06-30","filed":"2026-08-01","value":100,"source_urls":["https://www.sec.gov/a"]},
                        {"metric":"cash","period":"2026-03-31","filed":"2026-05-01","value":200},
                        {"metric":"revenues","period":"2026-06-30","filed":"2026-08-01","value":300},
                        {"metric":"revenues","period":"2026-03-31","filed":"2026-05-01","value":999},
                        {"metric":"revenues","period":"2025-06-30","filed":"2025-08-01","value":250}]}


def test_related_indicators_route_once_without_earning_support():
    x=routes(score())
    suggested=[r for r in x["routes"] if r["suggested"]]
    assert {r["path_id"] for r in suggested}=={"financing_pressure","refinancing_pressure","earnings_cash_gap"}
    accounting=next(r for r in suggested if r["path_id"]=="earnings_cash_gap")
    assert len(accounting["observations"])==2
    assert x["suggested_families"]==["earnings_quality","funding"]
    assert all(r["automatic_support"] is False for r in x["routes"])
    assert all(not r["suggested"] for r in x["routes"] if r["path_id"] in {"issuance_dilution","reporting_integrity","governance_control"})


@pytest.mark.parametrize("updates",[{"source":"ssi_latest_revision_cache"},{"historical_eligible":False}])
def test_limited_vintage_never_creates_automatic_prompts(updates):
    s=score();s.update(updates)
    assert not any(r["suggested"] for r in routes(s)["routes"])


def test_none_nan_and_pseudo_observations_do_not_generate_support():
    s=score();s["signals"]={"cash_burn":{"value":None,"score":1},"leverage":{"value":float("nan"),"score":1},"profit_without_cash":{"value":None,"score":0}}
    assert not any(r["suggested"] for r in routes(s)["routes"])


def test_future_and_same_day_facts_are_excluded_before_comparisons():
    s=score()
    s["evidence"]+=[{"metric":"cash","period":"2026-09-30","filed":"2026-10-12","value":9999},
                     {"metric":"cash","period":"2026-08-31","filed":"2026-10-11","value":8888}]
    cash=next(r for r in routes(s)["routes"] if r["path_id"]=="financing_pressure")["comparison_facts"][0]
    assert cash["new_value"]==100 and cash["prior_value"]==200


def test_flow_comparison_uses_same_quarter_prior_year_not_prior_quarter():
    x=routes(score())
    revenue=next(r for r in x["routes"] if r["path_id"]=="demand_decay")["comparison_facts"][0]
    assert revenue["new_value"]==300
    assert revenue["prior_value"]==250
    assert revenue["prior_period"]=="2025-06-30"


def test_missing_comparable_fact_remains_unknown():
    s=score();s["evidence"]=s["evidence"][:1]
    c=next(r for r in routes(s)["routes"] if r["path_id"]=="financing_pressure")["comparison_facts"][0]
    assert c["prior_value"] is None


def test_catalog_uses_real_short_alpha_ids():
    from reverse_splits.config import load_config
    from reverse_splits.fundamentals import FundamentalBridge
    valid={f["id"] for f in FundamentalBridge(load_config(ensure_dirs=False)).manifest()["frameworks"]}
    assert valid, "SSI frameworks.json not found through the bridge"
    assert all(set(p["frameworks"])<=valid for p in PATHS)
    assert plan()["adopted_on"]=="2026-10-11"


def test_plan_pending_until_dated_sources_and_disconfirmation_exist():
    p={"selected_path_ids":["financing_pressure","refinancing_pressure"],"primary_path_id":"financing_pressure",
       "causal_chain":"Cash gap forces expensive financing", "market_belief":"Cheap funding arrives", "independence_rationale":"Both routes describe the same funding problem", "lens_reviews":[{"lens_id":"cash_and_financing","status":"supported"}]}
    x=summarize(score(),p)
    assert x["families"]==["funding"] and x["related_warnings"] is True
    assert x["status"]=="research_plan_pending"
    assert any("dated source" in issue for issue in x["issues"])
    p["lens_reviews"][0].update(known_at="2026-10-10",source_url="https://www.sec.gov/a",locator="Liquidity note",mechanism="Cash gap",contradictory_evidence="Signed funding",falsifier="Funding extends runway")
    assert summarize(score(),p)["status"]=="research_plan_documented"
    p["lens_reviews"][0]["known_at"]="2026-10-12"
    assert summarize(score(),p)["status"]=="research_plan_pending"


@pytest.mark.parametrize("p",[{"selected_path_ids":[{}]}, {"selected_path_ids":["unknown"]}, {"selected_path_ids":["financing_pressure","financing_pressure"]}, {"primary_path_id":"financing_pressure"}])
def test_invalid_route_selection_is_rejected(p):
    with pytest.raises(ValueError):summarize(score(),p)


def test_selection_cannot_raise_grade_or_bypass_strategy_gates():
    l={"ticker":"TEST","fundamental":score(),"announcement_date":"2026-10-10"}
    p={"as_of":"2026-10-11","selected_path_ids":["financing_pressure"],"primary_path_id":"financing_pressure"}
    r=evaluate(l,p,datetime(2026,10,11,15,tzinfo=timezone.utc))
    assert r["status"]=="review_required" and r["research_quality"] is None
    assert r["framework_plan"]["status"]=="research_plan_pending"


def test_furnace_drafts_preserve_unknowns_and_require_review():
    p={"selected_path_ids":["financing_pressure"],"lens_reviews":[{"lens_id":"cash_and_financing","status":"supported","prior_value":"200","new_value":"100","known_at":"2026-10-10","source_url":"https://www.sec.gov/a","locator":"Liquidity note","mechanism":"Cash declined","falsifier":"Signed funding"}]}
    d=furnace_drafts("TEST",score(),p)[0]
    assert d["prior_value"]==200 and d["new_value"]==100
    assert d["tags"]==[] and d["proposed_tags"]
    assert d["review_status"]=="draft_requires_furnace_review" and d["confidence"]=="unscored"
    assert d["form"] is None and d["accession"] is None
    p["lens_reviews"][0]["new_value"]="nan"
    with pytest.raises(ValueError):furnace_drafts("TEST",score(),p)


def test_saved_plan_and_furnace_evidence_are_frozen(tmp_path):
    cfg=SimpleNamespace(data_dir=tmp_path)
    l={"ticker":"TEST","fundamental":score(),"announcement_date":"2026-10-10"}
    p={"as_of":"2026-10-11","decision":"review","reason":"Research funding hypothesis","selected_path_ids":["financing_pressure"],"primary_path_id":"financing_pressure"}
    saved=record_decision(cfg,l,p,datetime(2026,10,11,15,tzinfo=timezone.utc))
    p["primary_path_id"]="reporting_integrity"
    r=decisions(cfg)[0]
    assert r["inputs"]["primary_path_id"]=="financing_pressure"
    assert r["research_plan"]["version"]=="fundamentals_frameworks.v1"
    assert len(r["furnace_drafts"])==1
    assert saved["policy"]["version"]=="RSI-1.0"
