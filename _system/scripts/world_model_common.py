#!/usr/bin/env python3
"""Shared helpers for World Model KPI ledgers and linkages."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LINKAGES_DIR = ROOT / "_system" / "reference" / "linkages"
LINKAGES_MANIFEST = LINKAGES_DIR / "manifest.json"
DERIVED_METRICS = LINKAGES_DIR / "derived_metrics.json"
THEMES_MANIFEST = ROOT / "_system" / "reference" / "market-data" / "themes" / "manifest.json"
KPI_HISTORY_DIR = ROOT / "_system" / "reference" / "kpi" / "history"
DASHBOARD_WORLD_MODEL = ROOT / "dashboard" / "data" / "world_model.json"
WORLD_MODEL_DIR = ROOT / "_system" / "reference" / "world_model"
PREDICTION_CARDS_DIR = WORLD_MODEL_DIR / "themes"
SUPERORG_DIR = WORLD_MODEL_DIR / "superorg"
INDUSTRY_DIR = ROOT / "_system" / "reference" / "industry"
EXPERT_HORIZONS_DIR = WORLD_MODEL_DIR / "expert_horizons"

STALE_DAYS = 35
STATUS_VALUES = frozenset({"pass", "fail", "stale", "unchecked"})
EXPECTED_OPS = frozenset({"gte", "lte", "gt", "lt", "eq", "neq"})

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_as_of(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_path(obj: Any, path: str) -> Any:
    """Resolve dotted path with optional [n] indices (e.g. themes[0].indicators[1])."""
    if not path:
        return obj
    cur: Any = obj
    # Split on dots but keep [n] attached to the preceding token.
    parts = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    for part in parts:
        if cur is None:
            return None
        if part.startswith("[") and part.endswith("]"):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        m = re.fullmatch(r"(.+)\[(\d+)\]", part)
        if m:
            key, idx_s = m.group(1), m.group(2)
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
            if not isinstance(cur, list):
                return None
            idx = int(idx_s)
            if idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def path_exists(obj: Any, path: str) -> bool:
    if path is None:
        return False
    # Empty path invalid.
    if not str(path).strip():
        return False
    # Walk; distinguish missing vs present-null by checking each step.
    cur: Any = obj
    parts = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    if not parts:
        return False
    for i, part in enumerate(parts):
        if part.startswith("[") and part.endswith("]"):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return False
            cur = cur[idx]
            continue
        m = re.fullmatch(r"(.+)\[(\d+)\]", part)
        if m:
            key, idx_s = m.group(1), m.group(2)
            if not isinstance(cur, dict) or key not in cur:
                return False
            cur = cur[key]
            if not isinstance(cur, list):
                return False
            idx = int(idx_s)
            if idx >= len(cur):
                return False
            cur = cur[idx]
            continue
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def eval_expected(expected: dict | None, actual_value: Any) -> str:
    """Return pass/fail/unchecked for a numeric gate."""
    if actual_value is None:
        return "unchecked"
    if not expected or "op" not in expected or "value" not in expected:
        return "unchecked"
    op = expected["op"]
    try:
        target = float(expected["value"])
        actual = float(actual_value)
    except (TypeError, ValueError):
        return "unchecked"
    if op == "gte":
        return "pass" if actual >= target else "fail"
    if op == "lte":
        return "pass" if actual <= target else "fail"
    if op == "gt":
        return "pass" if actual > target else "fail"
    if op == "lt":
        return "pass" if actual < target else "fail"
    if op == "eq":
        return "pass" if abs(actual - target) < 1e-9 else "fail"
    if op == "neq":
        return "pass" if abs(actual - target) >= 1e-9 else "fail"
    return "unchecked"


def summarize_statuses(kpis: list[dict]) -> dict[str, int]:
    out = {"pass": 0, "fail": 0, "stale": 0, "unchecked": 0}
    for kpi in kpis:
        st = kpi.get("status") or "unchecked"
        if st in out:
            out[st] += 1
        else:
            out["unchecked"] += 1
    return out


def iter_kpi_ledgers() -> list[tuple[str, Path, dict]]:
    found: list[tuple[str, Path, dict]] = []
    for path in sorted(ROOT.glob("*/research/kpi_ledger.json")):
        ticker = path.parent.parent.name
        if ticker.startswith("_") or ticker.startswith("."):
            continue
        data = load_json(path)
        found.append((ticker, path, data))
    return found


def theme_series_lookup(series_id: str) -> dict | None:
    manifest = load_json(THEMES_MANIFEST)
    themes = manifest.get("themes") or {}
    for theme in themes.values():
        series = (theme or {}).get("series") or {}
        if series_id in series:
            return series[series_id]
    return None


def resolve_source_actual(source: str, ticker: str) -> tuple[Any, str | None]:
    """Return (value, as_of) for theme:/valuation:/derived: sources."""
    if not source:
        return None, None
    if source.startswith("theme:"):
        sid = source.split(":", 1)[1]
        row = theme_series_lookup(sid)
        if not row:
            return None, None
        return row.get("latest"), row.get("as_of")
    if source.startswith("derived:"):
        mid = source.split(":", 1)[1]
        derived = load_json(DERIVED_METRICS)
        metrics = derived.get("metrics") or {}
        row = metrics.get(mid) or {}
        return row.get("latest"), row.get("as_of")
    if source.startswith("valuation:"):
        path = source.split(":", 1)[1]
        val = load_json(ROOT / ticker / "research" / "valuation.json")
        return resolve_path(val, path), val.get("as_of")
    return None, None
