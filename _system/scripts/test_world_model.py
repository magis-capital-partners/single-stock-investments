#!/usr/bin/env python3
"""Offline tests for World Model ledger/linkage helpers."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import world_model_common as wm  # noqa: E402
import resolve_linkages as rl  # noqa: E402
import lint_kpi_ledger as lint  # noqa: E402


def test_resolve_path_indexed():
    obj = {"themes": [{"indicators": [{"id": "a", "latest": 1}]}]}
    assert wm.resolve_path(obj, "themes[0].indicators[0].latest") == 1
    assert wm.path_exists(obj, "themes[0].indicators[0].id")


def test_eval_expected():
    assert wm.eval_expected({"op": "gte", "value": 300}, 320) == "pass"
    assert wm.eval_expected({"op": "gte", "value": 300}, 200) == "fail"
    assert wm.eval_expected({"op": "lte", "value": 8}, None) == "unchecked"


def test_pilot_ledgers_lint():
    for ticker in ("TPL", "APLD", "LB", "ICE", "RGLD", "MSB"):
        path = ROOT / ticker / "research" / "kpi_ledger.json"
        assert path.exists(), ticker
        errs = lint.lint_ledger(ticker, wm.load_json(path))
        assert not errs, errs


def test_all_industry_tickers_have_ledgers():
    import scaffold_industry_kpi_ledgers as sc  # noqa: WPS433

    membership = sc.load_industry_membership()
    assert len(membership) >= 60
    missing = [
        t for t in membership
        if not (ROOT / t / "research" / "kpi_ledger.json").exists()
    ]
    assert not missing, f"missing ledgers: {missing[:10]}"
    # Spot-check scaffolds + curated
    assert (ROOT / "AMZN" / "research" / "kpi_ledger.json").exists()
    assert (ROOT / "SPGI" / "research" / "kpi_ledger.json").exists()
    assert (ROOT / "SJT" / "research" / "kpi_ledger.json").exists()
    ledgers = list(ROOT.glob("*/research/kpi_ledger.json"))
    assert len(ledgers) >= 62


def test_hyperscaler_edge_resolves():
    manifest = wm.load_json(wm.LINKAGES_MANIFEST)
    edges = {e["edge_id"]: e for e in manifest.get("edges") or []}
    assert "hyperscaler_capex_to_land_power" in edges
    resolved = rl.resolve_edge(edges["hyperscaler_capex_to_land_power"])
    assert resolved["edge_id"] == "hyperscaler_capex_to_land_power"
    # Theme manifest in-repo should carry a positive hyperscaler sum.
    if resolved.get("latest") is not None:
        assert float(resolved["latest"]) > 0
        assert resolved.get("in_base_irr") is False


def test_foresight_artifacts_exist():
    assert (wm.PREDICTION_CARDS_DIR / "ai_power_land.json").exists()
    assert (wm.PREDICTION_CARDS_DIR / "water_surface.json").exists()
    assert (wm.SUPERORG_DIR / "ice.json").exists()
    assert (wm.SUPERORG_DIR / "hyperscaler_ai_builders.json").exists()
    assert (wm.SUPERORG_DIR / "land_power_stack.json").exists()
    assert (wm.SUPERORG_DIR / "gold_royalty_cluster.json").exists()
    assert (wm.SUPERORG_DIR / "spacex_network.json").exists()
    assert (wm.EXPERT_HORIZONS_DIR / "agi.csv").exists()
    assert (wm.EXPERT_HORIZONS_DIR / "starship.csv").exists()
    assert (wm.PREDICTION_CARDS_DIR / "space_network.json").exists()
    assert (wm.INDUSTRY_DIR / "ai_power.json").exists()
    assert (wm.INDUSTRY_DIR / "agi.json").exists()
    assert (wm.INDUSTRY_DIR / "robotaxi.json").exists()
    assert (wm.INDUSTRY_DIR / "evtol_air_taxi.json").exists()
    assert (wm.INDUSTRY_DIR / "hyperscaler_cloud.json").exists()
    assert (wm.INDUSTRY_DIR / "water_surface.json").exists()
    ice = wm.load_json(wm.SUPERORG_DIR / "ice.json")
    assert ice.get("ticker") == "ICE"
    assert ice.get("role") == "portfolio_superorg"
    spacex = wm.load_json(wm.SUPERORG_DIR / "spacex_network.json")
    assert spacex.get("role") == "external_builder_superorg"
    assert "ECHO" in (spacex.get("tickers") or [])
    industry_files = list(wm.INDUSTRY_DIR.glob("*.json"))
    assert len(industry_files) == 14
    thesis = sum(
        1
        for p in industry_files
        if (wm.load_json(p) or {}).get("kind", "thesis") != "horizon_industry"
    )
    assert thesis == 11
    robotaxi = wm.load_json(wm.INDUSTRY_DIR / "robotaxi.json")
    assert "JOBY" not in (robotaxi.get("linked_tickers") or [])
    assert "UBER" in (robotaxi.get("linked_tickers") or [])
    evtol = wm.load_json(wm.INDUSTRY_DIR / "evtol_air_taxi.json")
    assert "JOBY" in (evtol.get("linked_tickers") or [])
    agi = wm.load_json(wm.INDUSTRY_DIR / "agi.json")
    assert agi.get("kind") == "horizon_industry"
    theme_cards = list(wm.PREDICTION_CARDS_DIR.glob("*.json"))
    assert len(theme_cards) == 12
    superorgs = list(wm.SUPERORG_DIR.glob("*.json"))
    assert len(superorgs) >= 5
    horizons = list(wm.EXPERT_HORIZONS_DIR.glob("*.csv"))
    assert len(horizons) >= 3


def test_apply_world_model_context_ice():
    import apply_world_model_context as awc  # noqa: WPS433

    strip = awc.load_strip()
    ctx = awc.build_context("ICE", strip, {})
    assert "exchange_markets" in (ctx.get("industry_node_ids") or [])
    assert ctx.get("in_base_irr") is False
    assert "implied_return" not in ctx
    assert ctx.get("predictability_class") != "P4_allocation"
    assert ctx.get("predictability_class") in (
        None,
        "P0_ill_defined",
        "P1_ecology",
        "P2_formation",
        "P3_oriented",
    )


def test_predictability_classes_and_ceiling():
    import predictability as pred  # noqa: WPS433

    doc = pred.load_classes()
    assert "P0_ill_defined" in doc["classes"]
    assert "P4_allocation" in doc["classes"]
    assert pred.class_for_horizon() == "P0_ill_defined"
    assert pred.class_for_kpi_row({"prediction_role": "orientation"}) == "P3_oriented"
    assert pred.infer_gameability("asx200_20d_realized_vol") == "high"
    assert pred.min_class("P3_oriented", "P1_ecology") == "P1_ecology"

    day = date(2026, 10, 16)

    def vol(vix, term, as_of="2026-10-15"):
        return pred.vol_regime_stress({"as_of": as_of, "regime": {"vix": vix, "term_state": term}}, today=day)

    calm = vol(16.5, "contango")
    assert calm["available"] is True and calm["stress"] is False and calm["regime_label"] == "calm"
    stressed = vol(31.0, "contango")
    assert stressed["stress"] is True
    inverted = vol(19.0, "backwardation")
    assert inverted["stress"] is True, "an inverted VIX curve is stress even below the VIX threshold"
    assert pred.vol_regime_stress({}, today=day)["available"] is False
    frozen = vol(16.5, "contango", as_of="2026-09-30")
    assert frozen["available"] is False and frozen["regime_label"] == "stale", "a frozen feed must not read calm"
    assert vol(16.5, "contango", as_of=None)["regime_label"] == "stale"
    assert vol(16.5, "contango", as_of="2026-10-12")["available"] is True, "a long weekend is not stale"
    bounds = pred.build_claim_boundaries(
        cards=[{"theme_id": "x", "predictability_class": "P3_oriented"}],
        horizons=[{"domain": "agi"}],
        industry=[{"node_id": "exchange_markets", "formation_tag": "increasing_returns"}],
        kpi_rows=[{
            "ticker": "ASX.AX",
            "kpi_id": "asx200_20d_realized_vol",
            "status": "fail",
            "gameability": "high",
            "predictability_class": "P3_oriented",
        }],
        regime=stressed,
        criticality={"demote": False, "available": False},
    )
    assert bounds["market_path_ceiling"] == "P1_ecology"
    assert bounds["claim_ceiling"] == "P1_ecology"
    assert bounds["thesis_hygiene_ceiling"] == "P3_oriented"
    assert any(d["artifact"].startswith("expert_horizon:") for d in bounds["demotions"])
    assert pred.find_banned_phrases("This is a complexity IRR fantasy") == ["complexity irr"]

    calm_bounds = pred.build_claim_boundaries(
        cards=[],
        horizons=[],
        industry=[],
        kpi_rows=[],
        regime=calm,
        criticality={
            "demote": True,
            "available": True,
            "dominant_confidence": 42,
            "threshold": 20,
        },
    )
    assert calm_bounds["market_path_ceiling"] == "P1_ecology"
    assert calm_bounds["thesis_hygiene_ceiling"] == "P3_oriented"
    assert any(row["artifact"] == "criticality:SPY" for row in calm_bounds["demotions"])

    quiet = pred.build_claim_boundaries(
        cards=[],
        horizons=[],
        industry=[],
        kpi_rows=[],
        regime=calm,
        criticality={"demote": False, "available": True, "demotion_enabled": False},
    )
    assert quiet["market_path_ceiling"] == "P3_oriented"


def test_criticality_gate_follows_the_error_diagram():
    import predictability as pred  # noqa: WPS433

    summary = {"by_symbol": {"SPY": {
        "quality_state": "ready",
        "direction": "positive_bubble",
        "confidence": {"positive": 40, "negative": 5},
        "critical_time": {"dispersion": 10},
    }}}
    diagram = {"selection": {
        "demotion_enabled": True,
        "confidence_threshold": 20,
        "min_concentration": 25,
        "plain_english": "threshold 20",
    }}
    gate = pred.criticality_market_path(summary, diagram)
    assert gate["demote"] is True
    summary["by_symbol"]["SPY"]["critical_time"]["dispersion"] = 40
    assert pred.criticality_market_path(summary, diagram)["demote"] is False
    summary["by_symbol"]["SPY"]["critical_time"]["dispersion"] = 10
    diagram["selection"]["demotion_enabled"] = False
    assert pred.criticality_market_path(summary, diagram)["demote"] is False


def test_kpi_history_zscore_from_theme_csv():
    import kpi_history_stats as khs  # noqa: WPS433

    points = khs.load_theme_points("vix_level")
    assert len(points) >= 20
    stats = khs.compute_stats(points, trailing=252, min_n=20)
    assert stats["status"] == "ok"
    assert stats["z_score"] is not None
    assert stats["n"] >= 20
    assert 0 <= float(stats["percentile"]) <= 100

    rows = [{
        "ticker": "ICE",
        "kpi_id": "vix_level",
        "label": "VIX",
        "source": "theme:vix_level",
        "actual": points[-1][1],
        "last_checked": points[-1][0],
    }]
    series = khs.annotate_rows(rows)
    assert rows[0]["history"]["series_key"] == "theme:vix_level"
    assert rows[0]["z_score"] is not None
    assert "theme:vix_level" in series
    assert len(series["theme:vix_level"]["points"]) >= 20


def test_soft_vol_floor_fail_is_attention_not_broken():
    import build_world_model_snapshot as snap  # noqa: WPS433

    state = {
        "broken": [{
            "ticker": "ASX.AX",
            "kpi_id": "asx200_20d_realized_vol",
            "status": "fail",
            "gameability": "high",
            "predictability_class": "P3_oriented",
            "binds_to": {"on_fail": "open_diligence"},
        }],
        "stale": [],
        "unchecked": [],
        "passes": [],
        "drifted_edges": [],
        "ledgers": [],
    }
    strip = snap.build_strip(state, "2026-07", [], [], [], [])
    assert strip["label"] == "attention"
    assert strip["counts"]["fail_hard"] == 0
    assert strip["counts"]["fail_soft"] == 1
    assert strip["broken"] == []
    assert len(strip["soft_fails"]) == 1
    assert any(h.get("kind") == "soft_fail" for h in strip["headlines"])


def test_exchange_vol_map_regions():
    import scaffold_industry_kpi_ledgers as sc  # noqa: WPS433

    vol_map = sc.load_exchange_vol_map()
    assert vol_map.get("regions")
    watch = set(vol_map.get("watch_only_tickers") or [])
    for ticker, region in (vol_map.get("ticker_region") or {}).items():
        assert region in vol_map["regions"], ticker
        folder = ROOT / ticker
        if ticker in watch:
            continue
        assert folder.is_dir(), f"{ticker} missing folder (add to watch_only_tickers if intentional)"

    jp = sc.exchange_market_kpis("8697.T")
    sources = {k["source"] for k in jp}
    assert "theme:n225_20d_realized_vol" in sources
    assert "theme:vix_level" in sources  # secondary global
    assert "theme:spy_20d_realized_vol" not in sources

    us = sc.exchange_market_kpis("CME")
    us_sources = {k["source"] for k in us}
    assert "theme:vix_level" in us_sources
    assert "theme:spy_20d_realized_vol" in us_sources
    assert "theme:n225_20d_realized_vol" not in us_sources

    ledger_jp = wm.load_json(ROOT / "8697.T" / "research" / "kpi_ledger.json")
    jp_ids = [k["kpi_id"] for k in (ledger_jp.get("kpis") or [])]
    assert "n225_20d_realized_vol" in jp_ids
    assert "vix_level" not in jp_ids  # primary is home; secondary uses vix_level_global
    assert "vix_level_global" in jp_ids


if __name__ == "__main__":
    test_resolve_path_indexed()
    test_eval_expected()
    test_pilot_ledgers_lint()
    test_all_industry_tickers_have_ledgers()
    test_hyperscaler_edge_resolves()
    test_foresight_artifacts_exist()
    test_apply_world_model_context_ice()
    test_predictability_classes_and_ceiling()
    test_kpi_history_zscore_from_theme_csv()
    test_soft_vol_floor_fail_is_attention_not_broken()
    test_exchange_vol_map_regions()
    print("test_world_model: ok")
