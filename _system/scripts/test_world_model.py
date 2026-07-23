#!/usr/bin/env python3
"""Offline tests for World Model ledger/linkage helpers."""
from __future__ import annotations

import sys
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
    assert (wm.EXPERT_HORIZONS_DIR / "agi.csv").exists()
    assert (wm.INDUSTRY_DIR / "ai_power.json").exists()
    assert (wm.INDUSTRY_DIR / "agi.json").exists()
    assert (wm.INDUSTRY_DIR / "robotaxi.json").exists()
    assert (wm.INDUSTRY_DIR / "hyperscaler_cloud.json").exists()
    assert (wm.INDUSTRY_DIR / "water_surface.json").exists()
    ice = wm.load_json(wm.SUPERORG_DIR / "ice.json")
    assert ice.get("ticker") == "ICE"
    assert ice.get("role") == "portfolio_superorg"
    industry_files = list(wm.INDUSTRY_DIR.glob("*.json"))
    assert len(industry_files) == 13
    thesis = sum(
        1
        for p in industry_files
        if (wm.load_json(p) or {}).get("kind", "thesis") != "horizon_industry"
    )
    assert thesis == 11
    agi = wm.load_json(wm.INDUSTRY_DIR / "agi.json")
    assert agi.get("kind") == "horizon_industry"
    theme_cards = list(wm.PREDICTION_CARDS_DIR.glob("*.json"))
    assert len(theme_cards) == 11


def test_apply_world_model_context_ice():
    import apply_world_model_context as awc  # noqa: WPS433

    strip = awc.load_strip()
    ctx = awc.build_context("ICE", strip, {})
    assert "exchange_markets" in (ctx.get("industry_node_ids") or [])
    assert ctx.get("in_base_irr") is False
    assert "implied_return" not in ctx


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
    test_exchange_vol_map_regions()
    print("test_world_model: ok")
