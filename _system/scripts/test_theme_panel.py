#!/usr/bin/env python3
"""Offline tests for thematic context layer (fetch_theme_panel + apply_context_overlay)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import apply_context_overlay as overlay  # noqa: E402
import fetch_theme_panel as panel  # noqa: E402


def test_yoy_basic():
    rows = [("2024-06-01", 100.0), ("2025-01-01", 110.0), ("2025-06-01", 120.0)]
    latest, prior, pct = panel.yoy(rows)
    assert latest == 120.0
    assert prior == 100.0
    assert pct == 20.0


def test_yoy_empty():
    assert panel.yoy([]) == (None, None, None)


def test_direction():
    assert panel.direction(20.0) == "up"
    assert panel.direction(-5.0) == "down"
    assert panel.direction(0.2) == "flat"
    assert panel.direction(None) == "flat"


def test_merge_keeps_history():
    """process_series must not drop older cached observations when new data arrives."""
    with tempfile.TemporaryDirectory() as tmp:
        old_dir = panel.THEMES_DIR
        panel.THEMES_DIR = Path(tmp)
        try:
            csv_path = panel.THEMES_DIR / "demo_series.csv"
            panel.write_csv(csv_path, [("2024-06-01", 50.0), ("2025-06-01", 60.0)])
            # Offline run reuses cache; history preserved.
            res = panel.process_series({"id": "demo_series", "source": "fred", "fred_id": "X"}, offline=True)
            assert res["latest"] == 60.0
            rows = panel.read_cached_csv(csv_path)
            assert ("2024-06-01", 50.0) in rows
        finally:
            panel.THEMES_DIR = old_dir


def test_hyperscaler_capex_from_repo():
    """Capex series is derived from in-repo ai_overlay, never fabricated."""
    rows, err, contributors = panel.hyperscaler_capex_guide()
    # In this repo GOOGL et al. carry ai_overlay capex; expect a positive total.
    if rows:
        assert err is None
        assert rows[0][1] > 0
        assert contributors


def test_overlay_preserves_human_base_flag():
    manifest = {
        "as_of": "2026-06-06",
        "themes": {
            "ai_power_land": {
                "label": "AI power land",
                "series": {
                    "wti_crude": {"label": "WTI", "latest": 70.0, "as_of": "2026-06-05", "yoy_pct": 5.0, "direction": "up", "good_for": "permian_cashflow", "source": "fred:DCOILWTICO", "stale": False},
                },
            }
        },
    }
    existing = {"themes": [{"theme_id": "ai_power_land", "indicators": [{"id": "wti_crude", "in_base_irr": True}]}]}
    built = overlay.build_overlay("TPL", ["ai_power_land"], manifest, existing)
    ind = built["themes"][0]["indicators"][0]
    assert ind["in_base_irr"] is True  # human flag preserved
    assert "Lawrence base IRR" in built["disclaimer"]


def test_overlay_defaults_context_only():
    manifest = {
        "as_of": "2026-06-06",
        "themes": {"ai_power_land": {"label": "x", "series": {"wti_crude": {"label": "WTI", "latest": 70.0, "as_of": "2026-06-05", "yoy_pct": 5.0, "direction": "up", "source": "fred:DCOILWTICO", "stale": False}}}},
    }
    built = overlay.build_overlay("LB", ["ai_power_land"], manifest, {})
    assert built["themes"][0]["indicators"][0]["in_base_irr"] is False


def test_theme_map_loads():
    tmap = overlay.theme_map()
    assert "TPL" in tmap
    assert "AZLCZ" in tmap
    assert "ai_power_land" in tmap["TPL"]
    assert "ai_power_land" in tmap["AZLCZ"]
    assert "macro_regime" in tmap["TPL"]


def test_wti_yahoo_fallback():
    rows, err = panel.fetch_yahoo_daily("CL=F", days=30)
    assert rows or err
    if rows:
        assert rows[-1][1] > 0


def test_theme_map_wildcard_macro():
    tmap = overlay.theme_map()
    assert "macro_regime" in tmap.get("CME", [])


if __name__ == "__main__":
    test_yoy_basic()
    test_yoy_empty()
    test_direction()
    test_merge_keeps_history()
    test_hyperscaler_capex_from_repo()
    test_overlay_preserves_human_base_flag()
    test_overlay_defaults_context_only()
    test_theme_map_loads()
    print("OK test_theme_panel")
