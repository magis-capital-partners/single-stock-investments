"""Offline, predeclared Calmar search over the frozen RSI-3.0 research inputs.

No download, paid API, broker connection, live trade or production-policy edit.
Results remain explored-history diagnostics, including all unsuccessful trials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from itertools import product
from pathlib import Path

from .ledger import read_json, write_json
from .net_edge_evidence import digest
from .net_edge_study import (PriceStore, collect_catalogue, cost_curve,
                             cost_observations, donor_rows, make_outcomes,
                             public_borrow_history, read_evidence, simulate)
from .net_edge_v3 import Account, StudyPolicy, payoff_forecast

START, END = "2018-05-01", "2026-10-13"
MIN_TRADES, MIN_ISSUERS, MIN_ACTIVE_YEARS = 30, 20, 3
FLOORS = (40., 60., 80., 90.)


def search_policies(base):
    """The complete grid is declared before the first additional trial runs."""
    for entry, hold in product(("announcement_next_open", "post_split_next_open"), (1, 5, 10, 20)):
        yield replace(base, entry=entry, sessions=hold, bracket=False)
        for profit, stop in product((.05, .10, .20), (.10, .20, .30)):
            yield replace(base, entry=entry, sessions=hold, bracket=True, profit_take=profit, stop_loss=stop)


def identifier(policy, variant):
    return (f"{policy.entry}_{policy.sessions}_"+
            (f"p{round(policy.profit_take*100)}_s{round(policy.stop_loss*100)}" if policy.bracket else "time")+
            f"_f{round(policy.fundamental_floor)}_{variant}")


def path_metrics(curve, initial, start, end):
    if initial <= 0 or not math.isfinite(initial) or start >= end or not curve:
        raise ValueError("A positive initial equity, dated interval and daily path are required")
    days = [row["date"] for row in curve]
    if days != sorted(set(days)) or days[0] < start or days[-1] > end:
        raise ValueError("Equity dates must be unique, ordered and inside the evaluation interval")
    values = [row["equity"] for row in curve]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        return {"status": "nonpositive_or_invalid_equity", "cagr": None, "max_drawdown": None, "calmar": None}
    years = (date.fromisoformat(end)-date.fromisoformat(start)).days/365.25
    cagr = (values[-1]/initial)**(1/years)-1
    peak, drawdown = initial, 0.
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1-value/peak)
    return {"status": "estimated" if drawdown > 0 else "zero_drawdown_unranked",
            "cagr": cagr, "max_drawdown": drawdown,
            "calmar": cagr/drawdown if drawdown > 0 else None,
            "total_return": values[-1]/initial-1, "net_pnl": values[-1]-initial,
            "initial_equity": initial, "ending_equity": values[-1], "years": years}


def period_metrics(curve, initial, start, end):
    before = [r for r in curve if r["date"] < start]
    rows = [r for r in curve if start <= r["date"] <= end]
    if not rows: return None
    return path_metrics(rows, before[-1]["equity"] if before else initial, start, end)


def summarize(result, policy, variant, initial):
    reasons = []
    if not result["performance_valid"]: reasons.append("unresolved_or_unfunded")
    trades = result["trade_ledger"]
    issuers = len({r["issuer"] for r in trades})
    years = len({r["entry_day"][:4] for r in trades})
    if len(trades) < MIN_TRADES: reasons.append("fewer_than_30_trades")
    if issuers < MIN_ISSUERS: reasons.append("fewer_than_20_issuers")
    if years < MIN_ACTIVE_YEARS: reasons.append("fewer_than_3_active_years")
    if result["performance_valid"]:
        stats = path_metrics(result["daily_equity_curve"], initial, START, END)
    else:
        stats = {"status": "unresolved_or_unfunded", "cagr": None, "max_drawdown": None, "calmar": None}
    if not trades or stats["calmar"] is None: reasons.append("no_rankable_trading_path")
    positive = sum(max(0., r["net_pnl"]) for r in trades)
    by_issuer = Counter()
    for row in trades: by_issuer[row["issuer"]] += row["net_pnl"]
    concentration = max((max(0., v) for v in by_issuer.values()), default=0)/positive if positive else None
    return {"id": identifier(policy, variant), "policy": asdict(policy), "variant": variant,
            **stats, "trades": len(trades), "issuers": issuers, "active_years": years,
            "sample_qualified": not reasons, "qualification_failures": reasons,
            "largest_issuer_fraction_of_positive_pnl": concentration,
            "costs": result["costs"], "funding_valid": result["funding_valid"],
            "unresolved_admitted_names": result["unresolved_admitted_names"],
            "open_positions": result["open_positions"], "skipped": result["skipped"],
            "yearly": [{"year": year, **(period_metrics(result["daily_equity_curve"], initial,
                          max(START, f"{year}-01-01"), min(END, f"{year}-12-31")) or {"status": "no_observations"})}
                       for year in range(2018, 2027)] if result["performance_valid"] else [],
            "last_three_years": period_metrics(result["daily_equity_curve"], initial, "2023-10-14", END)
                                  if result["performance_valid"] else None}


def ranked(rows, *, qualified=False):
    return sorted((r for r in rows if r.get("calmar") is not None and (not qualified or r["sample_qualified"])),
                  key=lambda r: (-r["calmar"], -r["trades"], r["id"]))


def neighborhood(row, rows):
    """One adjacent change in the predeclared grid; no selected ranges removed."""
    axes = {"sessions": (1, 5, 10, 20), "fundamental_floor": FLOORS,
            "profit_take": (.05, .10, .20), "stop_loss": (.10, .20, .30)}
    neighbors = []
    for other in rows:
        if other["variant"] != row["variant"]: continue
        a, b = row["policy"], other["policy"]
        if a["entry"] != b["entry"] or a["bracket"] != b["bracket"]: continue
        different = [key for key in axes if a[key] != b[key]]
        if len(different) != 1: continue
        key = different[0]
        if not a["bracket"] and key in {"profit_take", "stop_loss"}: continue
        if abs(axes[key].index(a[key])-axes[key].index(b[key])) == 1: neighbors.append(other)
    values = sorted(r["calmar"] for r in neighbors if r.get("calmar") is not None)
    middle = len(values)//2
    median = (values[middle] if len(values) % 2 else (values[middle-1]+values[middle])/2) if values else None
    return {"tested_neighbors": len(neighbors), "rankable_neighbors": len(values),
            "positive_neighbors": sum(v > 0 for v in values), "median_calmar": median,
            "ids": [r["id"] for r in neighbors]}


def bind_inputs(source, destination):
    local = destination/"local/net_edge_v3"
    manifest = read_json(destination/"net_edge_manifest_v3.json")
    snapshots = local/"frozen_snapshots.json"
    if digest(snapshots) != manifest["snapshots_sha256"]: raise ValueError("Frozen snapshot hash changed")
    if digest(destination/"net_edge_research_v3.json") != manifest["summary_sha256"]:
        raise ValueError("Frozen research summary changed")
    if digest(destination/"net_edge_profiles.json") != manifest["profile_sha256"]:
        raise ValueError("Original research profile changed")
    events, frozen = collect_catalogue(source)
    if digest(frozen/"manifest.json") != manifest["source_manifest_sha256"]:
        raise ValueError("Frozen source manifest changed")
    for relative, expected in manifest["execution_inputs"].items():
        if digest(source/relative) != expected: raise ValueError("Frozen cost input changed: "+relative)
    return read_json(snapshots), events, frozen, {"snapshot_sha256": digest(snapshots),
            "research_summary_sha256": manifest["summary_sha256"],
            "research_manifest_sha256": digest(destination/"net_edge_manifest_v3.json"),
            "source_manifest_sha256": manifest["source_manifest_sha256"],
            "execution_inputs": manifest["execution_inputs"]}


def run(args):
    destination = Path(__file__).resolve().parents[2]/"data/reverse_splits"
    output = destination/"local/calmar_search"
    output.mkdir(parents=True, exist_ok=True)
    settings = read_json(destination/"net_edge_profiles.json")
    base = StudyPolicy(**settings["policy"])
    primary = next(r for r in settings["accounts"] if r["id"] == settings["primary_account"])
    account = Account(**primary["account"])
    snapshots, events, frozen, bindings = bind_inputs(args.source_root.resolve(), destination)
    all_count = len(snapshots)
    snapshots = {k: s for k, s in snapshots.items() if s["screen_rating"] is not None}
    policies = list(search_policies(base))
    code = {name: digest(Path(__file__).with_name(name)) for name in
            ("calmar_research.py", "net_edge_study.py", "net_edge_v3.py", "net_edge.py")}
    plan = {"declared_at": datetime.now(timezone.utc).isoformat(), "data_cost_usd": 0,
            "network_requests": 0, "period": [START, END], "primary_account": primary,
            "policy_groups": len(policies), "portfolio_trials": len(policies)*len(FLOORS)*2,
            "floors": list(FLOORS), "policy_groups_detail": [asdict(p) for p in policies],
            "variants": ["fundamental", "net_edge"], "bindings": bindings, "code": code,
            "qualification": {"minimum_trades": MIN_TRADES, "minimum_issuers": MIN_ISSUERS,
                              "minimum_active_years": MIN_ACTIVE_YEARS},
            "selection": "Highest full-period calendar CAGR / absolute daily maximum drawdown; no-trade/zero-drawdown paths never rank.",
            "validation": "Previously explored history; calendar-year/last-three-year/parameter-neighborhood diagnostics are not untouched tests."}
    signature = hashlib.sha256(json.dumps({k: v for k, v in plan.items() if k != "declared_at"}, sort_keys=True).encode()).hexdigest()
    prior = read_json(output/"plan.json", {})
    if prior and prior.get("signature") != signature: raise ValueError("Search inputs/code changed; use a new output directory or preserve and move the old run")
    plan = prior or {**plan, "signature": signature}
    write_json(output/"plan.json", plan)
    from .universe_study import trading_calendar
    sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))
    store = PriceStore(frozen/"prices.sqlite", events)
    evidence = read_evidence(destination/"local/edge_inputs")
    evidence["borrow"] += public_borrow_history(args.source_root, events)
    old = read_json(args.source_root/"local/net_edge_v2/snapshots.json")
    costs = cost_observations(args.source_root, old)
    curves, rows, repro = {}, [], []
    source_summary = read_json(destination/"net_edge_research_v3.json")
    started = time.monotonic()
    for number, policy in enumerate(policies, 1):
        group_path = output/"groups"/(policy.fingerprint()+".json")
        if group_path.exists():
            bundle = read_json(group_path)
            forecasts, outcomes = bundle["forecasts"], bundle["outcomes"]
        else:
            outcomes = make_outcomes(snapshots, store, policy, sessions, END)
            donors = donor_rows(snapshots, outcomes, policy)
            forecasts = {k: payoff_forecast(s, donors, policy) for k, s in snapshots.items()}
            write_json(group_path, {"forecasts": forecasts, "outcomes": outcomes})
        for k, snapshot in snapshots.items():
            key = policy.entry, k
            if key not in curves and forecasts[k]["status"] == "estimated":
                curves[key] = cost_curve({**snapshot, "price": outcomes[k].get("entry_price") or snapshot["price"]}, costs, base)
        candidates = [{"snapshot": s, "outcome": outcomes[k], "forecast": forecasts[k],
                       "curve": curves.get((policy.entry, k), [])} for k, s in snapshots.items()]
        for floor, variant in product(FLOORS, ("fundamental", "net_edge")):
            p = replace(policy, fundamental_floor=floor)
            case_id = identifier(p, variant)
            path = output/"cases"/(case_id+".json")
            if path.exists():
                result = read_json(path)
            else:
                result = simulate(candidates, p, account, sessions, store, evidence, variant=variant, keep_daily=True)
                write_json(path, result)
            row = summarize(result, p, variant, account.equity)
            rows.append(row)
            if floor == base.fundamental_floor and (not p.bracket or (p.profit_take == base.profit_take and p.stop_loss == base.stop_loss)):
                original = next(r for r in source_summary["cases"] if r["entry"] == p.entry and r["sessions"] == p.sessions and r["bracket"] == p.bracket and r["account_id"] == primary["id"] and r["variant"] == variant)
                matched = original["trades"] == result["trades"] and original["performance_valid"] == result["performance_valid"] and (original["net_pnl"] is None or math.isclose(original["net_pnl"], result["net_pnl"], abs_tol=1e-7))
                repro.append({"case": case_id, "matched": matched})
                if not matched: raise ValueError("Original published case did not reproduce: "+case_id)
        write_json(output/"progress.json", {"completed_groups": number, "total_groups": len(policies), "trials": len(rows), "elapsed_seconds": time.monotonic()-started})
        print("Calmar search", number, "/", len(policies), "trials", len(rows), "seconds", round(time.monotonic()-started), flush=True)
    store.connection.close()
    for row in rows: row["neighborhood"] = neighborhood(row, rows)
    raw, qualified = ranked(rows), ranked(rows, qualified=True)
    summary = {"schema_version": "shorts_calmar_research.v1", "built_at": datetime.now(timezone.utc).isoformat(),
               "research_only": True, "authority": "none", "data_cost_usd": 0, "network_requests": 0,
               "plan": plan, "coverage": {"dated_snapshots": all_count, "numerically_rated": len(snapshots),
                   "trials": len(rows), "rankable": len(raw), "sample_qualified": len(qualified),
                   "positive_qualified": sum(r["calmar"] > 0 for r in qualified)},
               "original_reproduction": repro, "raw_winner": raw[0]["id"] if raw else None,
               "sample_qualified_winner": qualified[0]["id"] if qualified else None,
               "production_policy_changed": False, "strict_approvals_added": False,
               "ranked_ids": [r["id"] for r in raw], "qualified_ranked_ids": [r["id"] for r in qualified],
               "cases": rows,
               "limits": ["Historical optimization is not an untouched or prospective test.",
                          "Sample qualification is a minimum evidence screen, not statistical proof.",
                          "Quoted daily prices and modeled costs do not establish executable fills or account borrow approvals.",
                          "Annual borrow remains a 50% sensitivity in the primary search; borrowing costs are not optimized downward.",
                          "Full-period Calmar includes idle capital; terminal incurred settlement charges are reserved.",
                          "Strict evidence remains incomplete. No live recommendation or production-policy replacement is made."]}
    write_json(output/"summary.json", summary)
    print("COMPLETE", summary["coverage"], "raw", summary["raw_winner"], "qualified", summary["sample_qualified_winner"], flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    return run(parser.parse_args(argv))


if __name__ == "__main__": main()
