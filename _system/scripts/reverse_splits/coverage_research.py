"""RSI-4: broader free-data coverage and explicit, uncertainty-aware assumptions.

This is a new research version. It never rewrites frozen RSI-3 performance,
invents prices, calls a broker, or promotes estimates into complete evidence.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, pstdev

from .calmar_research import path_metrics
from .coverage_data import END, NY, CoverageStore, catalogue_inputs, collect_free_inputs
from .free_evidence import extract_terms
from .ledger import read_json, write_json
from .net_edge import FRAMEWORKS, moment
from .net_edge_evidence import digest, filing_rating
from .net_edge_study import (PriceStore, build_snapshots, calendar_mark, cost_curve, cost_observations,
                             donor_rows, entry_day, make_outcomes, read_evidence, simulate)
from .net_edge_v3 import Account, BorrowHistory, StudyPolicy, dated_borrow, loan_schedule, payoff_forecast, size_position

START, RECENT = "2018-05-01", "2023-10-14"


def write_public_json(path, value):
    """Retain all evidence while keeping thousands of lazy-loaded assets small."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)+"\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, newline="\n") as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


SIGNAL_FRAMEWORK = {"accrual_ratio": "accounting", "profit_without_cash": "earnings_vs_cash",
                    "cash_burn": "cash_burn", "leverage": "leverage_refinancing",
                    "margin_trend": "margin_contraction", "revenue_turn": "cycle_mean_reversion"}
WEIGHTS = {"accrual_ratio": 1., "profit_without_cash": .8, "cash_burn": 1.2,
           "leverage": 1., "margin_trend": 1., "revenue_turn": .8}
ASSUMPTIONS = [
    {"id": "identity", "rule": "An exact normalized company-name match to one SEC issuer may supply an estimated historical identity. A ticker alone is insufficient.",
     "consequence": "These links remain assumptions; recycled symbols and unrecognized name changes remain unresolved."},
    {"id": "clock", "rule": "Recover dated primary schedules from cached filings. Only a separately labeled sensitivity assumes a structured action was observable by its effective-day close.",
     "consequence": "An effective-day proxy cannot support an announcement-entry claim. Its first simulated entry is the following session."},
    {"id": "financials", "rule": "Missing signal values use the median of earlier observed other issuers, one latest observation per issuer, or neutral 50/100 before peers exist. No balance-sheet amount is filled with zero.",
     "consequence": "Estimated ratings are separate from reported financial scores. Missing evidence reduces conviction and widens the net-edge uncertainty allowance."},
    {"id": "stale_financials", "rule": "When the issuer's last as-filed period is 201–550 days old, reuse its historical signals as estimates before using other issuers. Assume the last annual operating burn persists and subtract elapsed burn from last cash, floored at zero, before computing runway.",
     "consequence": "Unreported financing or improving operations could invalidate this cash-depletion estimate. Old reported amounts and projected cash are separate; none are promoted to a fresh reported score."},
    {"id": "frameworks", "rule": "Assess all 27 routes. Quantitative evidence can support six deterioration mechanisms; filing passages remain context leads. Unresolved mechanisms contribute no extra positive edge.",
     "consequence": "Provisional conviction is rating × (0.35 + 0.65 × observed numerical fraction) × 0.75, with a further 0.8 identity-assumption multiplier. The 0.75 discount reserves for unresolved valuation/catalyst underwriting. It is not a probability. Fraud and bad-actor conclusions are never inferred."},
    {"id": "financing", "rule": "A reverse split changes units and creates zero economic dilution by itself. Model possible new issuance at 0%, 15% or 30% discounts, including the cash raised in per-share value.",
     "consequence": "Financing scenarios guide comparable matching and risk disclosure; their effect is not added a second time to historical short returns."},
    {"id": "price", "rule": "Fill gaps only with real free daily charts. Undo later split adjustments and check overlapping nominal observations. Existing provenance-bound nominal prices take priority.",
     "consequence": "No synthetic entry, exit, delisting return or fill. Unresolved admitted paths invalidate performance. Public reconstructed prices are not official auction evidence."},
    {"id": "announcement_plan", "rule": "Before the entry exists, use the last known closing price projected into the share units of the already-announced split, assuming no economic price move.",
     "consequence": "The plan is an estimate. Actual opening price and portfolio capacity are assessed separately at entry; future price data never enters the announcement plan."},
    {"id": "liquidity", "rule": "Compare 0.1% and 1% of prior average share volume, plus a $25 versus $100 minimum. Retain whole shares, fees, margin and the 2% aggregate +200% squeeze-loss budget.",
     "consequence": "Validated public daily volume can replace explicitly partial three-venue counts, with historical nominal volume units assumed. Larger participation adds a square-root impact allowance. These are capacity sensitivities, not evidence of available borrow or fills."},
    {"id": "slippage", "rule": "Use earlier other-issuer measured depth where available. Otherwise use a spread floor of max(0.5%, one cent / price), plus 2 × prior daily volatility × sqrt(order / prior daily dollar volume).",
     "consequence": "The fallback is an explicit cost assumption with an extra uncertainty reserve; twice-slippage cases are also replayed."},
    {"id": "borrow", "rule": "Use a prior public daily borrow proxy within 24 hours when present, with an assumed historical symbol link. Otherwise use 50% annualized. Double and sixfold fee scenarios scale both proxies and the fallback. Fees apply to rounded collateral across forecast settlement-to-return calendar days, including weekends.",
     "consequence": "If no fresh entry proxy exists, a stale announcement rate cannot reduce the fallback: use the greater of that last indication and the fallback, scaled in stress cases. Rates are not charges or approvals. The strict case admits nothing without an actual entry locate and execution evidence."},
    {"id": "tail", "rule": "Show a further 2% of starting capital squeeze-loss deduction and 50% borrower-access thinning using an identity-seeded ex-ante selection, without optimizing the seed.",
     "consequence": "A stop is not a guaranteed loss limit; no hypothetical tail event is described as an observed historical event."},
    {"id": "cashflows", "rule": "Import public dividend events as modeled payment-in-lieu costs when held across the ex-date. Unknown corporate cash adjustments remain uncovered.",
     "consequence": "Fractional split settlements and complete dividend coverage still require actual records."},
]


