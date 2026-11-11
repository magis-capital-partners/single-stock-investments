"""Evidence and diagnostics for the BTC context panel; no valuation authority."""
from __future__ import annotations

import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path

import btc_power_history as power
from btc_mining_economics import fee_adjusted_breakeven, reward_economics

HORIZON = date(2033, 12, 31)
Q2_URL = "https://horizonkinetics.com/app/uploads/Horizon-Kinetics-Q2-2026-Commentary-Final.pdf"
Q3_URL = "https://horizonkinetics.com/app/uploads/Horizon-Kinetics-Q3-2026-Commentary-Final.pdf"


def hk_references() -> dict:
    return {
        # Compatibility fields remain Q2. They are never silently reassigned.
        "model_2028": 270438.05, "supply_low": 150000, "supply_high": 250000,
        "current_all_in_commentary": 65000,
        "vintages": [
            {"id": "q2_2026", "label": "HK Q2 2026", "published": "2026-07",
             "url": Q2_URL, "pages": [32, 33, 34, 35, 36],
             "references": [
                 {"id": "q2_demand", "kind": "demand", "date": "2028-04-15", "value": 270438.05, "page": 32},
                 {"id": "q2_supply", "kind": "supply_band", "date": "2028-04-15", "low": 150000, "high": 250000, "page": 32},
                 {"id": "q2_cost", "kind": "production_cost", "date": "2028-04-15", "value": 130000, "page": 34},
                 {"id": "q2_sota", "kind": "sota_plus_25pct_return", "time_label": "Current at publication", "low": 117000, "high": 149000, "page": 34},
             ]},
            {"id": "q3_2026", "label": "HK Q3 2026", "published": "2026-11",
             "url": Q3_URL, "pages": [5, 6], "references": [
                 {"id": "q3_supply", "kind": "supply_reference", "date": "2028-04-15", "approximate": True,
                  "value": 130000, "low": 117000, "high": 149000, "page": 5},
                 {"id": "q3_demand", "kind": "demand_reference", "year": 2033, "approximate": True,
                  "value": 1000000, "page": 5, "date_precision": "year"},
             ]},
        ],
        "interpretation": "Q2 calls $117k–$149k current SOTA plus 25% return; Q3 uses the same endpoints for April 2028. Timing/basis reconciliation is unresolved. Preserve both vintages.",
        "hk_full_equation_available": False,
    }


