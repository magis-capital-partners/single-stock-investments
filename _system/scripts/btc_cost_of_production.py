#!/usr/bin/env python3
"""Hauck / HK-style Bitcoin cost-of-production identities.

Context only. Never auto-inflates Lawrence base IRR.

Electricity per coin = (hashrate × fleet J/TH × 24h × $/kWh) / coins per day.
All-in = electricity / power_share (HK: power is ~60% of total).
Fleet J/TH is time-varying: CBECI consumption/hashrate, or ASIC vintage mix.
"""
from __future__ import annotations

import csv
import gzip
import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CRYPTO_DIR = ROOT / "_system" / "reference" / "market-data" / "crypto"
ASIC_PATH = CRYPTO_DIR / "asic_generations.json"
UA = "MarvinResearch/1.0 (crypto-panel)"
CBECI_URL = "https://cbeci.org/api/v1.0.5/download/data"
HOURS_PER_YEAR = 24.0 * 365.0  # CBECI annualises with 8.76 TWh per GW
BLOCKS_PER_DAY = 144.0
HALVING_2028 = date(2028, 4, 15)
HALVING_2032 = date(2032, 4, 20)
DEFAULT_POWER_SHARE = 0.60
DEFAULT_PREMIUM = 1.75
KWH_HK = 0.05
KWH_LOW = 0.04
KWH_HIGH = 0.06

SUBSIDY_BY_HALVING_INDEX = {
    0: 50.0,
    1: 25.0,
    2: 12.5,
    3: 6.25,
    4: 3.125,
    5: 1.5625,
    6: 0.78125,
}
HALVINGS = [
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
    HALVING_2028,
    HALVING_2032,
]


def _get_bytes(url: str, timeout: int = 60) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        return None


def load_asic_catalog(path: Path | None = None) -> dict:
    p = path or ASIC_PATH
    if not p.exists():
        return {"models": [], "life_years": 5.0, "pue": 1.1, "roic": 0.25}
    return json.loads(p.read_text(encoding="utf-8"))


def halvings_before(d: date) -> int:
    return sum(1 for h in HALVINGS if h <= d)


def block_subsidy_on(d: date) -> float:
    n = halvings_before(d)
    return SUBSIDY_BY_HALVING_INDEX.get(min(n, 6), 0.78125)


def electricity_cost_per_coin(
    hash_eh: float,
    efficiency_j_th: float,
    electricity_usd_kwh: float,
    subsidy_btc: float,
) -> float | None:
    if hash_eh <= 0 or efficiency_j_th <= 0 or electricity_usd_kwh <= 0 or subsidy_btc <= 0:
        return None
    power_w = hash_eh * 1e6 * efficiency_j_th
    kwh_per_day = power_w * 24.0 / 1000.0
    coins_per_day = BLOCKS_PER_DAY * subsidy_btc
    return kwh_per_day * electricity_usd_kwh / coins_per_day


def all_in_cost_usd(
    hash_eh: float,
    efficiency_j_th: float,
    electricity_usd_kwh: float,
    subsidy_btc: float,
    power_share: float = DEFAULT_POWER_SHARE,
) -> float | None:
    elec = electricity_cost_per_coin(hash_eh, efficiency_j_th, electricity_usd_kwh, subsidy_btc)
    if elec is None or power_share <= 0:
        return None
    return elec / power_share


def watts_from(hash_eh: float, efficiency_j_th: float) -> float:
    return hash_eh * 1e6 * efficiency_j_th


def all_in_from_watts(
    watts: float,
    electricity_usd_kwh: float,
    subsidy_btc: float,
    power_share: float = DEFAULT_POWER_SHARE,
) -> float | None:
    if watts <= 0 or electricity_usd_kwh <= 0 or subsidy_btc <= 0 or power_share <= 0:
        return None
    kwh_per_day = watts * 24.0 / 1000.0
    coins = BLOCKS_PER_DAY * subsidy_btc
    return (kwh_per_day * electricity_usd_kwh / coins) / power_share


def fleet_jth_from_twh(twh_year: float, hash_eh: float) -> float | None:
    """Implied fleet J/TH from CBECI annualised TWh and network EH/s."""
    if twh_year <= 0 or hash_eh <= 0:
        return None
    gw = twh_year / (HOURS_PER_YEAR / 1000.0)
    return gw * 1000.0 / hash_eh


def twh_from_watts(watts: float) -> float:
    gw = watts / 1e9
    return gw * (HOURS_PER_YEAR / 1000.0)


def _hash_on(d: date, hash_eh: list[tuple[date, float]]) -> float | None:
    last = None
    for hd, hv in hash_eh:
        if hd <= d:
            last = hv
        else:
            break
    return last


