#!/usr/bin/env python3
"""Magis predictability-class helpers (World Model × Santa Fe claim gate)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CLASSES_PATH = ROOT / "_system" / "reference" / "world_model" / "predictability_classes.json"
VOL_METRICS = ROOT / "dashboard" / "data" / "vol_metrics_latest.json"
# VIX at or above this is "stressed" (the threshold the retired Darwin macro regime used).
VIX_STRESS = 28.0
VIX_ADAPTING = 22.0
# The vol metrics are nightly; a long weekend plus a holiday is four days old.
# Older than this the regime reads "stale", never "calm".
VOL_REGIME_MAX_AGE_DAYS = 5
CRITICALITY_SUMMARY = ROOT / "dashboard" / "data" / "criticality_summary.json"
ERROR_DIAGRAM = ROOT / "dashboard" / "data" / "criticality_error_diagram.json"

_CLASS_DOC: dict | None = None

def load_classes() -> dict:
    global _CLASS_DOC
    if _CLASS_DOC is None:
        _CLASS_DOC = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))
    return _CLASS_DOC


def class_rank(name: str | None) -> int:
    doc = load_classes()
    if not name:
        return -1
    meta = (doc.get("classes") or {}).get(name) or {}
    return int(meta.get("rank", -1))


def min_class(*names: str | None) -> str:
    """Most restrictive (lowest rank) among named classes."""
    valid = [n for n in names if n and class_rank(n) >= 0]
    if not valid:
        return "P0_ill_defined"
    return min(valid, key=class_rank)


def short_label(name: str | None) -> str:
    doc = load_classes()
    meta = (doc.get("classes") or {}).get(name or "") or {}
    return str(meta.get("short") or (name or "P0"))


def infer_gameability(kpi_id: str | None, explicit: Any = None) -> str | None:
    if explicit in ("low", "med", "high"):
        return explicit
    doc = load_classes()
    soft = set(doc.get("soft_vol_floor_kpi_ids") or [])
    if kpi_id and kpi_id in soft:
        return "high"
    return None


def class_for_kpi_row(kpi: dict) -> str:
    doc = load_classes()
    defaults = doc.get("defaults") or {}
    if kpi.get("prediction_role"):
        return str(defaults.get("kpi_with_prediction_role") or "P3_oriented")
    return str(defaults.get("kpi_without_prediction_role") or "P0_ill_defined")


def class_for_card(card: dict) -> str:
    explicit = card.get("predictability_class")
    if explicit and class_rank(explicit) >= 0:
        return str(explicit)
    doc = load_classes()
    return str((doc.get("defaults") or {}).get("theme_prediction_card") or "P3_oriented")


def class_for_horizon() -> str:
    doc = load_classes()
    return str((doc.get("defaults") or {}).get("expert_horizon_dates") or "P0_ill_defined")


def vol_regime_stress(doc: dict | None = None, *, today: date | None = None) -> dict:
    """Market regime for the market-path cap, from the nightly vol metrics (build_vol_metrics.py).

    Stressed when VIX is at or above VIX_STRESS or the VIX/VIX3M term structure is in
    backwardation. Replaces the Darwin observatory regime, retired with the allocator in 2026-10.
    A document without an ``as_of``, or older than VOL_REGIME_MAX_AGE_DAYS, is unavailable
    and labelled "stale": a frozen feed must not keep reporting calm.
    """
    path = str(VOL_METRICS.relative_to(ROOT)).replace("\\", "/")
    if doc is None:
        doc = _load_json(VOL_METRICS)
    regime = (doc or {}).get("regime") or {}
    vix = regime.get("vix")
    term = str(regime.get("term_state") or "").lower() or None
    if vix is None and term is None:
        return {"available": False, "stress": False, "regime_label": None, "path": path}
    as_of = (doc or {}).get("as_of")
    try:
        age = ((today or datetime.now(timezone.utc).date()) - date.fromisoformat(str(as_of)[:10])).days
    except ValueError:
        age = None
    if age is None or age > VOL_REGIME_MAX_AGE_DAYS:
        return {"available": False, "stress": False, "regime_label": "stale", "vix": vix,
                "term_state": term, "as_of": as_of, "age_days": age, "path": path}
    stress = (vix is not None and float(vix) >= VIX_STRESS) or term == "backwardation"
    label = "stressed" if stress else ("adapting" if vix is not None and float(vix) >= VIX_ADAPTING else "calm")
    return {
        "available": True,
        "stress": bool(stress),
        "regime_label": label,
        "vix": vix,
        "vix_pct1y": regime.get("vix_pct1y"),
        "term_state": term,
        "as_of": as_of,
        "age_days": age,
        "path": path,
    }


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def criticality_market_path(
    summary: dict | None = None,
    diagram: dict | None = None,
) -> dict:
    """Whether the live SPY ensemble may cap market-path language.

    The numeric cutoff comes from the error diagram. A missing diagram, or a
    diagram that found no separating threshold, leaves the cap off.
    """
    if summary is None:
        summary = _load_json(CRITICALITY_SUMMARY)
    if diagram is None:
        diagram = _load_json(ERROR_DIAGRAM)
    selection = diagram.get("selection") or {}
    spy = (summary.get("by_symbol") or {}).get("SPY") or {}
    confidence = spy.get("confidence") or {}
    positive = confidence.get("positive")
    negative = confidence.get("negative")
    dominant = None
    if positive is not None or negative is not None:
        dominant = max(float(positive or 0), float(negative or 0))
    dispersion = (spy.get("critical_time") or {}).get("dispersion")
    concentration = (
        None if dispersion is None
        else max(0.0, min(100.0, 100.0 - 3.0 * float(dispersion)))
    )
    threshold = selection.get("confidence_threshold")
    min_concentration = float(selection.get("min_concentration") or 25)
    enabled = bool(selection.get("demotion_enabled")) and threshold is not None
    ready = str(spy.get("quality_state") or spy.get("status") or "") in {"ready", "limited"}
    demote = bool(
        enabled
        and ready
        and dominant is not None
        and float(dominant) >= float(threshold)
        and concentration is not None
        and concentration >= min_concentration
    )
    return {
        "available": bool(selection) and bool(spy),
        "demote": demote,
        "demotion_enabled": enabled,
        "dominant_confidence": dominant,
        "threshold": threshold,
        "concentration": None if concentration is None else round(concentration, 2),
        "min_concentration": min_concentration,
        "direction": spy.get("direction"),
        "as_of": spy.get("as_of"),
        "plain_english": selection.get("plain_english"),
        "tail_label": (spy.get("tail") or {}).get("label"),
    }


def annotate_kpi_row(row: dict, kpi: dict | None = None) -> dict:
    src = kpi or row
    out = dict(row)
    out["predictability_class"] = class_for_kpi_row(src)
    game = infer_gameability(src.get("kpi_id"), src.get("gameability"))
    if game:
        out["gameability"] = game
    return out


def build_claim_boundaries(
    *,
    cards: list[dict],
    horizons: list[dict],
    industry: list[dict],
    kpi_rows: list[dict],
    regime: dict | None = None,
    criticality: dict | None = None,
) -> dict:
    doc = load_classes()
    defaults = doc.get("defaults") or {}
    thesis_ceiling = str(defaults.get("kpi_with_prediction_role") or "P3_oriented")
    reg = regime if regime is not None else vol_regime_stress()
    crit = criticality if criticality is not None else criticality_market_path()
    market_path = "P1_ecology" if (reg.get("stress") or crit.get("demote")) else thesis_ceiling
    claim_ceiling = min_class(thesis_ceiling, market_path)

    demotions: list[dict] = []
    for h in horizons:
        demotions.append({
            "artifact": f"expert_horizon:{h.get('domain')}",
            "predictability_class": class_for_horizon(),
            "reason": "Arrival-date quotes are observations, not Magis forecasts",
        })
    if reg.get("stress"):
        demotions.append({
            "artifact": "vol_metrics:regime",
            "predictability_class": "P1_ecology",
            "reason": (f"Market regime {reg.get('regime_label')} (VIX {reg.get('vix')}, "
                       f"term {reg.get('term_state')}) caps market-path language at P1"),
        })
    if crit.get("demote"):
        demotions.append({
            "artifact": "criticality:SPY",
            "predictability_class": "P1_ecology",
            "reason": (
                f"SPY ensemble confidence {crit.get('dominant_confidence')} "
                f">= {crit.get('threshold')} with a concentrated critical-time window"
            ),
        })

    goodhart = []
    for row in kpi_rows:
        if row.get("gameability") in ("med", "high"):
            goodhart.append({
                "ticker": row.get("ticker"),
                "kpi_id": row.get("kpi_id"),
                "gameability": row.get("gameability"),
                "status": row.get("status"),
                "note": "Soft performance criterion — Goodhart risk (Arthur)",
            })

    formation = [
        {
            "node_id": n.get("node_id"),
            "formation_tag": n.get("formation_tag"),
            "predictability_class": "P2_formation" if n.get("formation_tag") == "increasing_returns" else None,
        }
        for n in industry
        if n.get("formation_tag")
    ]

    caps = []
    if reg.get("available"):
        caps.append(f"regime {reg.get('regime_label')}")
    else:
        caps.append("regime unavailable")
    if crit.get("demote"):
        caps.append(
            f"SPY criticality {crit.get('dominant_confidence')} >= {crit.get('threshold')}"
        )
    reason = (
        f"Thesis hygiene may use {short_label(thesis_ceiling)}; "
        f"market-path language capped at {short_label(market_path)} "
        f"({'; '.join(caps)}). Steady means gates held, not path certainty."
    )

    return {
        "claim_ceiling": claim_ceiling,
        "thesis_hygiene_ceiling": thesis_ceiling,
        "market_path_ceiling": market_path,
        "reason": reason,
        "regime": reg,
        "criticality": crit,
        "demotions": demotions,
        "goodhart_watch": goodhart[:40],
        "formation_tags": formation,
        "engines": [
            {"id": "world_model", "role": "thesis foresight hygiene"},
            {"id": "vol_regime", "role": "VIX level and term structure cap on market-path language"},
            {"id": "criticality", "role": "LPPLS market-path cap when the error diagram allows it"},
            {"id": "house_valuation", "role": "Power Zone + contract + IC + human (P4 only)"},
            {"id": "legacy_lawrence", "role": "reference / specialist only"},
            {"id": "santa_fe", "role": "wisdom library — claim bans, no KPIs"},
        ],
        "banned_phrases": list(doc.get("banned_phrases") or []),
        "class_matrix_ref": str(CLASSES_PATH.relative_to(ROOT)).replace("\\", "/"),
    }


def find_banned_phrases(text: str) -> list[str]:
    doc = load_classes()
    hits = []
    lower = text.lower()
    for phrase in doc.get("banned_phrases") or []:
        if phrase.lower() in lower:
            hits.append(phrase)
    # Extra patterns for AGI/robotaxi date as Magis truth
    if re.search(r"\bagi\b.{0,40}\bby\s+20\d{2}", lower):
        hits.append("agi-by-year claim")
    if re.search(r"\brobotaxi\b.{0,40}\bby\s+20\d{2}", lower):
        hits.append("robotaxi-by-year claim")
    return sorted(set(hits))
