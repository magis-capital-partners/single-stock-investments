"""Period-aware share and capital-return calculations. Standard library only.

Every observation retains its economic period and source. Actual, basic, and
diluted shares are separate series; an unresolved adjustment never earns a rank.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from buyback_calendar import CALENDAR_ID, SOURCES as CALENDAR_SOURCES, trading_sessions

VERSION = "buyback.v2"
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K", "8-K"}
SHARE_TAGS = {
    "actual": [("us-gaap", "CommonStockSharesOutstanding"), ("dei", "EntityCommonStockSharesOutstanding"), ("ifrs-full", "NumberOfSharesOutstanding")],
    "basic": [("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"), ("ifrs-full", "WeightedAverageNumberOfSharesOutstandingBasic")],
    "diluted": [("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"), ("ifrs-full", "WeightedAverageNumberOfDilutedSharesOutstanding")],
}
FLOW_TAGS = {
    "repurchases": [("us-gaap", "PaymentsForRepurchaseOfCommonStock"), ("ifrs-full", "PaymentsForRepurchaseOfOwnShares")],
    "gross_shares": [("us-gaap", "StockRepurchasedDuringPeriodShares"), ("us-gaap", "TreasuryStockSharesAcquired")],
    "issuance": [("us-gaap", "ProceedsFromIssuanceOfCommonStock")],
    "cfo": [("us-gaap", "NetCashProvidedByUsedInOperatingActivities"), ("ifrs-full", "CashFlowsFromUsedInOperatingActivities")],
    "capex": [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"), ("ifrs-full", "PurchaseOfPropertyPlantAndEquipment")],
    "debt_issued": [("us-gaap", "ProceedsFromIssuanceOfLongTermDebt")],
    "debt_repaid": [("us-gaap", "RepaymentsOfLongTermDebt")],
}
DEFAULT_POLICY = {"quarterly_share_days": 150, "annual_share_days": 450, "price_warn_days": 2, "price_block_days": 5, "signal_prior_shrink_pct": 10, "signal_issuance_pct": 2}

def day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def metric(value=None, *, status="verified", reason=None, unit="percent", start=None, end=None, sources=None):
    return {"value": round(value, 4) if finite(value) else None, "unit": unit,
            "status": status if finite(value) else (status if status != "verified" else "unavailable"),
            "reason": reason, "start": start, "end": end, "sources": sources or [], "formula_version": VERSION}

def source(row):
    return {k: row.get(k) for k in ("tag", "accn", "filed", "start", "end", "unit", "scope", "url") if row.get(k) is not None}

def filing_url(cik, accession):
    if not cik or not accession:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{str(accession).replace('-', '')}/"

def observations(doc, specs, unit, cutoff, *, basis=None):
    """Deduplicate the SAME economic period, never the filing's fy label."""
    out = []
    for priority, (ns, tag) in enumerate(specs):
        rows = (((doc.get("facts") or {}).get(ns) or {}).get(tag) or {}).get("units", {}).get(unit, [])
        groups = {}
        for raw in rows:
            if raw.get("form") not in FORMS or not finite(raw.get("val")) or not day(raw.get("end")):
                continue
            if raw["end"][:10] > cutoff or (raw.get("filed") and raw["filed"][:10] > cutoff):
                continue
            if unit == "shares" and raw["val"] < 0:
                continue
            key = (raw.get("start"), raw["end"][:10], raw.get("scope", "entity"))
            groups.setdefault(key, []).append(raw)
        for (start, end, scope), facts in groups.items():
            latest = max(str(r.get("filed") or "") for r in facts)
            chosen = [r for r in facts if str(r.get("filed") or "") == latest]
            values = {r["val"] for r in chosen}
            r = dict(chosen[-1])
            r.update(value=r["val"] if len(values) == 1 else None, start=start, end=end,
                     tag=f"{ns}:{tag}", unit=unit, scope=scope, priority=priority,
                     status="verified" if len(values) == 1 else "ambiguous",
                     reason=None if len(values) == 1 else "conflicting_values_same_context",
                     url=filing_url(doc.get("cik"), r.get("accn")))
            if basis:
                r["basis"] = basis
            out.append(r)
    return sorted(out, key=lambda r: (r["end"], r.get("start") or "", r["priority"]))

