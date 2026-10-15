"""Build RSI-2.0 from frozen local evidence only; never downloads market data.

Run: python -m reverse_splits.net_edge_research --publish
from _system/scripts. The published output contains derived results, not quotes.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from .capital_risk import margin
from .config import load_config
from .execution_research import sweep
from .expansion import digest
from .fundamentals import FundamentalBridge
from .ledger import read_json, write_json
from .net_edge import (
    FRAMEWORKS,
    VERSION,
    EdgePolicy,
    available,
    carry,
    conviction,
    dilution,
    distribution,
    forecast,
    moment,
    size_fraction,
    stress_fraction,
)
from .portfolio_research import (
    available_book,
    commission,
    load_inputs,
    path_marks,
    performance,
)
from .portfolio_status import at as status_at
from .universe_study import trading_calendar

RUN_ID = "20261013T224003582762Z"


def load_reviews(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    return rows


def snapshots(cfg, rows, events, source, reviews):
    bridge = FundamentalBridge(cfg)
    conn = sqlite3.connect((source / "prices.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    result = {}
    for i, row in enumerate(rows):
        event = events[row["event_id"]]
        clock = moment(event.get("available_at"))
        if clock is None or clock >= moment(row["opened"]):
            result[row["key"]] = {"status": "announcement_clock_unavailable_before_entry"}
            continue
        # The bridge filters facts by filing availability before extracting them.
        # Date-only filings on the announcement day are conservatively omitted.
        asof = event["available_at"][:10]
        cik = event.get("cik") or (row["issuer"].split("/")[-1] if row["issuer"].startswith("cik/") else None)
        fundamental = bridge.score(row["ticker"], cik, asof)
        # Current SIC/profile must not decide a historical rating. The strict
        # case separately needs a dated operating-company profile review.
        numeric = [k for k, signal in fundamental.get("signals", {}).items()
                   if signal.get("value") is not None and signal.get("score") is not None]
        weights = sum(bridge.screen.FUNDAMENTAL_SIGNALS[k][1] for k in numeric) if bridge.screen else 0
        fundamental = {**fundamental, "score": round(100 * sum(
            fundamental["signals"][k]["score"] * bridge.screen.FUNDAMENTAL_SIGNALS[k][1] for k in numeric) / weights, 1)
            if len(numeric) >= 3 and weights else None,
            "historical_eligible": fundamental["source"] == "raw_companyfacts" and len(numeric) >= 3}
        records = [r for r in reviews if r.get("event_id") == row["event_id"] and available(r, clock)]
        review = max(records, key=lambda r: r["known_at"], default={})
        c = conviction(fundamental, review.get("frameworks", []), clock)
        d = dilution(review.get("dilution"), clock)
        # Use a nominal price available BEFORE the announcement; post-split
        # projection uses only the ratio in the dated primary schedule.
        prior = conn.execute("SELECT p.date,p.close FROM prices_daily p JOIN price_provenance v USING(ticker,date) "
                             "WHERE ticker=? AND p.date<? AND v.nominal=1 AND p.close>0 ORDER BY p.date DESC LIMIT 1",
                             (row["ticker"], asof)).fetchone()
        price = prior[1] / event["ratio"] if prior and event.get("ratio", 0) > 0 else None
        if prior and (date.fromisoformat(asof) - date.fromisoformat(prior[0])).days > 10:
            price = None
        liquidity = conn.execute("SELECT p.close*p.volume FROM prices_daily p JOIN price_provenance v USING(ticker,date) "
                                 "WHERE ticker=? AND p.date<? AND v.nominal=1 AND p.close>0 AND p.volume>=0 "
                                 "ORDER BY p.date DESC LIMIT 20", (row["ticker"], asof)).fetchall()
        prior_dollar_adv = sum(v[0] for v in liquidity) / 20 if liquidity else None
        locate = review.get("borrow", {})
        approved = bool(locate.get("approved") and locate.get("reference") and locate.get("issuer") == row["issuer"]
                        and available(locate, clock) and moment(locate.get("known_at"))
                        and 0 <= (clock - moment(locate["known_at"])).total_seconds() <= 4 * 3600
                        and isinstance(locate.get("annual_rate"), (int, float)) and locate["annual_rate"] >= 0
                        and math.isfinite(locate["annual_rate"]) and locate.get("shares", 0) > 0)
        # A forecast quote at announcement is not an executable locate days
        # later. Execution evidence is a distinct, time-filtered veto.
        entry_clock = moment(row["opened"])
        entry_locates = [r.get("entry_borrow", {}) for r in reviews if r.get("event_id") == row["event_id"]
                         and available(r, entry_clock)]
        entry_locates = [b for b in entry_locates if b.get("approved") and b.get("reference")
                         and b.get("issuer") == row["issuer"] and moment(b.get("known_at"))
                         and 0 <= (entry_clock - moment(b["known_at"])).total_seconds() <= 4 * 3600
                         and isinstance(b.get("annual_rate"), (int, float)) and math.isfinite(b["annual_rate"])
                         and b["annual_rate"] >= 0 and b.get("shares", 0) > 0]
        entry_borrow = max(entry_locates, key=lambda b: b["known_at"], default=None)
        result[row["key"]] = {"status": "frozen", "known_at": event["available_at"], "as_of": asof,
            "issuer": row["issuer"], "ticker": row["ticker"], "entry_day": row["date"],
            "ratio": event["ratio"], "price": price, "price_date": prior[0] if prior else None,
            "prior_dollar_adv": prior_dollar_adv,
            "screen_rating": c["screen_rating"], "conviction": c,
            "full_rating": c["rating"],
            "dilution": d["per_share_value_change"], "dilution_detail": d,
            "borrow": locate if approved else None, "historical_locate": approved,
            "entry_borrow": entry_borrow,
            "identity_reconciled": bool(review.get("identity_reconciled")),
            "operating_profile_verified": bool(review.get("operating_profile") == "operating"
                and review.get("operating_profile_source_url") and review.get("operating_profile_locator")),
            "source_url": event.get("source_url"), "fundamental_source": fundamental["source"],
            "fundamental_period": fundamental.get("latest_period"),
            "fundamental_signals": {k: v for k, v in fundamental.get("signals", {}).items() if v.get("value") is not None},
            "fundamental_evidence": fundamental.get("evidence", [])}
        if i % 100 == 0:
            print("Announcement snapshots", i + 1, "/", len(rows), flush=True)
    conn.close()
    return result


def exit_point(row, path, points, policy):
    entry = points[row["key"]]["1/entry"]
    first = moment(entry["fill_at"]).timestamp()
    close = moment(points[row["key"]]["1/close"]["decision_at"]).timestamp()
    deadline = min(close, moment(entry["decision_at"]).timestamp() + policy.max_minutes * 60)
    ref = entry["reference_mid"]
    trigger = ((path["mid"] <= ref * (1 - policy.profit_take)) | (path["mid"] >= ref * (1 + policy.stop_loss)))
    hits = np.flatnonzero((path["ts"] > first) & (path["ts"] <= deadline) & trigger & policy.use_bracket)
    at = float(path["ts"][hits[0]]) if len(hits) else deadline
    reason = "profit_take" if len(hits) and path["mid"][hits[0]] <= ref * (1 - policy.profit_take) else "stop_loss" if len(hits) else "time"
    desired = at + .1
    idx = min(len(path["ts"]) - 1, max(0, int(np.searchsorted(path["ts"], desired, side="right") - 1)))
    tradable = path["tradable_quote"]
    if not tradable[idx] or status_at(path["status_history"], "is_trading", desired) == "N":
        later = np.flatnonzero((path["ts"] >= desired) & tradable)
        if len(later):
            idx = int(later[0])
            desired = float(path["ts"][idx]) + .1
    book = available_book(path, desired)
    return {"exit_at": datetime.fromtimestamp(desired, timezone.utc).isoformat(),
            "exit_mid": float(path["mid"][idx]), "exit_book": book, "reason": reason,
            "queued_seconds": max(0., desired - at - .1), "missing_exit_quote": book is None,
            "hold_minutes": (desired - first) / 60}


def outcomes(rows, books, points, index, minute, status, root, policies):
    out = {name: {} for name in policies}
    for i, row in enumerate(rows):
        path = path_marks(root, row, index, minute, status.get(row["key"], {}))
        entry = points[row["key"]]["1/entry"]
        mid = entry["reference_mid"]
        entrybook = books.get(row["key"], {}).get("1/entry")
        decisionbook = books.get(row["key"], {}).get("1/decision")
        stamp = moment(entry["fill_at"]).timestamp()
        decision_stamp = moment(entry["decision_at"]).timestamp()
        hist = path["status_history"]
        blocked = any(status_at(hist, "is_trading", t) == "N" or status_at(hist, "is_short_sell_restricted", t) == "Y"
                      for t in (stamp, decision_stamp))
        for name, policy in policies.items():
            result = exit_point(row, path, points, policy)
            result.update(entry_mid=mid, entry_book=entrybook, decision_book=decisionbook,
                          entry_at=entry["fill_at"], entry_blocked=blocked,
                          entry_observed=bool(entry["reference_observed"]),
                          gross_return=(mid - result["exit_mid"]) / mid,
                          calendar_hold_days=(moment(result["exit_at"]).date() - moment(entry["fill_at"]).date()).days)
            out[name][row["key"]] = result
        if i % 150 == 0:
            print("Exit paths", i + 1, "/", len(rows), flush=True)
    return out


def payoff_donors(rows, frozen, outcomes, policy):
    donors = []
    for row in rows:
        s, o = frozen[row["key"]], outcomes[row["key"]]
        if s.get("screen_rating") is None or not o["entry_observed"]:
            continue
        costs = {}
        for dollars in (125, 500, 1250):
            q = max(1, math.floor(dollars / o["entry_mid"]))
            sell = sweep(o["entry_book"], "bid", q) if o["entry_book"] else None
            buy = sweep(o["exit_book"], "ask", q) if o["exit_book"] else None
            costs[dollars] = ((o["entry_mid"] - sell + buy - o["exit_mid"]) / o["entry_mid"]
                             if sell is not None and buy is not None else None)
        donors.append({"issuer": row["issuer"], "screen_rating": s["screen_rating"], "ratio": s["ratio"],
                       "full_rating": s.get("full_rating"),
                       "dilution": s["dilution"], "policy_hash": policy.fingerprint(),
                       "announcement_price": s.get("price"), "prior_dollar_adv": s.get("prior_dollar_adv"),
                       **{k: o[k] for k in ("gross_return", "exit_at", "hold_minutes", "calendar_hold_days")},
                       "hold_sessions": 0,
                       "costs": costs})
    return donors


def estimate(snapshot, donors, policy, sessions, notional=125.):
    if not snapshot.get("price") or snapshot.get("screen_rating") is None:
        return {"status": "announcement_price_or_fundamentals_missing", "net_edge": None, "donors": 0}
    size_bucket = next((d for d in (125, 500, 1250) if d >= notional), 1250)
    prior = [d for d in donors if d["issuer"] != snapshot["issuer"] and moment(d["exit_at"]) < moment(snapshot["known_at"])
             and d["costs"][size_bucket] is not None and d.get("announcement_price")
             and d.get("prior_dollar_adv") and snapshot.get("prior_dollar_adv")]
    # One latest observation per issuer for the cost forecast too.
    unique = {d["issuer"]: d for d in sorted(prior, key=lambda d: d["exit_at"])}
    selected = sorted(unique.values(), key=lambda d: (
        abs(math.log(d["announcement_price"] / snapshot["price"]))
        + abs(math.log(d["prior_dollar_adv"] / snapshot["prior_dollar_adv"])), d["issuer"]))[:policy.max_donors]
    if len(selected) < policy.min_donors:
        return {"status": "insufficient_prior_cost_issuers", "net_edge": None, "donors": len(selected)}
    slippage = sum(d["costs"][size_bucket] for d in selected) / len(selected)
    q = max(1, math.floor(notional / snapshot["price"]))
    comm = 2 * commission(q, snapshot["price"]) / (q * snapshot["price"])
    rate = snapshot["borrow"]["annual_rate"] if snapshot.get("borrow") else policy.assumed_annual_borrow
    result = forecast(snapshot, donors, policy, snapshot["price"], rate, sessions, slippage, comm)
    if result.get("net_edge") is not None:
        result["stress_borrow"] = (result["expected_billed_days"] * math.ceil(snapshot["price"] * 3 * 1.02)
                                   * rate * 3 / policy.borrow_day_basis / snapshot["price"])
    result.update(annual_borrow=rate, borrow_basis="dated_approved_locate" if snapshot.get("borrow") else "assumed_rate",
                  cost_donors=len(selected), latest_cost_exit=max(d["exit_at"] for d in selected),
                  forecast_order_notional=notional, cost_size_bucket=size_bucket)
    return result


def fill_price(book, side, q, mid, cost):
    if book:
        observed = sweep(book, side, q)
        if observed is not None:
            return observed, False
    # Missing executions are retained with a labeled prior-only cost estimate.
    return mid * (1 + cost if side == "ask" else 1 - min(cost, .95)), True


def replay(rows, frozen, outcomes, estimates, policy, sessions, calendar, variant, initial=50000.):
    nav = initial
    daily, trades, journal = [], [], []
    skips = Counter()
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    for day in calendar:
        before, used_margin, used_stress, issuers, admitted = nav, 0., 0., set(), []
        candidates = sorted(by_day.get(day, []), key=lambda r: (-(estimates[r["key"]].get("net_edge") or -1)
                            if variant in {"net_edge", "strict"} else -(r.get("dollar_adv") or 0), r["key"]))
        for r in candidates:
            s, o, e = frozen[r["key"]], outcomes[r["key"]], estimates[r["key"]]
            reason = None
            if s.get("status") != "frozen": reason = s["status"]
            elif o["entry_blocked"]: reason = "observed_halt_or_SSR"
            elif len(admitted) >= policy.max_names: reason = "maximum_names"
            elif r["issuer"] in issuers: reason = "issuer_already_open"
            elif e.get("net_edge") is None: reason = e["status"]
            elif variant != "baseline" and (s.get("screen_rating") is None or s["screen_rating"] < policy.fundamental_floor): reason = "fundamental_filter"
            elif variant in {"net_edge", "strict"} and s["conviction"]["framework"]["contradicted"]: reason = "contradicted_framework"
            elif variant == "strict" and not s["conviction"]["framework"]["complete"]: reason = "incomplete_dated_framework"
            elif variant == "strict" and not s["historical_locate"]: reason = "historical_locate_missing"
            elif variant == "strict" and not s.get("entry_borrow"): reason = "fresh_entry_locate_missing"
            elif variant == "strict" and not s["identity_reconciled"]: reason = "historical_identity_unreconciled"
            elif variant == "strict" and not s.get("operating_profile_verified"): reason = "historical_profile_unverified"
            elif variant == "strict" and s.get("dilution") is None: reason = "dilution_unreconciled"
            elif variant in {"net_edge", "strict"} and e["net_edge"] <= policy.minimum_net_edge: reason = "nonpositive_net_edge"
            fraction = (size_fraction(e, s["conviction"].get("rating") or s.get("screen_rating") or 0, policy)
                        if not reason and variant in {"net_edge", "strict"} else min(policy.max_name_fraction, policy.max_name_stress_loss / stress_fraction(e, policy)))
            q = max(0, math.floor(max(0, before) * fraction / o["entry_mid"]))
            if not reason:
                if not r.get("adv"): reason = "prior_volume_unavailable"
                else: q = min(q, math.floor(r["adv"] * policy.participation))
            if not reason:
                q = min(q, math.floor(max(0., .6 * before - used_margin) / margin(1, o["entry_mid"], 1.)),
                        math.floor(max(0., policy.max_sleeve_stress_loss * before - used_stress) / (stress_fraction(e, policy) * o["entry_mid"])))
                if s.get("entry_borrow"): q = min(q, int(s["entry_borrow"]["shares"]))
                if o["decision_book"]: q = min(q, sum(size for _, size in o["decision_book"]["bid_levels"]))
                if q * o["entry_mid"] < 100: reason = "minimum_order_or_capacity"
            if not reason and variant in {"net_edge", "strict"}:
                # Actual order size may make commission minima consume the edge.
                actual_comm = 2 * commission(q, o["entry_mid"]) / (q * o["entry_mid"])
                if e["net_edge"] + e["expected_commission"] - actual_comm <= policy.minimum_net_edge:
                    reason = "order_cost_consumes_edge"
                if not reason:
                    b = o["decision_book"]
                    quoted = sweep(b, "bid", q) if b else None
                    quoted_cost = (b["mid"] - quoted) / b["mid"] if quoted is not None else e["expected_slippage"] / 2
                    rate = s["entry_borrow"]["annual_rate"] if s.get("entry_borrow") else e["annual_borrow"]
                    updated_borrow = carry(day, day, o["entry_mid"], rate, sessions,
                                           minimum_days=policy.minimum_billed_days, basis=policy.borrow_day_basis)["fraction"]
                    if e["gross_edge"] - quoted_cost - e["expected_slippage"] / 2 - actual_comm - updated_borrow <= policy.minimum_net_edge:
                        reason = "entry_cost_consumes_edge"
            if reason:
                skips[reason] += 1
                journal.append({"key": r["key"], "ticker": r["ticker"], "date": day, "reason": reason, "shares": 0})
                continue
            sell, ei = fill_price(o["entry_book"], "bid", q, o["entry_mid"], e["expected_slippage"] / 2)
            buy, xi = fill_price(o["exit_book"], "ask", q, o["exit_mid"], e["expected_slippage"] / 2)
            rate = s["entry_borrow"]["annual_rate"] if s.get("entry_borrow") else e["annual_borrow"]
            loan = carry(day, o["exit_at"][:10], o["entry_mid"], rate, sessions,
                         minimum_days=policy.minimum_billed_days, basis=policy.borrow_day_basis)
            comm = commission(q, sell) + commission(q, buy)
            gross = q * o["entry_mid"]
            net = q * (sell - buy) - comm - loan["fraction"] * gross
            t = {"key": r["key"], "ticker": r["ticker"], "issuer": r["issuer"], "date": day,
                 "shares": q, "gross": gross, "net": net, "net_return": net / gross,
                 "borrow": loan["fraction"] * gross, "commission": comm,
                 "slippage": q * ((o["entry_mid"] - sell) + (buy - o["exit_mid"])),
                 "gross_pnl": q * (o["entry_mid"] - o["exit_mid"]),
                 "exit_reason": o["reason"], "hold_minutes": o["hold_minutes"],
                 "estimated_fill": ei or xi, "missing_exit_quote": o["missing_exit_quote"],
                 "expected_net_edge": e["net_edge"], "size_fraction": gross / before,
                 "expected_borrow": e["expected_borrow"] * gross}
            admitted.append(t)
            trades.append(t)
            journal.append({"key": r["key"], "ticker": r["ticker"], "date": day, "reason": "included", "shares": q})
            used_margin += margin(q, o["entry_mid"], 1.)
            used_stress += gross * stress_fraction(e, policy)
            issuers.add(r["issuer"])
        nav += sum(t["net"] for t in admitted)
        daily.append({"date": day, "equity": nav, "pnl": nav - before, "trades": len(admitted)})
    p = performance(daily, initial, calendar[0], calendar[-1])
    return {"variant": variant, "trades": len(trades), "issuers": len({t["issuer"] for t in trades}),
            "portfolio": p, "skipped": dict(skips),
            "costs": {key: sum(t[key] for t in trades) for key in ("borrow", "commission", "slippage", "expected_borrow")},
            "trade_distribution": distribution([t["net_return"] for t in trades]),
            "gross_pnl": sum(t["gross_pnl"] for t in trades),
            "summed_gross": sum(t["gross"] for t in trades),
            "estimated_fills": sum(t["estimated_fill"] for t in trades),
            "missing_exit_quotes": sum(t["missing_exit_quote"] for t in trades),
            "equity_curve": [{"date": calendar[0], "equity": initial}] + [{"date": d["date"], "equity": d["equity"]} for i, d in enumerate(daily) if i % 21 == 0 or d["trades"] or i == len(daily) - 1],
            "journal": journal, "trade_ledger": trades}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--reviews", type=str)
    args = parser.parse_args(argv)
    cfg = load_config()
    root = cfg.local_dir / "portfolio_research" / (RUN_ID + "__portfolio_v1")
    source = cfg.local_dir / "expansion" / "expansion_v2" / "runs" / RUN_ID
    output = cfg.local_dir / "net_edge_v2"
    output.mkdir(parents=True, exist_ok=True)
    rows, books, points, index, minute, _states, _current = load_inputs(cfg, root)
    events = {}
    for part in read_json(source / "event_outcomes.parts.json", {})["files"]:
        for line in (source / part["path"]).read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            events[event["event_id"]] = event
    status = read_json(root / "status_history.local.json", {})["histories"]
    reviews_path = cfg.data_dir / "net_edge_reviews.jsonl" if not args.reviews else Path(args.reviews)
    frozen = snapshots(cfg, rows, events, source, load_reviews(reviews_path))
    policies = {"bracket": EdgePolicy(), "time60": EdgePolicy(use_bracket=False, max_minutes=60),
                "close": EdgePolicy(use_bracket=False)}
    paths = outcomes(rows, books, points, index, minute, status, root, policies)
    sessions = trading_calendar("2018-04-01", "2026-11-15")
    calendar = [d for d in sessions if "2018-05-01" <= d <= "2026-10-13"]
    cases, audit = [], []
    for name, policy in policies.items():
        for minimum in (0, 1):
            p = replace(policy, minimum_billed_days=minimum)
            donors = payoff_donors(rows, frozen, paths[name], p)
            estimates = {r["key"]: estimate(frozen[r["key"]], donors, p, sessions) for r in rows}
            for variant in ("baseline", "fundamental", "net_edge", "strict"):
                result = replay(rows, frozen, paths[name], estimates, p, sessions, calendar, variant)
                result.update(id=f"{name}_{minimum}d_{variant}", exit=name, minimum_billed_days=minimum,
                              policy=asdict(p), policy_hash=p.fingerprint())
                if name == "bracket" and minimum == 0:
                    write_json(output / (variant + ".json"), result)
                    if variant == "net_edge":
                        decisions = {r["key"]: r for r in result["journal"]}
                        for r in rows:
                            s, e = frozen[r["key"]], estimates[r["key"]]
                            audit.append({"key": r["key"], "ticker": r["ticker"], "date": r["date"],
                                "announcement": s.get("known_at"), "source_url": s.get("source_url"),
                                "screen_rating": s.get("screen_rating"), "conviction": s.get("conviction"),
                                "fundamental_period": s.get("fundamental_period"), "dilution": s.get("dilution_detail"),
                                "historical_locate": s.get("historical_locate", False),
                                "estimate": {k: v for k, v in e.items() if k not in {"net_scenarios", "training_issuers"}},
                                "decision": decisions.get(r["key"])})
                result.pop("journal")
                result.pop("trade_ledger")
                cases.append(result)
                print(result["id"], result["trades"], "net", round(result["portfolio"]["net_pnl"], 2), flush=True)
    coverage = {"events": len(rows), "dated_snapshots": sum(s.get("status") == "frozen" for s in frozen.values()),
                "numeric_conviction": sum(s.get("screen_rating") is not None for s in frozen.values()),
                "full_framework_conviction": sum(s.get("conviction", {}).get("rating") is not None for s in frozen.values()),
                "reconciled_dilution": sum(s.get("dilution") is not None for s in frozen.values()),
                "dated_approved_locates": sum(s.get("historical_locate", False) for s in frozen.values())}
    publication = {"schema_version": "shorts_net_edge.v2", "version": VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(), "research_only": True, "authority": "none",
        "primary_case": "bracket_0d_net_edge", "coverage": coverage,
        "frameworks": list(FRAMEWORKS), "cases": cases, "names": sorted(audit, key=lambda r: r["date"], reverse=True),
        "definitions": {
            "conviction": "0–100 evidence rating: 60% filing-based deterioration and 40% documented framework support. Complete dated framework reviews are required for full conviction; the screen alone is provisional and is never a probability.",
            "gross_edge": "Mean same-policy short return from up to 60 other issuers whose trades had closed before this announcement. Nearest frozen fundamental score and announced ratio; full framework ratings and economic dilution matched only where documented for both issuers. Minimum 20 prior issuers.",
            "net_edge": "Gross expected return minus forecast round-trip spread/depth, commissions and probability-weighted holding-period borrow. All figures are fractions of opening gross exposure; expected cost forecasts use prior completed issuers only.",
            "skewness": "Third standardized central moment of the estimated short-return distribution. Positive values describe a right tail for short P&L. Gain/loss ratio is expected positive payoff divided by expected negative payoff, including their frequencies.",
            "sizing": "Quarter mean/second-moment sizing multiplied by evidence rating, capped at 2.5% notional and 0.5% equity loss under a +200% squeeze with triple-rate carry on triple-price collateral plus costs; then whole shares, 0.1% prior volume, three names, 2% sleeve stress and 60% entry-margin budget. Negative net edge receives zero size. Stops are triggers, not maximum losses.",
            "borrow": "Sum each scenario's settled calendar-day collateral × annual rate / 360, then average scenarios. US collateral is shares × ceil(1.02 × price). T+2 before May 28, 2024; T+1 thereafter. Weekends and exchange holidays enter through settlement dates. Same-day ordinary carry is zero under matched settlement; one billed day is a separate pre-borrow sensitivity. No hourly APR proration.",
            "dilution": "Reverse-split mechanical dilution is zero. Dated issuance, warrants and converts require reconciled share counts and net proceeds to common. Missing financing evidence stays unknown; no automatic dilution return is added to empirical gross edge."},
        "limits": [
            "The frozen sample contains completed and priced splits. It is a conditional replay and cannot establish an announcement-universe strategy; cancelled, failed and unpriced announcements require a separate full-universe cohort.",
            "Current history has no complete dated framework packages or approved historical locates. Full-framework results remain blocked; screen-only cases use explicitly assumed borrowing access and rates.",
            "Announcement time is the existing conservative availability clock. Same-day date-only filings are omitted. Current SEC industry metadata is excluded from numeric ratings; the strict case requires a dated operating-profile review. Security aliases and class identity still need historical reconciliation.",
            "The historical framework and dilution gaps are not filled with today's research. No claimed incremental return from qualitative frameworks or actual dilution exists until dated evidence is imported.",
            "Payoff donors and cost donors contain only earlier exits from other issuers. This history has been explored already; these are walk-forward estimates, not untouched validation or calibrated probabilities.",
            "Only intraday execution paths are replayed: close, 60 minutes, and 10% profit take / 20% adverse trigger / close. Multi-day carry is supported by the accrual engine but multi-day performance is not claimed.",
            "Forecast collateral is held at the announcement's nominal-price projection. One-day realized fee sensitivity uses the entry mark; these are assumptions rather than reconstructed broker invoices. Daily price/rate scenarios are supported by the carry engine.",
            "Missing/depth-limited fills use prior-issuer cost forecasts and remain in P&L. Stops may gap, halts may delay cover, and unobserved covers remain estimated. Closing drawdown omits intraday margin breaches; all results are conditional on funding and eventual cover.",
            "Small risk limits and commission minima can exclude otherwise positive expected-value names. No live capital, orders, or production RSI-1.0 thresholds change."],
        "sources": [
            {"title": "IBKR short-sale costs and settled positions", "url": "https://www.interactivebrokers.com/en/pricing/short-sale-cost.php"},
            {"title": "IBKR collateral and 360-day fee calculation", "url": "https://www.ibkrguides.com/reportingreference/reportguide/borrowfeedetails_default.htm"},
            {"title": "SEC settlement cycle", "url": "https://www.sec.gov/newsroom/press-releases/2024-62"},
            {"title": "SEC reverse stock splits", "url": "https://www.investor.gov/introduction-investing/investing-basics/glossary/reverse-stock-split"}]}
    write_json(output / "snapshots.json", frozen)
    write_json(output / "summary.json", publication)
    manifest = {"schema_version": "shorts_net_edge_manifest.v2", "summary_sha256": digest(output / "summary.json"),
                "source_run_id": RUN_ID, "source_manifest_sha256": digest(source / "manifest.json"),
                "inputs": {name: digest(root / name) for name in ("books.local.json", "points.local.json", "paths.local.json", "status_history.local.json")},
                "reviews_sha256": digest(reviews_path) if reviews_path.exists() else None,
                "snapshots_sha256": digest(output / "snapshots.json"),
                "code": {name: digest(Path(__file__).with_name(name)) for name in ("net_edge.py", "net_edge_research.py", "fundamentals.py")},
                "companyfacts": {str(path.relative_to(cfg.raw_dir)): digest(path)
                    for cik in {events[r['event_id']].get('cik') for r in rows if events[r['event_id']].get('cik')}
                    for path in [cfg.raw_dir / 'companyfacts' / f'CIK{int(cik):010d}.json'] if path.exists()}}
    write_json(output / "manifest.json", manifest)
    if args.publish:
        write_json(cfg.data_dir / "net_edge_research.json", publication)
        write_json(cfg.data_dir / "net_edge_manifest.json", manifest)
    print("Coverage", coverage, flush=True)
    return publication


if __name__ == "__main__":
    main()
