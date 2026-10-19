"""Four matched fundamental policies, fixed before examining their returns.

No payoff forecast or minimum financial coverage in the unfiltered comparator.
The three fundamental variants share fixed sizing, prior-liquidity ranking,
cost evidence and the same action/price universe. No production policy changes.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import hashlib
import json
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from itertools import repeat
from pathlib import Path
from statistics import mean, median

from .analysis import cluster_interval
from .calmar_research import END, START, bind_inputs, path_metrics
from .capital_risk import tail
from .clean_data_research import (CleanStore, price_event_universe, publish_parts, repaired_events,
                                  validate_sources, validated_price_overlay)
from .clean_data_sources import SecSources
from .coverage_research import write_public_json
from .fundamental_data import enrich, extended_document, gate, read_market_evidence
from .fundamental_prices import collect_prices
from .ledger import read_json
from .net_edge_evidence import digest
from .net_edge_study import (cost_curve, cost_observations, make_outcomes, source_available,
                             public_borrow_history, read_evidence, simulate, NY, days_between)
from .net_edge_v3 import Account, StudyPolicy, assessment, dated_borrow
from .net_edge import moment
from .portfolio_research import bootstrap_portfolio, performance
from .universe_study import trading_calendar

RECENT = "2023-10-14"
POLICIES = {"unfiltered": "No fundamental filter", "score60": "Score ≥60",
            "score50": "Score ≥50", "score60_or_distress": "Score ≥60 or cash-distress route"}
FOLDS = ((START, "2021-12-31"), ("2022-01-01", "2024-12-31"), ("2025-01-01", END))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fixed_cost_plan(snapshot, policy):
    """Zero predicted alpha; full planned holding period only estimates costs."""
    return {"status": "estimated", "known_at": snapshot["known_at"], "gross_edge": 0.,
            "gross_lower_bound": 0., "gross_scenarios": [0.],
            "holding_scenarios": [{"hold_sessions": policy.sessions-1}],
            "known_splits": [], "basis": "fixed_horizon_cost_reserve_no_alpha_forecast"}


def base_snapshots(events, evidence):
    """Construct the event universe before requesting any financial score."""
    reviews = defaultdict(list)
    for r in evidence["reviews"]: reviews[r["event_id"]].append(r)
    result = {}
    for e in events:
        cutoff = moment(e["available_at"])
        cik = str(e.get("cik") or (e["issuer"][4:] if e["issuer"].startswith("cik/") else "")).lstrip("0")
        dated = [r for r in reviews[e["event_id"]] if
                 (r["review_mode"] == "blinded_historical_reconstruction" or moment(r["review_created_at"]) <= cutoff)
                 and any(source_available(x, cutoff) for x in r.get("frameworks", []))]
        review = max(dated, key=lambda r: moment(r["review_created_at"]), default={})
        framework = assessment(review.get("frameworks", []), cutoff,
                               selected_mechanisms=review.get("selected_mechanisms", []), vetoes=review.get("vetoes", []))
        # These four experiments isolate the numerical financial policy. Keep
        # documentary tradability vetoes common; no thesis-alpha veto can leak
        # into the supposedly unfiltered comparator.
        framework["blocked"] = bool(set(framework["vetoes"])-{"thesis_falsified"})
        result[e["event_id"]] = {"key": e["event_id"], "ticker": e["ticker"], "database_ticker": e.get("database_ticker", e["ticker"]),
             "issuer": e["issuer"], "cik": cik, "known_at": cutoff.isoformat(), "ex_date": e.get("ex_date"),
             "ratio": e["ratio"], "screen_rating": None, "price": None, "prior_dollar_adv": None,
             "framework": framework, "source_url": e.get("source_url"),
             "announcement_borrow": dated_borrow(evidence["borrow"], e["issuer"], cutoff, approval=False, max_age_hours=24.)}
    return result


class VerifiedStore(CleanStore):
    def __init__(self, *args, verified=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.verified = verified or {}
        self.sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))

    def prior(self, ticker, day):
        end = bisect.bisect_left(self.sessions, day)
        allowed = self.sessions[max(0, end-20):end]
        prices = self.prices(ticker)
        cutoff = datetime.fromisoformat(day).replace(tzinfo=NY, hour=9, minute=30)
        return [{**prices[d], **({"volume": None} if prices[d].get("volume_known_at") and moment(prices[d]["volume_known_at"]) >= cutoff else {})}
                for d in allowed if isinstance(prices.get(d, {}).get("close"), (int, float)) and prices[d]["close"] > 0]

    def prices(self, ticker):
        if ticker not in self.cache:
            rows = super().prices(ticker)
            for day, record in self.verified.get(ticker, {}).items():
                # EOD observations can affect later-day capacity only. Import
                # receipts cannot backdate a value not published by the next day.
                if record["known_at"][:10] > str(date.fromisoformat(day)+timedelta(days=1)): continue
                old = rows.get(day, {})
                rows[day] = {**old, "date": day, **{k: v for k, v in record.items() if k in {"open", "high", "low", "close", "volume", "volume_known_at"}}}
            self.cache[ticker] = dict(sorted(rows.items()))
        return self.cache[ticker]


def summary(result, initial, start, end):
    trades, curve = result["trade_ledger"], result["daily_equity_curve"]
    usable = result["performance_valid"]
    daily = [{**d, "trades": d.get("entries", 0)+sum(t["entry_day"] <= d["date"] <= t["exit_day"] for t in trades),
              "pnl": d["equity"]-(curve[i-1]["equity"] if i else initial)} for i, d in enumerate(curve)]
    metrics = performance(daily, initial, start, end) if usable else {}
    gains = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] < 0]
    exposure = sum(t["notional"] for t in trades)
    by_issuer = Counter()
    for t in trades: by_issuer[t["issuer"]] += t["net_pnl"]
    positive = sum(max(0., x) for x in by_issuer.values())
    gross = sum(t["net_pnl"]+t["borrow"]+t["commission"]+t["slippage"]+t["cash_adjustments"] for t in trades)
    peak, intraday_dd = initial, 0.
    for d in curve:
        intraday_dd = max(intraday_dd, 1-d.get("joint_high_equity_bound", d["equity"])/peak)
        peak = max(peak, d["equity"])
    annual = []
    for year in sorted({d["date"][:4] for d in curve}):
        rows = [d for d in curve if d["date"].startswith(year)]
        before = [d for d in curve if d["date"] < rows[0]["date"]]
        base = before[-1]["equity"] if before else initial
        annual.append({"year": year, "trades": sum(t["entry_day"].startswith(year) for t in trades),
                       **(path_metrics(rows, base, max(start, year+"-01-01"), min(end, year+"-12-31")) if usable else {})})
    returns = [t["net_pnl"]/t["notional"] for t in trades]
    return {"performance_valid": usable, "trades": len(trades),
            "admitted": sum(j.get("shares", 0) > 0 for j in result["journal"]),
            "issuers": len(by_issuer), "active_years": len({t["entry_day"][:4] for t in trades}),
            "decisions": len(result["journal"]), "skipped": result["skipped"],
            "unresolved": result["unresolved_admitted_names"], "open_positions": result["open_positions"],
            "margin_breach_days": result["margin_stress_breaches"], "observed_fills": result["observed_fills"],
            "performance": metrics, "costs": {"gross_price_pnl": gross, **result["costs"],
                "cash_adjustments": sum(t["cash_adjustments"] for t in trades)},
            "trade_statistics": {"win_rate": len(gains)/len(trades) if trades else None,
                "profit_factor": sum(gains)/-sum(losses) if losses else None,
                "average_win": mean(gains) if gains else None, "average_loss": mean(losses) if losses else None,
                "expectancy_dollars": mean(t["net_pnl"] for t in trades) if trades else None,
                "mean_trade_return": mean(returns) if returns else None, "median_trade_return": median(returns) if returns else None,
                "net_return_on_exposure": sum(t["net_pnl"] for t in trades)/exposure if exposure else None,
                "summed_entry_exposure": exposure, "exit_reasons": dict(Counter(t["reason"] for t in trades)),
                "mean_held_calendar_days": mean((date.fromisoformat(t["exit_day"])-date.fromisoformat(t["entry_day"])).days for t in trades) if trades else None,
                "tail": tail([{"return": r} for r in returns], "return"),
                "issuer_clustered_mean_interval": cluster_interval([{"issuer": t["issuer"], "return": t["net_pnl"]/t["notional"]} for t in trades], field="return", cluster="issuer") if trades else None},
            "risk": {"joint_daily_high_drawdown_bound": intraday_dd if usable else None,
                "maximum_joint_high_margin_ratio": result["maximum_joint_high_margin_ratio"],
                "largest_issuer_share_of_positive_pnl": max((max(0., x) for x in by_issuer.values()), default=0)/positive if positive else None,
                "top_positive_issuer": max(by_issuer, key=by_issuer.get) if positive else None,
                "year_block_uncertainty": bootstrap_portfolio(daily, (date.fromisoformat(end)-date.fromisoformat(start)).days/365.25) if usable and trades else None},
            "annual": annual, "start": start, "end": end}


def replay(candidates, key, policy, account, sessions, store, evidence, start, end, *, drop_issuer=None, cost_multiplier=1.):
    rows = copy.deepcopy(candidates)
    for c in rows:
        if not gate(c["snapshot"], key): c["forecast"]["status"] = "fundamental_filter"
        if drop_issuer and c["snapshot"]["issuer"] == drop_issuer: c["forecast"]["status"] = "issuer_concentration_sensitivity"
        for r in c["curve"]:
            r["round_trip"] *= cost_multiplier
            r["uncertainty"] = r.get("uncertainty", 0.)*cost_multiplier
    last = max(i for i, d in enumerate(sessions) if d <= end)
    first = last-policy.sessions+1
    cutoff = sessions[first] if first >= 0 else str(date.fromisoformat(sessions[0])-timedelta(days=1))
    result = simulate(rows, policy, account, sessions, store, evidence, variant="baseline", keep_daily=True,
                      start_day=start, end_day=end, entry_end_day=cutoff, entry_ranking="prior_liquidity")
    return summary(result, account.equity, start, end), result


def selection(cases):
    """A declared participation floor, then chronological robustness; no tiny-DD winner."""
    qualified = []
    for case in cases:
        if case["id"] == "unfiltered": continue
        full = case["windows"]["full"]
        failures = []
        if not full["performance_valid"]: failures.append("unresolved_or_unfunded")
        if full["trades"] < 30 or full["issuers"] < 20 or full["active_years"] < 3: failures.append("insufficient_independent_participation")
        fold_values = [r["performance"].get("calmar_full_period") for r in case["chronological_periods"]]
        if any(v is None for v in fold_values): failures.append("unrankable_period")
        if any(r["trades"] < 5 for r in case["chronological_periods"]): failures.append("sparse_period")
        med = median(fold_values) if all(v is not None for v in fold_values) else None
        if med is None or med <= 0: failures.append("nonpositive_median_period_calmar")
        for r in case["cost_sensitivities"]:
            if not r["performance_valid"] or r["performance"].get("net_pnl", 0) <= 0: failures.append("cost_stress_not_positive")
        concentration = case["without_top_issuer"]
        if not concentration["performance_valid"] or concentration["performance"].get("net_pnl", 0) <= 0: failures.append("top_issuer_dependence")
        case["qualification"] = {"failures": sorted(set(failures)), "median_period_calmar": med,
                                  "qualified": not failures}
        if not failures: qualified.append(case)
    frontier = [c["id"] for c in qualified if not any(
        o["windows"]["full"]["trades"] >= c["windows"]["full"]["trades"] and
        o["qualification"]["median_period_calmar"] >= c["qualification"]["median_period_calmar"] and
        (o["windows"]["full"]["trades"] > c["windows"]["full"]["trades"] or o["qualification"]["median_period_calmar"] > c["qualification"]["median_period_calmar"])
        for o in qualified if o is not c)]
    return {"qualified_policies": [c["id"] for c in qualified], "participation_calmar_frontier": frontier,
            "paper_candidate": max(qualified, key=lambda c: (c["qualification"]["median_period_calmar"], c["windows"]["full"]["trades"]))["id"] if qualified else None,
            "production_policy_changed": False, "historical_results_are_explored": True}


def prepare(source, destination, sources, output):
    _, original, frozen, bindings = bind_inputs(source, destination)
    validate_sources(sources, original)
    events, rejected = repaired_events(original, sources)
    overlay, actions, _ = validated_price_overlay(source, destination, original)
    verified, rejected_market = read_market_evidence(output/"verified_market_data.jsonl")
    store = VerifiedStore(frozen/"prices.sqlite", price_event_universe(original, events, sources), overlay, actions, verified=verified)
    evidence = read_evidence(destination/"local/edge_inputs")
    evidence["borrow"] += public_borrow_history(source, original)
    signature = fingerprint({"sources": sources, "bindings": bindings, "code": {n: digest(Path(__file__).with_name(n)) for n in
        ("fundamental_data.py", "fundamental_study.py", "clean_data_facts.py", "net_edge_evidence.py", "net_edge_study.py")}})
    mappings = read_json(output/"custom_fact_mappings.json", [])
    signature += fingerprint(mappings)
    signature += digest(Path(__file__).parent.parent/"build_short_quant_screen.py")
    cache = output/"prepared.json"
    prepared = read_json(cache, {})
    if prepared.get("signature") == signature:
        snapshots = prepared["snapshots"]
    else:
        snapshots = base_snapshots(events, evidence)
        facts = defaultdict(list)
        documents = [(key, {**meta, "reviewed_tag_mappings": [m for m in mappings if m.get("source_sha256") == meta["source_sha256"]]}) for key, meta in sources["documents"].items()]
        with ProcessPoolExecutor(max_workers=4) as pool:
            for i, (cik, rows) in enumerate(pool.map(extended_document, documents, repeat(output))):
                facts[cik] += rows
                if i % 100 == 0: print("Extended financial extraction", i, "/", len(sources["documents"]), flush=True)
        from .fundamentals import _ssi_modules
        _, screen = _ssi_modules()
        raw_cache = OrderedDict()
        for s in sorted(snapshots.values(), key=lambda s: s["cik"]):
            cik = s["cik"]
            if cik not in raw_cache:
                meta = sources["facts"].get(cik)
                raw = {"cik": cik, "facts": {}}
                if meta:
                    path = Path(meta["path"])
                    if digest(path) != meta["sha256"]: raise ValueError("Company Facts hash changed")
                    raw = read_json(path)
                    if not raw.get("cik"):
                        proof = read_json(path.with_name(path.name+".identity.json"), {})
                        if proof.get("companyfacts_sha256") != meta["sha256"] or str(proof.get("cik", "")).lstrip("0") != cik: raise ValueError("Missing Company Facts identity proof")
                        raw = {**raw, "cik": cik}
                raw_cache[cik] = raw
                if len(raw_cache) > 8: raw_cache.popitem(last=False)
            enrich(s, raw_cache[cik], facts[cik], screen)
        write_public_json(cache, {"signature": signature, "snapshots": snapshots})
    return snapshots, store, evidence, bindings, {"rejected_actions": dict(Counter(r["reason"] for r in rejected)),
        "financial_status": dict(Counter(s["fundamental"]["status"] for s in snapshots.values())),
        "reported_scores": sum(s["screen_rating"] is not None for s in snapshots.values()),
        "cash_distress_routes": sum(s.get("cash_distress_route", False) for s in snapshots.values()),
        "completed_full_underwriting_reviews": sum(s["framework"]["complete"] and s["framework"]["thesis_supported"] for s in snapshots.values()),
        "reconciled_financing_records": len(evidence["capitalization"]),
        "actual_locate_approvals": sum(r.get("kind") == "approval" and r.get("approved") is True for r in evidence["borrow"]),
        "observed_broker_fills": sum(r.get("kind") == "fill" and r.get("observed") is True for r in evidence["executions"]),
        "verified_market_observations": sum(len(v) for v in verified.values()), "rejected_market_evidence": rejected_market}


def run(args):
    source, destination = args.source_root.resolve(), args.destination.resolve()
    output = destination/"local/fundamental_v6"
    output.mkdir(parents=True, exist_ok=True)
    sources = read_json(destination/"local/clean_data_v5"/args.sources_snapshot)
    if not sources.get("collection_complete"): raise ValueError("Source collection checkpoint is incomplete")
    # Recover SEC responses that omit a CIK using a separately hash-bound
    # submissions identity. This reuses cached GETs and exact SEC former names.
    sec = SecSources(source, destination, fetch=args.fetch_financials, maximum=500)
    events, _ = repaired_events(bind_inputs(source, destination)[1], sources)
    for cik in sorted({str(int(e["cik"])) for e in events if e.get("cik")} - sources["facts"].keys()):
        meta = sec.companyfacts(cik)
        if meta: sources["facts"][cik] = meta
    sources["requests_this_run"] += sec.client.requests
    sources["uncached_sources_pending"] = sorted(set(sources.get("uncached_sources_pending", [])) | sec.pending_urls)
    sources["network_status"] = dict(Counter(r["status"] for r in sec.audit))
    write_public_json(output/"used_sources.json", sources)
    reference = read_json(destination/"clean_data_research.json")
    policy, account = StudyPolicy(**reference["policy"]), Account(**reference["account"])
    plan = {"schema_version": "shorts_fundamental_plan.v1", "declared_at": datetime.now(timezone.utc).isoformat(),
        "policies": POLICIES, "policy": asdict(policy), "account": asdict(account), "chronological_periods": FOLDS,
        "selection": "30 trades, 20 issuers, three active years; at least five trades per chronological period; positive median period Calmar, all cost stresses and leave-top-issuer profit",
        "source_sha256": fingerprint(sources), "cost_sensitivities": ["double_borrow", "double_slippage", "one_billed_day"],
        "entry_ranking": "prior_liquidity", "payoff_forecast": "none", "matured_entry_cutoff": "end minus nine trading sessions, independent of realized exits",
        "alternative_route": "Fresh cash; TTM and latest-quarter runway each at most one year; operating loss; reported debt maturity within twelve months greater than cash. No financing passage qualifies by itself.",
        "data_cost_usd": 0, "production_policy_changed": False}
    plan["code_sha256"] = {name: digest(Path(__file__).with_name(name)) for name in
        ("fundamental_data.py", "fundamental_prices.py", "fundamental_study.py", "net_edge_study.py", "net_edge_v3.py", "clean_data_facts.py", "clean_data_sources.py", "portfolio_research.py", "net_edge_evidence.py", "net_edge_clock.py", "calmar_research.py", "coverage_data.py", "clean_data_research.py")}
    plan["shared_screen_sha256"] = digest(Path(__file__).parent.parent/"build_short_quant_screen.py")
    write_public_json(output/"plan.json", plan)
    snapshots, store, evidence, bindings, coverage = prepare(source, destination, sources, output)
    costs = cost_observations(source, read_json(source/"local/net_edge_v2/snapshots.json"))
    sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))
    prices, price_coverage = collect_prices(snapshots, store, policy, sessions, output, fetch=args.fetch_prices)
    for ticker, rows in prices.items():
        old = store.prices(ticker)
        store.cache[ticker] = dict(sorted({**rows, **old}.items()))
    for s in snapshots.values():
        before = store.prior(s["database_ticker"], datetime.fromisoformat(s["known_at"]).astimezone(NY).date().isoformat())
        s["price"] = before[-1]["close"] if before and days_between(before[-1]["date"], s["known_at"][:10]) <= 10 else None
        s["prior_dollar_adv"] = sum(r["close"]*r["volume"] for r in before if r.get("volume") is not None)/20 if before else None
    coverage["prioritized_price_recovery"] = price_coverage
    outcomes = make_outcomes(snapshots, store, policy, sessions, END)
    candidates = [{"snapshot": s, "outcome": outcomes[k], "forecast": fixed_cost_plan(s, policy),
                   "curve": cost_curve({**s, "price": outcomes[k].get("entry_price") or s["price"]}, costs, policy)} for k, s in snapshots.items()]
    cases, journals = [], {}
    for key, label in POLICIES.items():
        case = {"id": key, "label": label, "windows": {}}
        for period, start in (("full", START), ("recent", RECENT)):
            row, result = replay(candidates, key, policy, account, sessions, store, evidence, start, END)
            write_public_json(output/(key+"_"+period+".json"), result)
            case["windows"][period] = row
            journals[key, period] = {r["key"]: r for r in result["journal"]}
        case["chronological_periods"] = [replay(candidates, key, policy, account, sessions, store, evidence, start, end)[0] for start, end in FOLDS]
        case["cost_sensitivities"] = []
        for name in plan["cost_sensitivities"]:
            changed, e, cs = copy.deepcopy(candidates), copy.deepcopy(evidence), 1.
            p = replace(policy, minimum_billed_days=1) if name == "one_billed_day" else policy
            if name == "double_borrow":
                p = replace(policy, assumed_annual_borrow=policy.assumed_annual_borrow*2)
                for r in e["borrow"]:
                    if "annual_rate" in r: r["annual_rate"] *= 2
                for c in changed:
                    if c["snapshot"].get("announcement_borrow"): c["snapshot"]["announcement_borrow"]["annual_rate"] *= 2
            if name == "double_slippage": cs = 2.
            row, _ = replay(changed, key, p, account, sessions, store, e, START, END, cost_multiplier=cs)
            case["cost_sensitivities"].append({"scenario": name, **row})
        issuer = case["windows"]["full"]["risk"]["top_positive_issuer"]
        case["without_top_issuer"] = replay(candidates, key, policy, account, sessions, store, evidence, START, END, drop_issuer=issuer)[0]
        cases.append(case)
        print(key, [(p, r["trades"], r["performance"].get("calmar_full_period"), r["unresolved"]) for p, r in case["windows"].items()], flush=True)
    selection_result = selection(cases)
    queue = []
    for k, s in snapshots.items():
        journal = {key: {period: journals[key, period].get(k, {}).get("reason", "outside_entry_window") for period in ("full", "recent")} for key in POLICIES}
        queue.append({"key": k, "ticker": s["ticker"], "issuer": s["issuer"], "known_at": s["known_at"],
                      "score": s["screen_rating"], "financials": s["fundamental"], "policies": {key: gate(s, key) for key in POLICIES},
                      "decisions": journal, "source_url": s.get("source_url")})
    queue.sort(key=lambda r: (not (r["score"] is not None and r["score"] >= 60 and r["decisions"]["score60"]["recent"] in {"entry_price_unavailable", "minimum_order_or_capacity"}), r["ticker"], r["known_at"]))
    parts = publish_parts(queue, destination/"fundamental_packets", "data/shorts_fundamental_packets/", size=25, schema="shorts_fundamental_packet_part.v1")
    doc = {"schema_version": "shorts_fundamental_study.v1", "built_at": datetime.now(timezone.utc).isoformat(),
           "research_only": True, "authority": "none", "production_policy_changed": False, "data_cost_usd": 0,
           "code_sha256": {name: digest(Path(__file__).with_name(name)) for name in
               ("fundamental_data.py", "fundamental_prices.py", "fundamental_study.py", "net_edge_study.py", "net_edge_v3.py", "clean_data_facts.py", "clean_data_sources.py")},
           "plan": plan, "plan_sha256": fingerprint(plan), "bindings": bindings, "coverage": coverage, "cases": cases,
           "selection": selection_result, "packets": parts,
           "acquisition": {k: sources.get(k) for k in ("requests_this_run", "network_status", "uncached_sources_pending", "access_stopped")},
           "original_estimator_reference": reference["stages"][-2],
           "forward_validation": {"starts": next(d for d in sessions if d > datetime.now(timezone.utc).astimezone(NY).date().isoformat()),
                "policy_hash": fingerprint(plan), "status": "frozen_for_future_paper_observations", "completed_forward_trades": 0},
           "limits": ["All historical periods were explored. Chronological replays and resampling are diagnostics, not untouched forward validation.",
               "Unfiltered includes missing financial scores and has no payoff-donor gate. Twenty prior other issuers are still required for the execution-cost proxy.",
               "Full-horizon carry reserve and liquidity ranking are common to all four policies; counts differ from the original forecast-dependent 49/89 reference.",
               "Prices are daily-bar conditional executions. Historical locates, fills and complete halt/SSR execution evidence remain unavailable.",
               "The joint daily-high drawdown is a conservative bound, not a measured simultaneous liquidation or actual stop fill.",
               "Unresolved admitted liabilities or margin breaches suppress account performance. Closed-trade statistics exclude those outstanding liabilities and are incomplete when performance is invalid.",
               "Annual statements older than 200 days remain diagnostics until intervening disclosures are reconciled. Custom tags require an explicit source-reviewed mapping.",
               "No unverified volume increases the primary capacity estimate. No policy or capital approval is changed."]}
    if any(digest(Path(__file__).with_name(name)) != value for name, value in plan["code_sha256"].items()):
        raise ValueError("Research implementation changed during the replay; rerun before publication")
    if digest(Path(__file__).parent.parent/"build_short_quant_screen.py") != plan["shared_screen_sha256"]:
        raise ValueError("Financial scoring thresholds changed during the replay")
    # Publish aggregate derived statistics and cited financial evidence only.
    if args.publish: write_public_json(destination/"fundamental_research.json", doc)
    write_public_json(output/"summary.json", doc)
    store.connection.close()
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--sources-snapshot", default="sources-v6.json")
    parser.add_argument("--fetch-prices", action="store_true")
    parser.add_argument("--fetch-financials", action="store_true")
    parser.add_argument("--publish", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__": main()