def share_series(doc, cutoff):
    result = {}
    for basis, specs in SHARE_TAGS.items():
        rows = observations(doc, specs, "shares", cutoff, basis=basis)
        # Only matching dates may use tag preference. No weighted/actual splicing.
        grouped = {}
        for r in rows:
            if basis == "actual" and r.get("start"):
                continue
            if basis != "actual":
                duration = (day(r["end"]) - day(r["start"])).days + 1 if day(r.get("start")) else 0
                if not 70 <= duration <= 400:
                    continue
            key = (r.get("start"), r["end"])
            if key not in grouped or r["priority"] < grouped[key]["priority"]:
                grouped[key] = r
        result[basis] = sorted(grouped.values(), key=lambda r: (r["end"], r.get("start") or ""))
    return result

def apply_actions(rows, actions, cutoff, *, basis="actual"):
    out = copy.deepcopy(rows)
    for r in out:
        r["reported_value"] = r.get("value")
        r["split_factor"] = 1.0
        for a in sorted(actions, key=lambda a: a["effective"]):
            if a["effective"] > cutoff or not a.get("source") or not finite(a.get("ratio")) or a["ratio"] <= 0:
                continue
            if r["end"] >= a["effective"]:
                continue
            adjusted_through = r.get("adjusted_through") or ""
            if adjusted_through >= a["effective"] or r.get("accn") in a.get("restated_accessions", []):
                continue
            # Weighted comparative figures in post-split financial statements
            # are restated. Actual observations require explicit basis evidence.
            if (r.get("filed") or "") >= a["effective"]:
                if basis in {"basic", "diluted"}:
                    continue
                r.update(status="ambiguous", reason="historical_split_basis_unresolved")
                continue
            if finite(r.get("value")):
                r["value"] *= a["ratio"]
                r["split_factor"] *= a["ratio"]
        r["basis_as_of"] = cutoff
    # A ratio alone never establishes a split, merger, or cancellation.
    for prev, cur in zip(out, out[1:]) if basis != "flow_shares" else []:
        if finite(prev.get("value")) and finite(cur.get("value")) and prev["value"] > 0:
            ratio = cur["value"] / prev["value"]
            if ratio >= 1.4 or ratio <= .6:
                # Known actions already normalized these observations.
                cur.update(status="ambiguous", reason="unexplained_share_discontinuity")
    return out

def latest_actual(rows):
    candidates = [r for r in rows if not r.get("start")]
    return max(candidates, key=lambda r: (r["end"], r.get("filed") or "")) if candidates else None

def compare_shares(rows, years=1):
    current = latest_actual(rows)
    if not current:
        return metric(reason="actual_shares_unavailable")
    target = day(current["end"]) - timedelta(days=round(365.25 * years))
    candidates = [r for r in rows if r["end"] < current["end"] and abs((day(r["end"]) - target).days) <= (55 if years == 1 else 100)]
    if not candidates:
        return metric(reason="comparable_history_unavailable", end=current["end"])
    prior = min(candidates, key=lambda r: abs((day(r["end"]) - target).days))
    interval = [r for r in rows if prior["end"] <= r["end"] <= current["end"]]
    bad = next((r for r in interval if r.get("status") != "verified" or not finite(r.get("value"))), None)
    if bad:
        return metric(status="ambiguous", reason=bad.get("reason"), start=prior["end"], end=current["end"])
    if prior["value"] <= 0:
        return metric(reason="invalid_share_denominator")
    return metric(100 * (1 - current["value"] / prior["value"]), start=prior["end"], end=current["end"],
                  sources=[source(prior), source(current)]) | {"elapsed_days":(day(current["end"])-day(prior["end"])).days,"annualized_pct":100*(1-(current["value"]/prior["value"])**(365.25/(day(current["end"])-day(prior["end"])).days))}

def _duration(r):
    return (day(r["end"]) - day(r["start"])).days + 1 if day(r.get("start")) else 0