def estimate_ratings(snapshots):
    """Earlier financial evidence only; same-time batches cannot train each other."""
    history = defaultdict(dict)
    chronological = sorted(snapshots.values(), key=lambda s: (s["known_at"], s["key"]))
    by_clock = defaultdict(list)
    for s in chronological: by_clock[s["known_at"]].append(s)
    for batch in by_clock.values():
        for s in batch:
            signals = s["fundamental"].get("signals", {})
            observed = {k: v["score"] for k, v in signals.items() if k in WEIGHTS}
            stale = s.get("stale_financial_model", {}).get("estimated_signals", {})
            imputed, peers = {}, {}
            for key in WEIGHTS:
                prior = [v for issuer, v in history[key].items() if issuer != s["issuer"]]
                imputed[key] = observed.get(key, stale.get(key, median(prior) if prior else .5))
                peers[key] = len(prior)
            score = s["screen_rating"]
            s["reported_screen_rating"] = score
            s["rating_basis"] = "reported_financial_signals" if score is not None else "partial_financials_prior_peer_estimate"
            if score is None: score = 100*sum(imputed[k]*WEIGHTS[k] for k in WEIGHTS)/sum(WEIGHTS.values())
            quality = len(observed)/len(WEIGHTS)
            # Preserve an observed score; provisional conviction discounts missing
            # evidence, identity assumptions and an unverified full thesis.
            certainty = (.35+.65*quality) * .75 * (.8 if s.get("identity_assumed") else 1.)
            s["screen_rating"] = round(score, 1)
            s["sizing_rating"] = round(max(0., min(100., score*certainty)), 1)
            s["modeled_conviction"] = s["sizing_rating"]
            s["financial_evidence_fraction"] = quality
            s["imputed_signals"] = {k: {"value": imputed[k], "prior_other_issuers": 0 if k in stale else peers[k],
                                        "basis": "own_stale_asfiled_estimate" if k in stale else "earlier_other_issuer_median" if peers[k] else "neutral_prior"}
                                   for k in WEIGHTS if k not in observed}
            s["assumption_reserve"] = .005+.01*(1-quality)+(.005 if s.get("identity_assumed") else 0.)
        for s in batch:
            for key, row in s["fundamental"].get("signals", {}).items():
                if key in WEIGHTS: history[key][s["issuer"]] = row["score"]
    return snapshots


def financing_estimate(snapshot, store):
    """Mechanical issuance scenarios include proceeds; no split-created dilution."""
    f = snapshot["fundamental"]
    cash, cfo = f.get("balances", {}).get("cash"), f.get("flows", {}).get("cfo")
    runway = 12*cash/-cfo if cash is not None and cash >= 0 and cfo is not None and cfo < 0 else None
    need = max(0., -.5*cfo-cash) if cash is not None and cfo is not None and cfo < 0 else None
    shares = f.get("balances", {}).get("shares")
    share_facts = [r for r in f.get("evidence", []) if r.get("unit") == "shares"]
    filed = max((r.get("filed", "")[:10] for r in share_facts), default=None)
    day = moment(snapshot["known_at"]).astimezone(NY).date().isoformat()
    if shares and filed: shares *= store.factor(snapshot["database_ticker"], filed, day)
    cap = shares*snapshot["price"] if shares and snapshot.get("price") and f.get("currency") == "USD" else None
    probability = .75 if runway is not None and runway < 6 else .5 if runway is not None and runway < 12 else .25
    # $0 means explicitly modeled no issuance, not a guessed missing financing.
    scenarios = [{"probability": 1-probability, "issuance_fraction": 0., "discount": 0., "per_share_value_change": 0.}]
    for discount in (.15, .30):
        fraction = 0. if need == 0 else min(2., need/(cap*(1-discount))) if need is not None and need > 0 and cap else .25
        effect = (1+fraction*(1-discount))/(1+fraction)-1
        scenarios.append({"probability": probability/2, "issuance_fraction": fraction, "discount": discount,
                          "per_share_value_change": effect,
                          "net_proceeds": cap*fraction*(1-discount) if cap else None})
    return {"status": "assumed_financing_scenarios_not_reconciled_claims", "reverse_split_economic_dilution": 0.,
            "historical_runway_months": runway, "six_month_cash_need": need, "currency": f.get("currency"),
            "reported_share_market_value_estimate_usd": cap, "share_basis": "reported_filing_basis_then_subsequent_known_splits_assumed",
            "scenarios": scenarios, "expected_value_change": sum(r["probability"]*r["per_share_value_change"] for r in scenarios),
            "scenario_horizon_months": 6, "issuance_probability_assumed": probability,
            "unknown_claims": ["warrants", "convertibles", "ATM utilization", "senior claims", "issue timing"],
            "added_to_forecast_return": False}


def stale_financial_model(snapshot, facts):
    f = snapshot["fundamental"]
    if f["status"] != "stale_or_missing_period" or not f.get("period") or snapshot["cik"] not in facts: return {}
    age = (moment(snapshot["known_at"]).astimezone(NY).date()-datetime.fromisoformat(f["period"]).date()).days
    if not 200 < age <= 550: return {}
    from .fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    meta = facts[snapshot["cik"]]
    path = Path(meta["path"])
    if digest(path) != meta["sha256"]: raise ValueError("Cached financials changed")
    raw = read_json(path)
    if not raw.get("cik"):
        identity = read_json(path.with_name(path.name+".identity.json"), {})
        if identity.get("companyfacts_sha256") == meta["sha256"]: raw = {**raw, "cik": snapshot["cik"]}
    historical = filing_rating(raw, snapshot["known_at"], screen, expected_cik=snapshot["cik"], max_age_days=550)
    scores = {k: r["score"] for k, r in historical.get("signals", {}).items()}
    cash, cfo = historical.get("balances", {}).get("cash"), historical.get("flows", {}).get("cfo")
    projected_cash = None
    if cash is not None and cfo is not None and cfo < 0:
        projected_cash = max(0., cash+cfo*age/365.25)
        scores["cash_burn"] = max(0., min(1., (4-projected_cash/-cfo)/3))
    return {"basis": "stale_asfiled_carry_forward_no_unreported_financing_assumed", "period": f["period"], "age_days": age,
            "historical_balances": historical.get("balances", {}), "historical_flows": historical.get("flows", {}),
            "estimated_cash_after_elapsed_burn": projected_cash, "estimated_signals": scores,
            "currency": historical.get("currency"), "evidence": historical.get("evidence", []), "reported_score_eligible": False}


