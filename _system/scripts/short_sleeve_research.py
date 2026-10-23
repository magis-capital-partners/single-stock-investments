"""Aggregate portfolio-NAV scenarios from frozen local reverse-split evidence.

No network or broker access. Individual prices and trade records never publish.
The historical price study and the modeled net portfolio are separate outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

RUN = "20261013T224003582762Z"
HORIZONS = (1, 2, 5, 10, 20)
NAVS = (10_000_000,)
WEIGHTS = (25, 50, 100)
VERIFIED = {"primary_schedule_matched", "structured_corporate_action"}
SHORT_CREDIT_TIERS = ((100_000, 1_000_000, .0263), (1_000_000, 3_000_000, .0338), (3_000_000, None, .0363))
FINANCING = {
    "plan": "IBKR Pro USD", "as_of": "2026-10-19", "benchmark_annual": .0388,
    "non_interest_bearing_collateral": 100_000, "external_short_collateral": 100_000,
    "external_basis": "The first $100k band is assumed consumed by other USD shorts. A minimum $100k external balance is used; unknown higher account tiers could increase the marginal credit.",
    "tiers": [{"above": lo, "up_to": hi, "annual_rate": rate} for lo, hi, rate in SHORT_CREDIT_TIERS],
    "basis": "Current published rates applied throughout as a financing sensitivity, not historical paid interest. Other USD shorts consume the first $100k band; other cash credit/debit interest is excluded.",
    "sources": ["https://www.interactivebrokers.com/en/pricing/short-sale-cost.php",
                "https://www.interactivebrokers.com/en/accounts/fees/interestPaid_Example2.php",
                "https://www.interactivebrokers.com/en/trading/margin-calculation-details.php"],
}


def annual_short_credit(collateral, nav):
    """Tiered USD short-stock-collateral credit, not interest on total NAV."""
    factor = min(1., max(0., nav)/100_000)
    return factor*sum(max(0., min(collateral, hi if hi is not None else collateral)-lo)*rate
                      for lo, hi, rate in SHORT_CREDIT_TIERS)


def stats(values):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"n": 0}
    mean, sd = float(a.mean()), float(a.std())
    losses = a[a <= np.quantile(a, .05)]
    gains, lost = float(a[a > 0].sum()), float(-a[a < 0].sum())
    return {"n": len(a), "mean": mean, "median": float(np.median(a)), "sd": sd,
            "win_rate": float((a > 0).mean()), "best": float(a.max()), "worst": float(a.min()),
            "p05": float(np.quantile(a, .05)), "p25": float(np.quantile(a, .25)),
            "p75": float(np.quantile(a, .75)), "p95": float(np.quantile(a, .95)),
            "es95": float(-losses.mean()), "profit_factor": gains / lost if lost else None,
            "skew": float(np.mean(((a-mean)/sd)**3)) if sd else None,
            "excess_kurtosis": float(np.mean(((a-mean)/sd)**4)-3) if sd else None}


def margin(shares, price, house=1.):
    """Hypothetical equity requirement; sale proceeds are not added again."""
    floor = max(2.5*shares, price*shares) if price < 5 else max(5*shares, .3*price*shares)
    return max(floor, house*shares*price)


def commission(shares, price):
    return min(max(1., .005*shares), .01*shares*price) if shares > 0 else 0.


def settlement(day, calendar):
    lag = 1 if day >= "2024-05-28" else 2
    i = int(np.searchsorted(calendar, day, side="right")) + lag - 1
    return calendar[i]


def summary(pnl, initial, days):
    equity = initial + np.cumsum(pnl)
    prior = np.r_[initial, equity[:-1]]
    returns = np.divide(pnl, prior, out=np.zeros_like(pnl), where=prior > 0)
    peaks = np.maximum.accumulate(np.r_[initial, equity])[1:]
    drawdown = equity/peaks-1
    sd = float(returns.std())
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0)**2)))
    years = (date.fromisoformat(days[-1])-date.fromisoformat(days[0])).days/365.2425
    cagr = float((equity[-1]/initial)**(1/years)-1) if equity[-1] > 0 and min(equity) > 0 else None
    dd = float(drawdown.min())
    underwater, longest = 0, 0
    for d in drawdown:
        underwater = underwater+1 if d < -1e-12 else 0
        longest = max(longest, underwater)
    return {"ending_nav": float(equity[-1]), "net_pnl": float(pnl.sum()), "total_return": float(pnl.sum()/initial),
            "cagr": cagr, "max_drawdown": dd, "calmar": cagr/abs(dd) if dd < 0 and cagr is not None else None,
            "annual_volatility": sd*math.sqrt(252), "sharpe": float(returns.mean()/sd*math.sqrt(252)) if sd else None,
            "sortino": float(returns.mean()/downside*math.sqrt(252)) if downside else None,
            "worst_day": float(returns.min()), "best_day": float(returns.max()),
            "ulcer_index": float(np.sqrt(np.mean(drawdown**2))), "longest_drawdown_sessions": longest,
            "ruined": bool(min(equity) <= 0)}, equity, drawdown


def load_evidence(root):
    import exchange_calendars as xc
    ledger = root/"_system/data/reverse_splits"
    source = ledger/f"local/expansion/expansion_v2/runs/{RUN}"
    quote = ledger/f"local/execution_research/{RUN}__quotes_v1"
    events, actions = {}, defaultdict(dict)
    for part in sorted((source/"event_outcomes").glob("*.jsonl")):
        for line in part.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            events[e["event_id"]] = e
            if e["verification"] in VERIFIED and e.get("ratio"):
                actions[e.get("database_ticker", e["ticker"])][e["ex_date"]] = float(e["ratio"])
    targets = json.loads((quote/"targets.local.json").read_text())
    observations = json.loads((quote/"observations.local.json").read_text())
    cost_values, quoted_targets, quote_ages = [], [], []
    for t in targets:
        obs = observations.get(t["key"], {})
        a = (obs.get("bbo-1s/open/1") or obs.get("mbp-10/open/1") or {}).get("book")
        z = (obs.get("bbo-1s/close/-1") or obs.get("mbp-10/close/-1") or {}).get("book")
        if a and z and a["mid"] > 0:
            cost_values.append(((a["ask"]-a["bid"])+(z["ask"]-z["bid"]))/2/a["mid"])
            quoted_targets.append(t)
            quote_ages.extend([a["age_seconds"], z["age_seconds"]])
    expansion = json.loads((ledger/"expansion_summary.json").read_text())
    borrow = next(r for r in expansion["current_borrow_sensitivities"]["populations"] if r["population"] == "one_day_verified_names")
    # Spread quantiles plus the measured full-population mean displayed-depth cost.
    legacy = json.loads((ledger/"portfolio_research.json").read_text())
    depth = legacy["full_sample_cost_outcomes"]["costs"]["depth"]
    cases = [{"id": key, "label": label, "execution_fraction": float(np.quantile(cost_values, q))+depth,
              "spread_fraction": float(np.quantile(cost_values, q)), "depth_fraction": depth,
              "borrow_annual": borrow[b], "spread_quantile": q}
             for key, label, q, b in [("bear", "Bear", .75, "p90_annual_fraction"),
                                      ("base", "Base", .50, "mean_annual_fraction"),
                                      ("bull", "Bull", .25, "median_annual_fraction")]]
    cal = xc.get_calendar("XNYS", start="2018-03-01", end="2027-01-15")
    calendar = [d.date().isoformat() for d in cal.sessions]
    days = [d for d in calendar if "2018-05-01" <= d <= "2026-10-13"]
    conn = sqlite3.connect((source/"prices.sqlite").resolve().as_uri()+"?mode=ro&immutable=1", uri=True)
    prices, nominal = {}, {}
    for ticker in sorted({t["ticker"] for t in targets}):
        prices[ticker] = {d: {"open": op, "close": cl} for d, op, cl in conn.execute(
            "SELECT date,MAX(CASE WHEN point='open' THEN price END),MAX(CASE WHEN point='close' THEN price END) FROM official_auction_prices WHERE ticker=? GROUP BY date", (ticker,))}
        nominal[ticker] = {d: (p, v) for d, p, v in conn.execute(
            "SELECT p.date,p.close,p.volume FROM prices_daily p JOIN price_provenance v USING(ticker,date) WHERE p.ticker=? AND v.nominal=1", (ticker,))}
    conn.close()
    records = []
    for t in targets:
        if t["key"] != t["event_id"]:
            continue
        e = events[t["event_id"]]
        i = calendar.index(t["date"])
        volumes = []
        for day in calendar[i-20:i]:
            _, v = nominal.get(t["ticker"], {}).get(day, (None, None))
            factor = math.prod(r for ex, r in actions[t["ticker"]].items() if day < ex <= t["date"])
            if v is not None and v >= 0:
                volumes.append(v*factor)
        records.append({**t, "event": e, "adv": sum(volumes)/20 if volumes else 0., "calendar_i": i})
    settlements = {d: calendar[i+(1 if d >= "2024-05-28" else 2)] for i, d in enumerate(calendar[:-2])}
    return {"records": records, "events": events, "actions": actions, "prices": prices, "settlements": settlements,
            "days": days, "calendar": calendar, "cases": cases, "borrow": borrow,
            "legacy": legacy, "expansion": expansion,
            "calibration": {"paired_quotes": len(cost_values), "target_events": len(targets),
                            "quoted_issuers": len({t["issuer"] for t in quoted_targets}),
                            "quote_dates": [min(t["date"] for t in quoted_targets), max(t["date"] for t in quoted_targets)],
                            "datasets": dict(Counter(t["dataset"] for t in quoted_targets)),
                            "spread_mean": float(np.mean(cost_values)),
                            "spread_median": float(np.median(cost_values)),
                            "quote_age_p90_seconds": float(np.quantile(quote_ages, .9)),
                            "quote_age_max_seconds": max(quote_ages),
                            "depth_fraction": depth, "depth_reference_notional": 500,
                            "all_500_costs": legacy["full_sample_cost_outcomes"]["costs"],
                            "borrow_as_of": expansion["current_borrow_sensitivities"]["as_of"]}}


def price_groups(evidence):
    """Observed endpoint distributions: missing endpoints remain in denominators."""
    groups = []
    for h in HORIZONS:
        for cohort, title in [("primary", "All priced splits"), ("eligible", "Known before entry · unrestricted"), ("fundamental", "Fundamental score ≥60")]:
            values, issuers = [], set()
            population = [r for r in evidence["records"] if cohort in r["cohorts"]]
            if cohort == "primary" and h != 2:
                population = [{"event": e, "issuer": e["issuer"]} for e in evidence["events"].values()
                              if e.get("verification") in VERIFIED and any(o["cohort"] == f"ex_plus_1_h{h}" and o.get("gross_short_return") is not None for o in e["outcomes"])]
            for r in population:
                o = next((o for o in r["event"]["outcomes"] if o["cohort"] == f"ex_plus_1_h{h}"), None)
                if o and o.get("gross_short_return") is not None:
                    ret = o["gross_short_return"]
                elif h == 2:
                    end = evidence["calendar"][r["calendar_i"]+1]
                    p = evidence["prices"][r["ticker"]].get(end, {}).get("close")
                    # Do not infer the share basis across a further action in this new diagnostic.
                    if not p or any(r["date"] < ex <= end for ex in evidence["actions"][r["ticker"]]):
                        continue
                    ret = 1-p/r["open"]
                else:
                    continue
                values.append(ret)
                issuers.add(r["issuer"])
            edges = [-20, -5, -2, -1, -.5, -.2, -.1, 0, .1, .2, .5, 1.000001]
            counts = np.histogram(values, bins=edges)[0].tolist()
            groups.append({"horizon": h, "id": cohort, "label": title, "population": len(population),
                           "issuers": len(issuers), "missing": len(population)-len(values),
                           **stats(values), "histogram": {"edges": edges, "counts": counts}})
    return groups


def replay(evidence, nav, bps, horizon, scenario, capacity=True):
    days, calendar = evidence["days"], evidence["calendar"]
    settlements = evidence["settlements"]
    by_day = defaultdict(list)
    for r in evidence["records"]:
        if "eligible" in r["cohorts"]:
            by_day[r["date"]].append(r)
    pnl = np.zeros(len(days)); active = []; sparse = []; closed_returns = []; skip = Counter()
    entered, partial, delayed, missing_marks = 0, 0, 0, 0
    entry_notional, cost_total, carry_total, commission_total = 0., 0., 0., 0.
    credit_total = 0.; settled_collateral = defaultdict(float)

    def record_settled_collateral(first, last, collateral):
        for offset in range(max(0, (last-first).days)):
            settled_collateral[first+timedelta(days=offset)] += collateral
    max_margin = max_collateral = max_gross = 0.; min_headroom = nav
    max_stress_margin = max_stress_reserve = 0.
    target = nav*bps/10000
    equity = nav
    # Borrow billing is on settled calendar dates; weekend accrual posts on the next session.
    previous_day = date.fromisoformat(days[0])-timedelta(days=1)
    for i, day in enumerate(days):
        today = date.fromisoformat(day); daily = 0.
        for r in sorted(by_day[day], key=lambda r: (-r["adv"]*r["open"], r["issuer"])):
            if equity <= 0:
                skip["insolvent"] += 1; continue
            if len(active) >= 3 or any(p["issuer"] == r["issuer"] for p in active):
                skip["name_or_overlap_limit"] += 1; continue
            desired = math.floor(target/r["open"])
            q = min(desired, math.floor(.001*r["adv"])) if capacity else desired
            if q < 1 or q*r["open"] < 100:
                skip["minimum_or_capacity"] += 1; continue
            planned_i = r["calendar_i"]+horizon-1
            if planned_i >= len(calendar):
                skip["holding_period_incomplete"] += 1; continue
            notional = q*r["open"]
            execution = notional*scenario["execution_fraction"]/2
            comm = commission(q, r["open"])
            daily -= execution+comm
            p = {"ticker": r["ticker"], "issuer": r["issuer"], "q": float(q), "mark": r["open"],
                 "entry": day, "due": calendar[planned_i], "settled": settlements[day],
                 "exit_settlement": settlements[calendar[planned_i]], "original": notional,
                 "pnl": -execution-comm, "billing_mark": r["open"], "basis_uncertain": False}
            active.append(p); entered += 1; partial += int(q < desired)
            entry_notional += notional; cost_total += execution; commission_total += comm
        # Peak modeled requirement includes the entry and closing positions, before covers.
        req = sum(margin(p["q"], p["mark"]) for p in active)
        coll = sum(p["q"]*math.ceil(1.02*p["mark"]) for p in active)
        gross = sum(p["q"]*p["mark"] for p in active)
        opening_req, opening_coll, opening_gross = req, coll, gross
        opening_shock_req = sum(margin(p["q"], p["mark"]*3, house=2.) for p in active)
        req = coll = gross = shock_req = 0.
        remaining = []
        for p in active:
            for ex, factor in evidence["actions"][p["ticker"]].items():
                if ex == day and p["entry"] < day:
                    p["q"] *= factor; p["mark"] /= factor; p["billing_mark"] /= factor
            close = evidence["prices"][p["ticker"]].get(day, {}).get("close")
            if close and close > 0:
                change = p["q"]*(p["mark"]-close)
                daily += change; p["pnl"] += change; p["mark"] = close
            else:
                missing_marks += 1
            end_billing = p["exit_settlement"] if day == p["due"] and close else settlements[day]
            first = max(date.fromisoformat(p["settled"]), previous_day+timedelta(days=1))
            last = min(today+timedelta(days=1), date.fromisoformat(end_billing))
            billed = max(0, (last-first).days)
            billing_collateral = p["q"]*math.ceil(1.02*p["billing_mark"])
            fee = billing_collateral*scenario["borrow_annual"]*billed/360
            record_settled_collateral(first, last, billing_collateral)
            daily -= fee; p["pnl"] -= fee; carry_total += fee; p["billing_mark"] = p["mark"]
            req += margin(p["q"], p["mark"])
            coll += p["q"]*math.ceil(1.02*p["mark"])
            gross += p["q"]*p["mark"]
            shock_req += margin(p["q"], p["mark"]*3, house=2.)
            if day >= p["due"] and close:
                # All settled borrowing days are invoiced even if settlement is after the cover.
                cover_settlement = settlements[day]
                extra = max(0, (date.fromisoformat(cover_settlement)-max(today+timedelta(days=1), date.fromisoformat(p["settled"]))).days)
                final_fee = p["q"]*math.ceil(1.02*p["mark"])*scenario["borrow_annual"]*extra/360
                record_settled_collateral(max(today+timedelta(days=1), date.fromisoformat(p["settled"])),
                                          date.fromisoformat(cover_settlement), p["q"]*math.ceil(1.02*p["mark"]))
                execution = p["original"]*scenario["execution_fraction"]/2
                comm = commission(p["q"], close)
                daily -= execution+comm+final_fee; p["pnl"] -= execution+comm+final_fee
                cost_total += execution; commission_total += comm; carry_total += final_fee
                closed_returns.append(p["pnl"]/p["original"])
                delayed += int(day > p["due"])
            else:
                remaining.append(p)
        # One account-wide tier calculation per settled calendar day. Closed
        # trade positions remain in this ledger until their cover settles.
        credit = 0.
        for offset in range(1, (today-previous_day).days+1):
            balance = settled_collateral.get(previous_day+timedelta(days=offset), 0.)
            external = FINANCING["external_short_collateral"]
            credit += (annual_short_credit(external+balance, nav)-annual_short_credit(external, nav))/360
        credit_total += credit; daily += credit
        active = remaining; pnl[i] = daily; equity += daily
        closing_stress_reserve = 2*gross+shock_req
        req, coll, gross = max(req, opening_req), max(coll, opening_coll), max(gross, opening_gross)
        max_margin = max(max_margin, req); max_collateral = max(max_collateral, coll); max_gross = max(max_gross, gross)
        max_stress_margin = max(max_stress_margin, opening_shock_req, shock_req)
        max_stress_reserve = max(max_stress_reserve, 2*opening_gross+opening_shock_req, closing_stress_reserve)
        min_headroom = min(min_headroom, equity-req)
        if daily or req or coll:
            sparse.append([i, round(daily/nav, 10), round(req/nav, 8), round(coll/nav, 8)])
        previous_day = today
    financials, equity_curve, dd = summary(pnl, nav, days)
    monthly = []
    for i, day in enumerate(days):
        if i == len(days)-1 or days[i+1][:7] != day[:7]:
            monthly.append([day, round(float(equity_curve[i]/nav-1), 8), round(float(dd[i]), 8)])
    annual = []
    for year in sorted({d[:4] for d in days}):
        ix = [i for i, d in enumerate(days) if d.startswith(year)]
        start = nav if ix[0] == 0 else equity_curve[ix[0]-1]
        annual.append([year, float(pnl[ix].sum()/start) if start > 0 else None])
    return {"nav": nav, "bps": bps, "horizon": horizon, "scenario": scenario["id"], "capacity": capacity,
            "metrics": {**financials, "entered": entered, "closed": len(closed_returns), "partial": partial,
                        "delayed_covers": delayed, "unresolved": len(active), "missing_mark_days": missing_marks,
                        "idle_sessions": len(days)-sum(1 for row in sparse if row[1]),
                        "trades_per_year": entered/((date.fromisoformat(days[-1])-date.fromisoformat(days[0])).days/365.2425),
                        "mean_actual_weight": entry_notional/entered/nav if entered else 0.,
                        "peak_margin": max_margin/nav, "peak_collateral": max_collateral/nav,
                        "peak_gross": max_gross/nav, "minimum_headroom": min_headroom/nav,
                        "stress_margin_200": max_stress_margin/nav, "stress_reserve_200": max_stress_reserve/nav,
                        "execution_cost": cost_total, "commission_cost": commission_total, "borrow_cost": carry_total,
                        "proceeds_interest": credit_total, "net_borrow_cost": carry_total-credit_total,
                        "net_pnl_before_proceeds_interest": float(pnl.sum())-credit_total,
                        "trade_stats": stats(closed_returns), "skipped": dict(skip)},
            "series": sparse, "monthly": monthly, "annual": annual}


def reconciliation(root, evidence, groups):
    checks = []
    for group in (g for g in groups if g["id"] == "primary" and g["horizon"] != 2):
        old = next(r for r in evidence["expansion"]["event_study"]
                   if r["tier"] == "verified_actions" and r["cohort"] == f"ex_plus_1_h{group['horizon']}")
        matched = old["events"] == group["n"] and math.isclose(old["mean_gross_short_return"], group["mean"], abs_tol=1e-12)
        if not matched:
            raise ValueError("Observed price cohort does not reconcile to the published event study")
        checks.append({"horizon": group["horizon"], "events": group["n"], "mean": group["mean"], "matched": matched})
    legacy = next(c for c in evidence["legacy"]["cases"] if c["case"]["id"] == "eligible_close")
    path = root/f"_system/data/reverse_splits/local/portfolio_research/{RUN}__portfolio_v1/eligible_close.local.json"
    cached = json.loads(path.read_text(encoding="utf-8"))
    days = [r["date"] for r in cached["daily"]]
    pnl = np.array([r["pnl"] for r in cached["daily"]])
    if not math.isclose(float(pnl.sum()), legacy["portfolio"]["net_pnl"], abs_tol=1e-6):
        raise ValueError("Legacy cash P&L does not reproduce the published account")
    rebased, _, _ = summary(pnl, NAVS[0], days)
    policies = []
    # Compare against the policies published by this checkout, even when the
    # licensed frozen evidence lives in a different source checkout.
    published_ledger = Path(__file__).resolve().parents[2]/"_system/data/reverse_splits"
    for name in ("net_edge_research.json", "net_edge_research_v3.json"):
        p = published_ledger/name
        if p.exists():
            doc = json.loads(p.read_text(encoding="utf-8"))
            selected = next(c for c in doc["cases"] if c.get("id") == doc["primary_case"])
            policies.append({"file": name, "primary_case": doc["primary_case"], "trades": selected["trades"]})
    return {"price_checks": checks, "other_policies": policies,
            "legacy": {"case": "eligible_close", "trades": legacy["trades"],
                       "initial_nav": legacy["portfolio"]["initial_equity"],
                       "net_pnl": legacy["portfolio"]["net_pnl"], "cagr": legacy["portfolio"]["cagr"],
                       "max_drawdown": legacy["portfolio"]["max_drawdown"],
                       "mean_notional": sum(t["gross"] for t in cached["trades"])/len(cached["trades"]),
                       "spread_fraction": legacy["components"]["spread"]["rog"],
                       "depth_fraction": legacy["components"]["depth"]["rog"]},
            "same_tickets_on_10m": rebased,
            "differences": [
                "The earlier $50k account uses event-specific continuous quotes, displayed-book sizing, trading-status checks and entry-margin limits. Its 115 accepted trades have lower average spread/depth costs than the broad event population.",
                "This illustration uses opening/closing auction price benchmarks, fixed starting-$10m ticket sizes, an aggregate spread/depth sensitivity and optional prior-volume caps. It does not replay the earlier account's fills or admission decisions.",
                "Rescaling the same historical cash P&L to $10m preserves dollars and trades. Increasing orders to $25k-$100k requires a new fill/capacity test and cannot be obtained by multiplying the old CAGR.",
                "RSI-2/RSI-3 use different decision clocks and stricter net-edge filters. Zero admitted trades in their primary policies is not evidence of executable alpha at the new ticket sizes.",
            ]}


def build(root):
    evidence = load_evidence(root)
    models = []
    for nav in NAVS:
        for bps in WEIGHTS:
            for h in HORIZONS:
                for capacity in (True, False):
                    for case in evidence["cases"]:
                        models.append(replay(evidence, nav, bps, h, case, capacity))
    ledger = root/"_system/data/reverse_splits"
    groups = price_groups(evidence)
    return {"schema_version": "short_sleeve.v1", "as_of": "2026-10-13", "research_only": True, "authority": "none",
            "aggregate_only": True, "days": evidence["days"], "navs": NAVS, "weights": WEIGHTS, "horizons": HORIZONS,
            "defaults": {"nav": NAVS[0], "bps": 25, "horizon": 1, "scenario": "base", "capacity": False},
            "cases": evidence["cases"], "calibration": evidence["calibration"], "groups": groups,
            "financing": FINANCING, "reconciliation": reconciliation(root, evidence, groups),
            "models": models, "method": {"sizing": "Fixed dollars equal to the selected fraction of starting total portfolio NAV; no reinvestment or core-portfolio return assumed.",
            "admissions": "Known-before-entry, observed SSR-unrestricted cohort; three concurrent issuers, whole shares, $100 minimum. Borrow is assumed available.",
            "capacity": "Capacity-aware sizing caps shares at 0.1% of prior 20-session verified venue ADV. Partial target sizing is not proof of a broker fill. Target-size mode removes that cap and is a hypothetical capacity upper bound.",
            "execution": "Broad-cohort listing-venue quote half-spread quartiles plus a $500-reference full-population mean depth cost. This mixed-sample sensitivity is not the prior account's event-specific execution model, an auction fill model, consolidated NBBO, or evidence of costs at $25k-$100k. Commissions are separate.",
            "borrow": "Current indicative fee percentiles for quoted reverse-split names, applied as explicit historical sensitivities. Rounded 102% collateral, actual settlement calendar, T+2/T+1 and weekend accrual. Not historical invoices or approved locates.",
            "proceeds_interest": "IBKR Pro USD short-credit tiers are applied once per account to settled rounded short collateral, including weekends until cover settlement. The first $100k earns zero. Current 2026-10-19 rates are held fixed as a sensitivity; historical IBKR rates are not reconstructed. The first $100k band is assumed used by other shorts; a minimum external collateral balance of $100k gives a conservative marginal credit. Trade statistics exclude this account-level credit.",
            "cash_funding": "Short-credit income is separate from borrow fees. Other long-cash interest, collateral top-up funding costs and core-account debit interest are excluded because settled account cash and financing history are unavailable. Net results are conditional on that funding assumption, not Michael's actual all-in IBKR financing.",
            "marks": "Daily official closing-auction marks; missing marks carry the last observed liability and are counted. A missing cover waits for an observed close, never a zero-price exit.",
            "margin": "Hypothetical 100% house floor plus FINRA per-share maintenance floors. Collateral is rounded 102% of current market value. Collateral and equity margin are separate views of financing, not amounts to add together.",
            "monte_carlo": "2,000 five-year paths resample historical month blocks including all boundary sessions, jointly retaining daily net P&L, margin and collateral, including idle sessions. Fixed starting-NAV position sizing. Conditional resampling, not a forecast or a simulation of unseen squeezes.",
            "core_portfolio": "All growth and risk statistics describe the incremental short sleeve against total starting NAV with the core portfolio held flat. Combined Michael-portfolio CAGR, covariance, drawdown and actual excess liquidity are unavailable without his daily portfolio and broker margin history.",
            "exits": "Fixed holding-period exits; no guaranteed stop-loss or profit-taking fill is assumed."},
            "sources": [{"file": name, "sha256": hashlib.sha256((ledger/name).read_bytes()).hexdigest()} for name in ["expansion_summary.json", "portfolio_research.json", "execution_realism.json"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    doc = build(args.source_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"Published {len(doc['models'])} aggregate scenarios; {args.out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