def flow_for_period(rows, *, end=None):
    """FY + current cumulative YTD - comparable prior YTD, with source lineage."""
    rows = [r for r in rows if r.get("status") == "verified" and finite(r.get("value")) and 1 <= _duration(r) <= 400]
    if not rows:
        return metric(reason="reported_flow_unavailable", unit="USD")
    latest = max(rows, key=lambda r: (r["end"], _duration(r)))
    end = end or latest["end"]
    current = [r for r in rows if r["end"] == end]
    if not current:
        return metric(reason="matching_flow_period_unavailable", unit=latest["unit"])
    ytd = max(current, key=_duration)
    if 330 <= _duration(ytd) <= 400:
        return metric(ytd["value"], unit=ytd["unit"], start=ytd["start"], end=ytd["end"], sources=[source(ytd)]) | {"period_label": "FY"}
    annuals = [r for r in rows if 330 <= _duration(r) <= 400 and r["end"] < end and 0 < (day(ytd["start"]) - day(r["end"])).days <= 8]
    if annuals:
        annual = max(annuals, key=lambda r: r["end"])
        previous = [r for r in rows if r["end"] < annual["end"] and abs((day(ytd["end"]) - day(r["end"])).days - 365) <= 8 and abs(_duration(r) - _duration(ytd)) <= 8]
        if previous:
            prior = min(previous, key=lambda r: abs(_duration(r) - _duration(ytd)))
            return metric(annual["value"] + ytd["value"] - prior["value"], unit=ytd["unit"],
                          start=(day(prior["end"]) + timedelta(days=1)).isoformat(), end=end,
                          sources=[source(annual), source(ytd), source(prior)]) | {"period_label": "TTM"}
    # Fall back only to a clearly labelled last completed fiscal year.
    annuals = [r for r in rows if 330 <= _duration(r) <= 400]
    if annuals:
        annual = max(annuals, key=lambda r: r["end"])
        return metric(annual["value"], unit=annual["unit"], start=annual["start"], end=annual["end"],
                      sources=[source(annual)]) | {"period_label": "FY"}
    return metric(reason="ttm_not_reconcilable", unit=ytd["unit"], end=end)

def flows(doc, cutoff):
    result = {}
    for name, specs in FLOW_TAGS.items():
        unit = "shares" if name == "gross_shares" else "USD"
        # These are alternative tags, not additive components.
        available = [(ns, tag) for ns, tag in specs if (((doc.get("facts") or {}).get(ns) or {}).get(tag) or {}).get("units", {}).get(unit)]
        result[name] = observations(doc, available[:1], unit, cutoff) if available else []
    # Common issuance proceeds and option exercise proceeds may overlap in
    # issuer disclosures. Require an explicit total rather than adding both.
    return result

def business_age(start, end):
    """Compatibility name; US equity age now counts exchange sessions."""
    return trading_sessions(start, end)

def instrument_policy(company, kind):
    kind = (kind or "").lower().replace("-", "_")
    if kind in {"preferred","preferred_stock","warrant","rights","option"}:
        return "non_common_security"
    if kind in {"etf", "etp", "exchange_traded_fund"} or re.search(r"\b(etf|etp|spdr|ishares|proshares)\b|exchange.traded", company, re.I):
        return "creation_redemption"
    if kind in {"closed_end_fund", "listed_investment_company", "listed_investment_co", "investment_trust"}:
        return "nav_repurchases"
    if kind in {"royalty_trust", "commodity_trust"}:
        return "trust_units"
    return "operating"

def assessment(reduction, gross_qty, repurchase, fcf, debt, valuation, eligible):
    pieces = {"execution": {"score": None, "reason": "matching_gross_share_period_unavailable"},
              "funding": {"score": None, "reason": "matching_funding_period_unavailable"},
              "valuation": {"score": None, "reason": "dated_value_estimate_unavailable"}}
    if not eligible:
        return {"grade": None, "components": pieces, "confidence": "low"}
    if finite(reduction) and finite(gross_qty) and gross_qty > 0:
        retention = reduction / gross_qty
        pieces["execution"] = {"score": 2 if retention >= .8 else 1 if retention >= .5 else 0, "retention": round(retention, 4), "reason": None}
    if finite(repurchase) and repurchase > 0 and finite(fcf) and finite(debt):
        cover = fcf / repurchase
        pieces["funding"] = {"score": 2 if cover >= 1 and debt <= .25 * repurchase else 1 if cover >= .5 else 0, "coverage": round(cover, 4), "net_debt_issued": debt, "reason": None}
    if valuation and valuation.get("source") and finite(valuation.get("price_paid")) and finite(valuation.get("intrinsic_value")) and valuation["intrinsic_value"] > 0 and day(valuation.get("as_of")):
        rel = valuation["price_paid"] / valuation["intrinsic_value"]
        pieces["valuation"] = {"score": 2 if rel <= .85 else 1 if rel <= 1.0 else 0, "price_to_value": round(rel, 4), "as_of": valuation["as_of"], "source": valuation["source"], "reason": None}
    scores = [p["score"] for p in pieces.values()]
    grade = None if any(p is None for p in scores) else {6:"A",5:"B",4:"C",3:"D",2:"E",1:"E",0:"E"}[sum(scores)]
    return {"grade": grade, "components": pieces, "confidence": "high" if grade else "partial"}