def framework_packet(snapshot, documents, store):
    terms = []
    cutoff = moment(snapshot["known_at"])
    for d in documents:
        if moment(d["known_at"]) <= cutoff: terms.extend(extract_terms(d))
    signals = snapshot["fundamental"].get("signals", {})
    rows = []
    for key in FRAMEWORKS:
        numeric = [k for k, framework in SIGNAL_FRAMEWORK.items() if framework == key and k in signals]
        leads = [r for r in terms if key in r["frameworks"]]
        status = "unresolved_neutral_prior"
        if numeric: status = "numeric_risk_supported" if max(signals[k]["score"] for k in numeric) >= .5 else "numeric_risk_mitigated"
        elif leads: status = "dated_context_requires_reconciliation"
        if key == "reverse_split_impairment": status = "verified_action_no_automatic_value_loss"
        if key == "borrow_and_carry": status = "annual_rate_and_access_assumed"
        if key == "path_and_timing": status = "dated_action_conditional_daily_exit"
        if key == "crowding_squeeze": status = "unmeasured_squeeze_stress_budgeted"
        if key == "fraud_bad_actors": status = "unresolved_no_allegation"
        rows.append({"framework": key, "status": status, "numeric_signals": numeric,
                     "citations": [{k: r[k] for k in ("category", "known_at", "source_url", "source_sha256", "locator")} for r in leads[:3]],
                     "positive_edge_added": 0.})
    financing = financing_estimate(snapshot, store)
    return {"key": snapshot["key"], "ticker": snapshot["ticker"], "issuer": snapshot["issuer"],
            "known_at": snapshot["known_at"], "source_url": snapshot.get("source_url"),
            "rating_basis": snapshot["rating_basis"], "reported_rating": snapshot["reported_screen_rating"],
            "modeled_rating": snapshot["screen_rating"], "modeled_conviction": snapshot["modeled_conviction"],
            "imputed_signals": snapshot["imputed_signals"], "assumptions": snapshot.get("data_assumptions", []),
            "financial_evidence_fraction": snapshot["financial_evidence_fraction"],
            "financial_status": snapshot["fundamental"]["status"], "financial_period": snapshot["fundamental"].get("period"),
            "financials": snapshot["fundamental"],
            "stale_financial_model": snapshot.get("stale_financial_model", {}),
            "frameworks": rows, "financing": financing, "completed_underwriting": False,
            "reconstructed_at": datetime.now(timezone.utc).isoformat(), "outcome_blinded": True,
            "authority": "none"}


def prior_microstructure(snapshot, store, day):
    rows = [r for r in store.prior(snapshot["database_ticker"], day) if r.get("close") and r.get("volume") is not None]
    normalized = [r["close"]/store.factor(snapshot["database_ticker"], r["date"], day) for r in rows]
    returns = [math.log(b/a) for a, b in zip(normalized, normalized[1:]) if a > 0 and b > 0]
    return {"daily_volatility": max(.02, pstdev(returns)) if len(returns) >= 5 else .10,
            "observations": len(rows)}


def assumed_cost_curve(snapshot, outcome, store, measured, *, participation, multiple=1.):
    price, adv = outcome.get("entry_price"), outcome.get("prior_adv")
    if not price or not adv: return []
    micro = prior_microstructure(snapshot, store, outcome["entry_day"])
    vol = micro["daily_volatility"]
    result = []
    # Up to the fixed 2.5% name-notional cap; no inferred displayed inventory.
    for dollars in (25, 50, 100, 250, 500, 1000, 1250, 2500):
        observed = next((r for r in measured if r["notional"] >= dollars), None)
        volume_fraction = dollars/(adv*price)
        impact = 2*vol*math.sqrt(max(0., volume_fraction))
        if observed:
            base = observed["round_trip"]
            # Old measured curves were calibrated at 0.1% participation. A
            # larger capacity assumption cannot retain the identical cost curve.
            incremental = max(0., impact-2*vol*math.sqrt(min(.001, volume_fraction)))
            slip = base+incremental
            uncertainty = observed.get("uncertainty", 0.)
            basis, issuers = "prior_depth_plus_participation_impact", observed.get("issuers", 0)
        else:
            slip = max(.005, .01/price)+impact
            uncertainty = .5*slip
            basis, issuers = "assumed_tick_spread_and_square_root_impact", 0
        result.append({"notional": dollars, "round_trip": min(.95, slip*multiple), "issuers": issuers,
                       "uncertainty": uncertainty*multiple+snapshot["assumption_reserve"], "basis": basis,
                       "prior_bar_count": micro["observations"], "participation_limit": participation})
    return result


def scenario_plan():
    common = {"participation": .001, "minimum_notional": 100., "annual_borrow": .50, "slippage_multiple": 1.,
              "allow_estimated_ratings": True, "allow_clock_proxy": False, "access_fraction": 1.}
    return [
        {**common, "id": "recovered_reported", "label": "Recovered data · reported scores", "allow_estimated_ratings": False},
        {**common, "id": "documented_estimates", "label": "Documented estimates · original capacity"},
        {**common, "id": "effective_clock_proxy", "label": "Also assume effective-day observability", "allow_clock_proxy": True},
        {**common, "id": "minimum25", "label": "$25 minimum order", "minimum_notional": 25.},
        {**common, "id": "capacity1pct", "label": "1% volume capacity + impact", "participation": .01},
        {**common, "id": "borrow100", "label": "2× borrowing · 100% fallback", "annual_borrow": 1.},
        {**common, "id": "borrow300", "label": "6× borrowing · 300% fallback", "annual_borrow": 3.},
        {**common, "id": "slippage2x", "label": "Twice modeled slippage", "slippage_multiple": 2.},
        {**common, "id": "access50pct", "label": "50% hypothetical borrow access", "access_fraction": .5},
    ]


def deterministic_access(key, fraction):
    value = int(hashlib.sha256(("RSI4-access-v1/"+key).encode()).hexdigest()[:12], 16)/16**12
    return value < fraction


