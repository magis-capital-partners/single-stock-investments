"""Build RSI-3.0 from the frozen local catalogue, filings, books and daily bars.

python -m reverse_splits.net_edge_study --source-root PATH --publish
No market-data login or broker connection is made. Only --fetch-missing can
download public SEC companyfacts. Unavailable execution/borrow remains explicit.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
from collections import Counter, OrderedDict, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from zoneinfo import ZoneInfo

from .config import load_config
from .ledger import load_jsonl, read_json, write_json
from .net_edge import FRAMEWORKS, moment
from .net_edge_evidence import (capitalization, digest, fetch_missing_companyfacts,
                                filing_rating, prospective_status, validate_import)
from .net_edge_v3 import (VERSION, Account, StudyPolicy, assessment, calibration,
                          calendar_mark, commission, daily_exit, dated_borrow,
                          loan_schedule, maintenance_per_share, payoff_forecast, planning_sessions,
                          size_position, ssr_limit_fill)

RUN_ID = "20261013T224003582762Z"
NY = ZoneInfo("America/New_York")
SIZES = (100, 125, 250, 500, 1000, 2500, 5000, 10000)


def clock(day, hour=16):
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=NY).astimezone(timezone.utc).isoformat()


def history_at(history, field, stamp):
    values = history.get(field, {})
    i = bisect.bisect_right(values.get("ts", []), stamp)-1
    return values.get("value", [])[i] if i >= 0 else None


def sweep(book, side, quantity):
    rest, value = quantity, 0.
    for price, size in book.get(side+"_levels", []):
        part = min(rest, size); value += part*price; rest -= part
        if rest <= 0: return value/quantity
    return None


def collect_catalogue(source):
    root = source/"local/expansion/expansion_v2/runs"/RUN_ID
    index = read_json(root/"event_outcomes.parts.json")
    events = []
    for part in index["files"]:
        path = root/part["path"]
        if digest(path) != part["sha256"]: raise ValueError("Frozen event shard changed")
        events += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return events, root


class PriceStore:
    def __init__(self, database, events):
        self.connection = sqlite3.connect(database.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.cache = {}
        self.actions = defaultdict(set)
        for e in events:
            if e.get("verification") in {"primary_schedule_matched", "structured_corporate_action"} and e.get("ex_date") and e.get("ratio", 0) > 0:
                self.actions[e.get("database_ticker", e.get("ticker"))].add((e["ex_date"], e["ratio"]))

    def prices(self, ticker):
        if ticker not in self.cache:
            rows = self.connection.execute("SELECT p.* FROM prices_daily p JOIN price_provenance v USING(ticker,date) WHERE p.ticker=? AND v.nominal=1 ORDER BY p.date", (ticker,)).fetchall()
            self.cache[ticker] = {r["date"]: dict(r) for r in rows}
        return self.cache[ticker]

    def factor(self, ticker, first, last):
        return math.prod(ratio for day, ratio in self.actions[ticker] if first < day <= last)

    def prior(self, ticker, day):
        rows = [r for d, r in self.prices(ticker).items() if d < day and r.get("close") and r["close"] > 0]
        return rows[-20:]

    def normalized(self, ticker, entry_day, days):
        prices = self.prices(ticker)
        result = []
        for day in days:
            r = prices.get(day, {})
            factor = self.factor(ticker, entry_day, day)
            result.append({"date": day, **{k: r[k]*factor if r.get(k) is not None else None for k in ("open", "high", "low", "close")},
                           "nominal_close": r.get("close"), "share_factor": factor})
        return result


def cost_observations(source, snapshots):
    root = source/"local/portfolio_research"/(RUN_ID+"__portfolio_v1")
    books, points = {}, {}
    for part in (root, root/"repair"):
        books.update(read_json(part/"books.local.json", {})); points.update(read_json(part/"points.local.json", {}))
    result = []
    for key, pairs in books.items():
        s = snapshots.get(key, {})
        b, x = pairs.get("1/entry"), pairs.get("1/close")
        if not b or not x or not s.get("prior_dollar_adv") or not s.get("price"): continue
        costs = {}
        for dollars in SIZES:
            q = max(1, math.ceil(dollars/b["mid"]))
            sell, buy = sweep(b, "bid", q), sweep(x, "ask", q)
            if sell is not None and buy is not None:
                costs[dollars] = max(0., (b["mid"]-sell)/b["mid"]+(buy-x["mid"])/x["mid"])
        result.append({"issuer": s["issuer"], "exit_at": points[key]["1/close"]["fill_at"],
                       "price": b["mid"], "adv": s["prior_dollar_adv"], "costs": costs})
    return result


def cost_curve(snapshot, observations, policy):
    if not snapshot.get("price") or not snapshot.get("prior_dollar_adv"): return []
    prior = {}
    cutoff = moment(snapshot["known_at"])
    for r in sorted(observations, key=lambda r: r["exit_at"]):
        if r["issuer"] != snapshot["issuer"] and moment(r["exit_at"]) < cutoff:
            prior[r["issuer"]] = r
    selected = sorted(prior.values(), key=lambda r: (abs(math.log(r["price"]/snapshot["price"]))+
                                                    abs(math.log(r["adv"]/snapshot["prior_dollar_adv"])), r["issuer"]))[:policy.max_issuers]
    curve = []
    for dollars in SIZES:
        values = [r["costs"][dollars] for r in selected if dollars in r["costs"]]
        if len(values) < policy.min_issuers: continue
        curve.append({"notional": dollars, "round_trip": mean(values), "issuers": len(values),
                      "uncertainty": 1.282*stdev(values)/math.sqrt(len(values)) if len(values) > 1 else 0.,
                      "basis": "prior_other_issuer_displayed_depth_proxy",
                      "latest_exit": max(r["exit_at"] for r in selected if dollars in r["costs"])})
    return curve


def read_evidence(inputs):
    result = {}
    for kind in ("facts", "reviews", "capitalization", "borrow", "executions", "cashflows"):
        path = inputs/(kind+".jsonl")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
        for row in rows: validate_import(row, kind)
        result[kind] = rows
    return result


def build_snapshots(events, store, source, output, evidence):
    from .fundamentals import _ssi_modules
    _extractor, screen = _ssi_modules()
    if screen is None: raise RuntimeError("SSI fundamental thresholds are unavailable")
    cache, raw_hashes, snapshots, gaps = OrderedDict(), {}, {}, Counter()
    reviews, cap = defaultdict(list), defaultdict(list)
    for r in evidence["reviews"]: reviews[r["event_id"]].append(r)
    for r in evidence["capitalization"]: cap[r["event_id"]].append(r)
    overrides = defaultdict(list)
    for r in evidence["facts"]: overrides[r["issuer"]].append(r)
    for i, event in enumerate(sorted(events, key=lambda e: (e.get("issuer", ""), e.get("available_at") or ""))):
        known = moment(event.get("available_at"))
        if known is None:
            gaps["announcement_clock_unverified"] += 1; continue
        if event.get("verification") not in {"primary_schedule_matched", "primary_schedule_only", "structured_corporate_action"}:
            gaps["primary_schedule_unverified"] += 1; continue
        if not isinstance(event.get("ratio"), (int, float)) or event["ratio"] <= 0:
            gaps["split_ratio_unverified"] += 1; continue
        ticker, issuer = event.get("database_ticker", event["ticker"]), event["issuer"]
        cik = str(event.get("cik") or (issuer[4:] if issuer.startswith("cik/") else "")).lstrip("0")
        source_path = source/"local/raw/companyfacts"/f"CIK{int(cik):010d}.json" if cik.isdigit() else None
        new_path = output/"companyfacts"/source_path.name if source_path else None
        path = source_path if source_path and source_path.exists() else new_path
        if path and path.exists():
            if cik not in cache:
                cache[cik] = read_json(path); raw_hashes[path.name] = digest(path)
                if len(cache) > 8: cache.popitem(last=False)
            cache.move_to_end(cik)
            raw = cache[cik]
            identity_path = path.with_name(path.name+".identity.json")
            if raw.get("cik") is None and identity_path.exists():
                identity = read_json(identity_path)
                if str(identity.get("cik")) != cik or identity.get("companyfacts_sha256") != raw_hashes[path.name]:
                    raise ValueError("Cached companyfacts identity binding changed")
                raw_hashes[identity_path.name] = digest(identity_path)
                raw = {**raw, "cik": cik}
            fund = filing_rating(raw, known.isoformat(), screen, overrides=overrides[issuer], expected_cik=cik)
        elif overrides[issuer]:
            fund = filing_rating({"cik": cik, "facts": {}}, known.isoformat(), screen, overrides=overrides[issuer], expected_cik=cik)
        else:
            fund = {"score": None, "status": "raw_companyfacts_missing", "signals": {}, "evidence": []}
        if fund["score"] is None: gaps[fund["status"]] += 1
        before = store.prior(ticker, known.astimezone(NY).date().isoformat())
        price = before[-1]["close"] if before and days_between(before[-1]["date"], known.date().isoformat()) <= 10 else None
        adv = sum(r["close"]*r["volume"] for r in before if r.get("volume") is not None)/20 if before else None
        dated = [r for r in reviews[event["event_id"]]
                 if (r["review_mode"] == "blinded_historical_reconstruction" or moment(r["review_created_at"]) <= known)
                 and any(source_available(x, known) for x in r.get("frameworks", []))]
        review = max(dated, key=lambda r: r["review_created_at"], default={})
        framework = assessment(review.get("frameworks", []), known,
                               selected_mechanisms=review.get("selected_mechanisms", []), vetoes=review.get("vetoes", []))
        capital_rows = [r for r in cap[event["event_id"]] if source_available(r, known)]
        capital = capitalization(max(capital_rows, key=lambda r: r["known_at"], default=None), known.isoformat())
        b = dated_borrow(evidence["borrow"], issuer, known, approval=False, max_age_hours=24.)
        signals = {"numeric:"+k: v["score"] for k, v in fund["signals"].items()}
        snapshots[event["event_id"]] = {"key": event["event_id"], "ticker": event["ticker"], "database_ticker": ticker,
            "issuer": issuer, "cik": cik, "known_at": known.isoformat(), "ratio": event.get("ratio"),
            "screen_rating": fund["score"], "fundamental": fund, "framework": framework,
            "framework_features": {**signals, **framework["features"]},
            "dilution": capital.get("expected_value_change"), "capitalization": capital,
            "price": price, "prior_dollar_adv": adv, "announcement_borrow": b,
            "source_url": event.get("source_url"), "clock_basis": event.get("clock_basis"),
            "conviction_rating": review.get("conviction_rating") if framework["complete"] and framework["thesis_supported"] else None,
            "identity_verified": bool(review.get("identity_reconciled") and source_available(review.get("identity", {}), known) and str(issuer).startswith("cik/")),
            "profile_verified": bool(review.get("operating_profile") == "operating" and source_available(review.get("profile", {}), known)),
            "valuation_verified": bool(source_available(review.get("valuation", {}), known)),
            "catalyst_verified": bool(source_available(review.get("catalyst", {}), known)),
            "review_mode": review.get("review_mode"), "ex_date": event.get("ex_date")}
        if i % 500 == 0: print("Frozen filing snapshots", i, "/", len(events), flush=True)
    return snapshots, dict(gaps), raw_hashes


def source_available(record, cutoff):
    from .net_edge_clock import available
    return bool(record.get("source_url") and record.get("locator") and available(record, cutoff))


def days_between(first, last):
    return (datetime.fromisoformat(last).date()-datetime.fromisoformat(first).date()).days


def entry_day(snapshot, policy, sessions):
    if policy.entry == "post_split_next_open":
        after = snapshot.get("ex_date")
        if not after: return None
    else: after = moment(snapshot["known_at"]).astimezone(NY).date().isoformat()
    pos = bisect.bisect_right(sessions, after)
    return sessions[pos] if pos < len(sessions) else None


def make_outcomes(snapshots, store, policy, sessions, through):
    outcomes = {}
    for key, s in snapshots.items():
        day = entry_day(s, policy, sessions)
        if not day or day > through or moment(s["known_at"]) >= moment(clock(day, 9)):
            outcomes[key] = {"status": "no_future_entry_in_sample"}; continue
        first = store.prices(s["database_ticker"]).get(day, {})
        if not first.get("open") or first["open"] <= 0:
            outcomes[key] = {"status": "entry_price_unavailable", "entry_day": day}; continue
        ix = sessions.index(day)
        path_days = sessions[ix:ix+policy.sessions]
        bars = store.normalized(s["database_ticker"], day, path_days)
        result = daily_exit(bars, first["open"], policy)
        result.update(entry_day=day, entry_price=first["open"], bars=bars)
        before = store.prior(s["database_ticker"], day)
        result["prior_adv"] = sum(r["volume"]*store.factor(s["database_ticker"], r["date"], day) for r in before if r.get("volume") is not None)/20 if before else None
        if result["status"] == "daily_benchmark":
            if result["exit_day"] > through:
                result["status"] = "unresolved_price_path"
            else:
                result["exit_at"] = clock(result["exit_day"])
                before = store.prior(s["database_ticker"], day)
                result["prior_adv"] = sum(r["volume"]*store.factor(s["database_ticker"], r["date"], day) for r in before if r.get("volume") is not None)/20 if before else None
                first_settle = loan_schedule(day, result["exit_day"], first["open"], 0., sessions)["entry_settlement"]
                last_settle = loan_schedule(day, result["exit_day"], first["open"], 0., sessions)["exit_settlement"]
                result["collateral_factors"] = [calendar_mark(result["marks"], (datetime.fromisoformat(first_settle)+timedelta(days=i)).date().isoformat(), first["open"])/first["open"]
                                                 for i in range(max(0, days_between(first_settle, last_settle)))]
        outcomes[key] = result
    return outcomes


def donor_rows(snapshots, outcomes, policy):
    return [{"issuer": s["issuer"], "screen_rating": s["screen_rating"], "ratio": s["ratio"],
             "dilution": s["dilution"], "framework_features": s["framework_features"],
             "policy_hash": policy.fingerprint(), "gross_return": outcomes[k]["gross_return"],
             "exit_at": outcomes[k]["exit_at"], "hold_sessions": outcomes[k]["hold_sessions"],
             "collateral_factors": outcomes[k]["collateral_factors"]}
            for k, s in snapshots.items() if outcomes[k]["status"] == "daily_benchmark" and s["screen_rating"] is not None]


def public_borrow_history(source, events):
    """Map indications only inside a reconciled announcement window; no approvals."""
    mapping = defaultdict(list)
    for e in events:
        if moment(e.get("available_at")) and str(e.get("issuer", "")).startswith("cik/"):
            mapping[e["ticker"]].append(e)
    rows = []
    for path in sorted((source/"borrow_history").glob("*/*.jsonl")):
        for line in path.read_text().splitlines():
            r = json.loads(line)
            known = moment(r.get("as_of"))
            if known is None or r.get("fee_annual_fraction") is None: continue
            eligible = {e["issuer"] for e in mapping[r["ticker"]] if 0 <= (known-moment(e["available_at"])).days <= 60}
            if len(eligible) != 1: continue
            rows.append({"issuer": next(iter(eligible)), "ticker": r["ticker"], "kind": "indication",
                         "known_at": known.isoformat(), "annual_rate": r["fee_annual_fraction"],
                         "shares": r["available_shares"], "source_url": r.get("source_url"),
                         "locator": "public availability snapshot", "approved": False})
    return rows


def realized_loan(candidate, q, rate, sessions, store, evidence, policy):
    s, o = candidate["snapshot"], candidate["outcome"]
    schedule = loan_schedule(o["entry_day"], o["exit_day"], o["entry_price"], rate, sessions,
                             minimum_days=policy.minimum_billed_days, basis=policy.borrow_basis,
                             preborrow_fee_per_share=policy.preborrow_fee_per_share)
    missing = 0
    for row in schedule["days"]:
        mark = calendar_mark(o["marks"], row["date"], o["entry_price"])
        factor = store.factor(s["database_ticker"], o["entry_day"], row["date"])
        # Quantities and prices move inversely through splits; collateral rounds
        # on the nominal security, not on the economic normalized mark.
        nominal = mark/factor
        actual = [r for r in evidence if r.get("kind") == "accrual" and r["issuer"] == s["issuer"] and r.get("value_date") == row["date"]]
        observed = max(actual, key=lambda r: r["known_at"]) if actual else {}
        daily_rate = observed.get("annual_rate", rate)
        missing += not bool(actual)
        row.update(annual_rate=daily_rate, collateral_per_share=factor*math.ceil(nominal*1.02),
                   per_share=factor*observed.get("fee_per_share", math.ceil(nominal*1.02)*daily_rate/policy.borrow_basis),
                   observed_rate=bool(actual))
    schedule["fraction"] = (sum(r["per_share"] for r in schedule["days"])+policy.preborrow_fee_per_share)/o["entry_price"]
    schedule["modeled_rate_days"] = missing
    schedule["total"] = schedule["fraction"]*q*o["entry_price"]
    return schedule


def recalled_outcome(candidate, records):
    """Realized recall exit at the next available session open, never a signal."""
    s, o = candidate["snapshot"], candidate["outcome"]
    for r in sorted((r for r in records if r.get("kind") == "recall" and r["issuer"] == s["issuer"]), key=lambda r: r["known_at"]):
        stamp = moment(r["known_at"])
        entry = moment(clock(o["entry_day"], 9))+timedelta(minutes=30)
        if stamp < entry: continue
        eligible = [b for b in o.get("bars", []) if moment(clock(b["date"], 9))+timedelta(minutes=30) > stamp
                    and b["date"] <= o.get("exit_day", "9999-12-31")]
        if not eligible: continue
        bar = eligible[0]
        if not bar.get("open"):
            return {**candidate, "outcome": {**o, "status": "unresolved_recall_cover", "exit_day": None}}
        result = {**o, "exit_day": bar["date"], "exit_price": bar["open"], "exit_at": clock(bar["date"]),
                  "status": "daily_benchmark", "reason": "borrow_recall_next_open", "gross_return": 1-bar["open"]/o["entry_price"],
                  "marks": [m for m in o.get("marks", []) if m["date"] <= bar["date"]]}
        return {**candidate, "outcome": result}
    return candidate


def simulate(candidates, policy, account, sessions, store, evidence, *, variant,
             keep_daily=False, start_day="2018-05-01", end_day="2026-10-13", entry_end_day=None):
    by_day, positions, pending, ledger, journal, daily = defaultdict(list), [], [], [], [], []
    for c in candidates:
        if c["outcome"].get("entry_day"): by_day[c["outcome"]["entry_day"]].append(c)
    cash, skipped = account.equity, Counter()
    breaches, worst_margin, nav_high, maximum_dd = 0, 0., account.equity, 0.
    unresolved, observed_fills = set(), 0
    calendar = [d for d in sessions if start_day <= d <= end_day]
    if not calendar:
        raise ValueError("Simulation window contains no trading sessions")
    old_day = (datetime.fromisoformat(calendar[0])-timedelta(days=1)).date().isoformat()
    for day in calendar:
        # Return-settlement fees can accrue after the position itself is covered.
        charges = sum(r["amount"] for r in pending if old_day < r["date"] <= day)
        cash -= charges; pending = [r for r in pending if r["date"] > day]
        def open_mark(p):
            bar = next((b for b in p["candidate"]["outcome"]["bars"] if b["date"] == day), None)
            return bar.get("open") if bar and bar.get("open") else p["last_mark"]
        for p in positions: p["last_mark"] = open_mark(p)
        nav = cash-sum(p["shares"]*p["last_mark"] for p in positions)
        def margin(p, mark):
            s, o = p["candidate"]["snapshot"], p["candidate"]["outcome"]
            factor = store.factor(s["database_ticker"], o["entry_day"], day)
            return p["shares"]*factor*maintenance_per_share(mark/factor)
        used_margin = sum(margin(p, p["last_mark"]) for p in positions)
        used_stress = sum(p["shares"]*p["last_mark"]*p["size"]["stress_fraction"] for p in positions)
        day_entries = sorted(by_day.get(day, []) if not entry_end_day or day <= entry_end_day else [],
                             key=lambda c: (-(c["forecast"].get("gross_lower_bound") or -1), c["snapshot"]["key"]))
        for candidate in day_entries:
            s, o, f = candidate["snapshot"], candidate["outcome"], candidate["forecast"]
            reason = None
            # Entry eligibility must never depend on whether a later exit bar exists.
            if not o.get("entry_price"): reason = o["status"]
            elif f["status"] != "estimated": reason = f["status"]
            elif variant != "baseline" and (s.get("screen_rating") is None or s["screen_rating"] < policy.fundamental_floor): reason = "fundamental_filter"
            elif s["framework"]["blocked"]: reason = "documented_thesis_or_tradability_veto"
            elif len(positions) >= account.maximum_names: reason = "maximum_open_names"
            elif s["issuer"] in {p["candidate"]["snapshot"]["issuer"] for p in positions}: reason = "issuer_already_open"
            announce_borrow = s.get("announcement_borrow")
            entry_clock = moment(clock(day, 9))+timedelta(minutes=30)
            indicative = dated_borrow(evidence["borrow"], s["issuer"], entry_clock, approval=False, max_age_hours=24.)
            approval = dated_borrow(evidence["borrow"], s["issuer"], entry_clock, approval=True, max_age_hours=policy.locate_age_hours)
            rate = (indicative or announce_borrow or {}).get("annual_rate", policy.assumed_annual_borrow)
            entry_fill = observed_fill(evidence["executions"], s["key"], policy, "entry", day, entry_clock)
            if not reason and variant == "strict":
                if not s["identity_verified"]: reason = "historical_identity_unreconciled"
                elif not s["profile_verified"]: reason = "operating_profile_unverified"
                elif not s["framework"]["complete"] or not s["framework"]["thesis_supported"]: reason = "applicable_framework_reviews_incomplete"
                elif not s["valuation_verified"] or not s["catalyst_verified"]: reason = "valuation_or_catalyst_missing"
                elif s["dilution"] is None: reason = "financing_scenarios_unreconciled"
                elif not announce_borrow: reason = "announcement_borrow_indication_missing"
                elif not approval: reason = "entry_locate_missing"
                elif not entry_fill: reason = "entry_execution_evidence_missing"
            if not reason and indicative and indicative["shares"] <= 0: reason = "dated_borrow_unavailable"
            if not reason and not approval and any(r.get("kind") == "recall" and r["issuer"] == s["issuer"] and moment(r["known_at"]) <= entry_clock
                and (not indicative or moment(r["known_at"]) >= moment(indicative["known_at"])) for r in evidence["borrow"]):
                reason = "known_borrow_recall"
            result = {"shares": 0, "reason": reason} if reason else size_position(f, candidate["curve"], o["entry_price"], day, rate, sessions, policy, account,
                equity=nav, adv=o.get("prior_adv"), inventory=min(approval["shares"], entry_fill["shares"]) if variant == "strict" and approval and entry_fill else approval.get("shares") if approval else None,
                used_margin=used_margin, used_stress=used_stress, rating=s.get("conviction_rating") if variant == "strict" and s.get("conviction_rating") is not None else s["screen_rating"], mode="net_edge" if variant in {"net_edge", "strict"} else "baseline", carry_cache=candidate.setdefault("carry_cache", {}), calendar_asof=entry_clock.isoformat())
            reason = result["reason"]
            journal.append({"key": s["key"], "ticker": s["ticker"], "date": day, **result})
            if not result["shares"]:
                skipped[reason] += 1; continue
            q = result["shares"]
            candidate = recalled_outcome(candidate, evidence["borrow"])
            o = candidate["outcome"]
            sell = entry_fill["price"] if variant == "strict" else o["entry_price"]*(1-result["expected_slippage"]/2)
            cover = observed_fill(evidence["executions"], s["key"], policy, "cover", o.get("exit_day")) if variant == "strict" else None
            cover_factor = store.factor(s["database_ticker"], day, o["exit_day"]) if o.get("exit_day") else 1.
            resolved = o["status"] == "daily_benchmark" and (variant != "strict" or cover and cover["shares"] >= q*cover_factor)
            buy = (cover["price"]*cover_factor if variant == "strict" else o["exit_price"]*(1+result["expected_slippage"]/2)) if resolved else None
            if not resolved: unresolved.add(s["key"])
            loan = realized_loan(candidate, q, rate, sessions, store, evidence["borrow"], policy) if resolved else {"days": [], "total": None, "modeled_rate_days": 0}
            for row in loan["days"]: pending.append({"date": row["date"], "amount": q*row["per_share"]})
            adjustments = [r for r in evidence.get("cashflows", []) if r["event_id"] == s["key"] and day <= r.get("entitlement_date", r["value_date"]) <= (o.get("exit_day") or "9999-12-31")]
            adjustment = sum(q*r["cost_per_entry_share"] for r in adjustments)
            for r in adjustments:
                if r["value_date"] <= day: cash -= q*r["cost_per_entry_share"]
                else: pending.append({"date": r["value_date"], "amount": q*r["cost_per_entry_share"]})
            cash -= q*policy.preborrow_fee_per_share
            cash += q*sell-commission(q, sell, account)
            positions.append({"candidate": candidate, "shares": q, "sell": sell, "buy": buy, "last_mark": o["entry_price"], "size": result, "loan": loan, "cash_adjustments": adjustment})
            used_margin += result["margin"]; used_stress += result["notional"]*result["stress_fraction"]
            nav = cash-sum(p["shares"]*p["last_mark"] for p in positions)
        # The intraday high is a conservative joint margin check, not an assertion
        # that all independent highs occurred simultaneously.
        adverse = []
        for p in positions:
            bar = next((b for b in p["candidate"]["outcome"]["bars"] if b["date"] == day), None)
            adverse.append(bar.get("high") if bar and bar.get("high") else p["last_mark"])
        stress_nav = cash-sum(p["shares"]*m for p, m in zip(positions, adverse))
        stress_margin = sum(margin(p, m) for p, m in zip(positions, adverse))
        if positions and (stress_nav <= 0 or stress_margin > max(0, stress_nav)):
            breaches += 1
        worst_margin = max(worst_margin, stress_margin/max(stress_nav, 1.))
        still_open = []
        for p in positions:
            o, s = p["candidate"]["outcome"], p["candidate"]["snapshot"]
            bar = next((b for b in o["bars"] if b["date"] == day), None)
            if bar and bar.get("close"): p["last_mark"] = bar["close"]
            if o.get("exit_day") == day and p["buy"] is not None:
                q = p["shares"]
                factor = store.factor(s["database_ticker"], o["entry_day"], day)
                cover_fee = commission(q*factor, p["buy"]/factor, account)
                comm = commission(q, p["sell"], account)+cover_fee
                cash -= q*p["buy"]+cover_fee
                ledger.append({"key": s["key"], "ticker": s["ticker"], "issuer": s["issuer"], "entry_day": o["entry_day"], "exit_day": day,
                               "shares": q, "notional": q*o["entry_price"], "net_pnl": q*(p["sell"]-p["buy"])-comm-p["loan"]["total"]-p["cash_adjustments"],
                               "cash_adjustments": p["cash_adjustments"],
                               "borrow": p["loan"]["total"], "commission": comm, "modeled_rate_days": p["loan"]["modeled_rate_days"],
                               "slippage": q*((o["entry_price"]-p["sell"])+(p["buy"]-o["exit_price"])),
                               "reason": o["reason"], "execution_observed": variant == "strict", "expected_net_edge": p["size"]["net_edge"],
                               "fractional_split_entitlement": not math.isclose(q*store.factor(s["database_ticker"], o["entry_day"], day), round(q*store.factor(s["database_ticker"], o["entry_day"], day)))})
                observed_fills += 2 if variant == "strict" else 0
            else: still_open.append(p)
        positions = still_open
        nav = cash-sum(p["shares"]*p["last_mark"] for p in positions)
        nav_high = max(nav_high, nav); maximum_dd = min(maximum_dd, nav/nav_high-1)
        daily.append({"date": day, "equity": nav, "open_names": len(positions)})
        old_day = day
    # Include already-incurred return-settlement liabilities after the sample end.
    ending = daily[-1]["equity"]-sum(r["amount"] for r in pending)
    valid = not unresolved and not positions and breaches == 0
    result = {"variant": variant, "trades": len(ledger), "net_pnl": ending-account.equity if valid else None, "ending_equity": ending if valid else None,
            "conditional_marked_pnl": ending-account.equity, "performance_valid": valid,
            "unresolved_admitted_names": len(unresolved), "max_drawdown": maximum_dd if valid else None, "margin_stress_breaches": breaches,
            "maximum_joint_high_margin_ratio": worst_margin, "funding_valid": breaches == 0,
            "open_positions": len(positions), "costs": {k: sum(r[k] for r in ledger) for k in ("borrow", "commission", "slippage")},
            "skipped": dict(skipped), "execution_basis": "conditional_daily_bar_and_prior_depth_cost_scenario",
            "observed_fills": observed_fills, "dividend_history_complete": False,
            "equity_curve": [r for i, r in enumerate(daily) if i % 21 == 0 or i == len(daily)-1],
            "journal": journal, "trade_ledger": ledger}
    if keep_daily:
        # Reserve incurred post-cover settlement charges at the window end.
        result["daily_equity_curve"] = [*daily[:-1], {**daily[-1], "equity": ending}]
    return result


def observed_fill(records, event_id, policy, phase, day, decision=None):
    """Policy-bound execution reports. Cover evidence never gates entry."""
    if not day: return None
    eligible = [r for r in records if r.get("kind") == "fill" and r.get("event_id") == event_id
                and r.get("policy_hash") == policy.fingerprint() and r.get("phase") == phase
                and datetime.fromtimestamp(r["timestamp"], NY).date().isoformat() == day
                and r.get("observed") and r.get("compliance_verified")]
    if decision is not None:
        eligible = [r for r in eligible if decision.timestamp() <= r["timestamp"] <= decision.timestamp()+policy.ssr_timeout_seconds
                    and moment(r["known_at"]).timestamp() <= decision.timestamp()+policy.ssr_timeout_seconds]
    return min(eligible, key=lambda r: r["timestamp"], default=None)


def ssr_audit(source, evidence, policy):
    root = source/"local/portfolio_research"/(RUN_ID+"__portfolio_v1")
    points = read_json(root/"points.local.json", {}); points.update(read_json(root/"repair/points.local.json", {}))
    snapshots = read_json(source/"local/net_edge_v2/snapshots.json", {})
    histories = read_json(root/"status_history.local.json", {})["histories"]
    rows, counts = [], Counter()
    records = defaultdict(list)
    for r in evidence["executions"]:
        records[r["issuer"]].append({**r, "known_at": moment(r["known_at"]).timestamp()})
    for key, s in snapshots.items():
        if key not in points: continue
        entry = points[key]["1/entry"]
        t = moment(entry["decision_at"]).timestamp()
        halt, ssr = history_at(histories.get(key, {}), "is_trading", t) == "N", history_at(histories.get(key, {}), "is_short_sell_restricted", t) == "Y"
        reason = "halt" if halt else "ssr_requires_limit" if ssr else "market_entry_policy"
        counts[reason] += 1
        if ssr:
            outcome = ssr_limit_fill(records[s["issuer"]], t, 1, timeout_seconds=policy.ssr_timeout_seconds)
            rows.append({"ticker": s["ticker"], "event_id": key, "status": outcome["status"], "known_at": entry["decision_at"]})
    return {"counts": dict(counts), "limit_replay": dict(Counter(r["status"] for r in rows)), "names": rows,
            "rule": "Verified NBBO, eligible aggressive buy prints, queue depletion, price-test cancellation and a 15-minute timeout. Quotes alone do not fill a short limit."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--fetch-limit", type=int, default=20)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    destination = Path(__file__).resolve().parents[2]/"data/reverse_splits"
    output = destination/"local/net_edge_v3"; output.mkdir(parents=True, exist_ok=True)
    source = args.source_root.resolve()
    settings = read_json(args.profiles or destination/"net_edge_profiles.json")
    policy = StudyPolicy(**settings["policy"])
    code_hashes = {name: digest(Path(__file__).with_name(name)) for name in ("net_edge_study.py", "net_edge_v3.py", "net_edge_evidence.py", "net_edge_clock.py")}
    accounts = {r["id"]: Account(**r["account"]) for r in settings["accounts"]}
    events, frozen = collect_catalogue(source)
    # Exchange calendars are already a local research dependency; this import
    # makes no data-provider call.
    from .universe_study import trading_calendar
    sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))
    store = PriceStore(frozen/"prices.sqlite", events)
    evidence = read_evidence(destination/"local/edge_inputs")
    evidence["borrow"] += public_borrow_history(source, events)
    downloads = read_json(output/"sec_downloads.json", [])
    if args.fetch_missing:
        cfg = load_config()
        old_sample = read_json(source/"local/net_edge_v2/snapshots.json", {})
        ciks = [s.get("issuer", "").removeprefix("cik/") for s in old_sample.values()]
        downloads = fetch_missing_companyfacts(ciks, source/"local/raw/companyfacts", output/"companyfacts", cfg.section("edgar")["user_agent"], limit=args.fetch_limit)
        write_json(output/"sec_downloads.json", downloads)
    snapshots, gaps, raw_hashes = build_snapshots(events, store, source, output, evidence)
    if args.prepare_only:
        write_json(output/"frozen_snapshots.json", snapshots)
        print("Prepared", len(snapshots), "ratings", sum(s["screen_rating"] is not None for s in snapshots.values()), "gaps", gaps, flush=True)
        store.connection.close()
        return snapshots
    old = read_json(source/"local/net_edge_v2/snapshots.json")
    costs = cost_observations(source, old)
    announcement_curves = {k: cost_curve(s, costs, policy) for k, s in snapshots.items() if s["screen_rating"] is not None}
    entry_curves = {}
    cases, primary_names, validation, path_coverage, audit_files = [], [], {}, [], {}
    for entry in ("announcement_next_open", "post_split_next_open"):
        for hold in (1, 5, 10, 20):
            for bracket in (True, False):
                p = replace(policy, entry=entry, sessions=hold, bracket=bracket)
                outcomes = make_outcomes(snapshots, store, p, sessions, "2026-10-13")
                donors = donor_rows(snapshots, outcomes, p)
                forecasts = {k: payoff_forecast(s, donors, p) for k, s in snapshots.items()}
                for k, f in forecasts.items():
                    s = snapshots[k]
                    if f["status"] != "estimated" or not s.get("price"): continue
                    planned = entry_day(s, p, planning_sessions(sessions, s["known_at"]))
                    if not planned: continue
                    curve = announcement_curves[k]
                    rate = (s["announcement_borrow"] or {}).get("annual_rate", p.assumed_annual_borrow)
                    adv = s["prior_dollar_adv"]/s["price"] if s.get("prior_dollar_adv") else None
                    carry_cache = {}
                    f["announcement_plans"] = {account_id: size_position(f, curve, s["price"], planned, rate, sessions, p, account,
                        adv=adv, inventory=None, rating=s["screen_rating"], carry_cache=carry_cache) for account_id, account in accounts.items()}
                    f["announcement_borrow_basis"] = "dated_indication" if s["announcement_borrow"] else "assumed_rate_sensitivity"
                write_json(output/(f"frozen_forecasts_{entry}_{hold}_{'bracket' if bracket else 'time'}.json"), forecasts)
                # Re-price execution costs using information available at entry;
                # the thesis and training cutoff remain frozen at announcement.
                curves = {}
                for k, s in snapshots.items():
                    if forecasts[k]["status"] != "estimated": curves[k] = []; continue
                    cache_key = entry, k
                    if cache_key not in entry_curves:
                        entry_curves[cache_key] = cost_curve({**s, "price": outcomes[k].get("entry_price") or s["price"]}, costs, policy)
                    curves[k] = entry_curves[cache_key]
                candidates = [{"snapshot": s, "outcome": outcomes[k], "forecast": forecasts[k], "curve": curves[k]} for k, s in snapshots.items()]
                group = f"{entry}_{hold}_{'bracket' if bracket else 'time'}"
                audit = {"policy": group, "forecasts": {k: {field: value for field, value in f.items()
                         if field not in {"gross_scenarios", "holding_scenarios", "training_issuers"}}
                         for k, f in forecasts.items() if f["status"] == "estimated"},
                         "outcomes": {k: o["status"] for k, o in outcomes.items()}, "accounts": {}}
                path_coverage.append({"policy": group, "counts": dict(Counter(o["status"] for o in outcomes.values()))})
                diag = [{"prediction": forecasts[k]["gross_edge"], "realized": outcomes[k]["gross_return"], "announcement": s["known_at"]}
                        for k, s in snapshots.items() if forecasts[k]["status"] == "estimated" and outcomes[k]["status"] == "daily_benchmark"]
                validation[group] = calibration(diag, policy.prospective_start)
                for account_id, account in accounts.items():
                    for variant in ("baseline", "fundamental", "net_edge", "strict"):
                        result = simulate(candidates, p, account, sessions, store, evidence, variant=variant)
                        case_id = f"{group}_{account_id}_{variant}"
                        if variant == "net_edge":
                            audit["accounts"][account_id] = {r["key"]: {field: value for field, value in r.items() if field not in {"key", "ticker", "date", "failed_constraints"}} for r in result["journal"] if forecasts[r["key"]]["status"] == "estimated"}
                        if entry == policy.entry and hold == policy.sessions and bracket == policy.bracket and account_id == settings["primary_account"] and variant == "net_edge":
                            decisions = {r["key"]: r for r in result["journal"]}
                            primary_names = [{"key": k, "ticker": s["ticker"], "announcement": s["known_at"], "rating": s["screen_rating"],
                                "fundamental_status": s["fundamental"]["status"], "source_url": s["source_url"],
                                "framework_reviewed": s["framework"]["reviewed"], "financing_status": s["capitalization"]["status"],
                "borrow_indication": bool(s["announcement_borrow"]), "conviction_rating": s["conviction_rating"], "outcome_status": outcomes[k]["status"],
                                "forecast": {field: value for field, value in forecasts[k].items() if field not in {"gross_scenarios", "holding_scenarios", "training_issuers"}},
                                "size_curve": curves[k], "decision": decisions.get(k, {"shares": 0, "reason": outcomes[k]["status"]})}
                                for k, s in snapshots.items()]
                        write_json(output/(case_id+".json"), result)
                        result.pop("journal"); result.pop("trade_ledger")
                        result.update(id=case_id, group=group, entry=entry, sessions=hold, bracket=bracket, account_id=account_id)
                        cases.append(result)
                print(group, "paths", sum(o["status"] == "daily_benchmark" for o in outcomes.values()), flush=True)
                audit_path = destination/"net_edge_audits_v3"/(group+".json")
                write_json(audit_path, audit)
                audit_files[group] = {"url": "data/net_edge_audits_v3/"+audit_path.name, "sha256": digest(audit_path)}
    catalogue = [{k: e.get(k) for k in ("event_id", "ticker", "issuer", "available_at", "clock_basis", "verification", "ex_date", "source_url")} for e in events]
    announcements = load_jsonl(source/"announcements.jsonl")
    tasks = [{"event_id": k, "ticker": s["ticker"], "cutoff": s["known_at"], "source_url": s["source_url"],
              "fundamental_status": s["fundamental"]["status"], "missing_metrics": s["fundamental"].get("missing_metrics", []),
              "missing_frameworks": s["framework"]["missing"], "financing_needed": s["dilution"] is None,
              "identity_needed": not s["identity_verified"], "review_instruction": "Blind source review; no future price or outcome columns. Cite availability, mechanism, contrary evidence and falsifier."}
             for k, s in snapshots.items()]
    write_json(output/"frozen_snapshots.json", snapshots); write_json(output/"catalogue.json", catalogue); write_json(output/"blinded_review_queue.json", tasks)
    snapshot_count = len(snapshots)
    coverage = {"catalogue_events": len(events), "discovery_accessions": len({r.get("accession") for r in announcements}),
                "dated_primary_snapshots": snapshot_count, "numeric_ratings": sum(s["screen_rating"] is not None for s in snapshots.values()),
                "prior_numeric_ratings_691": sum(s.get("screen_rating") is not None for s in old.values()),
                "rescored_original_691": sum(snapshots.get(k, {}).get("screen_rating") is not None for k in old),
                "complete_framework_reviews": sum(s["framework"]["complete"] for s in snapshots.values()),
                "reconciled_financing": sum(s["dilution"] is not None for s in snapshots.values()),
                "announcement_borrow_indications": sum(bool(s["announcement_borrow"]) for s in snapshots.values()),
                "approved_entry_locates": sum(r.get("kind") == "approval" for r in evidence["borrow"]),
                "full_universe_complete": False, "gaps": gaps}
    primary_group = f"{policy.entry}_{policy.sessions}_{'bracket' if policy.bracket else 'time'}"
    publication = {"schema_version": "shorts_net_edge.v3", "version": VERSION, "built_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "authority": "none", "primary_case": f"{primary_group}_{settings['primary_account']}_net_edge",
        "coverage": coverage, "accounts": settings["accounts"], "policy": asdict(policy), "cases": cases,
        "names": sorted([{k: v for k, v in r.items() if k not in {"forecast", "decision", "size_curve"}} for r in primary_names], key=lambda r: r["announcement"], reverse=True), "audit_files": audit_files, "validation": validation,
        "path_coverage": path_coverage, "ssr": ssr_audit(source, evidence, policy),
        "prospective": prospective_status(destination),
        "data_tasks": {"blinded_reviews": len(tasks), "execution_import_rows": len(evidence["executions"]), "downloads": downloads},
        "definitions": {
            "edge": "Prior completed other issuers only. Gross return is shrunk toward zero; the lower bound is an issuer bootstrap estimate. Framework mechanisms and reconciled financing are separate matching features, never additive return bonuses.",
            "sizing": "Search feasible whole-share quantities using costs at each proposed size, commission minima, confidence-bound edge, fractional sizing, prior ADV, concurrent positions, margin and joint squeeze budgets.",
            "holding": "Next open after announcement or after the split; 1, 5, 10 or 20 sessions. Daily-bar brackets use the adverse stop first when both boundaries occur in one bar. These are conditional benchmarks, not observed executions.",
            "borrow": "Sum rounded nominal collateral times daily APR / 360 across settled calendar days for every prior holding scenario. Actual fee records are kept separate from forecasts. Pre-borrow fees/minimum days are explicit account assumptions.",
            "frameworks": "Every route is reviewed or explicitly unknown/N/A. Contrary evidence blocks a selected mechanism; only documented mandatory vetoes exclude other mechanisms. No full conviction is manufactured from a numerical screen.",
            "validation": "All historical periods were explored. Calibration is diagnostic. The policy freezes a prospective start; future forecasts must be archived before entry and never rebuilt using their outcomes."},
        "limits": ["Catalogue and discovery counts retain unpriced/unverified names; full-announcement completeness is not claimed.",
                   "Daily bars do not prove tradability, stop fills, SSR fills, inventory, borrow approval, dividend liabilities or settlement of fractional split entitlements.",
                   "All included P&L is a conditional execution/carry scenario. Strict results remain blocked without primary reviews, identity, financing, fresh entry approval and observed execution evidence.",
                   "Joint daily highs are a conservative funding diagnostic. A reported margin breach invalidates the scenario; it is not treated as a funded strategy return.",
                   "Source prices are verified nominal venue observations; missing bars remain unresolved in coverage, never silently converted into winning returns.",
                   "The bootstrap does not establish the probability of rare squeezes; separate +200% name and sleeve stress limits remain binding."],
        "sources": [{"title": "SEC Rule 201 execution guidance", "url": "https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions-7"},
                    {"title": "FINRA settlement holidays", "url": "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-extension-holiday-schedule"},
                    {"title": "IBKR daily borrow calculation", "url": "https://www.ibkrguides.com/reportingreference/reportguide/borrowfeedetails_default.htm"}]}
    write_json(output/"summary.json", publication)
    manifest = {"schema_version": "shorts_edge_manifest.v3", "summary_sha256": digest(output/"summary.json"),
                "source_run": RUN_ID, "source_manifest_sha256": digest(frozen/"manifest.json"), "profile_sha256": digest(args.profiles or destination/"net_edge_profiles.json"),
                "snapshots_sha256": digest(output/"frozen_snapshots.json"), "catalogue_sha256": digest(output/"catalogue.json"),
                "review_queue_sha256": digest(output/"blinded_review_queue.json"), "raw_companyfacts": raw_hashes,
                "code": code_hashes,
                "private_inputs": {kind: digest(destination/"local/edge_inputs"/(kind+".jsonl")) for kind in evidence if (destination/"local/edge_inputs"/(kind+".jsonl")).exists()},
                "execution_inputs": {str(p.relative_to(source)): digest(p) for p in (source/"local/portfolio_research"/(RUN_ID+"__portfolio_v1")).rglob("*.local.json") if p.name in {"books.local.json", "points.local.json", "status_history.local.json"}},
                "borrow_inputs": {str(p.relative_to(source)): digest(p) for p in (source/"borrow_history").glob("*/*.jsonl")},
                "audits": audit_files,
                "data_root_published": False}
    write_json(output/"manifest.json", manifest)
    if args.publish:
        write_json(destination/"net_edge_research_v3.json", publication); write_json(destination/"net_edge_manifest_v3.json", manifest)
    store.connection.close()
    print("Coverage", json.dumps(coverage), flush=True)
    return publication


if __name__ == "__main__": main()
