"""Fundamental observations -> falsifiable Short Alpha research, never findings.

This is an additive research process. It does not change RSI-1.0 selection,
execution or its historical comparator. Generated prompts remain unreviewed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from urllib.parse import urlparse

PLAN_VERSION = "fundamentals_frameworks.v1"

PATHS = [
    {"id": "financing_pressure", "label": "Cash runway → financing pressure", "family": "funding",
     "signals": ["cash_burn"], "lens_id": "cash_and_financing",
     "frameworks": ["cash_burn", "dilution_financing", "leverage_refinancing"],
     "category": "financial_oxygen", "tags": ["cash_runway", "financing_gap"],
     "metrics": ["cash", "cfo", "long_term_debt"], "books": ["einhorn", "schilit_perler"],
     "hypothesis": "Recurring cash consumption may force financing that damages common-equity value.",
     "confirm": ["Reconcile unrestricted cash, quarterly operating burn and maintenance capital spending.", "Read commitments, minimum-liquidity covenants, maturities, ATM capacity and signed funding terms.", "Model base, adverse and no-new-financing runway; distinguish an approved shelf from committed cash."],
     "contrary": "Positive recurring cash generation or committed financing extends runway without the hypothesized per-share damage.",
     "catalyst": "A documented funding deadline, maturity, cash milestone or financing announcement inside the affordable hold window.",
     "falsifier": "Define the minimum unrestricted cash/runway or acceptable funding terms that would invalidate the funding gap.",
     "limit": "The quantitative runway uses reported cash and trailing CFO; restricted cash, seasonality, capex and future funding require reconciliation."},
    {"id": "earnings_cash_gap", "label": "Earnings / cash gap → earnings-quality review", "family": "earnings_quality",
     "signals": ["accrual_ratio", "profit_without_cash"], "lens_id": "earnings_quality",
     "frameworks": ["earnings_vs_cash", "working_capital", "accounting"],
     "category": "accounting", "tags": [], "metrics": ["net_income", "cfo", "total_assets", "revenues"],
     "books": ["schilit_perler", "leder"],
     "hypothesis": "A reported earnings/cash gap may reflect poor collections, non-recurring accruals or a benign non-cash/seasonal explanation.",
     "confirm": ["Bridge net income to CFO line by line, including stock compensation and non-cash charges.", "Compare receivables, contract assets, reserves and collections against comparable sales periods.", "Read revenue policies, returns, payment terms and customer concentration; quantify the specific adjustment."],
     "contrary": "A documented seasonal reversal, collections catching up, or ordinary non-cash charges explain the gap.",
     "catalyst": "A dated collection, reserve, contract renewal or reporting event that can change the market's cash/earnings belief.",
     "falsifier": "State which collections or reconciled accrual reversal would remove the earnings-quality concern.",
     "limit": "An accrual ratio does not identify revenue manipulation, establish fraud or prove reported profits exist. Parent and child accounting labels share the same evidence."},
    {"id": "margin_impairment", "label": "Margin deterioration → operating failure hypothesis", "family": "operations",
     "signals": ["margin_trend"], "lens_id": "operating_impairment",
     "frameworks": ["margin_contraction", "supply_side", "cycle_mean_reversion"],
     "category": "operations", "tags": ["margin_contraction"],
     "metrics": ["operating_income", "revenues"], "books": ["einhorn"],
     "hypothesis": "Worsening margins may reveal declining pricing power, adverse mix or structural costs that the valuation has not reflected.",
     "confirm": ["Separate price, volume, mix, utilization and input/labor costs in segment results.", "Remove identified one-off restructuring or acquisition charges without ignoring recurring economic costs.", "Test whether competition, customer terms and unit economics imply durable damage rather than a normal cycle."],
     "contrary": "A temporary cost or utilization shock reverses and filed segment/unit economics support sustainable recovery.",
     "catalyst": "A dated earnings, contract reset, capacity addition or restructuring milestone that exposes the margin mechanism.",
     "falsifier": "Set the segment margin, price/volume or unit-economics recovery that contradicts the impairment case.",
     "limit": "Aggregate margin decline alone cannot distinguish structural impairment, investment spending and cyclicality."},
    {"id": "demand_decay", "label": "Revenue slowdown → demand and concentration review", "family": "operations",
     "signals": ["revenue_turn"], "lens_id": "operating_impairment",
     "frameworks": ["cycle_mean_reversion", "supply_side", "secular_obsolescence", "fad_single_product"],
     "category": "operations", "tags": ["customer_concentration", "backlog_quality"],
     "metrics": ["revenues", "operating_income"], "books": ["einhorn", "leder"],
     "hypothesis": "Slower revenue growth may expose weak demand, customer concentration or product decay rather than a sustainable growth franchise.",
     "confirm": ["Reconcile organic growth, acquisitions, currency and comparable periods.", "Read customer/product concentration, bookings, cancellations, backlog conversion and retention disclosures.", "Compare management's demand explanation with segment data and identified competing supply."],
     "contrary": "Order timing, currency or disposed operations explain the slowdown and comparable organic demand remains healthy.",
     "catalyst": "A dated customer renewal, product milestone or reporting event that tests the stated demand mechanism.",
     "falsifier": "Define the renewal, order conversion or comparable organic growth that would refute demand decay.",
     "limit": "Revenue slowdown and margin deterioration often describe the same operating mechanism; counting both labels does not establish independent corroboration."},
    {"id": "refinancing_pressure", "label": "Leverage → refinancing and equity-claim review", "family": "funding",
     "signals": ["leverage"], "lens_id": "cash_and_financing",
     "frameworks": ["leverage_refinancing", "off_balance_sheet", "dilution_financing"],
     "category": "financial_oxygen", "tags": ["covenant_pressure", "refinancing"],
     "metrics": ["long_term_debt", "total_assets", "stockholders_equity", "operating_income"], "books": ["einhorn", "leder"],
     "hypothesis": "Debt service, covenant constraints or refinancing terms may transfer value away from common equity.",
     "confirm": ["Reconcile all maturities, interest costs, collateral, revolvers, guarantees and off-balance-sheet commitments.", "Calculate covenant and minimum-liquidity headroom from the actual agreement definitions.", "Model common-equity value under refinancing, asset-sale and no-refinancing cases."],
     "contrary": "Ample covenant headroom and committed affordable funding resolve the maturity/liquidity problem.",
     "catalyst": "An identified maturity, covenant test or refinancing deadline supported by a filed agreement.",
     "falsifier": "Specify the signed refinancing terms or covenant headroom that remove the common-equity impairment.",
     "limit": "A debt/assets ratio or negative book equity does not establish a near-term default; dates and agreement terms require manual review."},
    {"id": "issuance_dilution", "label": "Issuance terms → per-share dilution review", "family": "funding",
     "signals": [], "lens_id": "cash_and_financing",
     "frameworks": ["dilution_financing", "leverage_refinancing"],
     "category": "financial_oxygen", "tags": ["serial_equity_issuance", "warrant_overhang"],
     "metrics": [], "books": ["einhorn", "leder"],
     "hypothesis": "Actual issuance, warrants or converts may impair common-equity value per share even if enterprise operations survive.",
     "confirm": ["Reconcile shares outstanding, issuance proceeds, warrant/convert strikes and reset clauses from primary documents.", "Build fully diluted common-equity values with debt, preferred claims, restricted proceeds and transaction costs.", "Distinguish economic dilution from the mechanical reverse-split share adjustment."],
     "contrary": "Financing creates enough per-share value or non-dilutive cash runway to offset the added claims.",
     "catalyst": "A documented issuance, conversion, reset or funding event with explicit terms and a date.",
     "falsifier": "Define acceptable fully diluted shares and net proceeds/value creation that negate the dilution thesis.",
     "limit": "Manual-only route. Changes in book equity are not proof of issuance, and reverse splits alone earn no impairment points."},
    {"id": "reporting_integrity", "label": "Disclosure changes → reporting-integrity review", "family": "disclosures",
     "signals": [], "lens_id": "disclosures_and_control",
     "frameworks": ["reporting_integrity", "capitalization_reserves", "acquisition_nongaap_kpi"],
     "category": "accounting", "tags": ["restatement", "material_weakness", "auditor_change", "non_gaap"],
     "metrics": [], "books": ["leder", "schilit_perler"],
     "hypothesis": "A specific accounting-policy, auditor or adjusted-metric change may undermine the reported earnings or disclosure baseline.",
     "confirm": ["Diff the exact note, audit opinion, control disclosure or KPI definition against the comparable filing.", "Quantify the change and retain management's explanation and any subsequent correction.", "Use a specific observed allegation-free tag; accounting conclusions require analyst review."],
     "contrary": "Primary documents resolve the apparent discrepancy or show a required disclosure update without economic impairment.",
     "catalyst": "A scheduled restatement, auditor/reporting update or other documented event that tests the disclosure issue.",
     "falsifier": "Specify the corrected/reconciled disclosure that would remove the stated accounting concern.",
     "limit": "Manual-only route. Material weaknesses and auditor changes are research leads, not fraud findings."},
    {"id": "governance_control", "label": "Control and incentives → common-equity payoff review", "family": "disclosures",
     "signals": [], "lens_id": "disclosures_and_control",
     "frameworks": ["governance_related_party", "promotion_insider_selling", "issuer_retaliation"],
     "category": "governance_legal", "tags": ["related_party", "controlling_holder", "compensation"],
     "metrics": [], "books": ["leder", "schilit_perler"],
     "hypothesis": "Documented control rights, incentives or related-party terms may create an adverse payoff for outside common shareholders.",
     "confirm": ["Read proxy, ownership, related-party notes, compensation and instrument terms.", "Reconcile any claimed insider sales to actual Form 4 transactions, plans and ownership changes.", "Quantify the economic transfer and retain the documented arm's-length or business explanation."],
     "contrary": "Primary documents show ordinary terms and aligned incentives or resolve the claimed economic transfer.",
     "catalyst": "A documented vote, transaction, lockup or contract event affecting outside common-equity value.",
     "falsifier": "State which terms or ownership reconciliation would eliminate the adverse payoff hypothesis.",
     "limit": "Manual-only route. Promotion, insider activity and related-party labels cannot be inferred from ordinary cash-flow or reverse-split data."},
]

STAGES = [
    {"id": "reconcile", "label": "1 · Reconcile the facts", "deliverable": "A dated issuer/instrument identity and comparable financial series with filing accession and source locators.", "implementation": "implemented", "next": "Read the actual notes and exhibits for restricted cash, custom tags and capital claims."},
    {"id": "map", "label": "2 · Choose the short mechanism", "deliverable": "One primary hypothesis, supporting frameworks and an explicit causal chain from the changed fact to common-equity damage.", "implementation": "implemented", "next": "Separate correlated warnings and state what the market appears to believe."},
    {"id": "verify", "label": "3 · Run the filing furnace", "deliverable": "Dated strengthening and weakening claims, prior/new values, exact sources and a falsifier; review all six lenses.", "implementation": "implemented", "next": "Review the suggested routes manually. Generated prompts carry no supporting-evidence grade."},
    {"id": "payoff", "label": "4 · Connect mechanism to payoff", "deliverable": "Bear/base/bull common-equity values, financing/dilution assumptions, catalyst window and the bullish recovery case.", "implementation": "review_workspace", "next": "Enter the scenario assumptions; current RSI-1.0 checks target downside, timing and carry without estimating probabilities."},
    {"id": "risk", "label": "5 · Make the short survivable", "deliverable": "Verified quote/locate and size against account-wide margin, correlated squeezes and the cost of waiting.", "implementation": "implemented", "next": "Reconcile live holdings and owner cash flows through the SSI handoff before measuring incremental portfolio risk."},
    {"id": "learn", "label": "6 · Test the combination", "deliverable": "Frozen forward decisions including passes; later collect fills, costs, daily equity and external flows.", "implementation": "decisions_implemented_outcomes_pending", "next": "Compare split-only, fundamentals-only and combined sleeves on the same universe/capital rules. Stratify by mechanism and sector without selecting a winning historical threshold."},
]


def plan():
    return deepcopy({"version": PLAN_VERSION, "adopted_on": "2026-10-11",
        "purpose": "Use fundamentals to discover a testable mechanism, Short Alpha to organize the hypothesis, and filing-furnace evidence to earn or weaken conviction.",
        "stages": STAGES, "paths": PATHS,
        "score_contract": {"fundamental": "Existing SSI numerical deterioration score; unchanged by selected frameworks.",
            "evidence": "Existing six-lens documentation grade; unknown remains unscored and generated prompts cannot raise it.",
            "tradability": "Existing quote, locate, catalyst, payoff and shared-account gates remain separate.",
            "independence": "Accounting parent/child tags share evidence. Cash burn, leverage and dilution belong to funding; revenue and margins belong to operations. Explain a distinct causal mechanism before treating related observations as corroboration."},
        "validation": "This additive process does not change RSI-1.0 trading thresholds or historical returns. New trading rules require a new strategy version and future evaluation.",
        "sources": [{"label": "SEC companyfacts coverage", "url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"},
                    {"label": "SEC financial-statement guide", "url": "https://www.sec.gov/about/reports-publications/investorpubsbegfinstmtguide"}]})


def _available(row, asof):
    filed = str(row.get("filed") or "")[:10]
    period = str(row.get("period") or "")[:10]
    try:
        return bool(filed and period and date.fromisoformat(filed) < date.fromisoformat(asof)
                    and date.fromisoformat(period) <= date.fromisoformat(asof))
    except ValueError:
        return False


def routes(score):
    signals = score.get("signals") or {}
    asof = score["as_of"]
    eligible = score.get("source") == "raw_companyfacts" and bool(score.get("historical_eligible"))
    output = []
    for path in PATHS:
        observed = []
        if eligible:
            for key in path["signals"]:
                signal = signals.get(key, {})
                value, severity = signal.get("value"), signal.get("score")
                if isinstance(value, (int, float)) and math.isfinite(value) and isinstance(severity, (int, float)) and math.isfinite(severity) and severity >= .5:
                    observed.append({"id": key, "value": value, "severity": severity, "note": signal.get("note")})
        evidence = [e for e in score.get("evidence", []) if e.get("metric") in path["metrics"] and _available(e, asof)]
        groups = {}
        for e in evidence:
            groups.setdefault(e["metric"], {}).setdefault(e["period"], e)
        comparisons = []
        for metric, periods in groups.items():
            # Quarterly flow facts compare the same fiscal quarter a year ago;
            # instant balance-sheet facts compare the preceding observation.
            ordered = sorted(periods.values(), key=lambda e: e["period"], reverse=True)
            current = ordered[0]
            if metric in {"revenues", "cfo", "net_income", "operating_income"}:
                prior = next((e for e in ordered[1:] if 330 <= (date.fromisoformat(current["period"]) - date.fromisoformat(e["period"])).days <= 400), None)
                basis = "Same fiscal quarter a year earlier, when available"
            else:
                prior = ordered[1] if len(ordered) > 1 else None
                basis = "Previous reported balance-sheet observation"
            comparisons.append({"metric": metric, "new_value": current.get("value"), "new_period": current["period"],
                                "prior_value": prior.get("value") if prior else None, "prior_period": prior["period"] if prior else None,
                                "comparison_basis": basis, "filed": current["filed"], "source_urls": current.get("source_urls", []),
                                "derived": bool(current.get("derived"))})
        output.append({"path_id": path["id"], "label": path["label"], "family": path["family"],
            "lens_id": path["lens_id"], "frameworks": path["frameworks"], "suggested": bool(observed),
            "observations": observed, "comparison_facts": comparisons,
            "status": "research_prompt" if observed else "manual_review" if not path["signals"] else "not_triggered_or_missing",
            "hypothesis": path["hypothesis"], "automatic_support": False})
    return {"version": PLAN_VERSION, "as_of": asof, "routes": output,
            "suggested_families": sorted({r["family"] for r in output if r["suggested"]}),
            "warning": "Suggested routes are questions generated from dated observations. They do not establish a mechanism, independent evidence, fraud, valuation downside or a tradable short."}


def summarize(score, payload):
    catalog = {p["id"]: p for p in PATHS}
    chosen = payload.get("selected_path_ids") or []
    if not isinstance(chosen, list) or any(not isinstance(p, str) or p not in catalog for p in chosen) or len(chosen) != len(set(chosen)):
        raise ValueError("Select unique research paths from the framework catalog")
    primary = payload.get("primary_path_id") or None
    if primary and primary not in chosen:
        raise ValueError("The primary hypothesis must be one of the selected research paths")
    families = sorted({catalog[p]["family"] for p in chosen})
    issues = []
    if not primary:
        issues.append("Choose one primary short mechanism")
    for key, label in [("causal_chain", "Write how the changed fact damages common equity"),
                       ("market_belief", "State the market belief the short disputes"),
                       ("independence_rationale", "Explain independent evidence and related warnings")]:
        if not str(payload.get(key) or "").strip():
            issues.append(label)
    reviews = {r["lens_id"]: r for r in payload.get("lens_reviews", [])}
    for path_id in chosen:
        path = catalog[path_id]
        review = reviews.get(path["lens_id"], {})
        if review.get("status", "unreviewed") == "unreviewed":
            issues.append(path["label"] + ": corresponding evidence lens is unreviewed")
        else:
            source = urlparse(str(review.get("source_url") or ""))
            known = str(review.get("known_at") or "")[:10]
            try:
                dated = bool(known and date.fromisoformat(known) <= date.fromisoformat(score["as_of"]))
            except ValueError:
                dated = False
            if not (dated and source.scheme in {"http", "https"} and source.hostname
                    and all(str(review.get(k) or "").strip() for k in ("locator", "mechanism", "contradictory_evidence", "falsifier"))):
                issues.append(path["label"] + ": dated source, exact locator, mechanism, contrary evidence and falsifier required")
            if review.get("status") == "contradicted":
                issues.append(path["label"] + ": original mechanism contradicted; revise or pass")
    return {"version": PLAN_VERSION, "primary_path_id": primary, "selected_path_ids": chosen,
            "frameworks": sorted({f for p in chosen for f in catalog[p]["frameworks"]}),
            "families": families, "related_warnings": len(chosen) > len(families),
            "status": "research_plan_documented" if not issues else "research_plan_pending", "issues": issues,
            "score_effect": "None: the plan does not alter deterioration, the evidence grade or RSI-1.0 trading gates.",
            "suggestions": routes(score)}


def furnace_drafts(ticker, score, payload):
    """Source-addressable analyst drafts, never mark a generated event reviewed."""
    catalog = {p["id"]: p for p in PATHS}
    reviews = {r["lens_id"]: r for r in payload.get("lens_reviews", [])}
    result = []
    def value(review, key):
        raw = review.get(key)
        if raw in (None, ""):
            return None
        try:
            number = float(raw)
        except (ValueError, TypeError):
            raise ValueError(f"Furnace {key}: enter a numeric value or leave unknown") from None
        if not math.isfinite(number):
            raise ValueError(f"Furnace {key}: value must be finite")
        return number
    for path_id in payload.get("selected_path_ids") or []:
        path = catalog[path_id]
        review = reviews.get(path["lens_id"], {})
        result.append({"ticker": ticker, "filed_at": review.get("known_at") or None,
            "form": review.get("form") or None, "accession": review.get("accession") or None,
            "category": path["category"], "tags": [], "proposed_tags": path["tags"],
            "claim": review.get("mechanism") or "", "prior_value": value(review, "prior_value"),
            "new_value": value(review, "new_value"), "unit": review.get("unit") or None,
            "prior_period": review.get("prior_period") or None, "new_period": review.get("new_period") or None,
            "evidence_ref": review.get("source_url") or None, "source_locator": review.get("locator") or None,
            "short_impact": {"supported": "strengthens", "contradicted": "weakens"}.get(review.get("status"), "unresolved"),
            "confidence": "unscored", "contradictory_evidence": review.get("contradictory_evidence") or "",
            "falsifier": review.get("falsifier") or "", "review_status": "draft_requires_furnace_review",
            "framework_path_id": path_id, "plan_version": PLAN_VERSION, "score_as_of": score["as_of"]})
    return result