def scenario_snapshot(snapshot, annual_fallback):
    result = copy.copy(snapshot)
    if indication := snapshot.get("announcement_borrow"):
        # A fresh entry indication takes precedence in simulate(). If it is
        # absent, preserve an expensive last indication and floor a cheap stale
        # rate at the explicitly assumed fallback. Scale BOTH in fee stress.
        result["announcement_borrow"] = {**indication,
            "annual_rate": max(annual_fallback, indication["annual_rate"]*annual_fallback/.5),
            "source_annual_rate": indication["annual_rate"], "entry_fallback_assumed": True}
    return result


def public_borrow_proxies(events, document):
    records, seen = [], set()
    for event in events:
        history = document.get("histories", {}).get(event["ticker"], {})
        for r in history.get("records", []):
            identity = event["issuer"], r["known_at"]
            if identity in seen: continue
            seen.add(identity)
            records.append({"issuer": event["issuer"], "kind": "indication", "known_at": r["known_at"],
                            "annual_rate": r["annual_rate"], "shares": r["available_shares"],
                            "source_url": history["source_url"], "source_sha256": history["source_sha256"],
                            "assumed_historical_identity": True, "account_approval": False,
                            "evidence_class": "public_daily_proxy_not_actual_charge"})
    return records


def announcement_plan(candidate, policy, account, sessions, evidence, *, variant):
    s, o, f = candidate["snapshot"], candidate["outcome"], candidate["forecast"]
    reference_price = candidate.get("announcement_reference_price")
    if not reference_price or not s.get("prior_dollar_adv") or not o.get("entry_day"):
        return {"shares": 0, "reason": "announcement_price_or_capacity_unavailable"}
    if f["status"] != "estimated": return {"shares": 0, "reason": f["status"]}
    if s["screen_rating"] < policy.fundamental_floor: return {"shares": 0, "reason": "fundamental_filter"}
    indicative = dated_borrow(evidence["borrow"], s["issuer"], moment(s["known_at"]), approval=False, max_age_hours=24.)
    rate = indicative["annual_rate"] if indicative else policy.assumed_annual_borrow
    # All costs, rating, rate and ADV are available at the thesis cutoff. Later
    # portfolio capacity and the realized opening auction cannot enter this plan.
    # A public inventory count also has nominal units on its observation day.
    inventory = indicative["shares"]*candidate["announcement_split_factor"] if indicative else None
    result = size_position(f, candidate["announcement_curve"], reference_price, o["entry_day"], rate, sessions, policy, account,
                           adv=s["prior_dollar_adv"]/reference_price, inventory=inventory,
                           rating=s["modeled_conviction"], mode="net_edge" if variant == "net_edge" else "baseline",
                           calendar_asof=s["known_at"])
    return {**result, "known_at": s["known_at"], "annual_borrow": rate,
            "borrow_basis": "dated_public_proxy_identity_assumed" if indicative else "annual_rate_assumption",
            "inventory_basis": "prior_public_indication_not_approval" if indicative else "access_assumed",
            "cost_and_capacity_basis": "announcement_last_close_projected_through_known_split_and_prior_volume",
            "projected_share_factor": candidate["announcement_split_factor"]}


def case_metrics(result, start):
    if result["performance_valid"]:
        return path_metrics(result["daily_equity_curve"], 50000., start, END)
    return {"status": "unresolved_or_unfunded", "net_pnl": None, "cagr": None, "max_drawdown": None, "calmar": None}


def collateral_scenarios(outcome, policy, sessions):
    if outcome.get("status") != "daily_benchmark": return outcome
    schedule = loan_schedule(outcome["entry_day"], outcome["exit_day"], outcome["entry_price"], 0., sessions,
                             minimum_days=policy.minimum_billed_days, basis=policy.borrow_basis)
    outcome["collateral_factors"] = [calendar_mark(outcome["marks"], r["date"],
        outcome["entry_price"])/outcome["entry_price"] for r in schedule["days"]]
    return outcome


def baseline_comparison(original, recovered, original_store, recovered_store, sessions):
    """Measure source recovery on the original denominator, without resizing trades.

    Duplicate baseline records stay visible here because the quoted 70/233 gaps
    counted records. They never become extra positions in the repaired study.
    """
    policy = StudyPolicy(entry="post_split_next_open")
    windows = {}
    for start, label in ((START, "full"), (RECENT, "recent")):
        scored, missing, repaired = [], [], []
        for key, s in original.items():
            if s.get("screen_rating") is None:
                continue
            day = entry_day(s, policy, sessions)
            if not day or not start <= day <= END:
                continue
            scored.append(key)
            ticker = s["database_ticker"]
            old_price = original_store.prices(ticker).get(day, {}).get("open")
            if isinstance(old_price, (float, int)) and math.isfinite(old_price) and old_price > 0:
                continue
            record = {"key": key, "ticker": s["ticker"], "entry_day": day}
            missing.append(record)
            price = recovered_store.prices(ticker).get(day, {}).get("open")
            if isinstance(price, (float, int)) and math.isfinite(price) and price > 0:
                repaired.append(record)
        windows[label] = {"original_scored_records": len(scored), "original_missing_entry_records": len(missing),
                          "recovered_entry_records": len(repaired), "remaining_missing_entry_records": len(missing)-len(repaired),
                          "recovered_records": repaired}
    reported = [s for s in recovered.values() if s["reported_screen_rating"] is not None]
    missing = [s for s in recovered.values() if s["fundamental"]["status"] == "raw_companyfacts_missing"]
    return {"basis": "original_event_records_same_next_session_entry_no_portfolio_or_policy_change",
            "limits": "Recovered daily opens are price observations, not fills or independent new trades. The repaired study deduplicates source records and applies separate cost and conviction assumptions; its P&L is not a data-only comparison with RSI-3.",
            "financials": {"original_reported_scores": sum(s.get("screen_rating") is not None for s in original.values()),
                           "current_reported_scores": len(reported),
                           "current_reported_existing_identity": sum(not s["identity_assumed"] for s in reported),
                           "current_reported_assumed_identity": sum(s["identity_assumed"] for s in reported),
                           "missing_issuer_identity": sum(not s.get("cik") for s in missing),
                           "identified_issuer_raw_file_missing": sum(bool(s.get("cik")) for s in missing)},
            "entry_prices": windows}