def asic_fleet_jth(
    d: date,
    catalog: dict,
    hash_eh: list[tuple[date, float]],
    *,
    apply_pue: bool = True,
) -> float | None:
    """Hashrate-at-release vintage mix. Newer gens dominate because the network grew."""
    models = catalog.get("models") or []
    life = float(catalog.get("life_years") or 5.0)
    pue = float(catalog.get("pue") or 1.1) if apply_pue else 1.0
    num = 0.0
    den = 0.0
    for m in models:
        try:
            rel = date.fromisoformat(str(m["release"]))
            jth = float(m["j_th"])
        except (KeyError, TypeError, ValueError):
            continue
        if rel > d or jth <= 0:
            continue
        age = (d - rel).days / 365.25
        if age >= life:
            continue
        survive = 1.0 - age / life
        mass = _hash_on(rel, hash_eh) or 1.0
        w = survive * mass
        num += w * jth
        den += w
    if den <= 0:
        return None
    return (num / den) * pue


def sota_jth(d: date, catalog: dict, *, apply_pue: bool = True) -> float | None:
    models = catalog.get("models") or []
    pue = float(catalog.get("pue") or 1.1) if apply_pue else 1.0
    best = None
    for m in models:
        try:
            rel = date.fromisoformat(str(m["release"]))
            jth = float(m["j_th"])
        except (KeyError, TypeError, ValueError):
            continue
        if rel > d or jth <= 0:
            continue
        best = jth if best is None else min(best, jth)
    if best is None:
        return None
    return best * pue


def sota_usd_per_th(d: date, catalog: dict) -> float:
    models = catalog.get("models") or []
    best_jth = None
    px = 25.0
    for m in models:
        try:
            rel = date.fromisoformat(str(m["release"]))
            jth = float(m["j_th"])
            usd = float(m.get("usd_per_th") or 25.0)
        except (KeyError, TypeError, ValueError):
            continue
        if rel > d or jth <= 0:
            continue
        if best_jth is None or jth < best_jth:
            best_jth = jth
            px = usd
    return px


def sota_roic_all_in(
    *,
    hash_eh: float,
    sota_j_th: float,
    electricity_usd_kwh: float,
    subsidy_btc: float,
    power_share: float,
    usd_per_th: float,
    roic: float = 0.25,
) -> float | None:
    """Cash all-in plus required profit so new ASICs earn `roic` on $/TH capital."""
    cash = all_in_cost_usd(hash_eh, sota_j_th, electricity_usd_kwh, subsidy_btc, power_share)
    if cash is None or hash_eh <= 0 or subsidy_btc <= 0 or usd_per_th <= 0:
        return None
    coins_per_year_per_th = (BLOCKS_PER_DAY * subsidy_btc * 365.0) / (hash_eh * 1e6)
    if coins_per_year_per_th <= 0:
        return None
    capex_per_annual_coin = usd_per_th / coins_per_year_per_th
    return cash + roic * capex_per_annual_coin


@dataclass
class CostState:
    as_of: date
    hash_eh: float
    fleet_jth: float
    electricity_usd_kwh: float
    subsidy_btc: float
    power_share: float = DEFAULT_POWER_SHARE
    premium_multiple: float = DEFAULT_PREMIUM

    def watts(self) -> float:
        return watts_from(self.hash_eh, self.fleet_jth)

    def all_in(self) -> float:
        v = all_in_cost_usd(
            self.hash_eh,
            self.fleet_jth,
            self.electricity_usd_kwh,
            self.subsidy_btc,
            self.power_share,
        )
        return float(v or 0.0)


def _scenario_point(
    *,
    watts: float,
    kwh: float,
    subsidy: float,
    power_share: float,
    premium: float,
    horizon: date,
    label: str,
) -> dict:
    all_in = all_in_from_watts(watts, kwh, subsidy, power_share) or 0.0
    return {
        "date": horizon.isoformat(),
        "label": label,
        "watts": watts,
        "electricity_usd_kwh": kwh,
        "subsidy_btc": subsidy,
        "all_in_usd": round(all_in, 2),
        "premium_usd": round(all_in * premium, 2),
        "electricity_only_usd": round(all_in * power_share, 2),
    }


