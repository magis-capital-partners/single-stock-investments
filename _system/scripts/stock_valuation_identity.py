"""Reviewed issuer bindings and publication-only withholding of mismatched claims."""
from __future__ import annotations
from copy import deepcopy
from valuation_forecast import attach_forecast


def financial_override(history, note):
    result = deepcopy(history)
    result["series"] = [{**s, "annual": s.get("annual", [])[-10:], "quarterly": s.get("quarterly", [])[-20:]} for s in history.get("series", [])]
    result["notes"] = [note, "Issuer financials retain their source periods and filing dates."]
    result["latest_period"] = max((p["period"] for s in result["series"] for frequency in ("annual", "quarterly") for p in s.get(frequency, [])), default=None)
    result["latest_fiscal_year_end"] = max((p["period"] for s in result["series"] for p in s.get("annual", [])), default=None)
    return result


def quarantine_prior_valuation(row, model):
    if not model.get("invalidate_recorded_model"):
        return row
    nulls = {c: None for c in ("low", "base", "high")}
    forecast = {"schema_version": "1.0", "status": "model_gap", "research_only": True, "capital_actionable": False,
                "as_of": model.get("quote", {}).get("as_of"), "model_as_of": None, "quote": model.get("quote", {}),
                "forward_irr_pct": nulls, "present_value_today_per_share": nulls, "buy_prices": [],
                "gaps": [{"code": "issuer_or_security_identity_changed", "message": model.get("identity_note")}],
                "source_refs": (model.get("source_identity") or {}).get("source_refs") or []}
    if model.get("quarantine_library"):
        forecast["quote"] = {"currency": model.get("currency"), "identity_status": "mismatch"}
    attach_forecast(row, forecast)
    row["capital_actionable"] = False
    row["valuation_decision"].update(eligible_for_capital=False, publishable_return=False, primary_publishable_return=False,
                                     status="evidence_blocked", model_as_of=None)
    if row.get("valuation_workbench"):
        row["valuation_workbench"]["decision"] = dict(row["valuation_decision"])
    return row


def apply_identity_to_model(model, reviewed, history):
    result = deepcopy(model)
    result["source_identity"] = reviewed
    result["identity_note"] = reviewed["note"]
    result["notes"].append(reviewed["note"])
    result["invalidate_recorded_model"] = reviewed.get("mode") in {"correct_parent", "quarantine"}
    result["financial_override"] = financial_override(history, reviewed["note"])
    if reviewed["mode"] == "quarantine":
        # The current SATS quote is preferred stock. Do not reinterpret the
        # user's old EchoStar research or holding as ownership of that claim.
        result.update(method="preferred", label="Current SATS preferred terms · identity unresolved",
                      anchor_label="Contract annual distribution / preferred share", quarantine_library=True,
                      anchor={"value": reviewed["annual_coupon"], "unit": "USD/shares", "period": reviewed["terms_as_of"],
                              "basis": "15% cumulative annual rate on $100 stated amount; payment remains conditional on declaration",
                              "source": {"url": reviewed["terms_source"], "ref": reviewed["terms_source"], "locator": "SATS Series A perpetual preferred terms"}},
                      cases={c: {"coupon_paid": (.5, 1, 1)[i], "exit_price": (70, 100, 110)[i]} for i, c in enumerate(("bear", "base", "bull"))},
                      blockers=["Confirm whether this coverage is EchoStar common (ECHO) or Strive preferred (SATS)"],
                      performance_override={"status": "evidence_blocked", "currency": "USD", "ticker": model["ticker"], "points": [],
                                            "reason": "SATS was reused for Strive preferred shares. Prior EchoStar common-share history is a different security."},
                      profile_override={"type": "Ticker and security identity needs review", "category": "preferred", "description": reviewed["note"],
                                        "focus": "Confirm the intended issuer and security before comparing price with value.",
                                        "countercase": "A reused ticker can attach a valid price to the wrong shareholder claim.",
                                        "drivers": ["Issuer and security identity", "Cumulative distribution rights", "Asset coverage", "Redemption terms"],
                                        "chart_metrics": [], "kpis": [], "key_inputs": ["coupon_paid", "exit_price"], "model_note": reviewed["note"]})
        result["inputs"]["anchor"] = reviewed["annual_coupon"]
        result["recorded_model"] = None
        result.pop("source_forecast", None)
        result["notes"] = [reviewed["note"], "This is a reference worksheet for today's quoted preferred security, not an assumption about which company the existing research or holding intends to cover.",
                           "Dividends are aggregated monthly for the scenario; actual declared payment dates differ. Payment and recovery are not guaranteed.",
                           "The preferred is perpetual. The exit price is an assumed future sale, not a contractual maturity or guaranteed redemption; call terms can constrain upside."]
        result["financial_override"] = {"currency": "USD", "series": [], "latest_period": None, "notes": [reviewed["note"]]}
    return result