def run(args):
    destination, source = args.destination.resolve(), args.source_root.resolve()
    output = destination/"local/coverage_v4"
    if args.collect or not (output/"inputs.json").exists():
        collect_free_inputs(source, destination, fetch=args.fetch, maximum=args.max_requests)
    inputs = read_json(output/"inputs.json")
    events, frozen, disclosures, _ = catalogue_inputs(source)
    if inputs["source_manifest_sha256"] != digest(frozen/"manifest.json"): raise ValueError("Frozen source changed")
    repaired = inputs["events"]
    # Keep the canonical split action map as well as newly repaired actions.
    store = CoverageStore(frozen/"prices.sqlite", events+repaired, inputs["supplemental"], inputs.get("chart_actions"))
    evidence = read_evidence(destination/"local/edge_inputs")
    borrow_inputs = read_json(output/"borrow_inputs.json", {})
    evidence["borrow"] += public_borrow_proxies(repaired, borrow_inputs)
    evidence["borrow"] = BorrowHistory(evidence["borrow"])
    snapshots, gaps, hashes = build_snapshots(repaired, store, source, output, evidence)
    event_map = {e["event_id"]: e for e in repaired}
    for key, s in snapshots.items():
        s["data_assumptions"] = event_map[key]["assumptions"]
        s["identity_assumed"] = "identity_exact_company_name_current_registry" in s["data_assumptions"]
        s["clock_assumed"] = "effective_date_clock_proxy" in s["data_assumptions"]
        s["stale_financial_model"] = stale_financial_model(s, inputs["facts"])
    estimate_ratings(snapshots)
    # Text assessment is outcome-blinded and supplied only dated issuer filings.
    by_cik = defaultdict(list)
    for d in disclosures:
        if d.get("text_file"): by_cik[str(int(d["cik"]))].append(d)
    packets, packet_specs = {}, []
    for i, s in enumerate(snapshots.values()):
        docs = []
        eligible = [d for d in by_cik[s["cik"]] if moment(d["available_at"]) <= moment(s["known_at"])
                    and (moment(s["known_at"])-moment(d["available_at"])).days <= 180]
        for d in sorted(eligible, key=lambda r: r["available_at"], reverse=True)[:4]:
            p = source.parents[2]/d["text_file"]
            if not p.resolve().is_relative_to(source.parents[2].resolve()) or not p.exists(): continue
            acc = d["accession"]
            docs.append({"text": p.read_text(encoding="utf-8", errors="replace"), "known_at": d["available_at"],
                         "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(d['cik'])}/{acc}/",
                         "source_sha256": digest(p), "accessionNumber": acc})
        packet = framework_packet(s, docs, store)
        # Financing is a declared model feature, never an extra return overlay.
        s["dilution"] = packet["financing"]["expected_value_change"]
        packets[s["key"]] = packet
        name = hashlib.sha256(s["key"].encode()).hexdigest()[:24]+".json"
        write_public_json(output/"packets"/name, packet)
        packet_specs.append({"key": s["key"], "ticker": s["ticker"], "known_at": s["known_at"],
                             "rating_basis": s["rating_basis"], "reported_rating": s["reported_screen_rating"],
                             "modeled_rating": s["screen_rating"], "modeled_conviction": s["modeled_conviction"],
                             "clock_assumed": s["clock_assumed"], "identity_assumed": s["identity_assumed"],
                             "url": "data/shorts_coverage_packets/"+name, "sha256": digest(output/"packets"/name)})
        if i % 500 == 0: print(f"RSI-4 frameworks {i}/{len(snapshots)}", flush=True)
    from .universe_study import trading_calendar
    sessions = tuple(trading_calendar("2018-01-01", "2027-02-01"))
    post_policy = StudyPolicy(entry="post_split_next_open")
    late_publications = set()
    for key, s in snapshots.items():
        post_day = entry_day(s, post_policy, sessions)
        if post_day and moment(s["known_at"]) >= datetime.fromisoformat(post_day).replace(tzinfo=NY, hour=9):
            late_publications.add(key)
    policies = [StudyPolicy(entry=entry, sessions=hold, bracket=bracket, profit_take=target, stop_loss=stop,
                            fundamental_floor=60., minimum_billed_days=1)
                for entry, hold, bracket, target, stop in (
                    ("announcement_next_open", 5, True, .10, .20),
                    ("post_split_next_open", 10, True, .20, .20),
                    ("post_split_next_open", 10, False, .20, .20))]
    plan = {"created_at": datetime.now(timezone.utc).isoformat(), "policies": [asdict(p) for p in policies],
            "scenarios": scenario_plan(), "selection": "Coverage/cost comparisons declared before new results; prior exits remain explored.",
            "account": asdict(Account(name_stress_budget=.02)), "input_sha256": digest(output/"inputs.json"),
            "code_sha256": digest(Path(__file__)), "data_cost_usd": 0}
    plan["signature"] = hashlib.sha256(json.dumps({k: v for k, v in plan.items() if k != "created_at"}, sort_keys=True).encode()).hexdigest()
    write_json(output/"plan.json", plan)
    observations = cost_observations(source, read_json(source/"local/net_edge_v2/snapshots.json"))
    rows, audit_specs = [], {}
    for n, policy in enumerate(policies):
        outcomes = make_outcomes(snapshots, store, policy, sessions, END)
        outcomes = {k: collateral_scenarios(o, policy, sessions) for k, o in outcomes.items()}
        # Only reported scores and non-proxy clocks train empirical returns.
        # The expanded/inferred cohort cannot manufacture a favorable peer prior.
        training = {k: s for k, s in snapshots.items() if s["reported_screen_rating"] is not None and not s["clock_assumed"] and k not in late_publications}
        donors = donor_rows(training, outcomes, policy)
        forecasts = {k: payoff_forecast(s, donors, policy) for k, s in snapshots.items()}
        measured = {k: cost_curve({**s, "price": outcomes[k].get("entry_price") or s["price"]}, observations, policy)
                    for k, s in snapshots.items()}
        announcement_references = {}
        for key, s in snapshots.items():
            prior = store.prior(s["database_ticker"], moment(s["known_at"]).astimezone(NY).date().isoformat())
            last_day = prior[-1]["date"] if prior else None
            entry = outcomes[key].get("entry_day")
            factor = math.prod(r["ratio"] for r in forecasts[key].get("known_splits", []) if last_day and entry and last_day < r["date"] <= entry)
            announcement_references[key] = (s["price"]/factor if s.get("price") else None, factor)
        announcement_measured = {k: cost_curve({**s, "price": announcement_references[k][0]}, observations, policy) for k, s in snapshots.items()}
        for scenario in scenario_plan():
            upstream = {}
            candidates = []
            for key, s in snapshots.items():
                if key in late_publications:
                    upstream[key] = "publication_after_post_split_entry_window"; continue
                if s["clock_assumed"] and not scenario["allow_clock_proxy"]:
                    upstream[key] = "effective_clock_proxy_not_enabled"; continue
                if s["reported_screen_rating"] is None and not scenario["allow_estimated_ratings"]:
                    upstream[key] = "reported_financial_score_unavailable"; continue
                if not deterministic_access(key, scenario["access_fraction"]):
                    upstream[key] = "hypothetical_borrow_access_denied"; continue
                s = scenario_snapshot(s, scenario["annual_borrow"])
                f = copy.deepcopy(forecasts[key])
                # Missing evidence attenuates positive estimated alpha toward zero
                # without making negative forecasts look better.
                if f["status"] == "estimated" and f["gross_edge"] > 0:
                    reliability = .5+.5*s["financial_evidence_fraction"]
                    f["gross_edge"] *= reliability
                    f["gross_lower_bound"] -= (1-reliability)*abs(f["unshrunk_gross_edge"])
                curve = assumed_cost_curve(s, outcomes[key], store, measured[key], participation=scenario["participation"], multiple=scenario["slippage_multiple"])
                # Separate announcement cost plans from entry-time feasibility.
                reference_price, split_factor = announcement_references[key]
                ann_outcome = {"entry_price": reference_price, "prior_adv": s["prior_dollar_adv"]/reference_price if reference_price and s.get("prior_dollar_adv") else None,
                               "entry_day": moment(s["known_at"]).astimezone(NY).date().isoformat()}
                ann_curve = assumed_cost_curve(s, ann_outcome, store, announcement_measured[key], participation=scenario["participation"], multiple=scenario["slippage_multiple"])
                candidates.append({"snapshot": s, "outcome": outcomes[key], "forecast": f, "curve": curve, "announcement_curve": ann_curve,
                                   "announcement_reference_price": reference_price, "announcement_split_factor": split_factor})
            p = replace(policy, assumed_annual_borrow=scenario["annual_borrow"], minimum_notional=scenario["minimum_notional"])
            account = Account(name_stress_budget=.02, participation=scenario["participation"])
            # Public ex-date cash dividends become modeled liabilities, never
            # valuation or selection features. Missing data does not gate entry.
            cash_evidence = copy.deepcopy(evidence)
            for record in cash_evidence["borrow"]:
                if record.get("annual_rate") is not None: record["annual_rate"] *= scenario["annual_borrow"]/.5
            for c in candidates:
                s, o = c["snapshot"], c["outcome"]
                if not o.get("entry_day"): continue
                for div in inputs["dividends"].get(s["database_ticker"], []):
                    if div["date"] <= o["entry_day"]: continue
                    factor = store.factor(s["database_ticker"], o["entry_day"], div["date"])
                    cash_evidence["cashflows"].append({"event_id": s["key"], "kind": "dividend", "value_date": div["date"],
                                                      "entitlement_date": div["date"], "cost_per_entry_share": div["amount"]*factor,
                                                      "assumed_ex_date_payment": True})
            for variant in ("fundamental", "net_edge"):
                announcement_plans = {c["snapshot"]["key"]: announcement_plan(c, p, account, sessions, cash_evidence, variant=variant)
                                      for c in candidates}
                candidate_by_key = {c["snapshot"]["key"]: c for c in candidates}
                for start, window in ((START, "full"), (RECENT, "recent")):
                    cid = f"p{n}_{scenario['id']}_{variant}_{window}"
                    entry_cutoff = [day for day in sessions if day <= END][-p.sessions]
                    result = simulate(candidates, p, account, sessions, store, cash_evidence,
                                      variant=variant, keep_daily=True, start_day=start, entry_end_day=entry_cutoff)
                    # Reserve every admitted missing path. Never prune its event
                    # based on whether its future outcome improves the result.
                    write_json(output/"cases"/(cid+".json"), result)
                    stats = case_metrics(result, start)
                    ledger = result["trade_ledger"]
                    counted = [r for r in result["journal"] if r.get("shares")]
                    window_keys = {k for k, s in snapshots.items() if (day := entry_day(s, p, sessions)) and start <= day <= END}
                    upstream_window = Counter(upstream[k] for k in window_keys if k in upstream)
                    visited = {r["key"] for r in result["journal"]}
                    pre_loop = Counter("entry_window_reserved_for_maximum_hold" if entry_day(snapshots[k], p, sessions) > entry_cutoff else outcomes[k]["status"]
                                       for k in window_keys-visited-upstream.keys())
                    row = {"id": cid, "policy_id": f"p{n}", "scenario_id": scenario["id"], "label": scenario["label"],
                           "variant": variant, "window": window, "start": start, "end": END,
                           "last_new_entry_day": entry_cutoff,
                           "policy": asdict(p), "account": asdict(account), **stats,
                           "trades": result["trades"], "issuers": len({t["issuer"] for t in ledger}),
                           "window_candidate_events": len(window_keys), "considered_events": len(result["journal"]),
                           "upstream_exclusions": dict(upstream_window), "pre_loop_exclusions": dict(pre_loop),
                           "skipped": result["skipped"], "performance_valid": result["performance_valid"],
                           "unresolved_admitted_names": result["unresolved_admitted_names"], "open_positions": result["open_positions"],
                           "margin_stress_breaches": result["margin_stress_breaches"], "costs": result["costs"],
                           "estimated_rating_trades": sum(snapshots[t["key"]]["reported_screen_rating"] is None for t in ledger),
                           "assumed_identity_trades": sum(snapshots[t["key"]]["identity_assumed"] for t in ledger),
                           "assumed_clock_trades": sum(snapshots[t["key"]]["clock_assumed"] for t in ledger),
                           "public_reconstructed_entry_trades": sum(store.prices(snapshots[t["key"]]["database_ticker"])[t["entry_day"]].get("source") == "free_chart_reconstructed_nominal" for t in ledger),
                           "public_volume_sized_trades": sum(any(r.get("volume_source") for r in store.prior(snapshots[t["key"]]["database_ticker"], t["entry_day"])) for t in ledger),
                           "admitted_positions": len(counted), "sample_qualified": result["performance_valid"] and len(ledger) >= 30 and len({t["issuer"] for t in ledger}) >= 20 and len({t["entry_day"][:4] for t in ledger}) >= 3,
                           "extra_2pct_loss_pnl": stats.get("net_pnl")-1000 if stats.get("net_pnl") is not None else None}
                    rows.append(row)
                    audit = {"schema_version": "shorts_coverage_audit.v1", "id": cid, "authority": "none", "research_only": True,
                             "scenario": scenario, "policy": asdict(p), "journal": result["journal"],
                             "trades": [{k: t[k] for k in ("key", "ticker", "issuer", "entry_day", "exit_day", "shares")} for t in ledger],
                             "aggregate_costs": result["costs"], "individual_price_returns_published": False,
                             "private_case_sha256": digest(output/"cases"/(cid+".json")),
                             "daily_equity_curve": result["daily_equity_curve"],
                             "forecasts": {r["key"]: {k: candidate_by_key[r["key"]]["forecast"].get(k) for k in
                                            ("status", "gross_edge", "gross_lower_bound", "expected_hold_sessions", "donors", "latest_training_exit")}
                                           for r in result["journal"]},
                             "announcement_plans": {r["key"]: announcement_plans[r["key"]] for r in result["journal"]}}
                    ap = output/"audits"/(cid+".json")
                    write_public_json(ap, audit)
                    audit_specs[cid] = {"url": "data/shorts_coverage_audits/"+ap.name, "sha256": digest(ap)}
            print(f"RSI-4 policy {n+1}/3 scenario {scenario['id']}: {len(candidates)} candidates", flush=True)
    original_path = destination/"local/net_edge_v3/frozen_snapshots.json"
    comparison = None
    if original_path.exists():
        original_store = PriceStore(frozen/"prices.sqlite", events)
        try:
            comparison = baseline_comparison(read_json(original_path), snapshots, original_store, store, sessions)
        finally:
            original_store.connection.close()
    store.connection.close()
    coverage = {**inputs["coverage"], "snapshots": len(snapshots),
                "reported_ratings": sum(s["reported_screen_rating"] is not None for s in snapshots.values()),
                "estimated_ratings": sum(s["reported_screen_rating"] is None for s in snapshots.values()),
                "own_stale_financial_estimates": sum(bool(s["stale_financial_model"]) for s in snapshots.values()),
                "clock_proxy_events": sum(s["clock_assumed"] for s in snapshots.values()),
                "assumed_identity_events": sum(s["identity_assumed"] for s in snapshots.values()),
                "framework_packets": len(packets), "framework_routes_per_packet": len(FRAMEWORKS),
                "complete_underwriting": 0, "approved_locates": 0, "observed_fills": 0,
                "supplemented_price_symbols": len(inputs["supplemental"]),
                "supplemental_price_bars": sum(len(v) for v in inputs["supplemental"].values()),
                "partial_venue_volume_observations_replaced": store.volume_overrides,
                "public_borrow_symbols": borrow_inputs.get("symbols_with_records", 0),
                "public_borrow_daily_records": borrow_inputs.get("daily_records", 0),
                "announcement_borrow_proxies": sum(dated_borrow(evidence["borrow"], s["issuer"], moment(s["known_at"]), approval=False, max_age_hours=24.) is not None for s in snapshots.values()),
                "price_source_status": dict(Counter(r["status"] for r in inputs["price_status"])),
                "event_exclusions": dict(Counter(r["reason"] for r in inputs["rejected"])), "financial_gaps": gaps}
    summary = {"schema_version": "shorts_coverage_research.v1", "version": "RSI-4.0", "built_at": datetime.now(timezone.utc).isoformat(),
               "research_only": True, "authority": "none", "data_cost_usd": 0, "paid_requests": 0,
               "frozen_rsi3_unchanged": True, "coverage": coverage, "assumptions": ASSUMPTIONS,
               "baseline_comparison": comparison,
               "plan": plan, "cases": rows, "names": packet_specs, "audit_files": audit_specs,
               "strict_case": {"trades": 0, "reason": "Historical locate approval, fills and full underwriting cannot be assumed into observed evidence."},
               "remaining": ["Incomplete event universe and ambiguous historical security identities.",
                             "Historical borrowed inventory, actual rates/charges, recalls and account approvals.",
                             "Historical NBBO, auction fills, halts and SSR-compliant order execution.",
                             "Fully reconciled warrants, convertibles, ATM issuance, valuation and catalysts.",
                             "Missing delisted prices, unobserved dividends and fractional corporate-action settlements."],
               "bindings": {"frozen_rsi3_summary_sha256": digest(destination/"net_edge_research_v3.json"),
                            "source_manifest_sha256": inputs["source_manifest_sha256"], "raw_financials": hashes,
                            "coverage_inputs_sha256": digest(output/"inputs.json"),
                            "original_snapshots_sha256": digest(original_path) if comparison else None},
               "collection": {"data_cost_usd": 0, "network_requests_this_collection": inputs["network_requests_this_run"],
                              "network_status": inputs["network_status"]}}
    write_public_json(output/"summary.json", summary)
    errors = audit_publication(summary)
    if errors: raise ValueError("RSI-4 validation failed: "+"; ".join(errors[:10]))
    if args.publish:
        import shutil
        write_public_json(destination/"coverage_research.json", summary)
        shutil.copytree(output/"packets", destination/"coverage_packets", dirs_exist_ok=True)
        shutil.copytree(output/"audits", destination/"coverage_audits", dirs_exist_ok=True)
    print(json.dumps({"coverage": coverage, "cases": len(rows), "validation_errors": errors}), flush=True)
    return summary