def forward_scenarios(now: CostState) -> dict:
    """24-month (2028-04-15) and 6-year (2032-04-20) supply fans.

    Naive HK freezes watts and $/kWh, so cost doubles when subsidy halves.
    Efficiency deflation retires watts. Power inflation raises miner kWh.
    Mixed base: slow watt growth plus a modest kWh increase.
    """
    w0 = now.watts()
    k0 = now.electricity_usd_kwh
    share = now.power_share
    prem = now.premium_multiple
    s2028, s2032 = 1.5625, 0.78125
    out = {
        "naive_hk": {
            "2028": _scenario_point(
                watts=w0, kwh=k0, subsidy=s2028, power_share=share, premium=prem,
                horizon=HALVING_2028, label="naive_hk",
            ),
            "2032": _scenario_point(
                watts=w0, kwh=k0, subsidy=s2032, power_share=share, premium=prem,
                horizon=HALVING_2032, label="naive_hk",
            ),
        },
        "efficiency_deflation": {
            "2028": _scenario_point(
                watts=w0 * 0.85, kwh=k0, subsidy=s2028, power_share=share, premium=prem,
                horizon=HALVING_2028, label="efficiency_deflation",
            ),
            "2032": _scenario_point(
                watts=w0 * 0.70, kwh=k0, subsidy=s2032, power_share=share, premium=prem,
                horizon=HALVING_2032, label="efficiency_deflation",
            ),
        },
        "power_inflation": {
            "2028": _scenario_point(
                watts=w0, kwh=k0 * 1.20, subsidy=s2028, power_share=share, premium=prem,
                horizon=HALVING_2028, label="power_inflation",
            ),
            "2032": _scenario_point(
                watts=w0, kwh=k0 * 1.40, subsidy=s2032, power_share=share, premium=prem,
                horizon=HALVING_2032, label="power_inflation",
            ),
        },
        "mixed_base": {
            "2028": _scenario_point(
                watts=w0 * 1.10, kwh=k0 * 1.10, subsidy=s2028, power_share=share, premium=prem,
                horizon=HALVING_2028, label="mixed_base",
            ),
            "2032": _scenario_point(
                watts=w0 * 1.25, kwh=k0 * 1.20, subsidy=s2032, power_share=share, premium=prem,
                horizon=HALVING_2032, label="mixed_base",
            ),
        },
    }
    return out


def kwh_scenario_row(d: date) -> dict[str, float]:
    # Constant HK-comparable miner power. Do not use US residential (~$0.20).
    return {
        "date": d.isoformat(),
        "hk_005": KWH_HK,
        "low_004": KWH_LOW,
        "high_006": KWH_HIGH,
        "survey": KWH_HK,
    }


def live_sensitivities(
    *,
    hash_eh: float,
    fleet_jth: float,
    subsidy_btc: float,
    sota_jth: float | None = None,
    usd_per_th: float = 25.0,
    roic: float = 0.25,
) -> dict:
    """Level bands for the JSON, not the narrative. HK-comparable $0.05 / 60% is the middle."""
    kwh: dict[str, float | None] = {}
    for k in (KWH_LOW, KWH_HK, KWH_HIGH):
        v = all_in_cost_usd(hash_eh, fleet_jth, k, subsidy_btc, DEFAULT_POWER_SHARE)
        kwh[f"{k:.2f}"] = round(v, 2) if v else None
    share: dict[str, float | None] = {}
    for s in (0.55, 0.60, 0.70):
        v = all_in_cost_usd(hash_eh, fleet_jth, KWH_HK, subsidy_btc, s)
        share[f"{s:.2f}"] = round(v, 2) if v else None
    avg = all_in_cost_usd(hash_eh, fleet_jth, KWH_HK, subsidy_btc, DEFAULT_POWER_SHARE)
    fleet: dict[str, float | None] = {
        "average": round(avg, 2) if avg else None,
        "sota_cash": None,
        "sota_roic": None,
    }
    if sota_jth:
        cash = all_in_cost_usd(hash_eh, sota_jth, KWH_HK, subsidy_btc, DEFAULT_POWER_SHARE)
        roic_v = sota_roic_all_in(
            hash_eh=hash_eh,
            sota_j_th=sota_jth,
            electricity_usd_kwh=KWH_HK,
            subsidy_btc=subsidy_btc,
            power_share=DEFAULT_POWER_SHARE,
            usd_per_th=usd_per_th,
            roic=roic,
        )
        fleet["sota_cash"] = round(cash, 2) if cash else None
        fleet["sota_roic"] = round(roic_v, 2) if roic_v else None
    return {
        "kwh_usd": kwh,
        "power_share": share,
        "fleet": fleet,
        "note": (
            "Sensitivities at today's hashrate and subsidy. "
            "Do not use US residential electricity. Context only."
        ),
    }


