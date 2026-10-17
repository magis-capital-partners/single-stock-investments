"""Declared sizing and three-year extension of the explored-history search.

Two local workers read the existing price store; no network or broker is used.
The total +200% squeeze-loss budget stays at 2% of the research account.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from .calmar_research import (END, FLOORS, START, bind_inputs, identifier, neighborhood,
                             path_metrics, ranked, search_policies, summarize)
from .calmar_validation import evaluate, robust_failures
from .ledger import read_json, write_json
from .net_edge_evidence import digest
from .net_edge_study import PriceStore, cost_curve, cost_observations, public_borrow_history, read_evidence, simulate
from .net_edge_v3 import Account, StudyPolicy

RECENT = "2023-10-14"
RISKS = (.005, .01, .02)
_context = None


def model_id(policy, variant, risk):
    return identifier(policy, variant)+(f"_risk{round(risk*10000)}" if risk != RISKS[0] else "")


def summarize_window(result, policy, variant, account, start):
    row = summarize(result, policy, variant, account.equity)
    if start == RECENT and result["performance_valid"]:
        row.update(path_metrics(result["daily_equity_curve"], account.equity, RECENT, END))
    row["id"] = model_id(policy, variant, account.name_stress_budget)
    row["account"] = asdict(account)
    row["start"], row["end"] = start, END
    return row


def extended_neighborhood(row, rows):
    risk = row["account"]["name_stress_budget"]
    same = [r for r in rows if r["account"]["name_stress_budget"] == risk]
    base = neighborhood(row, same)
    extra = [r for r in rows if r["variant"] == row["variant"] and r["policy"] == row["policy"]
             and abs(RISKS.index(r["account"]["name_stress_budget"])-RISKS.index(risk)) == 1]
    ids = base["ids"]+[r["id"] for r in extra]
    by_id = {r["id"]: r for r in rows}
    values = sorted(by_id[k]["calmar"] for k in ids if by_id[k].get("calmar") is not None)
    i = len(values)//2
    return {"ids": ids, "tested_neighbors": len(ids), "rankable_neighbors": len(values),
            "positive_neighbors": sum(v > 0 for v in values),
            "median_calmar": (values[i] if len(values) % 2 else (values[i-1]+values[i])/2) if values else None}


def initialize(source, root, output):
    global _context
    source, root, output = Path(source), Path(root), Path(output)
    snapshots, events, frozen, _ = bind_inputs(source, root)
    snapshots = {k: s for k, s in snapshots.items() if s["screen_rating"] is not None}
    from .universe_study import trading_calendar
    sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))
    evidence = read_evidence(root/"local/edge_inputs")
    evidence["borrow"] += public_borrow_history(source, events)
    settings = read_json(root/"net_edge_profiles.json")
    primary = next(r for r in settings["accounts"] if r["id"] == settings["primary_account"])
    _context = {"snapshots": snapshots, "sessions": sessions, "store": PriceStore(frozen/"prices.sqlite", events),
                "evidence": evidence, "account": Account(**primary["account"]), "output": output,
                "costs": cost_observations(source, read_json(source/"local/net_edge_v2/snapshots.json")), "curves": {}}


def candidates_for(policy):
    ctx = _context
    bundle = read_json(ctx["output"]/"groups"/(policy.fingerprint()+".json"))
    candidates = []
    for key, snapshot in ctx["snapshots"].items():
        f, outcome = bundle["forecasts"][key], bundle["outcomes"][key]
        cache_key = policy.entry, key
        if cache_key not in ctx["curves"] and f["status"] == "estimated":
            ctx["curves"][cache_key] = cost_curve({**snapshot, "price": outcome.get("entry_price") or snapshot["price"]}, ctx["costs"], policy)
        candidates.append({"snapshot": snapshot, "forecast": f, "outcome": outcome, "curve": ctx["curves"].get(cache_key, [])})
    return candidates


def run_group(policy_dict):
    ctx = _context
    policy = StudyPolicy(**policy_dict)
    candidates = candidates_for(policy)
    full, recent = [], []
    for risk in RISKS:
        account = replace(ctx["account"], name_stress_budget=risk)
        for floor in FLOORS:
            p = replace(policy, fundamental_floor=floor)
            for variant in ("fundamental", "net_edge"):
                for start, rows, suffix in ((START, full, "full"), (RECENT, recent, "recent")):
                    name = model_id(p, variant, risk)
                    path = ctx["output"]/"extended_cases"/(name+"_"+suffix+".json")
                    if start == START and risk == RISKS[0]:
                        path = ctx["output"]/"cases"/(name+".json")
                    if path.exists(): result = read_json(path)
                    else:
                        result = simulate(candidates, p, account, ctx["sessions"], ctx["store"], ctx["evidence"],
                                          variant=variant, keep_daily=True, start_day=start)
                        write_json(path, result)
                    rows.append(summarize_window(result, p, variant, account, start))
    return full, recent


def stress_case(row):
    ctx = _context
    p, account = StudyPolicy(**row["policy"]), Account(**row["account"])
    candidates = candidates_for(p)
    full, recent = {}, {}
    for label, multiple, slip, minimum in (("double_borrow", 2., 1., p.minimum_billed_days),
             ("sixfold_borrow", 6., 1., p.minimum_billed_days), ("double_slippage", 1., 2., p.minimum_billed_days),
             ("one_billed_day", 1., 1., max(1, p.minimum_billed_days))):
        scenario, evidence = copy.deepcopy(candidates), copy.deepcopy(ctx["evidence"])
        for record in evidence["borrow"]:
            if record.get("annual_rate") is not None: record["annual_rate"] *= multiple
            if record.get("fee_per_share") is not None: record["fee_per_share"] *= multiple
        for c in scenario:
            quote = c["snapshot"].get("announcement_borrow")
            if quote: quote["annual_rate"] *= multiple
            for level in c["curve"]:
                level["round_trip"] *= slip
                level["uncertainty"] *= slip
        trial = replace(p, assumed_annual_borrow=p.assumed_annual_borrow*multiple, minimum_billed_days=minimum)
        full[label] = evaluate(scenario, trial, account, ctx["sessions"], ctx["store"], evidence, row["variant"])
        recent[label] = evaluate(scenario, trial, account, ctx["sessions"], ctx["store"], evidence, row["variant"], start=RECENT)
    periods = [evaluate(candidates, p, account, ctx["sessions"], ctx["store"], ctx["evidence"], row["variant"], start=a, end=b)
               for a, b in ((START, "2021-12-31"), ("2022-01-01", "2024-12-31"), ("2025-01-01", END))]
    recent_periods = [evaluate(candidates, p, account, ctx["sessions"], ctx["store"], ctx["evidence"], row["variant"],
                              start=f"{year}-01-01", end=min(END, f"{year}-12-31")) for year in (2024, 2025, 2026)]
    return row["id"], {"cost_scenarios": full, "separate_periods": periods,
                       "recent_cost_scenarios": recent, "recent_separate_periods": recent_periods,
                       "other_capital_scenarios": {}}


def run(args):
    root = Path(__file__).resolve().parents[2]/"data/reverse_splits"
    output = root/"local/calmar_search"
    original = read_json(output/"summary.json")
    base = StudyPolicy(**original["plan"]["policy_groups_detail"][0])
    policies = [asdict(p) for p in search_policies(base)]
    plan = {"declared_at": datetime.now(timezone.utc).isoformat(), "code_sha256": digest(Path(__file__)),
            "original_summary_sha256": digest(output/"summary.json"), "risks": list(RISKS),
            "account_sleeve_stress_budget": .02, "primary_equity": 50000.,
            "additional_full_trials": 1280, "recent_trials": 1920, "recent_start": RECENT,
            "recent_basis": "Each parameter set starts flat with $50,000; no inherited positions or capital path.",
            "selection_context": "Sizing and trailing-three-year extension declared after inspecting the first 640 full-history trials. All history remains explored.",
            "finalists": "Top 10 sample-qualified full-period, top 5 sample-qualified recent, top 2 raw full-period, best sample-qualified net-edge full/recent, frozen default; deduplicated.",
            "data_cost_usd": 0, "network_requests": 0}
    key = hashlib.sha256(json.dumps({k: v for k, v in plan.items() if k != "declared_at"}, sort_keys=True).encode()).hexdigest()
    old = read_json(output/"extended_plan.json", {})
    if old and old.get("signature") != key: raise ValueError("Extended search inputs/code changed")
    plan = old or {**plan, "signature": key}
    write_json(output/"extended_plan.json", plan)
    full, recent = [], []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize,
                             initargs=(str(args.source_root), str(root), str(output))) as pool:
        tasks = [pool.submit(run_group, p) for p in policies]
        for number, task in enumerate(as_completed(tasks), 1):
            a, b = task.result(); full.extend(a); recent.extend(b)
            write_json(output/"extended_progress.json", {"groups": number, "total_groups": len(policies),
                                                        "full_trials": len(full), "recent_trials": len(recent)})
            print("Extended Calmar", number, "/", len(policies), "full", len(full), "recent", len(recent), flush=True)
    full.sort(key=lambda r: r["id"]); recent.sort(key=lambda r: r["id"])
    for rows in (full, recent):
        for row in rows: row["neighborhood"] = extended_neighborhood(row, rows)
    full_rank, recent_rank = ranked(full), ranked(recent)
    qualified, recent_qualified = ranked(full, qualified=True), ranked(recent, qualified=True)
    by_id, by_recent = {r["id"]: r for r in full}, {r["id"]: r for r in recent}
    for row in full: row["last_three_years"] = {k: v for k, v in by_recent[row["id"]].items()
                          if k in {"calmar", "cagr", "max_drawdown", "net_pnl", "trades", "issuers", "sample_qualified"}}
    chosen = [r["id"] for r in qualified[:10]+recent_qualified[:5]+full_rank[:2]]
    chosen += [r["id"] for r in qualified if r["variant"] == "net_edge"][:1]
    chosen += [r["id"] for r in recent_qualified if r["variant"] == "net_edge"][:1]
    chosen += ["announcement_next_open_5_p10_s20_f60_net_edge"]
    chosen = list(dict.fromkeys(chosen))
    write_json(output/"extended_results_before_validation.json", {"plan": plan, "cases": full, "recent_cases": recent,
                "finalists": chosen})
    checks = {}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize,
                             initargs=(str(args.source_root), str(root), str(output))) as pool:
        tasks = [pool.submit(stress_case, by_id[k]) for k in chosen]
        for number, task in enumerate(as_completed(tasks), 1):
            case_id, result = task.result()
            failed = robust_failures(by_id[case_id], result)
            result.update(robustness_failures=failed, passes_declared_robustness_checks=not failed)
            recent_row = {**by_recent[case_id], "last_three_years": by_recent[case_id]}
            recent_failed = robust_failures(recent_row, {"cost_scenarios": result["recent_cost_scenarios"],
                                                        "separate_periods": result["recent_separate_periods"]})
            result.update(recent_robustness_failures=recent_failed, recent_passes_declared_checks=not recent_failed)
            checks[case_id] = result
            write_json(output/"extended_validation_progress.json", checks)
            print("Extended validation", number, "/", len(chosen), case_id, failed, "recent", recent_failed, flush=True)
    passing = [r["id"] for r in qualified if checks.get(r["id"], {}).get("passes_declared_robustness_checks")]
    recent_passing = [r["id"] for r in recent_qualified if checks.get(r["id"], {}).get("recent_passes_declared_checks")]
    original.update(cases=full, recent_cases=recent, extension={"plan": plan},
        ranked_ids=[r["id"] for r in full_rank], qualified_ranked_ids=[r["id"] for r in qualified],
        recent_ranked_ids=[r["id"] for r in recent_rank], recent_qualified_ranked_ids=[r["id"] for r in recent_qualified],
        raw_winner=full_rank[0]["id"] if full_rank else None,
        sample_qualified_winner=qualified[0]["id"] if qualified else None,
        validation={"plan": {"finalists": chosen, "extension_plan_sha256": digest(output/"extended_plan.json")},
                    "cases": checks, "passing_tested_ids": passing, "paper_candidate": passing[0] if passing else None,
                    "recent_passing_tested_ids": recent_passing, "recent_paper_candidate": recent_passing[0] if recent_passing else None,
                    "status": "paper_research_candidate_only" if passing else "no_robust_full_history_candidate"},
        published_at=datetime.now(timezone.utc).isoformat())
    original["coverage"].update(trials=len(full), portfolio_replays=len(full)+len(recent), rankable=len(full_rank),
        sample_qualified=len(qualified), positive_qualified=sum(r["calmar"] > 0 for r in qualified),
        recent_sample_qualified=len(recent_qualified), recent_positive_qualified=sum(r["calmar"] > 0 for r in recent_qualified))
    write_json(output/"extended_summary.json", original)
    if args.publish:
        # The expanded matrix exceeds the Pages 20 MiB staging limit when
        # pretty-printed. Compact serialization retains every result and hash.
        (root/"calmar_research.json").write_text(json.dumps(original, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    print("EXTENSION COMPLETE", original["coverage"], "full", passing[:1], "recent", recent_passing[:1], flush=True)
    return original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--publish", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__": main()