def company_record(entry, doc, quote, *, as_of, actions=None, policies=None, overrides=None):
    policy = {**DEFAULT_POLICY, **(policies or {})}
    overrides = overrides or {}
    ticker = entry["ticker"]
    cik = entry.get("cik") or (str(doc.get("cik")).zfill(10) if doc.get("cik") else None)
    if entry.get("instrument_type") in {"preferred","preferred_stock","warrant","rights","option"}:
        cik=None
    issuer_id = "cik:" + str(int(cik)) if cik else "issuer:" + ticker
    series = share_series(doc, as_of)
    for basis, extra in (overrides.get("share_observations") or {}).items():
        if basis == "actual" and overrides.get("class_weights"):
            series[basis] = []
        additions=[r for r in extra if r.get("source") and r["end"] <= as_of]
        by_date={r["end"]:r for r in series.setdefault(basis,[])}
        for r in additions:
            if r["end"] not in by_date or (r.get("filed") or "") >= (by_date[r["end"]].get("filed") or ""):
                by_date[r["end"]]=r
        series[basis]=sorted(by_date.values(),key=lambda r:r["end"])
    for basis in series:
        series[basis] = apply_actions(series[basis], actions or [], as_of, basis=basis)
    current = latest_actual(series["actual"])
    annual_only = not any(str(r.get("form") or "").startswith("10-Q") for r in series["actual"])
    max_age = policy["annual_share_days"] if annual_only and any("20-F" in str(r.get("form")) or "40-F" in str(r.get("form")) for r in series["actual"]) else policy["quarterly_share_days"]
    age = (day(as_of) - day(current["end"])).days if current else None
    state = "unavailable" if not current else ("ambiguous" if current.get("status") != "verified" else "stale" if age > max_age else "verified")
    reason = "actual_shares_unavailable" if not current else current.get("reason") or ("share_observation_overdue" if state == "stale" else None)
    if current and finite(current.get("value")) and current["value"]<=0:
        state,reason="ambiguous","no_outstanding_common_shares"
    behavior = instrument_policy(entry.get("company", ""), entry.get("instrument_type"))
    if entry.get("class_scope") == "requires_class_reconciliation":
        state, reason = "ambiguous", "security_class_reconciliation_required"
    if behavior=="non_common_security":state,reason="unsupported","common_equity_metrics_not_applicable_to_security"
    eligible = state == "verified" and behavior in {"operating","nav_repurchases"}
    changes = {str(y): compare_shares(series["actual"], y) for y in (1, 3, 5)}
    for m in changes.values():
        if not eligible:
            m.update(value=None, status=state if state != "verified" else "unsupported", reason=reason or behavior)
    raw_flows = flows(doc, as_of)
    raw_flows["gross_shares"] = apply_actions(raw_flows["gross_shares"], actions or [], as_of, basis="flow_shares")
    cash = {name: flow_for_period(rows) for name, rows in raw_flows.items()}
    rep = cash["repurchases"]
    qdate = quote.get("as_of")
    quote_calendar = quote.get("calendar") or (CALENDAR_ID if entry.get("market", "US") in {"US", "OTC"} else None)
    quote_age = trading_sessions(qdate, as_of, quote_calendar)
    price_ok = finite(quote.get("price")) and quote["price"] > 0 and quote_age is not None and quote_age <= policy["price_block_days"] and str(qdate)<=as_of and (quote.get("currency")=="USD" or not quote.get("currency") and entry.get("market","US") in {"US","OTC"})
    # A current vendor cap is an independent cross-check, never an invitation
    # to multiply stale/class-incompatible EDGAR shares by a current price.
    mv = None
    mv_status = "unavailable"
    if price_ok and eligible and finite(current.get("value")) and entry.get("class_scope", "entity") == "entity":
        mv = quote["price"] * current["value"]
        mv_status = "derived"
        vendor_shares = quote.get("shares_outstanding")
        if finite(vendor_shares) and vendor_shares > 0 and abs(current["value"] / vendor_shares - 1) > .25:
            mv, mv_status = None, "ambiguous"
    if entry.get("class_scope") == "requires_class_reconciliation":
        eligible, state, reason = False, "ambiguous", "security_class_reconciliation_required"
    denominator_sources=([source(current)] if current else [])+[{"tag":"market:Close","url":quote.get("source_url"),"path":"_system/reference/market-data/fundamentals/index_float_adv.json","ticker":ticker,"end":qdate,"value":quote.get("price"),"unit":"USD_per_share"}]
    ratio = metric(reason="compatible_current_market_value_unavailable")
    if mv and rep["value"] is not None and (day(as_of) - day(rep["end"])).days <= 450:
        ratio = metric(100 * rep["value"] / mv, status="derived", start=rep["start"], end=rep["end"], sources=rep["sources"]+denominator_sources)
        ratio["period_label"] = rep.get("period_label")
    issuance = cash["issuance"]
    net_ratio = metric(reason="matching_issuance_cash_unavailable")
    option_proceeds=observations(doc,[("us-gaap","ProceedsFromStockOptionsExercised")],"USD",as_of)
    issuance_scope_unclear=any(r.get("value",0)>0 and r.get("start")==rep.get("start") and r.get("end")==rep.get("end") for r in option_proceeds)
    if issuance_scope_unclear:net_ratio["reason"]="option_proceeds_overlap_requires_reconciliation"
    if mv and rep["value"] is not None and issuance["value"] is not None and not issuance_scope_unclear and (day(as_of)-day(rep["end"])).days<=450 and (rep["start"], rep["end"]) == (issuance["start"], issuance["end"]):
        net_ratio = metric(100 * (rep["value"] - issuance["value"]) / mv, status="derived", start=rep["start"], end=rep["end"], sources=rep["sources"] + issuance["sources"] + denominator_sources)
    one, five = changes["1"]["value"], changes["5"]["value"]
    pace = None
    recent_cash=rep["value"] is not None and rep["value"]>0 and (day(as_of)-day(rep["end"])).days<=450
    prior_cash=flow_for_period([r for r in raw_flows["repurchases"] if rep.get("end") and 330<=(day(rep["end"])-day(r["end"])).days<=400])
    execution_faster=prior_cash.get("value") is not None and prior_cash["value"]>0 and rep.get("value") is not None and rep["value"]>=1.25*prior_cash["value"] and abs(_duration(rep)-_duration(prior_cash))<=8
    if eligible and recent_cash and one is not None and five is not None:
        baseline = changes["5"].get("annualized_pct",0)
        pace = "issuing_again" if five >= policy["signal_prior_shrink_pct"] and one <= -policy["signal_issuance_pct"] else "stopped" if five >= 10 and abs(one) < 1.5 else "accelerating" if execution_faster and one >= 3 and baseline > 1 and one >= baseline * 1.5 else "steady" if one >= 1.5 or five >= 10 else None
    peak = metric(reason="comparable_history_unavailable")
    valid = [r for r in series["actual"] if finite(r.get("value")) and r["value"] > 0]
    if eligible and valid and all(r.get("status") == "verified" for r in series["actual"]):
        p = max(valid, key=lambda r: r["value"])
        peak = metric(100 * (1 - current["value"] / p["value"]), start=p["end"], end=current["end"], sources=[source(p),source(current)])
    # Match the outstanding interval to the exact gross-flow interval.
    gross = cash["gross_shares"]
    start_point = next((r for r in series["actual"] if gross.get("start") and day(r["end"]) == day(gross["start"]) - timedelta(days=1) and r.get("status") == "verified"), None)
    end_point = next((r for r in series["actual"] if r["end"] == gross.get("end") and r.get("status") == "verified"), None)
    reduction = start_point["value"] - end_point["value"] if start_point and end_point else None
    matching = lambda a,b: a.get("start") == b.get("start") and a.get("end") == b.get("end") and a.get("value") is not None and b.get("value") is not None
    fcf = cash["cfo"]["value"] - cash["capex"]["value"] if matching(cash["cfo"], rep) and matching(cash["capex"], rep) else None
    debt = cash["debt_issued"]["value"] - cash["debt_repaid"]["value"] if matching(cash["debt_issued"],rep) and matching(cash["debt_repaid"],rep) else None
    if behavior=="nav_repurchases" or re.search(r"bank|insurance|bancorp", entry.get("company",""), re.I):
        fcf = debt = None
    scores = assessment(reduction if matching(gross,rep) else None, gross["value"] if matching(gross,rep) else None, rep["value"], fcf, debt, overrides.get("valuation"), eligible)
    efficiency = metric(100*reduction/gross["value"], status="derived", start=gross.get("start"), end=gross.get("end"),
                        sources=gross["sources"]+[source(start_point),source(end_point)]) if eligible and reduction is not None and gross["value"] and start_point and end_point else metric(reason="matching_share_bridge_unavailable")
    if gross.get("end") and (day(as_of)-day(gross["end"])).days>450:
        efficiency.update(value=None,status="stale",reason="share_bridge_overdue")
    bridge = {"start":gross.get("start"),"end":gross.get("end"),"beginning":start_point["value"] if start_point else None,
              "ending":end_point["value"] if end_point else None,"gross_repurchased":gross.get("value"),
              "unexplained_net_additions":(end_point["value"]-start_point["value"]+gross["value"]) if start_point and end_point and gross["value"] is not None else None,
              "reason":"A residual includes issuance and other adjustments; attribution requires filing evidence."}
    historical=[r for r in series["actual"] if current and r["end"]<current["end"] and r["end"]>=(day(current["end"])-timedelta(days=6*366)).isoformat() and r.get("status")=="verified" and finite(r.get("value"))]
    declines=sum(b["value"]<a["value"] for a,b in zip(historical,historical[1:]))
    recent=[r for r in series["actual"][-3:] if r.get("status")=="verified" and finite(r.get("value"))]
    persistent=len(recent)==3 and all(b["value"]>a["value"] for a,b in zip(recent,recent[1:]))
    sources = ([source(current)] if current else []) + rep["sources"]
    result = {"schema_version": VERSION, "issuer_id": issuer_id, "ticker": ticker, "company": entry.get("company", ticker), "cik": cik,
              "book": entry.get("book"), "aliases": entry.get("aliases", [ticker]), "as_of": as_of, "shares_end": current["end"] if current else None,
              "data_status": state, "data_reason": reason, "confidence": "high" if eligible else "low", "rank_eligible": eligible and one is not None,
              "share_age_days": age, "price_as_of": qdate, "price_age_business_days": quote_age, "price_age_trading_sessions": quote_age,
              "price_calendar": quote_calendar, "price_calendar_sources": CALENDAR_SOURCES if quote_calendar == CALENDAR_ID else [],
              "price_warning":"quote_calendar_unavailable" if quote_age is None and qdate else "quote_older_than_two_trading_sessions" if quote_age is not None and quote_age>policy["price_warn_days"] else None,
              "market_value_usd": round(mv) if mv else None, "market_value_status": mv_status,"market_value_basis":"current listing price multiplied by comparable common-equivalent shares", "price":quote.get("price") if price_ok else None,
              "instrument_policy": behavior, "non_operating": behavior in {"creation_redemption","trust_units","non_common_security"},
              "shares_now": current.get("value") if current and state == "verified" else None,
              "metrics": {"net_reduction_1y": changes["1"],"net_reduction_3y": changes["3"],"net_reduction_5y": changes["5"],"since_peak":peak,"gross_cash_ratio":ratio,"net_cash_ratio":net_ratio,"retirement_efficiency":efficiency},
              "retired_since_peak_pct": peak["value"], "change_1y_pct": -one if one is not None else None,
              "change_5y_pct": -five if five is not None else None,"buyback_yield_pct": ratio["value"], "yield_period": rep.get("period_label"),
              "repurchase_fy_usd": rep["value"],"repurchase_end":rep.get("end"), "pace": pace, "grade": scores["grade"],
              "assessment": scores, "assessment_period":{"start":rep.get("start"),"end":rep.get("end")}, "sources": sources, "share_basis": "actual", "split_review": any(r.get("status") != "verified" for r in series["actual"]),
              "share_review": state == "ambiguous", "history_start": series["actual"][0]["end"] if series["actual"] else None,
              "point_count":len(series["actual"]), "research_only":True,"in_base_irr":False,"authority":"none",
              "prior_shrink_observation_count":len(historical),"prior_decline_periods":declines,"issuance_persistence":"multiple_observations" if persistent else "first_observation",
              "issuance_cause":overrides.get("issuance_cause", "unresolved"),"explanation": overrides.get("explanation"),"explanation_source":overrides.get("source")}
    detail = {"issuer_id":issuer_id,"ticker":ticker,"series":series,"flows":raw_flows,"cash_periods":cash,"share_bridge":bridge,"actions":actions or [],"assessment":scores,"sources":sources}
    return result, detail

