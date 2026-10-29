"""Deterministic biotech research, availability gates, and paper accounting.

No network or broker access. Inputs retain observation and publication clocks;
historical results require dated features and total-return marks.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BASELINE = {
    "id": "biotech-baseline-v1",
    "status": "research",
    "hypothesis": "Specialist ownership and spend value improve diversified biotech selection after costs.",
    "factors": {"specialist_consensus": 0.5, "spend_value": 0.5},
    "required": ["specialist_consensus", "spend_value"],
    "optional_experiments": ["insider_non_ceo", "peer_momentum", "short_interest"],
    "portfolio": {"capital": 100000, "max_names": 25, "max_name_weight": 0.04,
                  "selection_fraction": 0.2, "rebalance": "monthly", "hedge": "XBI"},
    "costs": {"one_way_bps": 25, "hedge_borrow_apr": 0.03, "stock_borrow": "observed_only"},
    "max_age_days": {"specialist_consensus": 200, "spend_value": 180,
                     "insider_non_ceo": 100, "peer_momentum": 45, "short_interest": 45},
    "validation": {"minimum_years": 5, "minimum_validation_months": 12,
                   "minimum_forward_days": 90, "net_excess_return_minimum": 0,
                   "maximum_drawdown": 0.3, "maximum_variants": 12},
    "authority": "research_and_paper_only",
}

FACTOR_FIELDS = {
    "specialist_consensus": "consensus_score", "spend_value": "spend_value",
    "insider_non_ceo": "insider_score", "peer_momentum": "peer_momentum_12m",
    "short_interest": "short_interest_pct",
}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def register_protocol(path, protocol, registered_at):
    """A protocol identifier cannot silently acquire different rules."""
    if not protocol.get("id") or not protocol.get("required"):
        raise ValueError("A protocol needs an identifier and required factors")
    if any(number(w) is None or w <= 0 for w in protocol["factors"].values()):
        raise ValueError("Factor weights must be finite and positive")
    if not set(protocol["required"]).issubset(protocol["factors"]) or not set(protocol["factors"]).issubset(FACTOR_FIELDS):
        raise ValueError("Required factors must have a supported factor definition and weight")
    if protocol["portfolio"]["capital"] <= 0 or not 0 < protocol["portfolio"]["max_name_weight"] <= 1:
        raise ValueError("Portfolio capital and position limits must be positive")
    path = Path(path)
    registry = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    prior = registry.get(protocol["id"])
    digest = checksum(protocol)
    if prior and prior["sha256"] != digest:
        raise ValueError("Registered protocol changed; use a new protocol identifier")
    if prior:
        return prior
    registry[protocol["id"]] = {"sha256": digest, "registered_at": registered_at,
                                "rules": protocol}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return registry[protocol["id"]]


def clinical_peer_momentum(profiles, returns, decision_day, minimum_peers=3):
    """Similarity-weighted OTHER-company returns from dated clinical descriptors.

    Company names are never a proxy for clinical similarity. Return observations
    must end before the decision, and today's profile cannot describe the past.
    """
    cutoff = day(decision_day)
    valid = {}
    for profile in sorted(profiles, key=lambda r: str(r.get("known_at") or "")):
        known = day(profile.get("known_at"))
        if known and known < cutoff and profile.get("clinical_tags"):
            valid[profile["ticker"]] = set(profile["clinical_tags"])
    past = {}
    for row in returns:
        end = day(row.get("end_date"))
        if end and end < cutoff and number(row.get("return_12m")) is not None:
            if row["ticker"] not in past or end > day(past[row["ticker"]]["end_date"]):
                past[row["ticker"]] = row
    result = {}
    for ticker, tags in valid.items():
        peers = []
        for other, candidate in valid.items():
            if other == ticker or other not in past:
                continue
            similarity = len(tags & candidate) / len(tags | candidate)
            if similarity:
                peers.append((other, similarity, float(past[other]["return_12m"])))
        result[ticker] = {"peer_momentum_12m": sum(w*r for _, w, r in peers)/sum(w for _, w, _ in peers) if len(peers) >= minimum_peers else None,
                          "peer_tickers": [t for t, _, _ in peers], "peer_count": len(peers),
                          "known_at": decision_day, "status": "computed" if len(peers) >= minimum_peers else "insufficient_peers"}
    return result


def percentile(values, inverse=False):
    """Midrank tied values; missing inputs never become zeros."""
    valid = {k: number(v) for k, v in values.items() if number(v) is not None}
    ordered = sorted(valid.values())
    n = len(ordered)
    out = {}
    for key, value in valid.items():
        lo = sum(v < value for v in ordered)
        ties = sum(v == value for v in ordered)
        rank = 50.0 if n == 1 else 100 * (lo + (ties - 1) / 2) / (n - 1)
        out[key] = round(100 - rank if inverse else rank, 4)
    return out


def score_rows(rows, protocol=None):
    protocol = protocol or BASELINE
    ranks = {}
    rank_universe = [r for r in rows if r.get("eligible") is not False and r.get("identity_status") not in {"unresolved", "quarantined", "out_of_scope"} and all(number(r.get(FACTOR_FIELDS[f])) is not None for f in protocol["required"])]
    for factor in protocol["factors"]:
        field = FACTOR_FIELDS[factor]
        ranks[factor] = percentile({r["ticker"]: r.get(field) for r in rank_universe}, inverse=factor == "spend_value")
    result = []
    for raw in rows:
        row = dict(raw)
        parts = {factor: ranks[factor].get(row["ticker"]) for factor in protocol["factors"]}
        missing = [f for f in protocol["required"] if number(row.get(FACTOR_FIELDS[f])) is None]
        row["factor_ranks"] = parts
        row["missing_required"] = missing
        weights = protocol["factors"]
        # A different available-factor model needs a different registered protocol.
        row["strategy_score"] = None if missing or any(parts.get(f) is None for f in weights) else round(sum(parts[f] * weights[f] for f in weights) / sum(weights.values()), 3)
        row["protocol_id"] = protocol["id"]
        result.append(row)
    return sorted(result, key=lambda r: (r["strategy_score"] is None, -(r["strategy_score"] or 0), r["ticker"]))


def source_state(value, observed_at, as_of, max_age):
    observed, current = day(observed_at), day(as_of)
    if number(value) is None:
        return {"status": "missing", "age_days": None}
    if observed is None:
        return {"status": "undated", "age_days": None}
    age = (current - observed).days
    return {"status": "future" if age < 0 else "stale" if age > max_age else "current", "age_days": age}


def available_rows(observations, decision_day, protocol=None):
    """Use strictly prior publication clocks and the newest usable vintage."""
    protocol = protocol or BASELINE
    cutoff = day(decision_day)
    selected, rejected = {}, []
    for raw in observations:
        known = day(raw.get("known_at"))
        observed = day(raw.get("as_of"))
        if not known or not observed or known >= cutoff or observed > known:
            rejected.append({"ticker": raw.get("ticker"), "reason": "missing_or_future_availability"})
            continue
        ticker = str(raw.get("ticker") or "").upper()
        if not ticker or raw.get("eligible") is False or raw.get("identity_status") != "verified":
            rejected.append({"ticker": ticker, "reason": "identity_not_verified_or_ineligible"})
            continue
        # Inputs cannot be carried forward indefinitely.
        factor_dates = raw.get("factor_dates") or {}
        if any(not day(factor_dates.get(f, observed)) or (cutoff - day(factor_dates.get(f, observed))).days > protocol["max_age_days"][f]
               for f in protocol["required"]):
            continue
        previous = selected.get(ticker)
        if previous is None or str(raw["known_at"]) > str(previous["known_at"]):
            selected[ticker] = {**raw, "ticker": ticker}
    return score_rows(list(selected.values()), protocol), rejected


def targets(rows, variant="long_only", protocol=None, borrow=None):
    protocol = protocol or BASELINE
    p = protocol["portfolio"]
    eligible = [r for r in rows if r.get("strategy_score") is not None and r.get("eligible") is not False]
    eligible.sort(key=lambda r: (-r["strategy_score"], r["ticker"]))
    count = min(p["max_names"], max(1, math.ceil(len(eligible) * p["selection_fraction"])))
    longs = eligible[:count]
    weight = min(p["max_name_weight"], 1 / len(longs)) if longs else 0
    weights = {r["ticker"]: weight for r in longs}
    abstentions = []
    if variant == "xbi_hedged" and weights:
        weights[p["hedge"]] = -sum(weights.values())
    elif variant == "long_short":
        long_set = set(weights)
        shorts = sorted((r for r in eligible if r["ticker"] not in long_set), key=lambda r: (r["strategy_score"], r["ticker"]))[:count]
        for row in shorts:
            loan = (borrow or {}).get(row["ticker"], {})
            if loan.get("available") is not True or number(loan.get("apr")) is None or number(loan.get("apr")) < 0:
                abstentions.append({"ticker": row["ticker"], "reason": "no_dated_borrow_evidence"})
            else:
                weights[row["ticker"]] = -min(p["max_name_weight"], 1 / max(len(shorts), 1))
    return weights, abstentions


def performance(returns):
    if not returns or any(v is None for v in returns):
        return {"status": "incomplete_marks", "observations": len(returns)}
    if any(v <= -1 for v in returns):
        return {"status": "insolvent_account", "observations": len(returns), "total_return": -1,
                "max_drawdown": -1}
    nav, peak, drawdown = 1.0, 1.0, 0.0
    for value in returns:
        nav *= 1 + value
        peak = max(nav, peak)
        drawdown = min(drawdown, nav / peak - 1)
    vol = statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None
    mean = statistics.mean(returns) * 252
    return {"status": "measured", "observations": len(returns), "total_return": nav - 1,
            "cagr": nav ** (252 / len(returns)) - 1 if nav > 0 else -1,
            "volatility": vol, "sharpe": mean / vol if vol else None, "max_drawdown": drawdown,
            "worst_session": min(returns), "best_session": max(returns)}


def backtest(observations, marks, protocol=None):
    """Close-to-close simulation. Feature clocks precede each rebalance date.

    Each mark supplies a total_return for that session, plus dated borrow.
    Missing marks invalidate the affected account series, never erase a liability.
    """
    protocol = protocol or BASELINE
    by_day = {}
    for raw in marks:
        when = str(raw.get("date") or "")[:10]
        if day(when):
            by_day.setdefault(when, {})[raw["ticker"]] = raw
    dates = sorted(by_day)
    variants = []
    for variant in ("long_only", "xbi_hedged", "long_short", "eligible_universe", "xbi"):
        weights, daily, events = {}, [], []
        previous_month, prior_day = None, None
        for when in dates:
            data = by_day[when]
            rows, rejected = available_rows(observations, when, protocol)
            month = when[:7]
            turnover = 0.0
            # New targets earn returns from the NEXT session, so a close-based
            # selection cannot claim the same close-to-close return.
            missing = [t for t, w in weights.items() if w and number(data.get(t, {}).get("total_return")) is None]
            gross = None if missing else sum(w * float(data[t]["total_return"]) for t, w in weights.items())
            elapsed = (day(when) - day(prior_day)).days if prior_day else 1
            carry = 0.0
            for ticker, weight in weights.items():
                if weight >= 0:
                    continue
                apr = protocol["costs"]["hedge_borrow_apr"] if ticker == protocol["portfolio"]["hedge"] else number(data.get(ticker, {}).get("borrow_apr"))
                if apr is None or apr < 0:
                    missing.append(ticker + ":borrow")
                else:
                    carry += abs(weight) * apr * elapsed / 365
            ret = gross - carry if gross is not None and not missing else None
            if ret is not None and 1 + ret > 0:
                weights = {t: w * (1 + float(data[t]["total_return"])) / (1 + ret) for t, w in weights.items()}
            if month != previous_month and not missing:
                loans = {t: {"available": r.get("borrow_available") is True, "apr": number(r.get("borrow_apr"))} for t, r in data.items()}
                if variant == "eligible_universe":
                    names = [r["ticker"] for r in rows if r.get("strategy_score") is not None]
                    new = {t: min(protocol["portfolio"]["max_name_weight"], 1 / len(names)) for t in names}
                    abstentions = []
                elif variant == "xbi":
                    new = {protocol["portfolio"]["hedge"]: 1.0} if protocol["portfolio"]["hedge"] in data else {}
                    abstentions = []
                else:
                    new, abstentions = targets(rows, variant, protocol, loans)
                # Every held target needs a dated mark at the decision close.
                unavailable = [t for t in new if number(data.get(t, {}).get("total_return")) is None]
                if unavailable:
                    events.append({"date": when, "reason": "missing_entry_mark", "tickers": unavailable})
                else:
                    investable = 1.0
                    cost_rate = protocol["costs"]["one_way_bps"] / 10000
                    for _ in range(30):
                        turnover = sum(abs(investable * new.get(t, 0) - weights.get(t, 0)) for t in set(new) | set(weights))
                        investable = 1 - turnover * cost_rate
                    weights = new
                    previous_month = month
                events.extend({"date": when, **r} for r in abstentions)
            # Costs are paid from the account at the decision close. Solve for
            # the investable fraction so target weights use NAV after fees.
            cost_rate = protocol["costs"]["one_way_bps"] / 10000
            costs = turnover * cost_rate
            net = (1 + ret) * (1 - costs) - 1 if ret is not None else None
            daily.append({"date": when, "return": net, "gross_return": gross,
                          "cost": costs + carry, "turnover": turnover,
                          "gross_exposure": sum(abs(w) for w in weights.values()),
                          "net_exposure": sum(weights.values()), "unpriced_liabilities": missing})
            prior_day = when
        active = any(r["gross_exposure"] > 0 for r in daily)
        metrics = performance([r["return"] for r in daily]) if active else {"status": "no_eligible_observations", "observations": len(daily)}
        if active:
            metrics.update(turnover=sum(r["turnover"] for r in daily),
                           cost_fraction_sum=sum(r["cost"] for r in daily))
        variants.append({"id": variant, "metrics": metrics, "daily": daily, "events": events})
    return {"protocol_id": protocol["id"], "protocol_sha256": checksum(protocol),
            "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
            "variants_tested": 5 if dates else 0, "variants_registered": 5,
            "status": "exploratory" if dates else "awaiting_dated_inputs", "variants": variants,
            "validation": {"status": "not_validated", "reason": "Independent holdout and forward outcomes required; published exploratory dates are not a holdout."}}


def portfolio_risk(rows, weights, capital, marks):
    """Report missing risk inputs alongside measured concentration and stresses."""
    features = {r["ticker"]: r for r in rows}
    latest = {}
    for mark in sorted(marks, key=lambda r: str(r.get("date", ""))):
        latest[mark["ticker"]] = mark
    positions = []
    groups = {}
    for ticker, weight in weights.items():
        row, mark = features.get(ticker, {}), latest.get(ticker, {})
        adv = number(mark.get("dollar_volume_20d"))
        runway = number(row.get("cash_runway_months"))
        indication = row.get("indication") or "Unclassified"
        groups[indication] = groups.get(indication, 0) + abs(weight)
        positions.append({"ticker": ticker, "weight": weight, "dollar_volume_20d": adv,
                          "days_to_exit_at_one_percent_adv": abs(weight)*capital/(adv*.01) if adv and adv > 0 else None,
                          "cash_runway_months": runway, "next_catalyst": row.get("next_catalyst"),
                          "missing": [k for k, v in {"liquidity": adv, "cash_runway": runway,
                                                       "clinical_catalyst": row.get("next_catalyst")}.items() if v is None]})
    return {"gross_exposure": sum(abs(w) for w in weights.values()), "net_exposure": sum(weights.values()),
            "largest_name": max((abs(w) for w in weights.values()), default=0),
            "indication_exposure": groups, "positions": positions,
            "stress_assumptions": {"long_loss": .7, "short_price_increase": 3.0},
            "combined_tail_stress": -sum(w*.7 if w>0 else abs(w)*3 for w in weights.values()),
            "status": "incomplete_inputs" if not positions or any(r["missing"] for r in positions) else "measured_inputs"}


def paper_snapshot(rows, as_of, protocol=None, prices=None, previous=None):
    """Prepare a paper rebalance; quotes alone never create observed fills."""
    protocol = protocol or BASELINE
    weights, abstentions = targets(rows, "long_only", protocol)
    previous = previous or {}
    prior = previous.get("target_weights", {})
    orders = []
    for ticker in sorted(set(weights) | set(prior)):
        delta = weights.get(ticker, 0) - prior.get(ticker, 0)
        if abs(delta) < 1e-10:
            continue
        mark = (prices or {}).get(ticker)
        orders.append({"ticker": ticker, "weight_change": round(delta, 8),
                       "notional": round(delta * protocol["portfolio"]["capital"], 2),
                       "status": "awaiting_simulated_fill", "reference_mark": mark,
                       "observed_fill": False})
    return {"id": checksum({"as_of": as_of, "protocol": checksum(protocol), "weights": weights})[:20],
            "as_of": as_of, "protocol_id": protocol["id"], "protocol_sha256": checksum(protocol),
            "status": "proposed_rebalance", "capital_basis": "hypothetical", "initial_capital": protocol["portfolio"]["capital"],
            "target_weights": weights, "cash_weight": round(1 - sum(weights.values()), 8),
            "orders": orders, "positions": [], "realized_pnl": None, "total_return": None,
            "abstentions": abstentions, "independent_outcomes": 0, "authority": protocol["authority"]}


def read_paper(path):
    path = Path(path)
    events = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()] if path.exists() else []
    previous = None
    for event in events:
        if event.get("previous_sha256") != (checksum(previous) if previous else None):
            raise ValueError("Paper ledger hash chain is invalid")
        previous = event
    return events


def append_paper(path, snapshot):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.close(descriptor)
        prior = read_paper(path)
        if any(r["id"] == snapshot["id"] for r in prior):
            return False
        if prior and snapshot["as_of"] < prior[-1]["as_of"]:
            raise ValueError("Paper events cannot be appended before the last recorded date")
        event = {**snapshot, "previous_sha256": checksum(prior[-1]) if prior else None}
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
        return True
    finally:
        lock.unlink(missing_ok=True)
