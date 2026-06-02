"""Shared helpers for evidence_refresh / commodity_nav optionality pipeline."""
from __future__ import annotations

from typing import Any


def has_evidence_refresh_config(val: dict | None) -> bool:
    if not val:
        return False
    return bool((val.get("evidence_refresh") or {}).get("type"))


def synthesis_in_dive(val: dict) -> bool:
    """Whether deep dive should render Total synthesis IRR block."""
    cfg = val.get("evidence_refresh") or {}
    if "synthesis_in_dive" in cfg:
        return bool(cfg.get("synthesis_in_dive"))
    # Default: yield_curve stance gate uses Lawrence base only in markdown
    if val.get("method") == "yield_curve" and has_evidence_refresh_config(val):
        return False
    syn = val.get("synthesis") or {}
    return syn.get("status") == "complete" and val.get("method") != "yield_curve"


def lawrence_base_return_pct(val: dict) -> float | None:
    results = val.get("results") or val.get("results_lawrence_legacy") or {}
    pct = (results.get("base") or {}).get("return_pct")
    if pct is not None:
        return float(pct)
    return (val.get("implied_return") or {}).get("base_pct")


def residual_slack_per_share(val: dict) -> float | None:
    sotp = (val.get("scenarios") or {}).get("base", {}).get("sotp_build") or {}
    for line in sotp.get("lines") or []:
        if line.get("id") in ("residual", "tie_out"):
            return float(line.get("uplift_per_share") or 0)
    return None


def max_residual_allowed(val: dict) -> float:
    cfg = val.get("evidence_refresh") or {}
    return float(cfg.get("max_residual_uplift_per_share", 5.0))