def monthly_dates(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    points = {start, end}
    while cursor <= end:
        if cursor >= start:
            points.add(cursor)
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return sorted(points)


def demand_diagnostics(series: list[tuple[date, float]], as_of: date, fit_fn, price_fn) -> dict:
    sensitivity = []
    for origin in (date(2009, 1, 3), date(2011, 1, 1)):
        for start in (date(2011, 1, 1), date(2015, 1, 1), date(2020, 1, 1)):
            rows = [(d, p) for d, p in series if start <= d <= as_of]
            unconstrained = fit_fn(rows, origin=origin, constrain=False)
            sensitivity.append({"origin": origin.isoformat(), "window_start": start.isoformat(),
                                "fit": unconstrained,
                                "price_2033": price_fn(unconstrained, HORIZON)})
    holdouts = []
    for year in (2017, 2020, 2022, 2024):
        cutoff = date(year, 1, 1)
        target = cutoff + timedelta(days=365)
        if target > as_of:
            continue
        train = [(d, p) for d, p in series if d <= cutoff]
        actual = [(d, p) for d, p in series if cutoff < d <= target]
        if len(train) < 365 or not actual or (target - actual[-1][0]).days > 7:
            continue
        for constrained in (True, False):
            fitted = fit_fn(train, constrain=constrained)
            predicted = price_fn(fitted, actual[-1][0])
            if predicted is not None:
                holdouts.append({"cutoff": cutoff.isoformat(), "target": actual[-1][0].isoformat(),
                                 "fit_kind": "constrained" if constrained else "unconstrained",
                                 "k": fitted["k"], "prediction": round(predicted, 2),
                                 "actual": actual[-1][1],
                                 "absolute_error_pct": round(100 * abs(predicted / actual[-1][1] - 1), 2)})
    implied = []
    for origin in (date(2009, 1, 3), date(2011, 1, 1)):
        for endpoint in (date(2033, 1, 1), HORIZON):
            t1 = (date(2028, 4, 15) - origin).days / 365.25
            t2 = (endpoint - origin).days / 365.25
            k = math.log(1000000 / 270438.05) / math.log(t2 / t1)
            implied.append({"origin": origin.isoformat(), "illustrative_2033_date": endpoint.isoformat(), "k": round(k, 4)})
    return {"sensitivity": sensitivity, "one_year_holdouts": holdouts,
            "default_policy": "Existing constrained fit retained; free fit is diagnostic, not automatically promoted.",
            "hk_anchor_implied": {"values": implied, "hk_published_exponent": False,
                                  "note": "Illustrative calculation combining Q2 demand and Q3 approximate-year references from different vintages; not HK's equation. No fitted curve is attributed to HK."}}


def input_freshness(directory: Path, as_of: date, catalog: dict) -> dict:
    path = directory / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    records = {}
    for theme in manifest.get("themes", {}).values():
        records.update(theme.get("series", {}))
    rows = []
    for sid, label, threshold in (
        ("btc_spot_usd", "BTC spot", 7), ("btc_hash_rate_eh", "Network hashrate", 7),
        ("btc_difficulty", "Difficulty", 7), ("btc_avg_fee_per_block_usd", "Fees per block", 7),
        ("btc_all_in_cost_usd", "Production-cost reconstruction", 7),
        ("btc_cbeci_guess_jth", "Cambridge efficiency comparison", 30),
    ):
        p = directory / f"{sid}.csv"
        observations = []
        if p.exists():
            with p.open(encoding="utf-8", newline="") as stream:
                observations = [r["date"] for r in csv.DictReader(stream)
                                if r.get("date", "9999") <= as_of.isoformat() and r.get("value")]
        through = max(observations) if observations else None
        age = (as_of - date.fromisoformat(through)).days if through else None
        rec = records.get(sid, {})
        rows.append({"id": sid, "label": label, "observed_through": through, "age_days": age,
                     "max_age_days": threshold, "stale": age is None or age > threshold,
                     "refresh_error": rec.get("error"), "source": rec.get("source", sid + ".csv")})
    power_meta = power.metadata(as_of, directory)
    for sid, label, through, threshold in (
        ("asic_catalog", "ASIC specification review", catalog.get("as_of"), 90),
        ("electricity_proxy", "Industrial electricity proxy observation", power_meta["through"], 180),
    ):
        reviewed_after_snapshot = bool(through and through > as_of.isoformat())
        if reviewed_after_snapshot:
            through = None
        age = (as_of - date.fromisoformat(through)).days if through else None
        rows.append({"id": sid, "label": label, "observed_through": through, "age_days": age,
                     "max_age_days": threshold, "stale": age is None or age > threshold,
                     "reviewed_after_snapshot": reviewed_after_snapshot})
    return {"evaluated_on": as_of.isoformat(), "inputs": rows,
            "stale_count": sum(r["stale"] for r in rows),
            "note": "Observation dates survive failed refreshes. Browser also checks age at read time.",
            "cost_refresh": manifest.get("btc_cost_of_production", {}),
            "power_refresh": manifest.get("btc_power_history", {})}


def fee_context(path: Path, as_of: date, spot_series: list[tuple[date, float]],
                all_in: float, scenarios: dict, price_fn) -> dict:
    fees = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as stream:
            fees = [r for r in csv.DictReader(stream) if r.get("date", "9999") <= as_of.isoformat()]
    fees.sort(key=lambda r: r["date"])
    latest = fees[-1] if fees else None
    fee_usd = float(latest["value"]) if latest else None
    fee_day = date.fromisoformat(latest["date"]) if latest else None
    prices = [(d, p) for d, p in spot_series if fee_day and d <= fee_day]
    price = prices[-1][1] if prices else None
    # Do not convert an old dollar observation at today's price.
    dated_conversion = bool(price and fee_day and (fee_day - prices[-1][0]).days <= 7)
    fee_btc = fee_usd / price if dated_conversion else None
    available = fee_btc is not None
    baseline = fee_btc if available else 0.0
    curves = []
    for year in ("2028", "2032", "2033"):
        point = (scenarios.get("mixed_base") or {}).get(year)
        if not point:
            continue
        day = date.fromisoformat(point["date"])
        for label, amount in (("zero", 0.0), ("latest_rate_constant", baseline), ("high_fee_assumption", .25)):
            curves.append({"horizon": year, "date": day.isoformat(), "scenario": label,
                           **reward_economics(point["all_in_usd"], point["subsidy_btc"], amount, price_fn(day) or 0)})
    sub = 3.125 if as_of < date(2028, 4, 15) else (1.5625 if as_of < date(2032, 4, 20) else .78125)
    return {"available": available, "observed_on": latest["date"] if latest else None,
            "historical_data_note": "Current mined-block download is observed. Older committed history may include projected mempool estimates; no historical fee backtest is claimed.",
            "fee_usd_per_block": fee_usd, "fee_btc_per_block": fee_btc,
            "conversion_price_date": prices[-1][0].isoformat() if dated_conversion else None,
            "current_breakeven_usd": fee_adjusted_breakeven(all_in * 144 * sub, 144 * sub, 144 * (fee_usd or 0)) if available else None,
            "scenarios": curves,
            "assumptions": "144 blocks/day. Latest BTC fee rate held constant is a scenario, not a forecast; high case assumes 0.25 BTC/block. Future security revenue uses our constrained demand price, not HK's target. Missing fees are not labeled observed zero.",
            "issuance_note": "Fees transfer existing BTC. Production cost per issued coin is distinct from fee-adjusted revenue breakeven."}


def rig_comparison(catalog: dict, hash_eh: float, as_of: date, subsidy: float) -> dict:
    rows = []
    pue = float(catalog.get("pue", 1.1))
    for rig in catalog.get("models", []):
        if not rig.get("spec_source_url") or rig["release"] > as_of.isoformat():
            continue
        price_observations = [p for p in rig.get("price_observations", []) if p["date"] <= as_of.isoformat()]
        capex = float(price_observations[-1]["usd_per_th"]) if price_observations else float(rig["usd_per_th"])
        utilization = .95
        infrastructure = 5.0 if rig.get("cooling") == "hydro" else 2.0
        capital = capex + infrastructure
        annual_coins = 144 * subsidy * 365 / (hash_eh * 1e6) * utilization if hash_eh > 0 else 0
        if annual_coins <= 0:
            continue
        electricity = float(rig["j_th"]) * pue * .024 * .05 * 365 * utilization / annual_coins
        ancillary = electricity * .15
        depreciation = capital / 3 / annual_coins
        required_profit = capital * .25 / annual_coins
        value = electricity + ancillary + depreciation + required_profit
        rows.append({"id": rig["id"], "name": rig["name"], "source_url": rig["spec_source_url"],
                     "j_th_nameplate": rig["j_th"], "th_s": rig["th_s"], "watts": rig["watts"],
                     "cooling": rig.get("cooling"), "release": rig["release"],
                     "release_basis": rig.get("release_basis", "Legacy date assumption"),
                     "equipment_usd_per_th": capex, "price_status": "manufacturer_quote" if price_observations else "assumption",
                     "price_date": price_observations[-1]["date"] if price_observations else None,
                     "electricity_usd": round(electricity, 2), "ancillary_opex_usd": round(ancillary, 2),
                     "depreciation_usd": round(depreciation, 2), "required_profit_usd": round(required_profit, 2),
                     "all_in_usd": round(value - required_profit, 2), "plus_25pct_return_usd": round(value, 2),
                     "gap_to_hk_low_usd": round(value - 117000, 2), "gap_to_hk_high_usd": round(value - 149000, 2),
                     "sensitivities": {
                         "power_004_usd": round(value - .2 * (electricity + ancillary), 2),
                         "power_006_usd": round(value + .2 * (electricity + ancillary), 2),
                         "life_2years_usd": round(value + capital / 6 / annual_coins, 2),
                         "utilization_085_usd": round(electricity + ancillary + (depreciation + required_profit) * .95 / .85, 2),
                         "equipment_price_plus_50pct_usd": round(value + capex * .5 * (1 / 3 + .25) / annual_coins, 2),
                     }})
    return {"rigs": rows,
            "assumptions": {"electricity_usd_kwh": .05, "pue": pue, "utilization": .95,
                            "ancillary_opex_fraction_of_power": .15, "depreciation_years": 3,
                            "salvage_value": 0, "annual_return_on_installed_capital": .25,
                            "infrastructure_usd_per_th": {"air": 2, "hydro": 5}},
            "method": "Explicit capital schedule: electricity + ancillary cash opex + straight-line depreciation + 25% annual return on installed capital. No depreciation double count through the legacy 60% electricity gross-up.",
            "reconciliation": "Compare with Q2 current $117k–$149k; Q3 reuses those endpoints at April 2028. Neither rig identities nor full capital schedules are published. Remaining differences are not calibrated away.",
            "fleet_limitation": "Historical fleet weights are a hashrate-at-release survival proxy, not measured shipments. Compare Cambridge and 3/5/7-year survival sensitivities; adding catalog models is not evidence of market share."}
