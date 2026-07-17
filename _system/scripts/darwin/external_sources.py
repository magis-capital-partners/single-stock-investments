"""Resolve etf-dashboard / ls-algo data paths for Darwin observatory."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import ROOT

EXTERNAL_ROOT = ROOT / "_system" / "reference" / "market-data" / "external"
MANIFEST_PATH = EXTERNAL_ROOT / "sources_manifest.json"

# Override via env: DARWIN_ETF_DASHBOARD_ROOT, DARWIN_LS_ALGO_ROOT
DEFAULT_PATHS = [
    ROOT / "_external" / "etf-dashboard",
    ROOT.parent / "etf-dashboard",
    Path(os.environ.get("DARWIN_ETF_DASHBOARD_ROOT", "")),
]

LS_ALGO_PATHS = [
    ROOT / "_external" / "ls-algo",
    ROOT.parent / "ls-algo",
    Path(os.environ.get("DARWIN_LS_ALGO_ROOT", "")),
]


def _first_existing(candidates: list[Path]) -> Path | None:
    for p in candidates:
        if p and str(p) != "." and p.is_dir():
            return p.resolve()
    return None


def etf_dashboard_root() -> Path | None:
    """Prefer a root that actually has data/ (skip empty _external stubs)."""
    candidates = [p for p in DEFAULT_PATHS if p]
    # First pass: directory with options_cache or vrp_health
    for p in candidates:
        if not p or str(p) == ".":
            continue
        if not p.is_dir():
            continue
        if (p / "data" / "options_cache.json").exists() or (p / "data" / "vrp_health.json").exists():
            return p.resolve()
    return _first_existing(candidates)


def ls_algo_root() -> Path | None:
    return _first_existing([p for p in LS_ALGO_PATHS if p])


def etf_data_path(name: str) -> Path | None:
    root = etf_dashboard_root()
    if not root:
        return None
    p = root / "data" / name
    return p if p.exists() else None


def risk_dashboard_latest() -> Path | None:
    root = ls_algo_root()
    if not root:
        return None
    p = root / "risk_dashboard" / "data" / "latest.json"
    return p if p.exists() else None


def ls_algo_screened_csv() -> Path | None:
    """Live screened ETF universe (Underlying column = tradeable reference)."""
    root = ls_algo_root()
    if not root:
        return None
    p = root / "data" / "etf_screened_today.csv"
    return p if p.exists() else None


def save_sources_manifest() -> dict:
    EXTERNAL_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "etf_dashboard": str(etf_dashboard_root() or ""),
        "ls_algo": str(ls_algo_root() or ""),
        "files": {},
    }
    for label, fn in [
            ("vrp_health", "vrp_health.json"),
            ("vrp_live", "vrp_live.json"),
            ("borrow_spike_risk", "borrow_spike_risk.json"),
            ("macro_event_calendar", "macro_event_calendar.json"),
            ("vol_shape_history", "vol_shape_history.json"),
            ("etf_metrics_daily", "etf_metrics_daily.csv"),
        ]:
        p = etf_data_path(fn)
        if p:
            payload["files"][label] = str(p)
    rd = risk_dashboard_latest()
    if rd:
        payload["files"]["risk_dashboard_latest"] = str(rd)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