def audit_publication(doc):
    errors = []
    if doc.get("data_cost_usd") != 0 or doc.get("paid_requests") != 0 or doc.get("authority") != "none": errors.append("cost_or_authority")
    if doc.get("frozen_rsi3_unchanged") is not True: errors.append("frozen_version_rewritten")
    if comparison := doc.get("baseline_comparison"):
        financials = comparison["financials"]
        if financials["current_reported_scores"] != doc["coverage"]["reported_ratings"] or financials["current_reported_existing_identity"]+financials["current_reported_assumed_identity"] != financials["current_reported_scores"]:
            errors.append("financial_recovery_mismatch")
        for window, row in comparison["entry_prices"].items():
            if row["recovered_entry_records"]+row["remaining_missing_entry_records"] != row["original_missing_entry_records"] or len(row["recovered_records"]) != row["recovered_entry_records"]:
                errors.append("entry_recovery_mismatch/"+window)
    plan = doc["plan"]
    declared = {k: v for k, v in plan.items() if k not in {"created_at", "signature"}}
    if hashlib.sha256(json.dumps(declared, sort_keys=True).encode()).hexdigest() != plan["signature"]: errors.append("declared_plan_changed")
    expected = len(plan["policies"])*len(plan["scenarios"])*4
    if len(doc["cases"]) != expected or len({r["id"] for r in doc["cases"]}) != expected: errors.append("incomplete_scenario_matrix")
    for row in doc["cases"]:
        if row["admitted_positions"]+sum(row["skipped"].values()) != row["considered_events"]: errors.append("attrition_mismatch/"+row["id"])
        if row["window_candidate_events"] != row["considered_events"]+sum(row["upstream_exclusions"].values())+sum(row["pre_loop_exclusions"].values()): errors.append("upstream_attrition_mismatch/"+row["id"])
        if row["performance_valid"] and (row["unresolved_admitted_names"] or row["open_positions"] or row["margin_stress_breaches"]): errors.append("invalid_path_published/"+row["id"])
        if not row["performance_valid"] and any(row.get(k) is not None for k in ("net_pnl", "cagr", "max_drawdown", "calmar")): errors.append("invalid_metrics/"+row["id"])
        if row["account"]["sleeve_stress_budget"] != .02: errors.append("risk_budget_changed")
        if row.get("calmar") is not None and (not row.get("max_drawdown") or not math.isclose(row["calmar"], row["cagr"]/row["max_drawdown"])): errors.append("calmar_mismatch/"+row["id"])
    return errors


