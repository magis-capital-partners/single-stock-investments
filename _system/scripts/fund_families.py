#!/usr/bin/env python3
"""Fund-family helpers for Consensus sibling-letter collapse."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAMILIES_PATH = ROOT / "_system" / "data" / "fund_families.json"

_COMMENT_NORM = re.compile(r"\s+")


@lru_cache(maxsize=1)
def load_fund_families() -> dict[str, dict]:
    if not FAMILIES_PATH.exists():
        return {}
    try:
        doc = json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    families = doc.get("families") if isinstance(doc, dict) else None
    if not isinstance(families, dict):
        return {}
    out: dict[str, dict] = {}
    for fam_id, meta in families.items():
        if not isinstance(meta, dict):
            continue
        fund_ids = {
            str(x).strip().lower()
            for x in (meta.get("fund_ids") or [])
            if str(x).strip()
        }
        out[str(fam_id).strip().lower()] = {
            "display": meta.get("display") or str(fam_id),
            "fund_ids": fund_ids,
        }
    return out


@lru_cache(maxsize=1)
def _fund_id_to_family() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for fam_id, meta in load_fund_families().items():
        for fid in meta.get("fund_ids") or []:
            mapping[fid] = fam_id
    return mapping


def family_id_for_fund(fund_id: str | None, *, family_id: str | None = None) -> str | None:
    """Return curated family id, or None when the fund stands alone."""
    if family_id:
        return str(family_id).strip().lower() or None
    fid = (fund_id or "").strip().lower()
    if not fid:
        return None
    mapped = _fund_id_to_family().get(fid)
    if mapped:
        return mapped
    # Heuristic: ancora-bellator → ancora when curated file lists the prefix
    prefix = fid.split("-", 1)[0]
    families = load_fund_families()
    if prefix in families:
        return prefix
    return None


def family_display(family_id: str | None) -> str:
    if not family_id:
        return ""
    meta = load_fund_families().get(family_id) or {}
    return str(meta.get("display") or family_id)


def consensus_vote_key(
    fund_id: str | None,
    fund: str | None = None,
    *,
    family_id: str | None = None,
) -> str:
    """Key used for fund_count / lean — one vote per family."""
    fam = family_id_for_fund(fund_id, family_id=family_id)
    if fam:
        return family_display(fam) or fam
    return (fund or fund_id or "Unknown").strip() or "Unknown"


def normalize_commentary(text: str | None) -> str:
    return _COMMENT_NORM.sub(" ", (text or "").strip().lower())