class FilingFactsParser(HTMLParser):
    """Extract inline XBRL facts AND class/period contexts without a DOM dependency."""
    def __init__(self, accession, filed, url):
        super().__init__(convert_charrefs=True)
        self.accession,self.filed,self.url=accession,filed,url
        self.contexts={};self.context=None;self.field=None;self.field_text=[];self.fact=None;self.facts=[];self.depth=0
    def handle_starttag(self, tag, attrs):
        a=dict(attrs);t=tag.lower().split(":")[-1]
        if t=="context":
            self.context={"id":a.get("id"),"members":[]}
        if self.context is not None and t in {"instant","startdate","enddate","explicitmember"}:
            self.field=t;self.field_text=[]
        if t=="nonfraction" and a.get("name"):
            self.fact={**a,"text":[]};self.depth=1
        elif self.fact is not None:
            self.depth+=1
    def handle_data(self, text):
        if self.field:self.field_text.append(text)
        if self.fact is not None:self.fact["text"].append(text)
    def handle_endtag(self, tag):
        t=tag.lower().split(":")[-1]
        if self.field==t and self.context is not None:
            val="".join(self.field_text).strip()
            if t=="explicitmember":self.context["members"].append(val)
            else:self.context[t]=val
            self.field=None
        if t=="context" and self.context is not None:
            self.contexts[self.context["id"]]=self.context;self.context=None
        if self.fact is not None:
            self.depth-=1
            if self.depth==0:
                self.facts.append(self.fact);self.fact=None
    def observations(self):
        rows=[]
        for f in self.facts:
            c=self.contexts.get(f.get("contextref"),{})
            text="".join(f["text"]).replace(",","").strip()
            try: value=float(text)*10**int(f.get("scale","0"))*(-1 if f.get("sign")=="-" else 1)
            except (ValueError,OverflowError):continue
            if not finite(value):continue
            rows.append({"tag":f["name"],"value":value,"start":c.get("startdate"),"end":c.get("instant") or c.get("enddate"),
                         "scope":"|".join(c.get("members",[])) or "entity","accn":self.accession,"filed":self.filed,
                         "url":self.url,"status":"verified","unit":f.get("unitref"),"source":"inline_xbrl"})
        return rows

