"""AMH macro regime overlay (Workstream D)."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

MACRO_DIR = ROOT / "_system" / "reference" / "market-data" / "macro"
BENCH_DIR = ROOT / "_system" / "reference" / "market-data" / "benchmarks"


def _load_fred_monthly(path: Path, value_col: str = "VALUE") -> dict[str, float]:
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with path.open(encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}
        fields = [x.strip() for x in reader.fieldnames]
        date_key = next(
            (k for k in fields if k.upper() in ("DATE", "OBSERVATION_DATE")),
            fields[0],
        )
        val_key = next(
            (k for k in fields if k.upper() in ("VALUE", "DGS10", "VIXCLS", "CPIAUCSL")),
            fields[-1],
        )
        for row in reader:
            d = (row.get(date_key) or "").strip()
            if not d or d == ".":
                continue
            try:
                v = float(row.get(val_key) or row.get(value_col) or "")
            except ValueError:
                continue
            out[d[:7]] = v
    return out


def _load_stooq_monthly(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with path.open(encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("Date") or row.get("date") or "").strip()
            try:
                c = float(row.get("Close") or row.get("close") or "")
            except ValueError:
                continue
            if d:
                out[d[:7]] = c
    return out


def _macro_state_from_series(vix: dict, y10: dict, cpi: dict, month: str) -> dict:
    m = month
    vix_val = vix.get(m)
    y_val = y10.get(m)
    cpi_yoy = None
    if len(cpi) >= 13:
        keys = sorted(cpi.keys())
        if m in keys:
            i = keys.index(m)
            if i >= 12:
                prev = cpi[keys[i - 12]]
                cur = cpi[m]
                if prev > 0:
                    cpi_yoy = (cur / prev - 1.0) * 100.0

    label = "calm"
    if vix_val is not None and vix_val >= 28:
        label = "stressed"
    elif vix_val is not None and vix_val >= 22:
        label = "adapting"
    elif y_val is not None and y_val >= 4.5:
        label = "adapting"

    return {
        "label": label,
        "as_of_month": m,
        "vix": round(vix_val, 2) if vix_val is not None else None,
        "yield_10y": round(y_val, 3) if y_val is not None else None,
        "cpi_yoy_pct": round(cpi_yoy, 2) if cpi_yoy is not None else None,
        "macro_available": bool(vix or y10),
    }


def macro_state_as_of(month: str) -> dict:
    """Macro regime using data available on or before month (YYYY-MM)."""
    vix = _load_fred_monthly(MACRO_DIR / "fred_vix.csv")
    y10 = _load_fred_monthly(MACRO_DIR / "fred_dgs10.csv")
    cpi = _load_fred_monthly(MACRO_DIR / "fred_cpi.csv")
    months = sorted(set(vix) | set(y10) | set(cpi))
    if not months:
        return {
            "label": "calm",
            "as_of_month": month[:7],
            "vix": None,
            "yield_10y": None,
            "cpi_yoy_pct": None,
            "macro_available": False,
        }
    target = month[:7]
    eligible = [m for m in months if m <= target]
    m = eligible[-1] if eligible else months[0]
    return _macro_state_from_series(vix, y10, cpi, m)


def latest_macro_state() -> dict:
    """Rule-based regime from VIX, 10Y yield, CPI YoY."""
    vix = _load_fred_monthly(MACRO_DIR / "fred_vix.csv")
    y10 = _load_fred_monthly(MACRO_DIR / "fred_dgs10.csv")
    cpi = _load_fred_monthly(MACRO_DIR / "fred_cpi.csv")

    months = sorted(set(vix) | set(y10) | set(cpi))
    if not months:
        return {
            "label": "calm",
            "vix": None,
            "yield_10y": None,
            "cpi_yoy_pct": None,
            "macro_available": False,
        }

    m = months[-1]
    return _macro_state_from_series(vix, y10, cpi, m)


def merge_regime(
    research_label: str,
    macro: dict,
    mandate: dict,
) -> dict:
    """Combine Marvin research regime with macro overlay."""
    macro_label = macro.get("label", "calm")
    if research_label == "stressed" or macro_label == "stressed":
        final = "stressed"
    elif research_label == "adapting" or macro_label == "adapting":
        final = "adapting"
    else:
        final = "calm"

    regime_cfg = mandate.get("regime") or {}
    multipliers = {
        "calm": 1.0,
        "adapting": regime_cfg.get("adapting_turnover_multiplier", 1.2),
        "stressed": regime_cfg.get("stressed_turnover_multiplier", 1.5),
    }
    return {
        "label": final,
        "research": research_label,
        "macro": macro_label,
        "turnover_multiplier": multipliers.get(final, 1.0),
        "macro_detail": macro,
    }


def regime_constraint_overrides(regime: dict, mandate: dict) -> dict:
    """Tighter caps when stressed."""
    m = dict(mandate.get("mandate") or mandate)
    label = regime.get("label", "calm")
    if label == "stressed":
        m["max_abs_weight_change_pct_per_rebalance"] = min(
            m.get("max_abs_weight_change_pct_per_rebalance", 2.5),
            1.5,
        )
        m["max_one_way_turnover_pct_per_rebalance"] = min(
            m.get("max_one_way_turnover_pct_per_rebalance", 10.0),
            7.0,
        )
    elif label == "adapting":
        m["max_abs_weight_change_pct_per_rebalance"] = min(
            m.get("max_abs_weight_change_pct_per_rebalance", 2.5),
            2.0,
        )
    mult = regime.get("turnover_multiplier", 1.0)
    if mult > 1.0:
        m["max_one_way_turnover_pct_per_rebalance"] = (
            m.get("max_one_way_turnover_pct_per_rebalance", 10.0) / mult
        )
    return m
