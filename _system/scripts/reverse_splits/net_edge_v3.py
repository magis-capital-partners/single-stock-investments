"""RSI-3.0 research primitives: prior-only forecasts and size-dependent costs.

No provider or broker access. A price benchmark is never an executable fill.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from statistics import mean

import numpy as np

from .net_edge import FRAMEWORKS, distribution, moment
from .net_edge_clock import available

VERSION = "RSI-3.0"
HARD_VETOES = {"identity_mismatch", "instrument_ineligible", "borrow_unavailable",
               "unfunded_stress", "thesis_falsified"}


@lru_cache(maxsize=16)
def settlement_calendar(sessions):
    """US equity settlement differs from exchange opening dates.

    FINRA's holiday schedule excludes Columbus/Veterans Day. DTCC operated
    normally on the 2018 and 2025 national days of mourning. A Saturday
    Veterans Day does not close Friday (DTCC notice 19155-23).
    """
    holidays = set()
    for year in {int(s[:4]) for s in sessions}:
        october = date(year, 10, 1)
        holidays.add((october+timedelta(days=(7-october.weekday()) % 7+7)).isoformat())
        veterans = date(year, 11, 11)
        holidays.add((veterans+timedelta(days=1 if veterans.weekday() == 6 else 0)).isoformat())
    extra = {d for d in ("2018-12-05", "2025-01-09") if sessions[0] <= d <= sessions[-1]}
    return tuple(sorted((set(sessions) | extra)-holidays))


def settlement_day(trade_day, sessions):
    calendar = settlement_calendar(tuple(sessions))
    lag = 1 if trade_day >= "2024-05-28" else 2
    index = bisect.bisect_right(calendar, trade_day)+lag-1
    if index >= len(calendar): raise ValueError("Settlement calendar does not cover the loan")
    return date.fromisoformat(calendar[index])


@lru_cache(maxsize=4096)
def _planning_sessions(sessions, known_at):
    """Do not project a later emergency market closure into an earlier plan.

    Conservative next-day availability for the public closure announcements.
    Realized trading paths still follow the actual exchange calendar.
    """
    if not known_at: return sessions
    cutoff = moment(known_at)
    closures = {"2018-12-05": "2018-12-03T00:00:00+00:00", "2025-01-09": "2024-12-31T00:00:00+00:00"}
    extra = {d for d, available_at in closures.items() if sessions[0] <= d <= sessions[-1] and cutoff < moment(available_at)}
    return tuple(sorted(set(sessions) | extra)) if extra else sessions


def planning_sessions(sessions, known_at):
    return _planning_sessions(tuple(sessions), known_at)


@dataclass(frozen=True)
class StudyPolicy:
    entry: str = "announcement_next_open"
    sessions: int = 5
    bracket: bool = True
    profit_take: float = .10
    stop_loss: float = .20
    fundamental_floor: float = 60.
    min_issuers: int = 20
    max_issuers: int = 60
    confidence: float = .90
    bootstrap_samples: int = 512
    shrinkage_issuers: int = 20
    kelly_fraction: float = .25
    assumed_annual_borrow: float = .50
    minimum_billed_days: int = 0
    borrow_basis: int = 360
    preborrow_fee_per_share: float = 0.
    maximum_quote_age_seconds: float = 15.
    locate_age_hours: float = 4.
    ssr_timeout_seconds: int = 900
    minimum_notional: float = 100.
    prospective_start: str = "2026-10-16"

    def __post_init__(self):
        if self.entry not in {"announcement_next_open", "post_split_next_open"}:
            raise ValueError("Unknown entry policy")
        if self.sessions not in {1, 5, 10, 20} or not 0 < self.profit_take < 1 or self.stop_loss <= 0:
            raise ValueError("Invalid exit policy")
        if self.min_issuers < 2 or self.max_issuers < self.min_issuers:
            raise ValueError("Invalid donor limits")
        if not .5 < self.confidence < 1 or self.bootstrap_samples < 100 or self.shrinkage_issuers < 0:
            raise ValueError("Invalid uncertainty policy")
        if self.borrow_basis not in {360, 365} or self.minimum_billed_days < 0:
            raise ValueError("Invalid borrow billing")
        for key in ("assumed_annual_borrow", "preborrow_fee_per_share", "minimum_notional",
                    "fundamental_floor", "kelly_fraction", "maximum_quote_age_seconds", "locate_age_hours"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) < 0:
                raise ValueError(f"Invalid {key}")
        date.fromisoformat(self.prospective_start)

    def fingerprint(self):
        # Costs, capital and inference settings must not change which exit a donor followed.
        fields = ("entry", "sessions", "bracket", "profit_take", "stop_loss")
        return hashlib.sha256(json.dumps({k: getattr(self, k) for k in fields}, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Account:
    equity: float = 50000.
    commission_per_share: float = .005
    commission_minimum: float = 1.
    commission_max_fraction: float = .01
    maximum_name_fraction: float = .025
    name_stress_budget: float = .005
    sleeve_stress_budget: float = .02
    squeeze_increase: float = 2.
    margin_fraction: float = .60
    participation: float = .001
    maximum_names: int = 3

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid account setting: {key}")
        if self.equity <= 0 or self.squeeze_increase <= 0 or self.maximum_names < 1 or not isinstance(self.maximum_names, int):
            raise ValueError("Invalid capital settings")
        for key in ("maximum_name_fraction", "name_stress_budget", "sleeve_stress_budget",
                    "margin_fraction", "participation", "commission_max_fraction"):
            if getattr(self, key) > 1:
                raise ValueError(f"{key} must be a fraction")


def commission(shares, price, account):
    if shares <= 0 or price <= 0:
        return 0.
    return min(max(account.commission_minimum, shares * account.commission_per_share),
               shares * price * account.commission_max_fraction)


def assessment(reviews, cutoff, *, selected_mechanisms=(), vetoes=()):
    """Review every route; contrary evidence vetoes only the selected thesis.

    A documented N/A counts as reviewed, never as support. A missing route stays
    unknown. Valuation and catalyst need their own explicit primary reviews.
    """
    selected = {}
    for row in reviews:
        if row.get("framework") not in FRAMEWORKS or not available(row, cutoff):
            continue
        if row.get("status") not in {"supported", "contradicted", "unresolved", "not_applicable"}:
            continue
        if not all(row.get(k) for k in ("source_url", "locator", "mechanism", "contrary_evidence", "falsifier")):
            continue
        if not str(row["source_url"]).startswith("https://"):
            continue
        key = row["framework"]
        if key not in selected or str(row["known_at"]) > str(selected[key]["known_at"]):
            selected[key] = row
    mechanisms = set(selected_mechanisms)
    if not mechanisms <= set(FRAMEWORKS):
        raise ValueError("Unknown selected mechanism")
    contradiction = sorted(k for k in mechanisms if selected.get(k, {}).get("status") == "contradicted")
    active_vetoes = sorted({v["reason"] for v in vetoes if v.get("reason") in HARD_VETOES
                           and v.get("source_url") and v.get("locator") and available(v, cutoff)})
    supported = sorted(k for k, r in selected.items() if r["status"] == "supported")
    thesis = bool(mechanisms and mechanisms <= set(supported))
    unresolved = sorted(k for k, r in selected.items() if r["status"] == "unresolved")
    missing = sorted(set(FRAMEWORKS) - selected.keys())
    return {"reviewed": len(selected), "total": len(FRAMEWORKS), "missing": missing,
            "unresolved": unresolved, "supported": supported, "selected_mechanisms": sorted(mechanisms),
            "contradicted_selected_mechanisms": contradiction, "vetoes": active_vetoes,
            "complete": not missing and not unresolved, "thesis_supported": thesis,
            "features": {k: 1. if v["status"] == "supported" else 0.
                         for k, v in selected.items() if v["status"] != "unresolved"},
            "blocked": bool(contradiction or active_vetoes)}


def dated_borrow(observations, issuer, cutoff, *, approval=False, max_age_hours=4.):
    eligible = []
    recalls = [moment(r.get("known_at")) for r in observations if r.get("issuer") == issuer and r.get("kind") == "recall" and moment(r.get("known_at")) and moment(r["known_at"]) <= cutoff]
    latest_recall = max(recalls) if recalls else None
    for row in observations:
        stamp = moment(row.get("known_at"))
        rate, quantity = row.get("annual_rate"), row.get("shares")
        if (row.get("issuer") != issuer or stamp is None or stamp > cutoff or latest_recall and stamp <= latest_recall
                or row.get("kind") not in {"indication", "approval"}
                or (cutoff - stamp).total_seconds() > max_age_hours * 3600):
            continue
        if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate < 0:
            continue
        if not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or quantity < 0:
            continue
        if approval and not (row.get("kind") == "approval" and row.get("approved")
                             and row.get("reference") and quantity > 0):
            continue
        eligible.append(row)
    return max(eligible, key=lambda r: r["known_at"], default=None)


def loan_schedule(entry_day, exit_day, price, annual_rate, sessions, *, minimum_days=0,
                  basis=360, daily_prices=None, daily_rates=None, daily_share_factors=None,
                  preborrow_fee_per_share=0.):
    if price <= 0 or annual_rate < 0 or not math.isfinite(price + annual_rate) or exit_day < entry_day:
        raise ValueError("Invalid loan")
    first, last = settlement_day(entry_day, sessions), settlement_day(exit_day, sessions)
    days = max(minimum_days, (last - first).days)
    records = []
    for i in range(days):
        day = (first + timedelta(days=i)).isoformat()
        mark = (daily_prices or {}).get(day, price)
        rate = (daily_rates or {}).get(day, annual_rate)
        factor = (daily_share_factors or {}).get(day, 1.)
        if mark <= 0 or rate < 0 or factor <= 0 or not math.isfinite(mark + rate + factor):
            raise ValueError("Invalid daily loan observation")
        records.append({"date": day, "collateral_per_share": factor*math.ceil(mark * 1.02),
                        "annual_rate": rate, "per_share": factor*math.ceil(mark * 1.02) * rate / basis})
    return {"fraction": (sum(r["per_share"] for r in records) + preborrow_fee_per_share) / price,
            "billed_calendar_days": days, "days": records,
            "preborrow_fee_per_share": preborrow_fee_per_share,
            "entry_settlement": first.isoformat(), "exit_settlement": last.isoformat()}


def expected_carry(scenarios, entry_day, price, rate, sessions, policy, *, known_splits=()):
    """Only caller-supplied ex-ante scenarios; never the tested trade's exit."""
    loans = []
    entry_index = sessions.index(entry_day)
    for scenario in scenarios:
        hold = scenario["hold_sessions"]
        if not isinstance(hold, int) or hold < 0 or entry_index + hold >= len(sessions):
            raise ValueError("Invalid forecast holding duration")
        exit_day = sessions[entry_index + hold]
        first = settlement_day(entry_day, sessions)
        # Donor paths are completed before the forecast cutoff. Re-project their
        # relative marks/rates onto this entry's actual settlement calendar.
        last = settlement_day(exit_day, sessions)
        billed = max(policy.minimum_billed_days, (last-first).days)
        factors = {str(first+timedelta(days=i)): math.prod(r["ratio"] for r in known_splits if entry_day < r["date"] <= str(first+timedelta(days=i))) for i in range(billed)}
        marks = {day: price*(scenario.get("collateral_factors", [])[i] if i < len(scenario.get("collateral_factors", [])) else 1.)/factor for i, (day, factor) in enumerate(factors.items())}
        rates = {str(first + timedelta(days=i)): rate * f for i, f in enumerate(scenario.get("rate_factors", []))}
        loans.append(loan_schedule(entry_day, exit_day, price, rate, sessions,
                                  minimum_days=policy.minimum_billed_days, basis=policy.borrow_basis,
                                  daily_prices=marks, daily_rates=rates, daily_share_factors=factors,
                                  preborrow_fee_per_share=policy.preborrow_fee_per_share))
    return {"fraction": mean(r["fraction"] for r in loans),
            "expected_billed_days": mean(r["billed_calendar_days"] for r in loans),
            "fractions": [r["fraction"] for r in loans]}