def miner_stance(
    spot: float | None,
    all_in: float | None,
    sota_roic: float | None,
) -> dict:
    if not spot or not all_in or all_in <= 0:
        return {
            "label": "unknown",
            "plain_english": "Need spot and the reconstructed average-fleet all-in cost.",
        }
    if spot < 0.95 * all_in:
        return {
            "label": "below_fleet_floor",
            "plain_english": (
                "Spot is at or under the average-fleet all-in floor. "
                "Promotional public miners with worse power and unpaid new capex are underwater."
            ),
        }
    if sota_roic and spot < sota_roic:
        return {
            "label": "above_fleet_floor_below_sota_roic",
            "plain_english": (
                "Average fleet is cash-profitable at this spot. "
                "New state-of-the-art machines with a 25 percent ROIC hurdle are not earning that return."
            ),
        }
    return {
        "label": "above_sota_roic",
        "plain_english": (
            "Spot is above both the average-fleet all-in floor and the SOTA-plus-25-percent-ROIC band."
        ),
    }


def parse_cbeci_csv(text: str) -> list[dict]:
    """CBECI download: annualised TWh MAX / MIN / GUESS."""
    rows: list[dict] = []
    for line in text.splitlines():
        if not line or line.startswith("Average") or line.startswith("Timestamp"):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            d = date.fromisoformat(parts[1][:10])
            mx, mn, guess = float(parts[2]), float(parts[3]), float(parts[4])
        except (TypeError, ValueError):
            continue
        if guess <= 0:
            continue
        rows.append({"d": d, "twh_max": mx, "twh_min": mn, "twh_guess": guess})
    rows.sort(key=lambda r: r["d"])
    return rows


def fetch_cbeci_twh(*, offline: bool = False) -> list[dict]:
    cache = CRYPTO_DIR / "cbeci_twh_raw.csv"
    if not offline:
        raw = _get_bytes(CBECI_URL)
        if raw:
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
            parsed = parse_cbeci_csv(text)
            if parsed:
                _write_cbeci_raw(cache, parsed)
                return parsed
    if cache.exists():
        return _read_cbeci_raw(cache)
    return []


def _write_cbeci_raw(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "twh_max", "twh_min", "twh_guess"])
        for r in rows:
            w.writerow([r["d"].isoformat(), r["twh_max"], r["twh_min"], r["twh_guess"]])


