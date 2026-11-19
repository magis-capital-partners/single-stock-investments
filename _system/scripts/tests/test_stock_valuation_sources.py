"""Foreign currency, vendor durations and issuer identity must remain explicit."""
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stock_valuation_sources import vendor_history
from stock_valuation_models import build_research_model
from stock_valuation_identity import apply_identity_to_model, quarantine_prior_valuation
import pytest

def quote():return {"value":100,"currency":"HKD","as_of":"2026-11-18","source_url":"https://finance.yahoo.com/quote/0700.HK/history/","symbol":"0700.HK"}
def vendor():return {"symbol":"0700.HK","source_url":"https://query1.finance.yahoo.com/timeseries","retrieved_at":"2026-11-19T12:00:00+00:00","data":{"timeseries":{"result":[{"meta":{"symbol":["0700.HK"]},"annualDilutedEPS":[{"asOfDate":"2025-12-31","periodType":"12M","currencyCode":"CNY","reportedValue":{"raw":10}},{"asOfDate":"2026-09-30","periodType":"3M","currencyCode":"CNY","reportedValue":{"raw":999}}]}]}}}

def test_vendor_preserves_native_reporting_unit_and_does_not_annualize_quarters():
    h=vendor_history(vendor(),"2026-11-19")
    assert h["currency"]=="CNY" and h["series"][0]["unit"]=="CNY/shares"
    assert [p["value"] for p in h["series"][0]["annual"]]==[10]
    bad=vendor();bad["data"]["timeseries"]["result"][0]["meta"]["symbol"]=["OTHER"]
    with pytest.raises(ValueError,match="listing"):vendor_history(bad,"2026-11-19")

def test_spot_fx_is_dated_exact_pair_and_does_not_clear_an_adr_gap():
    h=vendor_history(vendor(),"2026-11-19");q=quote()
    fx={"from_currency":"CNY","to_currency":"HKD","as_of":"2026-11-18","rate":1.1,"source_url":"https://finance.yahoo.com/fx"}
    q["fx_to_listing"]=fx
    m=build_research_model("0700.HK",{},h,q,basis_verified=True)
    assert m["inputs"]["anchor"]==11 and m["anchor"]["reporting_value"]==10
    assert m["anchor"]["reporting_currency"]=="CNY" and m["anchor"]["unit"]=="HKD/shares"
    q["claim_unverified"]=True
    assert any("ADR" in gap for gap in build_research_model("0700.HK",{},h,q,basis_verified=True)["blockers"])
    q["fx_to_listing"]={**fx,"as_of":"2026-01-01"}
    assert any("currency" in gap for gap in build_research_model("0700.HK",{},h,q,basis_verified=True)["blockers"])

def test_vendor_split_basis_is_not_silently_adjusted_a_second_time():
    m=build_research_model("0700.HK",{},vendor_history(vendor(),"2026-11-19"),{**quote(),"currency":"CNY"},basis_verified=True,splits=[{"date":"2026-06-01","ratio":2}])
    assert m["inputs"]["anchor"]==10
    assert any("corporate action" in g for g in m["blockers"])

def test_issuer_identity_quarantine_withholds_prior_returns_and_does_not_promote_a_new_claim():
    base=build_research_model("SATS",{}, {"series":[]}, {**quote(),"currency":"USD","symbol":"SATS"})
    reviewed={"mode":"quarantine","note":"Prior common and current preferred are different claims", "source_refs":["https://www.sec.gov/issuer"],"annual_coupon":15,"terms_as_of":"2026-09-30","terms_source":"https://www.sec.gov/terms"}
    m=apply_identity_to_model(base,reviewed,{"series":[],"currency":"USD"})
    assert m["method"]=="preferred" and m["blockers"] and m["quarantine_library"]
    assert m["financial_override"]["series"]==[] and m["performance_override"]["points"]==[]
    row={"valuation_decision":{"publishable_return":True,"value_per_share":{"base":123},"eligible_for_capital":True},"valuation_workbench":{"decision":{}}}
    quarantine_prior_valuation(row,m)
    assert row["valuation_decision"]["value_per_share"]["base"] is None
    assert row["valuation_decision"]["forward_return_at_price_pct"]["base"] is None
    assert row["valuation_decision"]["publishable_return"] is False
    assert row["valuation_decision"]["eligible_for_capital"] is False
    assert row["shared_forecast"]["quote"]["identity_status"]=="mismatch"
    assert row["valuation_workbench"]["decision"]["publishable_return"] is False
    other={"valuation_decision":{"publishable_return":False}}
    original=deepcopy(other);quarantine_prior_valuation(other,{})
    assert other==original