def prior_issuers(snapshot, donors, policy):
    cutoff = moment(snapshot["known_at"])
    policy_hash = policy.fingerprint()
    unique = {}
    for donor in sorted(donors, key=lambda d: d["exit_at"]):
        if (donor["issuer"] != snapshot["issuer"] and moment(donor["exit_at"]) < cutoff
                and donor.get("screen_rating") is not None and donor.get("policy_hash") == policy_hash):
            unique[donor["issuer"]] = donor
    def distance(row):
        value = abs(row["screen_rating"] - snapshot["screen_rating"]) / 100
        value += .2 * abs(math.log(row["ratio"] / snapshot["ratio"]))
        common = row.get("framework_features", {}).keys() & snapshot.get("framework_features", {}).keys()
        if common:
            value += math.fsum(abs(row["framework_features"][k] - snapshot["framework_features"][k]) for k in common)/len(common)
        if row.get("dilution") is not None and snapshot.get("dilution") is not None:
            value += abs(row["dilution"] - snapshot["dilution"])
        return value, row["issuer"]
    return sorted(unique.values(), key=distance)[:policy.max_issuers]


def payoff_forecast(snapshot, donors, policy):
    if snapshot.get("screen_rating") is None:
        return {"status": "fundamentals_unavailable"}
    if not isinstance(snapshot.get("ratio"), (int, float)) or snapshot["ratio"] <= 0:
        return {"status": "split_ratio_unverified"}
    selected = prior_issuers(snapshot, donors, policy)
    if len(selected) < policy.min_issuers:
        return {"status": "insufficient_prior_issuers", "donors": len(selected)}
    returns = np.array([d["gross_return"] for d in selected], dtype=float)
    seed = int(hashlib.sha256((snapshot["issuer"] + snapshot["known_at"] + policy.fingerprint()).encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    boot = returns[rng.integers(0, len(returns), (policy.bootstrap_samples, len(returns)))].mean(axis=1)
    shrink = len(returns) / (len(returns) + policy.shrinkage_issuers)
    return {"status": "estimated", "donors": len(selected), "gross_edge": float(returns.mean()) * shrink,
            "unshrunk_gross_edge": float(returns.mean()),
            "gross_lower_bound": float(np.quantile(boot, 1-policy.confidence)) * shrink,
            "gross_upper_bound": float(np.quantile(boot, policy.confidence)) * shrink,
            "confidence": policy.confidence, "shrinkage": shrink,
            "known_at": snapshot["known_at"],
            "gross": distribution(returns.tolist()), "gross_scenarios": returns.tolist(),
            "holding_scenarios": [{k: d[k] for k in ("hold_sessions", "collateral_factors", "rate_factors") if k in d} for d in selected],
            "expected_hold_sessions": mean(d["hold_sessions"] for d in selected),
            "latest_training_exit": max(d["exit_at"] for d in selected),
            "training_issuers": [d["issuer"] for d in selected],
            "known_splits": [{"date": snapshot["ex_date"], "ratio": snapshot["ratio"]}] if snapshot.get("ex_date") else [],
            "framework_matched_donors": sum(bool((d.get("framework_features", {}).keys() & snapshot.get("framework_features", {}).keys()) - {k for k in snapshot.get("framework_features", {}) if k.startswith("numeric:")}) for d in selected),
            "dilution_matched_donors": sum(d.get("dilution") is not None for d in selected) if snapshot.get("dilution") is not None else 0}


def cost_at(curve, notional):
    """Use the next larger observed size; never extrapolate beyond depth."""
    eligible = [r for r in curve if r["notional"] >= notional and r.get("round_trip") is not None]
    return min(eligible, key=lambda r: r["notional"]) if eligible else None


def size_position(forecast, curve, price, entry_day, rate, sessions, policy, account, *,
                  equity=None, adv=None, inventory=None, used_margin=0., used_stress=0.,
                  rating=100., mode="net_edge", carry_cache=None, calendar_asof=None):
    """Search costs at each feasible size; a tiny order cannot veto a larger one."""
    nav = account.equity if equity is None else equity
    if forecast.get("status") != "estimated":
        return {"shares": 0, "reason": forecast.get("status", "forecast_unavailable")}
    if nav <= 0 or price <= 0 or adv is None:
        return {"shares": 0, "reason": "capital_or_capacity_unavailable"}
    maximum = min(nav * account.maximum_name_fraction / price, adv * account.participation,
                  max(0., account.margin_fraction * nav - used_margin) / maintenance_per_share(price))
    if inventory is not None:
        maximum = min(maximum, inventory)
    # Even before costs, the shock limit is a hard upper bound.
    maximum = min(maximum, nav * account.name_stress_budget / (price * account.squeeze_increase),
                  max(0., nav * account.sleeve_stress_budget-used_stress) / (price*account.squeeze_increase))
    maximum = max(0, math.floor(maximum))
    if maximum * price < policy.minimum_notional:
        return {"shares": 0, "reason": "minimum_order_or_capacity"}
    cache = carry_cache if carry_cache is not None else {}
    sessions = planning_sessions(sessions, calendar_asof or forecast.get("known_at"))
    shock = 1+account.squeeze_increase
    cache_key = entry_day, price, rate, shock
    if cache_key not in cache:
        carry = expected_carry(forecast["holding_scenarios"], entry_day, price, rate, sessions, policy, known_splits=forecast.get("known_splits", []))
        # Rounding collateral at triple price matters for low-price shares.
        stressed = expected_carry(forecast["holding_scenarios"], entry_day, price*shock, rate*3, sessions, policy, known_splits=forecast.get("known_splits", []))
        cache[cache_key] = carry, stressed["fraction"]*shock
    carry, stress_borrow = cache[cache_key]
    if maximum <= 4000:
        candidates = range(max(1, math.ceil(policy.minimum_notional/price)), maximum+1)
    else:
        candidates = sorted({maximum, max(1, math.ceil(policy.minimum_notional/price)),
                             *[int(x) for x in np.geomspace(1, maximum, 256)],
                             *[min(maximum, math.floor(r["notional"]/price)) for r in curve]})
    # Calculate the broker fee on nominal cover shares after known splits.
    # Vectorization preserves commission minima/caps without a nested size loop.
    candidates = list(candidates)
    if mode == "baseline":
        candidates.reverse()  # Largest feasible order is the exact baseline objective.
    elif forecast["gross_lower_bound"] <= 0:
        # Nonnegative costs cannot rescue a nonpositive gross lower bound.
        # Within a cost bucket, dollar lower-bound edge decreases with size;
        # evaluate its first whole-share order for an exact rejected-trial audit.
        minimum = max(1, math.ceil(policy.minimum_notional/price))
        candidates = sorted({minimum, *[math.floor(r["notional"]/price)+1 for r in curve
                                         if minimum <= math.floor(r["notional"]/price)+1 <= maximum]})
    durations = forecast["holding_scenarios"]
    entry_index = sessions.index(entry_day)
    factors = np.array([math.prod(r["ratio"] for r in forecast.get("known_splits", [])
                       if entry_day < r["date"] <= sessions[entry_index+s["hold_sessions"]]) for s in durations])
    returns = forecast.get("gross_scenarios", [forecast["gross_edge"]]*len(durations))
    exits = np.maximum(1e-8, 1-np.array(returns))*price
    quantities = np.array(candidates, dtype=float)[:, None]
    covers = np.minimum(np.maximum(account.commission_minimum, quantities*factors*account.commission_per_share),
                        quantities*exits*account.commission_max_fraction).mean(axis=1)
    fees = {q: (commission(q, price, account)+float(fee))/(q*price) for q, fee in zip(candidates, covers) if q > 0}
    best, trial = None, None
    failures = set()
    for q in candidates:
        if q <= 0 or q*price < policy.minimum_notional:
            continue
        cost = cost_at(curve, q*price)
        if cost is None:
            failures.add("cost_depth_unavailable"); continue
        comm = fees[q]
        costs = cost["round_trip"]+comm+carry["fraction"]
        edge = forecast["gross_edge"]-costs
        lower = forecast["gross_lower_bound"]-costs-cost.get("uncertainty", 0.)
        stress = account.squeeze_increase+cost["round_trip"]+comm+stress_borrow
        dollars = q*price
        diagnostic = {"trial_shares": q, "trial_notional": dollars, "net_edge": edge, "net_lower_bound": lower,
                      "expected_commission": comm, "expected_slippage": cost["round_trip"],
                      "expected_borrow": carry["fraction"], "expected_billed_days": carry["expected_billed_days"]}
        if trial is None or dollars*lower > trial["trial_notional"]*trial["net_lower_bound"]:
            trial = diagnostic
        if (dollars*stress > nav*account.name_stress_budget+1e-9
                or dollars*stress+used_stress > nav*account.sleeve_stress_budget+1e-9):
            failures.add("squeeze_budget"); continue
        if mode == "net_edge":
            if edge <= 0 or lower <= 0:
                failures.add("edge_uncertain_or_nonpositive"); continue
            second = forecast["gross"]["variance"]+edge*edge
            fraction = policy.kelly_fraction*lower/max(second, 1e-12)*max(0., min(1., rating/100))
            if dollars/nav > fraction:
                failures.add("fractional_sizing_limit"); continue
        candidate = {"shares": q, "notional": dollars, "net_edge": edge, "net_lower_bound": lower,
                     "expected_commission": comm, "expected_slippage": cost["round_trip"],
                     "expected_borrow": carry["fraction"], "expected_billed_days": carry["expected_billed_days"],
                     "cost_issuers": cost.get("issuers"), "cost_basis": cost.get("basis"),
                     "cost_size_bucket": cost["notional"], "stress_fraction": stress,
                     "margin": q*maintenance_per_share(price), "reason": "included"}
        if best is None or dollars*(lower if mode == "net_edge" else 1) > best["notional"]*(best["net_lower_bound"] if mode == "net_edge" else 1):
            best = candidate
        if mode == "baseline": break
    result = best or {**(trial or {}), "shares": 0, "reason": "edge_uncertain_or_nonpositive" if "edge_uncertain_or_nonpositive" in failures else sorted(failures)[0] if failures else "minimum_order_or_capacity",
                      "failed_constraints": sorted(failures)}
    q = result.get("shares") or result.get("trial_shares")
    if q:
        cover_fees = np.minimum(np.maximum(account.commission_minimum, q*factors*account.commission_per_share), q*exits*account.commission_max_fraction)
        scenario_fees = (commission(q, price, account)+cover_fees)/(q*price)
        centered = np.array(returns)-(float(np.mean(returns))-forecast["gross_edge"])
        result["net_distribution"] = distribution((centered-result["expected_slippage"]-scenario_fees-np.array(carry["fractions"])).tolist())
    return result


def maintenance_per_share(price):
    return max(price, 2.5 if price < 5 else 5.)


def daily_exit(bars, entry_price, policy):
    """Daily-bar benchmark. Ambiguous same-bar brackets take the adverse exit.

    Gaps execute at the opening benchmark. Touches do not assert actual fills.
    Missing bars and truncated horizons remain unresolved, never disappear.
    """
    stop, target = entry_price*(1+policy.stop_loss), entry_price*(1-policy.profit_take)
    marks = []
    for i, bar in enumerate(bars[:policy.sessions]):
        if not all(isinstance(bar.get(k), (float, int)) and math.isfinite(bar[k]) and bar[k] > 0
                   for k in ("open", "high", "low", "close")):
            return {"status": "unresolved_price_path", "marks": marks}
        if not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
            return {"status": "invalid_daily_bar", "marks": marks}
        marks.append({"date": bar["date"], "close": bar["close"], "adverse_high": bar["high"]})
        reason, price = None, None
        if policy.bracket:
            if bar["open"] >= stop: reason, price = "stop_gap", bar["open"]
            elif bar["open"] <= target: reason, price = "profit_gap", bar["open"]
            elif bar["high"] >= stop: reason, price = "stop_bar_bound", stop
            elif bar["low"] <= target: reason, price = "profit_bar_bound", target
        if reason or i == policy.sessions-1:
            return {"status": "daily_benchmark", "exit_day": bar["date"], "exit_price": price or bar["close"],
                    "reason": reason or "time", "hold_sessions": i, "marks": marks,
                    "gross_return": (entry_price-(price or bar["close"]))/entry_price,
                    "execution_observed": False}
    return {"status": "unresolved_price_path", "marks": marks}


def ssr_limit_fill(records, decision_at, shares, *, timeout_seconds=900, max_quote_age=15.,
                   queue_ahead=0, tick=.01):
    """Conservative SSR fill from verified NBBO and aggressive buy prints.

    Sampled quotes alone never fill a resting short. The fixed limit is
    cancelled when the national bid reaches it. Repricing requires a new run.
    """
    if shares <= 0 or tick <= 0 or timeout_seconds <= 0 or max_quote_age < 0 or queue_ahead < 0:
        raise ValueError("Invalid SSR order")
    end = decision_at+timeout_seconds
    quote, limit, remaining, filled, value = None, None, shares, 0, 0.
    queue = queue_ahead
    for row in sorted(records, key=lambda r: r["timestamp"]):
        at = row["timestamp"]
        if at > end: break
        if row.get("kind") == "quote" and row.get("nbbo_verified"):
            if row.get("known_at", at) > at: continue
            if row.get("is_trading") == "N": quote = None; continue
            bid, ask = row.get("bid"), row.get("ask")
            if bid is None or ask is None or bid <= 0 or ask < bid: continue
            quote = row
            if at >= decision_at and limit is None:
                limit = math.floor(bid/tick+1+1e-8)*tick
            if limit is not None and bid >= limit:
                return {"status": "cancelled_price_test", "shares": filled, "limit": limit, "price": value/filled if filled else None}
        if at >= decision_at and quote is not None and limit is None and at-quote["timestamp"] <= max_quote_age:
            limit = math.floor(quote["bid"]/tick+1+1e-8)*tick
        if at < decision_at or quote is None or limit is None or at-quote["timestamp"] > max_quote_age:
            continue
        if (row.get("kind") != "trade" or row.get("aggressor") != "buy"
                or row.get("price", 0) < limit or row.get("price", 0) <= quote["bid"]
                or row.get("known_at", at) > at or not row.get("regular_trade", False)):
            continue
        volume = max(0, int(row.get("size", 0)))
        ahead = min(queue, volume); queue -= ahead; volume -= ahead
        part = min(remaining, volume); remaining -= part; filled += part; value += part*limit
        if not remaining:
            return {"status": "filled", "shares": filled, "price": value/filled, "fill_at": at,
                    "limit": limit, "nbbo_verified": True}
    return {"status": "partial_timeout" if filled else "unfilled_or_execution_evidence_missing",
            "shares": filled, "price": value/filled if filled else None, "limit": limit}


def calendar_mark(marks, day, default):
    before = [m for m in marks if m["date"] < day]
    return before[-1]["close"] if before else default


def calibration(records, prospective_start):
    """Previously explored history is explicitly diagnostic, never held-out."""
    rows = sorted(records, key=lambda r: r["prediction"])
    bins = []
    for part in np.array_split(np.arange(len(rows)), min(5, len(rows))):
        if len(part):
            group = [rows[int(i)] for i in part]
            bins.append({"names": len(group), "predicted": mean(r["prediction"] for r in group),
                         "realized_benchmark": mean(r["realized"] for r in group)})
    return {"status": "historical_diagnostic_only", "observations": len(rows), "bins": bins,
            "mean_absolute_error": mean(abs(r["prediction"]-r["realized"]) for r in rows) if rows else None,
            "prospective_start": prospective_start,
            "prospective_observations": sum(r["announcement"][:10] >= prospective_start for r in rows),
            "note": "All existing history was explored. Prospective predictions must be frozen before outcomes; no untouched historical validation is claimed."}
