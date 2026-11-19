"""Source identity, financial-period matching and research authority regressions."""
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock_valuation_models import build_research_model, paired_per_share, set_valuation_inputs, model_for_stock
from build_stock_valuation_inputs import source_history, source_profile
import pytest

QUOTE = {"value": 50, "currency": "USD", "as_of": "2026-11-18", "source_url": "https://example.org/price", "symbol": "TEST"}
def series(identity, value, unit="USD", start="2025-01-01", period="2025-12-31", filed="2026-02-01", statement="income"):
    p={"value":value,"period":period,"source":{"url":"https://www.sec.gov/example","filed":filed}}
    if start:p["start"]=start
    return {"id":identity,"statement":statement,"unit":unit,"annual":[p],"quarterly":[p] if statement=="balance" else []}

def history(*rows):return {"currency":"USD","series":list(rows)}
def build(h,category="operating",**kw):return build_research_model("TEST",{"category":category},h,QUOTE,basis_verified=True,**kw)

def test_operating_model_uses_source_fcf_per_matching_diluted_share_and_never_ocf_alone():
    h=history(series("free_cash_flow",100),series("diluted_shares",10,"shares"))
    m=build(h)
    assert m["method"]=="owner_cash" and m["inputs"]["anchor"]==10
    assert len(m["anchor"]["source_refs"])==2
    assert [p["value"] for p in m["anchor"]["calculation_inputs"]]==[100,10]
    assert build(history(series("ocf",100)))["inputs"]["anchor"] is None
    h["series"][1]["annual"][0]["start"]="2025-07-01"
    assert paired_per_share(h,"free_cash_flow") is None

def test_banks_use_equity_or_earnings_not_operating_cash_flow():
    h=history(series("free_cash_flow",100),series("diluted_shares",10,"shares"),series("diluted_eps",3,"USD/shares"))
    assert build(h,"bank")["method"]=="earnings"
    assert build(h,"bank")["inputs"]["anchor"]==3
    m=build(history(series("equity",100,start=None,statement="balance"),series("shares",10,"shares",start=None,statement="balance")),"bank")
    assert m["method"]=="book" and m["inputs"]["anchor"]==10

def test_new_bank_and_broker_facts_override_a_missing_cached_industry_code():
    h=history(series("free_cash_flow",100),series("diluted_shares",10,"shares"),series("diluted_eps",3,"USD/shares"))
    fact={"units":{"USD":[{"end":"2026-09-30","filed":"2026-11-01","val":100}]}}
    for facts in ({"Deposits":fact,"InterestIncomeExpenseNet":fact},{"BrokerDealerRegulatoryNetCapital":fact}):
        p=source_profile({"category":"operating"},{"facts":{"us-gaap":facts}},"TEST","2026-11-19")
        m=build_research_model("TEST",p,h,QUOTE,basis_verified=True)
        assert p["category"]=="bank" and m["method"]=="earnings"
        assert m["inputs"]["anchor"]==3
    assert source_profile({"category":"holding"},{"facts":{"us-gaap":{"Deposits":fact,"InterestIncomeExpenseNet":fact}}},"HOLD","2026-11-19")["category"]=="holding"
    past={"units":{"USD":[{"end":"2020-12-31","filed":"2021-02-01","val":100}]}}
    assert source_profile({"category":"operating"},{"facts":{"us-gaap":{"Deposits":past,"InterestIncomeExpenseNet":past}}},"UTILITY","2026-11-19")["category"]=="operating"

def test_new_loss_does_not_reuse_an_older_profitable_year_and_funds_never_infer_nav_from_price():
    row=series("diluted_eps",-2,"USD/shares")
    row["annual"].insert(0,{**row["annual"][0],"value":4,"period":"2024-12-31"})
    assert build(history(row))["inputs"]["anchor"]==-2
    fund=build(history(),"fund")
    assert fund["method"]=="nav" and fund["inputs"]["anchor"] is None