def audit_artifacts(root, dashboard=None):
    root = Path(root)
    source = root/"coverage_research.json"
    if not source.exists(): return []
    doc = read_json(source)
    errors = audit_publication(doc)
    if doc["bindings"]["frozen_rsi3_summary_sha256"] != digest(root/"net_edge_research_v3.json"): errors.append("RSI-4 frozen base changed")
    by_id = {r["id"]: r for r in doc["cases"]}
    names_by_key = {r["key"]: r for r in doc["names"]}
    for key, spec in doc["audit_files"].items():
        path = root/"coverage_audits"/(key+".json")
        if spec["url"] != "data/shorts_coverage_audits/"+key+".json" or digest(path) != spec["sha256"]:
            errors.append("audit_hash/"+key); continue
        audit = read_json(path)
        row = by_id[key]
        if len(audit["trades"]) != row["trades"] or len(audit["journal"]) != row["considered_events"]: errors.append("audit_count/"+key)
        if dict(Counter(r["reason"] for r in audit["journal"] if not r.get("shares"))) != row["skipped"]: errors.append("audit_attrition/"+key)
        if audit["aggregate_costs"] != row["costs"]: errors.append("audit_costs/"+key)
        if audit.get("individual_price_returns_published") is not False or any(
                set(t)-{"key", "ticker", "issuer", "entry_day", "exit_day", "shares"} for t in audit["trades"]): errors.append("individual_price_returns_published/"+key)
        if row["performance_valid"]:
            computed = path_metrics(audit["daily_equity_curve"], 50000., row["start"], row["end"])
            for metric in ("net_pnl", "calmar", "max_drawdown", "cagr"):
                if computed[metric] != row[metric]: errors.append("audit_metrics/"+key+"/"+metric)
        for event, forecast in audit["forecasts"].items():
            if forecast.get("latest_training_exit"):
                name = names_by_key.get(event)
                if not name or moment(forecast["latest_training_exit"]) >= moment(name["known_at"]): errors.append("future_training_exit/"+event)
        if dashboard:
            target = Path(dashboard)/"shorts_coverage_audits"/path.name
            if not target.exists() or digest(target) != spec["sha256"]: errors.append("dashboard_audit_hash/"+key)
    for spec in doc["names"]:
        name = Path(spec["url"]).name
        path = root/"coverage_packets"/name
        if not re_packet_name(name) or digest(path) != spec["sha256"]: errors.append("packet_hash/"+spec["key"]); continue
        packet = read_json(path)
        if packet["key"] != spec["key"] or packet["completed_underwriting"] or not packet["outcome_blinded"]: errors.append("packet_claim/"+spec["key"])
        if {r["framework"] for r in packet["frameworks"]} != set(FRAMEWORKS): errors.append("packet_routes/"+spec["key"])
        if packet["financing"]["reverse_split_economic_dilution"] != 0 or packet["financing"]["added_to_forecast_return"]: errors.append("double_counted_dilution/"+spec["key"])
        for framework in packet["frameworks"]:
            if any(moment(c["known_at"]) > moment(packet["known_at"]) for c in framework["citations"]): errors.append("future_citation/"+spec["key"])
        if dashboard:
            target = Path(dashboard)/"shorts_coverage_packets"/name
            if not target.exists() or digest(target) != spec["sha256"]: errors.append("dashboard_packet_hash/"+spec["key"])
    if dashboard:
        target = Path(dashboard)/"shorts_coverage_research.json"
        if not target.exists() or digest(target) != digest(source): errors.append("dashboard_summary_hash")
    return errors


def re_packet_name(value):
    import re
    return bool(re.fullmatch(r"[a-f0-9]{24}\.json", value))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--max-requests", type=int, default=3000)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.max_requests <= 3000: parser.error("Free request budget must be 0–3000")
    run(args)


if __name__ == "__main__": main()
