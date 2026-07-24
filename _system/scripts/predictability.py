#!/usr/bin/env python3
"""Magis predictability-class helpers (World Model × Santa Fe claim gate)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CLASSES_PATH = ROOT / "_system" / "reference" / "world_model" / "predictability_classes.json"
DARWIN_OBS = ROOT / "dashboard" / "data" / "darwin_observatory.json"

_CLASS_DOC: dict | None = None

STRESS_LABELS = frozenset({
    "stress",
    "stressed",
    "complex",
    "crisis",
    "turbulent",
    "high_stress",
})


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


def darwin_regime_stress(obs: dict | None = None) -> dict:
    """Return Darwin regime signal for Magis market-path demotion."""
    if obs is None:
        if not DARWIN_OBS.exists():
            return {
                "available": False,
                "stress": False,
                "regime_label": None,
                "path": str(DARWIN_OBS.relative_to(ROOT)).replace("\\", "/"),
            }
        try:
            obs = json.loads(DARWIN_OBS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            obs = {}
    regime = (obs or {}).get("regime") or {}
    labels = [
        str(regime.get("label") or "").lower(),
        str(regime.get("research") or "").lower(),
        str(regime.get("macro") or "").lower(),
    ]
    stress = any(lab in STRESS_LABELS for lab in labels if lab)
    return {
        "available": bool(obs),
        "stress": stress,
        "regime_label": regime.get("label") or labels[0] or None,
        "research": regime.get("research"),
        "macro": regime.get("macro"),
        "path": str(DARWIN_OBS.relative_to(ROOT)).replace("\\", "/"),
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
    darwin: dict | None = None,
) -> dict:
    doc = load_classes()
    defaults = doc.get("defaults") or {}
    thesis_ceiling = str(defaults.get("kpi_with_prediction_role") or "P3_oriented")
    dwin = darwin if darwin is not None else darwin_regime_stress()
    market_path = "P1_ecology" if dwin.get("stress") else thesis_ceiling
    claim_ceiling = min_class(thesis_ceiling, market_path)

    demotions: list[dict] = []
    for h in horizons:
        demotions.append({
            "artifact": f"expert_horizon:{h.get('domain')}",
            "predictability_class": class_for_horizon(),
            "reason": "Arrival-date quotes are observations, not Magis forecasts",
        })
    if dwin.get("stress"):
        demotions.append({
            "artifact": "darwin_observatory",
            "predictability_class": "P1_ecology",
            "reason": f"Darwin regime={dwin.get('regime_label')} caps market-path language at P1",
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

    reason = (
        f"Thesis hygiene may use {short_label(thesis_ceiling)}; "
        f"market-path language capped at {short_label(market_path)}"
        + (f" (Darwin {dwin.get('regime_label')})" if dwin.get("available") else " (Darwin unavailable)")
        + ". Steady means gates held, not path certainty."
    )

    return {
        "claim_ceiling": claim_ceiling,
        "thesis_hygiene_ceiling": thesis_ceiling,
        "market_path_ceiling": market_path,
        "reason": reason,
        "darwin": dwin,
        "demotions": demotions,
        "goodhart_watch": goodhart[:40],
        "formation_tags": formation,
        "engines": [
            {"id": "world_model", "role": "thesis foresight hygiene"},
            {"id": "darwin", "role": "regime / ecology engine"},
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
