#!/usr/bin/env python3
"""Tests for Hauck-style BTC cost-of-production identities and scenarios."""
from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import btc_cost_of_production as cop  # noqa: E402


def test_electricity_and_all_in_match_hk_65k_identity():
    """Known 16 J/TH × 915 EH × $0.05 × 60% share lands on HK's $65k print."""
    elec = cop.electricity_cost_per_coin(
        hash_eh=915.0,
        efficiency_j_th=16.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=3.125,
    )
    all_in = cop.all_in_cost_usd(
        hash_eh=915.0,
        efficiency_j_th=16.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=3.125,
        power_share=0.60,
    )
    assert abs(elec - 39040.0) < 1.0, elec
    assert abs(all_in - 65066.67) < 1.0, all_in


def test_thirstier_2023_fleet_is_not_eleven_thousand():
    """Constant-16 J/TH would print ~$11k in Aug 2023; a 30 J/TH fleet does not."""
    all_in = cop.all_in_cost_usd(
        hash_eh=319.0,
        efficiency_j_th=30.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=6.25,
        power_share=0.60,
    )
    constant16 = cop.all_in_cost_usd(
        hash_eh=319.0,
        efficiency_j_th=16.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=6.25,
        power_share=0.60,
    )
    assert abs(constant16 - 11342.22) < 2.0, constant16
    assert all_in > 20000, all_in
    assert abs(all_in - 21266.67) < 2.0, all_in


def test_varying_efficiency_breaks_hashrate_scalar():
    """If J/TH halves when hashrate doubles, cost per coin is unchanged."""
    a = cop.all_in_cost_usd(400.0, 32.0, 0.05, 3.125, 0.60)
    b = cop.all_in_cost_usd(800.0, 16.0, 0.05, 3.125, 0.60)
    assert a is not None and b is not None
    assert abs(a - b) < 1e-6
    scaled = cop.all_in_cost_usd(800.0, 32.0, 0.05, 3.125, 0.60)
    assert scaled is not None
    assert abs(scaled / a - 2.0) < 1e-6


def test_cbeci_twh_to_jth():
    """2023-08 CBECI guess 143.52 TWh at 426.6 EH → ~38.4 J/TH."""
    jth = cop.fleet_jth_from_twh(twh_year=143.52124790379202, hash_eh=426.6057383177011)
    assert jth is not None
    assert 37.0 < jth < 40.0, jth


def test_asic_mix_improves_over_time():
    catalog = cop.load_asic_catalog()
    hash_eh = [
        (date(2016, 6, 1), 1.5),
        (date(2020, 5, 1), 110.0),
        (date(2022, 7, 1), 220.0),
        (date(2023, 8, 5), 319.0),
        (date(2024, 2, 1), 550.0),
        (date(2026, 9, 6), 915.0),
    ]
    jth_2023 = cop.asic_fleet_jth(date(2023, 8, 5), catalog, hash_eh)
    jth_2026 = cop.asic_fleet_jth(date(2026, 9, 6), catalog, hash_eh)
    assert jth_2023 is not None and jth_2026 is not None
    assert jth_2023 > jth_2026, (jth_2023, jth_2026)
    assert jth_2026 < 22.0, jth_2026
    assert jth_2023 > 20.0, jth_2023


def test_sota_is_more_efficient_than_fleet():
    catalog = cop.load_asic_catalog()
    hash_eh = [
        (date(2024, 2, 1), 550.0),
        (date(2026, 9, 6), 915.0),
    ]
    fleet = cop.asic_fleet_jth(date(2026, 9, 6), catalog, hash_eh)
    sota = cop.sota_jth(date(2026, 9, 6), catalog)
    assert fleet is not None and sota is not None
    assert sota < fleet


def test_naive_forward_doubles_at_halving():
    now = cop.CostState(
        as_of=date(2026, 9, 6),
        hash_eh=915.0,
        fleet_jth=16.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=3.125,
        power_share=0.60,
        premium_multiple=1.75,
    )
    fan = cop.forward_scenarios(now)
    naive = fan["naive_hk"]
    assert abs(naive["2028"]["all_in_usd"] / now.all_in() - 2.0) < 1e-4
    assert abs(naive["2032"]["all_in_usd"] / now.all_in() - 4.0) < 1e-4
    assert abs(naive["2028"]["premium_usd"] / naive["2028"]["all_in_usd"] - 1.75) < 1e-6