def parse_filing_facts(html, *, accession, filed, url):
    p=FilingFactsParser(accession,filed,url);p.feed(html);return p.observations()

def issuance_signals(rows):
    out=[]
    seen=set()
    for r in rows:
        identity=r.get("issuer_id") or r.get("ticker")
        if identity in seen:continue
        seen.add(identity)
        if r.get("pace")!="issuing_again" or not r.get("rank_eligible") or r.get("non_operating") or r.get("instrument_policy")=="nav_repurchases":
            continue
        # Share-count arithmetic alone does not establish prior repurchasing.
        if not r.get("repurchase_fy_usd") or r["repurchase_fy_usd"] <= 0 or r.get("prior_shrink_observation_count",0)<3 or r.get("prior_decline_periods",0)<2:
            continue
        out.append({**{k:r.get(k) for k in ("ticker","company","issuer_id","aliases","change_1y_pct","change_5y_pct","shares_end","grade","issuance_cause","explanation","sources","confidence","repurchase_fy_usd","repurchase_end","issuance_persistence","explanation_source")},
                    "framework_id":"dilution_financing","kind":"candidate_signal","ranked_short":False,"pace":"issuing_again","data_status":r.get("data_status")})
    return sorted(out,key=lambda r:-(r.get("change_1y_pct") or 0))

def snapshot_id(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()[:20]
