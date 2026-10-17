"""RSI-2.0 research primitives. No network, broker access, or fitted probabilities.

Announcement snapshots, empirical payoff distributions, settlement-day carry and
bounded sizing are separate so no realized holding period enters a forecast.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

from .research_lens import LENSES

VERSION = "RSI-2.0"
# Every Short Alpha route is represented, including the conclusion-only fraud tag.
FRAMEWORKS = tuple(sorted({f for lens in LENSES for f in lens["frameworks"]} | {
    "reverse_split_impairment", "structural_decay", "share_supply", "fraud_bad_actors"}))


@dataclass(frozen=True)
class EdgePolicy:
    use_bracket: bool = True
    profit_take: float = .10
    stop_loss: float = .20
    max_minutes: int = 390
    fundamental_floor: float = 60.
    min_donors: int = 20
    max_donors: int = 60
    minimum_net_edge: float = 0.
    kelly_fraction: float = .25
    max_name_fraction: float = .025
    max_name_stress_loss: float = .005
    max_sleeve_stress_loss: float = .02
    squeeze_return: float = -2.
    assumed_annual_borrow: float = .50
    minimum_billed_days: int = 0
    borrow_day_basis: int = 360
    max_names: int = 3
    participation: float = .001

    def __post_init__(self):
        if not (0 < self.profit_take < 1 and self.stop_loss > 0 and 0 < self.max_minutes <= 390):
            raise ValueError("Use a positive intraday hold, profit take below 100%, and positive stop")
        if self.min_donors < 2 or self.max_donors < self.min_donors:
            raise ValueError("Insufficient donor limits")
        if self.borrow_day_basis not in (360, 365) or self.minimum_billed_days < 0:
            raise ValueError("Invalid carry convention")
        for field in ("fundamental_floor", "minimum_net_edge", "kelly_fraction", "max_name_fraction",
                      "max_name_stress_loss", "max_sleeve_stress_loss", "assumed_annual_borrow"):
            if not math.isfinite(getattr(self, field)) or getattr(self, field) < 0:
                raise ValueError(f"Invalid {field}")

    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def moment(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (ValueError, TypeError):
        return None


def available(record, cutoff):
    """Date-only evidence waits until the next day; unknown clocks fail closed."""
    stamp = moment(record.get("known_at"))
    if stamp:
        return stamp <= cutoff
    value = str(record.get("known_at") or "")
    return len(value) == 10 and value < cutoff.date().isoformat()


def framework_assessment(reviews, cutoff):
    selected = {}
    for row in reviews:
        key = row.get("framework")
        if key not in FRAMEWORKS or not available(row, cutoff):
            continue
        if not all(row.get(k) for k in ("source_url", "locator", "mechanism", "contrary_evidence", "falsifier")):
            continue
        if not str(row["source_url"]).startswith("https://"):
            continue
        if row.get("status") not in {"supported", "contradicted", "unresolved", "not_applicable"}:
            continue
        # Latest available revision, independent of input-file ordering.
        if key not in selected or str(row["known_at"]) > str(selected[key]["known_at"]):
            selected[key] = row
    missing = [key for key in FRAMEWORKS if key not in selected]
    contradicted = [key for key, row in selected.items() if row["status"] == "contradicted"]
    unresolved = [key for key, row in selected.items() if row["status"] == "unresolved"]
    applicable = [r for r in selected.values() if r["status"] != "not_applicable"]
    supported = sum(r["status"] == "supported" for r in applicable)
    lenses = []
    for lens in LENSES:
        rows = [selected[f] for f in lens["frameworks"] if f in selected]
        lenses.append({"id": lens["id"], "label": lens["label"],
                       "supported": sum(r["status"] == "supported" for r in rows),
                       "reviewed": len(rows), "total": len(lens["frameworks"])})
    # N/A cannot manufacture conviction; all-N/A and unsupported reviews fail.
    supported_lenses = {r["id"] for r in lenses if r["supported"]}
    thesis = ({"valuation_and_payoff", "catalyst_and_path"} <= supported_lenses
              and len(supported_lenses - {"valuation_and_payoff", "catalyst_and_path"}) >= 2
              and bool(supported_lenses & {"cash_and_financing", "operating_impairment"}))
    complete = not missing and not unresolved and not contradicted and thesis
    return {"complete": complete, "reviewed": len(selected), "total": len(FRAMEWORKS),
            "missing": missing, "contradicted": contradicted, "unresolved": unresolved,
            "support_fraction": supported / len(applicable) if applicable else None,
            "lenses": lenses, "thesis_supported": thesis}


def conviction(fundamental, reviews, cutoff):
    framework = framework_assessment(reviews, cutoff)
    score = fundamental.get("score")
    valid = bool(fundamental.get("historical_eligible") and fundamental.get("source") == "raw_companyfacts"
                 and score is not None and fundamental.get("evidence_count", 0) >= 3)
    latest = fundamental.get("latest_period")
    fresh = bool(latest and 0 <= (cutoff.date() - date.fromisoformat(latest)).days <= 200)
    numeric = float(score) if valid and fresh else None
    rating = (.6 * numeric + 40 * framework["support_fraction"]
              if numeric is not None and framework["complete"] else None)
    return {"rating": rating, "screen_rating": numeric,
            "grade": ("High" if rating >= 80 else "Medium" if rating >= 60 else "Low") if rating is not None else "Provisional",
            "framework": framework, "fundamentals_available": numeric is not None,
            "meaning": "Evidence rating, not a win probability. Screen-only ratings are provisional."}


def dilution(record, cutoff):
    """Known issuance changes ownership; a reverse split alone changes no value.

    Shares are all on the same pre-split basis. Net proceeds accrue to common
    equity; costs and senior claims must already be deducted by the reviewer.
    """
    if not record or not available(record, cutoff) or not record.get("source_url") or not record.get("locator"):
        return {"status": "unavailable", "ownership_dilution": None, "per_share_value_change": None,
                "mechanical_split_dilution": 0.}
    old = float(record["shares_before"])
    new = float(record["incremental_shares"])
    equity = float(record["common_equity_value_before"])
    proceeds = float(record["net_proceeds_to_common"])
    if not all(math.isfinite(x) for x in (old, new, equity, proceeds)) or old <= 0 or new < 0 or equity <= 0:
        raise ValueError("Invalid reconciled dilution inputs")
    change = ((equity + proceeds) / (old + new)) / (equity / old) - 1
    return {"status": "reconciled", "ownership_dilution": new / (old + new),
            "per_share_value_change": change, "mechanical_split_dilution": 0.,
            "known_at": record["known_at"], "source_url": record["source_url"]}


def settlement_day(trade_day, sessions):
    lag = 1 if trade_day >= "2024-05-28" else 2
    after = [d for d in sessions if d > trade_day]
    if len(after) < lag:
        raise ValueError("Settlement calendar does not cover the holding period")
    return date.fromisoformat(after[lag - 1])


def carry(entry_day, exit_day, price, annual_rate, sessions, *, minimum_days=0, basis=360,
          daily_prices=None, daily_rates=None):
    """Per-opening-notional loan cost, accrued on settled calendar days.

    Daily forecasts must be supplied as ex-ante scenarios. Realized accrual may
    instead use contemporaneous daily collateral marks and fees. Fees never
    compound. Minimum-day/pre-borrow charges are explicit, including same-day.
    """
    if price <= 0 or annual_rate < 0 or not math.isfinite(price + annual_rate) or basis not in (360, 365):
        raise ValueError("Invalid carry inputs")
    if exit_day < entry_day:
        raise ValueError("Exit precedes entry")
    first, last = settlement_day(entry_day, sessions), settlement_day(exit_day, sessions)
    days = max(minimum_days, (last - first).days)
    costs = []
    for i in range(days):
        day = (first + timedelta(days=i)).isoformat()
        mark = (daily_prices or {}).get(day, price)
        rate = (daily_rates or {}).get(day, annual_rate)
        if not math.isfinite(mark + rate) or mark <= 0 or rate < 0:
            raise ValueError("Invalid daily collateral or fee")
        costs.append(math.ceil(mark * 1.02) * rate / basis / price)
    return {"fraction": sum(costs), "billed_calendar_days": days,
            "entry_settlement": first.isoformat(), "exit_settlement": last.isoformat()}


def distribution(returns):
    if not returns:
        return {k: None for k in ("mean", "variance", "skewness", "gain_loss_ratio", "win_rate", "expected_shortfall_5pct")}
    mean = sum(returns) / len(returns)
    variance = sum((x - mean) ** 2 for x in returns) / len(returns)
    gain = sum(max(x, 0) for x in returns) / len(returns)
    loss = sum(max(-x, 0) for x in returns) / len(returns)
    worst = sorted(returns)[:max(1, math.ceil(.05 * len(returns)))]
    return {"mean": mean, "variance": variance,
            "skewness": sum((x - mean) ** 3 for x in returns) / len(returns) / variance ** 1.5 if variance > 0 else None,
            "gain_loss_ratio": gain / loss if loss else None,
            "win_rate": sum(x > 0 for x in returns) / len(returns),
            "expected_shortfall_5pct": max(0., -sum(worst) / len(worst))}


def forecast(snapshot, donors, policy, price, annual_rate, sessions, expected_slippage,
             expected_commission, *, minimum_days=None):
    """Only other issuers' completed outcomes known before announcement qualify.

    Similarity uses frozen fundamental ratings and split ratios; reconciled
    dilution is used only when both parties have it. Missing dilution stays
    unknown. No deterioration score is converted into a probability of profit.
    """
    cutoff = moment(snapshot["known_at"])
    if cutoff is None or price <= 0:
        raise ValueError("A dated snapshot and positive announcement price are required")
    pool = [d for d in donors if d["issuer"] != snapshot["issuer"]
            and moment(d["exit_at"]) is not None and moment(d["exit_at"]) < cutoff
            and d.get("screen_rating") is not None and d.get("policy_hash") == policy.fingerprint()]
    # Keep one most recent event per issuer; repeated splits are not independent.
    unique = {}
    for d in sorted(pool, key=lambda d: d["exit_at"]):
        unique[d["issuer"]] = d
    def distance(d):
        result = abs(d["screen_rating"] - snapshot["screen_rating"]) / 100
        result += .2 * abs(math.log(d["ratio"] / snapshot["ratio"]))
        if snapshot.get("full_rating") is not None and d.get("full_rating") is not None:
            result += abs(d["full_rating"] - snapshot["full_rating"]) / 100
        a, b = snapshot.get("dilution"), d.get("dilution")
        if a is not None and b is not None:
            result += abs(a - b)
        return result, d["issuer"]
    selected = sorted(unique.values(), key=distance)[:policy.max_donors]
    if len(selected) < policy.min_donors:
        return {"status": "insufficient_prior_issuers", "donors": len(selected), "net_edge": None}
    gross, net, fees, billed = [], [], [], []
    for d in selected:
        # Project trading-session durations onto THIS calendar. Reusing a
        # donor's calendar days would bill weekends incorrectly for new entries.
        hold = d["hold_sessions"]
        if not isinstance(hold, int) or hold < 0:
            raise ValueError("Holding scenarios require a nonnegative session count")
        entry_index = sessions.index(snapshot["entry_day"])
        if entry_index + hold >= len(sessions):
            raise ValueError("Exit scenarios exceed the settlement calendar")
        exit_day = sessions[entry_index + hold]
        loan = carry(snapshot["entry_day"], exit_day, price, annual_rate, sessions,
                     minimum_days=policy.minimum_billed_days if minimum_days is None else minimum_days,
                     basis=policy.borrow_day_basis)
        fee = loan["fraction"]
        gross.append(d["gross_return"])
        fees.append(fee)
        billed.append(loan["billed_calendar_days"])
        net.append(d["gross_return"] - expected_slippage - expected_commission - fee)
    g, n = distribution(gross), distribution(net)
    return {"status": "estimated", "donors": len(selected), "gross_edge": g["mean"],
            "net_edge": n["mean"], "expected_borrow": sum(fees) / len(fees),
            "expected_slippage": expected_slippage, "expected_commission": expected_commission,
            "expected_hold_minutes": sum(d["hold_minutes"] for d in selected) / len(selected),
            "expected_billed_days": sum(billed) / len(billed),
            "gross": g, "net": n, "net_scenarios": net,
            "latest_training_exit": max(d["exit_at"] for d in selected),
            "training_issuers": [d["issuer"] for d in selected],
            "framework_matched_donors": sum(d.get("full_rating") is not None for d in selected) if snapshot.get("full_rating") is not None else 0,
            "dilution_matched_donors": sum(d.get("dilution") is not None for d in selected) if snapshot.get("dilution") is not None else 0}


def size_fraction(estimate, rating, policy):
    if estimate.get("net_edge") is None or estimate["net_edge"] <= policy.minimum_net_edge:
        return 0.
    # Conservative fractional mean/second-moment sizing. Include an unbounded-
    # short shock floor and external loss limits; the stop is never a loss cap.
    second = estimate["net"]["variance"] + estimate["net_edge"] ** 2
    fractional = policy.kelly_fraction * estimate["net_edge"] / max(second, 1e-12)
    conviction_multiplier = max(0., min(1., rating / 100))
    stress = stress_fraction(estimate, policy)
    return max(0., min(policy.max_name_fraction, fractional * conviction_multiplier,
                       policy.max_name_stress_loss / stress))


def stress_fraction(estimate, policy):
    return (abs(policy.squeeze_return) + estimate.get("stress_borrow", estimate.get("expected_borrow", 0) * 9)
            + estimate.get("expected_commission", 0) + estimate.get("expected_slippage", 0))