def test_efficiency_deflation_rises_less_than_double():
    now = cop.CostState(
        as_of=date(2026, 9, 6),
        hash_eh=915.0,
        fleet_jth=16.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=3.125,
        power_share=0.60,
        premium_multiple=1.75,
    )
    fan = cop.forward_scenarios(now)
    naive_2028 = fan["naive_hk"]["2028"]["all_in_usd"]
    defl_2028 = fan["efficiency_deflation"]["2028"]["all_in_usd"]
    infl_2028 = fan["power_inflation"]["2028"]["all_in_usd"]
    mixed_2028 = fan["mixed_base"]["2028"]["all_in_usd"]
    assert defl_2028 < naive_2028
    assert infl_2028 > naive_2028
    assert mixed_2028 != naive_2028


def test_sota_roic_exceeds_sota_cash():
    cash = cop.all_in_cost_usd(915.0, 12.0, 0.05, 3.125, 0.60)
    roic = cop.sota_roic_all_in(
        hash_eh=915.0,
        sota_j_th=12.0,
        electricity_usd_kwh=0.05,
        subsidy_btc=3.125,
        power_share=0.60,
        usd_per_th=40.0,
        roic=0.25,
    )
    assert cash is not None and roic is not None
    assert roic > cash


def test_kwh_scenarios_are_labeled():
    rows = cop.kwh_scenario_row(date(2026, 9, 6))
    assert rows["hk_005"] == 0.05
    assert rows["low_004"] == 0.04
    assert rows["high_006"] == 0.06
    assert "residential_us" not in rows


def test_reconstructed_2023_all_in_is_not_eleven_k():
    """Live CSV after fetch: 2023 floor must exceed the old constant-16 print."""
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "_system" / "reference" / "market-data" / "crypto" / "btc_all_in_cost_usd.csv"
    if not p.exists():
        return
    rows = cop.read_csv_dates(p)
    hit = None
    for d, v in rows:
        if d <= date(2023, 8, 5):
            hit = v
    assert hit is not None
    assert hit > 15000, hit


def test_kwh_sensitivity_is_monotonic():
    sens = cop.live_sensitivities(
        hash_eh=874.0,
        fleet_jth=14.7,
        subsidy_btc=3.125,
        sota_jth=11.0,
        usd_per_th=35.0,
    )
    assert sens["kwh_usd"]["0.04"] < sens["kwh_usd"]["0.05"] < sens["kwh_usd"]["0.06"]
    assert sens["power_share"]["0.70"] < sens["power_share"]["0.60"] < sens["power_share"]["0.55"]
    assert sens["fleet"]["sota_cash"] < sens["fleet"]["sota_roic"]


def test_miner_stance_labels():
    below = cop.miner_stance(50000.0, 57000.0, 89000.0)
    assert below["label"] == "below_fleet_floor"
    mid = cop.miner_stance(76000.0, 57000.0, 89000.0)
    assert mid["label"] == "above_fleet_floor_below_sota_roic"
    above = cop.miner_stance(120000.0, 57000.0, 89000.0)
    assert above["label"] == "above_sota_roic"


def test_reconstructed_2026_near_hk_order():
    p = Path(__file__).resolve().parents[2] / "_system" / "reference" / "market-data" / "crypto" / "btc_all_in_cost_usd.csv"
    if not p.exists():
        return
    rows = cop.read_csv_dates(p)
    latest = rows[-1][1]
    # HK $65k at 16 J/TH / ~900 EH. Live hash/efficiency will differ; stay same order of magnitude.
    assert 35000 < latest < 120000, latest


def main() -> int:
    test_electricity_and_all_in_match_hk_65k_identity()
    test_thirstier_2023_fleet_is_not_eleven_thousand()
    test_varying_efficiency_breaks_hashrate_scalar()
    test_cbeci_twh_to_jth()
    test_asic_mix_improves_over_time()
    test_sota_is_more_efficient_than_fleet()
    test_naive_forward_doubles_at_halving()
    test_efficiency_deflation_rises_less_than_double()
    test_sota_roic_exceeds_sota_cash()
    test_kwh_scenarios_are_labeled()
    test_kwh_sensitivity_is_monotonic()
    test_miner_stance_labels()
    test_reconstructed_2023_all_in_is_not_eleven_k()
    test_reconstructed_2026_near_hk_order()
    print("test_btc_cost_of_production: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
