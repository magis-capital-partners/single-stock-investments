"""Cost, capital and separate-period checks of the offline Calmar search.

These checks use already explored history. They never constitute an untouched
holdout, a broker approval, or authority to change production policy.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import hashlib
import json
import math
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .calmar_research import END, START, bind_inputs, path_metrics, ranked
from .ledger import read_json, write_json
from .net_edge_evidence import digest
from .net_edge_study import PriceStore, cost_curve, cost_observations, public_borrow_history, read_evidence, simulate
from .net_edge_v3 import Account, StudyPolicy

PERIODS = ((START, "2021-12-31"), ("2022-01-01", "2024-12-31"), ("2025-01-01", END))


def finalist_ids(summary):
    chosen = summary["qualified_ranked_ids"][:10]+summary["ranked_ids"][:2]
    by_id = {r["id"]: r for r in summary["cases"]}
    chosen += [key for key in summary["qualified_ranked_ids"] if by_id[key]["variant"] == "net_edge"][:1]
    chosen += ["announcement_next_open_5_p10_s20_f60_net_edge"]
    return list(dict.fromkeys(chosen))


def robust_failures(row, checks):
    failed = list(row["qualification_failures"])
    if row.get("calmar") is None or row["calmar"] <= 0: failed.append("no_positive_full_period_calmar")
    if (row.get("largest_issuer_fraction_of_positive_pnl") or 0) > .5:
        failed.append("one_issuer_dominates_positive_pnl")
    recent = row.get("last_three_years") or {}
    if recent.get("cagr") is None or recent["cagr"] <= 0: failed.append("nonpositive_last_three_years")
    near = row["neighborhood"]
    if (not near["rankable_neighbors"] or near["positive_neighbors"]*2 < near["rankable_neighbors"]
            or near["median_calmar"] is None or near["median_calmar"] <= 0):
        failed.append("neighboring_parameters_not_positive")
    for key in ("double_borrow", "double_slippage", "one_billed_day"):
        outcome = checks["cost_scenarios"][key]
        if outcome.get("cagr") is None or outcome["cagr"] <= 0: failed.append(key+"_not_positive")
    if sum((p.get("cagr") or 0) > 0 for p in checks["separate_periods"]) < 2:
        failed.append("fewer_than_two_positive_separate_periods")
    return list(dict.fromkeys(failed))


def evaluate(candidates, policy, account, sessions, store, evidence, variant, *, start=START, end=END):
    cutoff = None
    if end != END:
        last = bisect.bisect_right(sessions, end)-1
        cutoff = sessions[last-policy.sessions+1]
    result = simulate(candidates, policy, account, sessions, store, evidence, variant=variant,
                      keep_daily=True, start_day=start, end_day=end, entry_end_day=cutoff)
    stats = path_metrics(result["daily_equity_curve"], account.equity, start, end) if result["performance_valid"] else {
        "status": "unresolved_or_unfunded", "cagr": None, "calmar": None, "max_drawdown": None}
    return {**stats, "start": start, "end": end, "trades": result["trades"],
            "issuers": len({r["issuer"] for r in result["trade_ledger"]}),
            "funding_valid": result["funding_valid"], "open_positions": result["open_positions"],
            "unresolved_admitted_names": result["unresolved_admitted_names"], "entry_cutoff": cutoff}


def run(args):
    root = Path(__file__).resolve().parents[2]/"data/reverse_splits"
    output = root/"local/calmar_search"
    summary_path = output/"summary.json"
    summary = read_json(summary_path)
    plan = summary["plan"]
    for name, expected in plan["code"].items():
        if digest(Path(__file__).with_name(name)) != expected: raise ValueError("Search code changed before validation: "+name)
    settings = read_json(root/"net_edge_profiles.json")
    primary = next(r for r in settings["accounts"] if r["id"] == settings["primary_account"])
    account = Account(**primary["account"])
    snapshots, events, frozen, bindings = bind_inputs(args.source_root, root)
    if bindings != plan["bindings"]: raise ValueError("Search inputs changed before validation")
    snapshots = {k: s for k, s in snapshots.items() if s["screen_rating"] is not None}
    from .universe_study import trading_calendar
    sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))
    store = PriceStore(frozen/"prices.sqlite", events)
    evidence = read_evidence(root/"local/edge_inputs")
    evidence["borrow"] += public_borrow_history(args.source_root, events)
    costs = cost_observations(args.source_root, read_json(args.source_root/"local/net_edge_v2/snapshots.json"))
    rows = {r["id"]: r for r in summary["cases"]}
    selected = finalist_ids(summary)
    validation_plan = {"declared_at": datetime.now(timezone.utc).isoformat(), "code_sha256": digest(Path(__file__)),
                       "search_summary_sha256": digest(summary_path), "finalists": selected,
                       "source_price_store_sha256": digest(frozen/"prices.sqlite"),
                       "method": "10 highest sample-qualified + 2 highest raw + a qualified net-edge case + frozen default; deduplicated",
                       "periods": list(PERIODS), "cost_scenarios": ["double_borrow", "sixfold_borrow", "double_slippage", "one_billed_day"],
                       "acceptance": "Sample-qualified, positive full/recent return, no issuer supplies over half of positive P&L, positive median neighborhood and >=half positive neighbors, positive doubled borrow/slippage and minimum-one-day billing, >=2 of 3 positive separate periods.",
                       "data_cost_usd": 0, "network_requests": 0}
    write_json(output/"validation_plan.json", validation_plan)
    checks, curves = {}, {}
    for index, case_id in enumerate(selected, 1):
        row = rows[case_id]
        p = StudyPolicy(**row["policy"])
        bundle = read_json(output/"groups"/(p.fingerprint()+".json"))
        candidates = []
        for key, snapshot in snapshots.items():
            f, o = bundle["forecasts"][key], bundle["outcomes"][key]
            cache_key = p.entry, key
            if cache_key not in curves and f["status"] == "estimated":
                curves[cache_key] = cost_curve({**snapshot, "price": o.get("entry_price") or snapshot["price"]}, costs, p)
            candidates.append({"snapshot": snapshot, "forecast": f, "outcome": o, "curve": curves.get(cache_key, [])})
        cost_results = {}
        for label, multiple, slip, minimum in (("double_borrow", 2., 1., p.minimum_billed_days),
                 ("sixfold_borrow", 6., 1., p.minimum_billed_days), ("double_slippage", 1., 2., p.minimum_billed_days),
                 ("one_billed_day", 1., 1., max(1, p.minimum_billed_days))):
            scenario = copy.deepcopy(candidates)
            scenario_evidence = copy.deepcopy(evidence)
            for record in scenario_evidence["borrow"]:
                if record.get("annual_rate") is not None: record["annual_rate"] *= multiple
                if record.get("fee_per_share") is not None: record["fee_per_share"] *= multiple
            for candidate in scenario:
                b = candidate["snapshot"].get("announcement_borrow")
                if b: b["annual_rate"] *= multiple
                for level in candidate["curve"]:
                    level["round_trip"] *= slip
                    level["uncertainty"] *= slip
            cost_results[label] = evaluate(scenario, replace(p, assumed_annual_borrow=p.assumed_annual_borrow*multiple,
                                                            minimum_billed_days=minimum),
                                           account, sessions, store, scenario_evidence, row["variant"])
        separate = [evaluate(candidates, p, account, sessions, store, evidence, row["variant"], start=start, end=end)
                    for start, end in PERIODS]
        capitals = {setting["id"]: evaluate(candidates, p, Account(**setting["account"]), sessions, store,
                                            evidence, row["variant"]) for setting in settings["accounts"] if setting["id"] != primary["id"]}
        result = {"cost_scenarios": cost_results, "separate_periods": separate, "other_capital_scenarios": capitals}
        result["robustness_failures"] = robust_failures(row, result)
        result["passes_declared_robustness_checks"] = not result["robustness_failures"]
        checks[case_id] = result
        write_json(output/"validation_progress.json", checks)
        print("Calmar validation", index, "/", len(selected), case_id, result["robustness_failures"], flush=True)
    store.connection.close()
    passing = [r for r in summary["qualified_ranked_ids"] if checks.get(r, {}).get("passes_declared_robustness_checks")]
    summary["validation"] = {"plan": validation_plan, "cases": checks,
                             "passing_tested_ids": passing,
                             "paper_candidate": passing[0] if passing else None,
                             "status": "paper_research_candidate_only" if passing else "no_robust_candidate_among_tested_finalists"}
    summary["published_at"] = datetime.now(timezone.utc).isoformat()
    write_json(output/"validated_summary.json", summary)
    if args.publish:
        write_json(root/"calmar_research.json", summary)
    print("VALIDATED", summary["validation"]["status"], "candidate", summary["validation"]["paper_candidate"], flush=True)
    return summary


def audit_publication(root, dashboard=None):
    root = Path(root)
    source = root/"calmar_research.json"
    if not source.exists(): return []
    doc = read_json(source)
    errors = []
    if (doc.get("schema_version") != "shorts_calmar_research.v1" or doc.get("data_cost_usd") != 0
            or doc.get("network_requests") != 0 or doc.get("authority") != "none"
            or doc.get("production_policy_changed") is not False or doc.get("strict_approvals_added") is not False):
        errors.append("Calmar research has invalid cost/scope claims")
    plan = doc["plan"]
    payload = {k: v for k, v in plan.items() if k not in {"signature", "declared_at"}}
    if hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() != plan["signature"]:
        errors.append("Calmar declared search plan changed")
    if plan["bindings"]["research_summary_sha256"] != digest(root/"net_edge_research_v3.json"):
        errors.append("Calmar research is bound to a different frozen study")
    cases = doc["cases"]
    extension = doc.get("extension", {}).get("plan")
    total = plan["portfolio_trials"]+(extension["additional_full_trials"] if extension else 0)
    if extension:
        declared = {k: v for k, v in extension.items() if k not in {"signature", "declared_at"}}
        if hashlib.sha256(json.dumps(declared, sort_keys=True).encode()).hexdigest() != extension["signature"]:
            errors.append("Calmar sizing extension plan changed")
        if (extension["risks"] != [.005, .01, .02] or extension["account_sleeve_stress_budget"] != .02
                or len(doc.get("recent_cases", [])) != extension["recent_trials"]):
            errors.append("Calmar sizing/recent-period coverage is invalid")
    if len(cases) != total or len({r["id"] for r in cases}) != len(cases):
        errors.append("Calmar trials are incomplete or duplicated")
    if [r["id"] for r in ranked(cases)] != doc["ranked_ids"] or [r["id"] for r in ranked(cases, qualified=True)] != doc["qualified_ranked_ids"]:
        errors.append("Calmar ranking disagrees with the complete trial set")
    if not doc["original_reproduction"] or not all(r["matched"] for r in doc["original_reproduction"]):
        errors.append("Calmar search did not reproduce the frozen comparisons")
    for row in cases+doc.get("recent_cases", []):
        if row.get("calmar") is not None and (not math.isfinite(row["calmar"]) or not row["trades"]
                or not row.get("max_drawdown") or not math.isclose(row["calmar"], row["cagr"]/row["max_drawdown"])):
            errors.append("Invalid Calmar ratio: "+row["id"])
        if row["sample_qualified"] and (row["trades"] < 30 or row["issuers"] < 20 or row["active_years"] < 3
                                        or row["qualification_failures"]):
            errors.append("Sparse Calmar trial promoted to sample-qualified: "+row["id"])
        if extension and (row["account"]["equity"] != 50000. or row["account"]["sleeve_stress_budget"] != .02
                or row["account"]["name_stress_budget"] not in extension["risks"]
                or row["policy"]["assumed_annual_borrow"] != .5 or row["policy"]["confidence"] != .9):
            errors.append("Calmar extension changed a fixed capital/cost/risk setting")
    passing = []
    by_id = {r["id"]: r for r in cases}
    for key, checks in doc["validation"]["cases"].items():
        failed = robust_failures(by_id[key], checks)
        if failed != checks["robustness_failures"] or checks["passes_declared_robustness_checks"] != (not failed):
            errors.append("Calmar robustness claims disagree with diagnostics: "+key)
        if not failed: passing.append(key)
    expected = [key for key in doc["qualified_ranked_ids"] if key in passing]
    if expected != doc["validation"]["passing_tested_ids"] or doc["validation"]["paper_candidate"] != (expected[0] if expected else None):
        errors.append("Calmar paper candidate does not follow the declared screens")
    if extension:
        recent = doc["recent_cases"]
        if [r["id"] for r in ranked(recent)] != doc["recent_ranked_ids"] or [r["id"] for r in ranked(recent, qualified=True)] != doc["recent_qualified_ranked_ids"]:
            errors.append("Calmar recent-period ranking is inconsistent")
        by_recent = {r["id"]: r for r in recent}
        if set(by_recent) != set(by_id): errors.append("Calmar recent/full grids differ")
        recent_pass = []
        for key, checks in doc["validation"]["cases"].items():
            row = {**by_recent[key], "last_three_years": by_recent[key]}
            failed = robust_failures(row, {"cost_scenarios": checks["recent_cost_scenarios"], "separate_periods": checks["recent_separate_periods"]})
            if failed != checks["recent_robustness_failures"] or checks["recent_passes_declared_checks"] != (not failed):
                errors.append("Calmar recent robustness claims disagree with diagnostics: "+key)
            if not failed: recent_pass.append(key)
        expected = [key for key in doc["recent_qualified_ranked_ids"] if key in recent_pass]
        if expected != doc["validation"]["recent_passing_tested_ids"] or doc["validation"]["recent_paper_candidate"] != (expected[0] if expected else None):
            errors.append("Calmar recent paper candidate does not follow the screens")
    if dashboard:
        target = Path(dashboard)/"shorts_calmar_research.json"
        if not target.exists() or digest(target) != digest(source): errors.append("Dashboard Calmar research differs from source")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__": main()