def test_currency_and_claim_mismatches_fail_closed_and_split_basis_is_applied_once():
    h=history(series("diluted_eps",10,"EUR/shares"))
    assert any("currency" in x for x in build(h)["blockers"])
    h=history(series("diluted_eps",10,"USD/shares",filed="2026-07-01"))
    m=build(h,splits=[{"date":"2026-06-01","ratio":2},{"date":"2026-08-01","ratio":2}])
    assert m["inputs"]["anchor"]==5
    q={**QUOTE,"claim_unverified":True}
    assert any("ADR" in x for x in build_research_model("TEST",{},h,q,basis_verified=True)["blockers"])

def test_recorded_payoff_has_fixed_date_and_present_value_is_not_made_into_a_payoff():
    raw={"method":"yield_curve","as_of":"2026-01-01","scenarios":{c:{"payoff":100,"years":5} for c in ("bear","base","bull")}}
    m=build(history(),"development",raw_model=raw)
    assert m["method"]=="payoff" and m["cases"]["base"]["payoff_date"]=="2031-01-01"
    m=build(history(),"development",contract={"valuation":{"range_per_share":{"base":100}}})
    assert m["cases"]["base"]["payoff"] is None

def test_debt_and_private_claim_templates_never_borrow_underlying_common_earnings():
    for ticker in ("CSU.DB", "GKTX.PS1"):
        m=build_research_model(ticker,{"category":"operating"},history(series("diluted_eps",10,"USD/shares")),QUOTE,basis_verified=True)
        assert m["method"]=="payoff" and m["inputs"]["anchor"] is None
        assert any("specific claim" in gap for gap in m["blockers"])

def test_stock_models_are_screening_only_and_never_mutate_capital_fields(tmp_path):
    row={"shared_forecast":{"quote":QUOTE},"valuation_decision":{"eligible_for_capital":False}}
    original=deepcopy(row)
    m=build(history(series("diluted_eps",3,"USD/shares")))
    set_valuation_inputs(tmp_path,{"schema_version":"stock-valuation-inputs.v1","companies":{"TEST":m}})
    result=model_for_stock(tmp_path,"TEST",{},history(),row)
    result["inputs"]["anchor"]=999
    assert m["inputs"]["anchor"]==3 and row==original
    assert m["authority"]=="screening_only" and m["capital_actionable"] is False
    with pytest.raises(ValueError,match="identity"):
        set_valuation_inputs(tmp_path,{"schema_version":"stock-valuation-inputs.v1","companies":{"WRONG":m}})

def test_valid_dated_issuer_schedule_takes_precedence_and_keeps_future_dates():
    f={"status":"available","model_as_of":"2026-11-16","quote":QUOTE,
       "forward_cashflow_schedule":{c:[{"date":"2027-11-16","amount_per_share":3,"proof_node":"dividend"},{"date":"2028-11-15","amount_per_share":100,"proof_node":"equity_exit"}] for c in ("low","base","high")}}
    m=build(history(series("diluted_eps",5,"USD/shares")),contract={"shared_forecast":f})
    assert m["method"]=="dated_cashflows"
    assert m["cases"]["base"]["cashflows"][-1]=={"date":"2028-11-15","distribution":0,"terminal":100}
    assert m["inputs"]["entry_date"]=="2026-11-18"
    f["forward_cashflow_schedule"]["base"][0]["date"]="2026-11-17"
    assert build(history(),contract={"shared_forecast":f})["method"]!="dated_cashflows"

def test_sec_extraction_excludes_future_facts_and_mismatched_cashflow_durations():
    def fact(start,end,val,filed="2026-02-01"):
        return {"start":start,"end":end,"val":val,"filed":filed,"form":"10-K","accn":"0000000001-26-000001"}
    data={"cik":1,"facts":{"us-gaap":{
        "NetCashProvidedByUsedInOperatingActivities":{"units":{"USD":[fact("2025-01-01","2025-12-31",100),fact("2026-01-01","2026-12-31",500,"2027-02-01")]}},
        "PaymentsToAcquirePropertyPlantAndEquipment":{"units":{"USD":[fact("2024-12-01","2025-12-31",20)]}}
    }}}
    h=source_history(data,"USD","2026-11-19")
    assert next(s for s in h["series"] if s["id"]=="ocf")["annual"][0]["value"]==100
    assert next(s for s in h["series"] if s["id"]=="free_cash_flow")["annual"]==[]