def _read_cbeci_raw(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                out.append(
                    {
                        "d": date.fromisoformat(row["date"]),
                        "twh_max": float(row["twh_max"]),
                        "twh_min": float(row["twh_min"]),
                        "twh_guess": float(row["twh_guess"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return out


def read_csv_dates(path: Path) -> list[tuple[date, float]]:
    if not path.exists():
        return []
    rows: list[tuple[date, float]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                d = date.fromisoformat(str(row.get("date") or "").strip())
                v = float(row.get("value"))
            except (TypeError, ValueError):
                continue
            if v <= 0:
                continue
            rows.append((d, v))
    rows.sort(key=lambda x: x[0])
    return rows


def write_csv(path: Path, rows: list[tuple[date, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in rows:
            w.writerow([d.isoformat(), round(v, 6)])


def write_csv_multi(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def join_ffill(index: list[date], series: list[tuple[date, float]]) -> dict[date, float]:
    out: dict[date, float] = {}
    last = None
    j = 0
    for d in index:
        while j < len(series) and series[j][0] <= d:
            last = series[j][1]
            j += 1
        if last is not None:
            out[d] = last
    return out


def build_and_write(*, offline: bool = False) -> dict:
    """Rebuild fleet J/TH, kWh scenarios, electricity-only and all-in cost CSVs."""
    hash_eh = read_csv_dates(CRYPTO_DIR / "btc_hash_rate_eh.csv")
    catalog = load_asic_catalog()
    cbeci = fetch_cbeci_twh(offline=offline)
    if not hash_eh:
        return {"ok": False, "error": "missing_hashrate"}

    hash_by_d = {d: v for d, v in hash_eh}
    cbeci_guess_jth: list[tuple[date, float]] = []
    cbeci_min_jth: list[tuple[date, float]] = []
    twh_guess_rows: list[tuple[date, float]] = []
    for rec in cbeci:
        h = _hash_on(rec["d"], hash_eh)
        if not h:
            continue
        g = fleet_jth_from_twh(rec["twh_guess"], h)
        mn = fleet_jth_from_twh(rec["twh_min"], h)
        if g:
            cbeci_guess_jth.append((rec["d"], g))
            twh_guess_rows.append((rec["d"], rec["twh_guess"]))
        if mn:
            cbeci_min_jth.append((rec["d"], mn))

    last_cbeci = cbeci_guess_jth[-1][0] if cbeci_guess_jth else None
    fleet_rows: list[tuple[date, float]] = []
    sota_rows: list[tuple[date, float]] = []
    elec_rows: list[tuple[date, float]] = []
    all_in_rows: list[tuple[date, float]] = []
    sota_cash_rows: list[tuple[date, float]] = []
    sota_roic_rows: list[tuple[date, float]] = []
    kwh_rows: list[dict] = []
    source_rows: list[dict] = []

    # Monthly sample of hashrate dates plus month-ends, keep daily if short
    sample = hash_eh
    if len(sample) > 2500:
        by_month: dict[str, tuple[date, float]] = {}
        for d, v in hash_eh:
            by_month[d.strftime("%Y-%m")] = (d, v)
        sample = sorted(by_month.values(), key=lambda x: x[0])
        if sample[-1][0] != hash_eh[-1][0]:
            sample.append(hash_eh[-1])

    cbeci_map = {d: v for d, v in cbeci_guess_jth}
    for d, h in sample:
        mix = asic_fleet_jth(d, catalog, hash_eh)
        sota = sota_jth(d, catalog)
        if mix:
            fleet = mix
            src = "asic_vintage_mix"
        elif last_cbeci and d <= last_cbeci and d in cbeci_map:
            fleet = cbeci_map[d]
            src = "cbeci_guess"
        else:
            continue
        kwh = KWH_HK
        sub = block_subsidy_on(d)
        elec = electricity_cost_per_coin(h, fleet, kwh, sub)
        all_in = all_in_cost_usd(h, fleet, kwh, sub, DEFAULT_POWER_SHARE)
        if elec is None or all_in is None:
            continue
        fleet_rows.append((d, fleet))
        elec_rows.append((d, elec))
        all_in_rows.append((d, all_in))
        kwh_rows.append(kwh_scenario_row(d))
        source_rows.append({"date": d.isoformat(), "source": src, "fleet_jth": round(fleet, 4)})
        if sota:
            sota_rows.append((d, sota))
            sc = all_in_cost_usd(h, sota, kwh, sub, DEFAULT_POWER_SHARE)
            sr = sota_roic_all_in(
                hash_eh=h,
                sota_j_th=sota,
                electricity_usd_kwh=kwh,
                subsidy_btc=sub,
                power_share=DEFAULT_POWER_SHARE,
                usd_per_th=sota_usd_per_th(d, catalog),
                roic=float(catalog.get("roic") or 0.25),
            )
            if sc:
                sota_cash_rows.append((d, sc))
            if sr:
                sota_roic_rows.append((d, sr))

    write_csv(CRYPTO_DIR / "btc_fleet_jth.csv", fleet_rows)
    write_csv(CRYPTO_DIR / "btc_sota_jth.csv", sota_rows)
    write_csv(CRYPTO_DIR / "btc_network_twh.csv", twh_guess_rows)
    write_csv(CRYPTO_DIR / "btc_electricity_only_cost_usd.csv", elec_rows)
    write_csv(CRYPTO_DIR / "btc_all_in_cost_usd.csv", all_in_rows)
    write_csv(CRYPTO_DIR / "btc_sota_cash_cost_usd.csv", sota_cash_rows)
    write_csv(CRYPTO_DIR / "btc_sota_roic_cost_usd.csv", sota_roic_rows)
    write_csv(CRYPTO_DIR / "btc_cbeci_guess_jth.csv", cbeci_guess_jth)
    write_csv(CRYPTO_DIR / "btc_cbeci_min_jth.csv", cbeci_min_jth)
    write_csv_multi(
        CRYPTO_DIR / "btc_miner_kwh_usd.csv",
        ["date", "hk_005", "low_004", "high_006", "survey"],
        kwh_rows,
    )
    latest = all_in_rows[-1] if all_in_rows else None
    return {
        "ok": True,
        "n_all_in": len(all_in_rows),
        "latest_all_in": round(latest[1], 2) if latest else None,
        "latest_date": latest[0].isoformat() if latest else None,
        "latest_fleet_jth": round(fleet_rows[-1][1], 4) if fleet_rows else None,
        "latest_electricity_only": round(elec_rows[-1][1], 2) if elec_rows else None,
        "latest_sota_cash": round(sota_cash_rows[-1][1], 2) if sota_cash_rows else None,
        "latest_sota_roic": round(sota_roic_rows[-1][1], 2) if sota_roic_rows else None,
        "fleet_source": "asic_vintage_mix",
        "cbeci_through": last_cbeci.isoformat() if last_cbeci else None,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    out = build_and_write(offline=args.offline)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
