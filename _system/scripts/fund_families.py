#!/usr/bin/env python3
"""Fund-family helpers for Consensus sibling-letter collapse and vote keys."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAMILIES_PATH = ROOT / "_system" / "data" / "fund_families.json"
REVIEWS_PENDING = ROOT / "_system" / "reviews" / "pending"

_COMMENT_NORM = re.compile(r"\s+")
MIN_COLLAPSE_COMMENT_LEN = 80


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
    """Return curated family id, or prefix match against seeded families."""
    if family_id:
        return str(family_id).strip().lower() or None
    fid = (fund_id or "").strip().lower()
    if not fid:
        return None
    mapped = _fund_id_to_family().get(fid)
    if mapped:
        return mapped
    prefix = fid.split("-", 1)[0]
    families = load_fund_families()
    if prefix in families:
        return prefix
    # Multi-token seed ids (prince-street-*)
    for fam_id in families:
        if fid == fam_id or fid.startswith(fam_id + "-"):
            return fam_id
    return None


def family_display(family_id: str | None) -> str:
    if not family_id:
        return ""
    meta = load_fund_families().get(family_id) or {}
    return str(meta.get("display") or family_id)


def normalize_commentary(text: str | None) -> str:
    return _COMMENT_NORM.sub(" ", (text or "").strip().lower())


def commentary_hash(text: str | None) -> str:
    norm = normalize_commentary(text)
    if len(norm) < MIN_COLLAPSE_COMMENT_LEN:
        return ""
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def consensus_vote_key(
    fund_id: str | None,
    fund: str | None = None,
    *,
    family_id: str | None = None,
    commentary: str | None = None,
    action: str | None = None,
) -> str | None:
    """
    Key used for lean / fund_count.

    Returns None for pure discussed (mentioned only — not a vote).
    Otherwise: family display, commentary-cluster hash, or fund name.
    """
    act = (action or "discussed").lower()
    if act not in {"new", "add", "buy", "trim", "exit", "short"}:
        return None
    fam = family_id_for_fund(fund_id, family_id=family_id)
    if fam:
        return family_display(fam) or fam
    ch = commentary_hash(commentary)
    if ch:
        return f"idea:{ch}"
    return (fund or fund_id or "Unknown").strip() or "Unknown"


def collapse_display_label(
    fund: str | None,
    fund_id: str | None,
    sibling_count: int,
    *,
    family_id: str | None = None,
) -> str:
    if sibling_count <= 0:
        return fund or fund_id or "Unknown"
    total = 1 + sibling_count
    fam = family_id or family_id_for_fund(fund_id)
    if fam:
        return f"{family_display(fam) or fam.title()} ({total} strategies)"
    return f"{fund or fund_id} (+{sibling_count})"


def propose_fund_families(letters: list[dict], *, as_of: str) -> list[dict]:
    """
    Auto-propose families: shared hyphen prefix + ≥2 identical ticker snippets in a quarter.
    """
    # (quarter, prefix, ticker, norm_comment) -> set of fund_ids
    clusters: dict[tuple, set[str]] = defaultdict(set)
    fund_names: dict[str, str] = {}
    for letter in letters:
        q = letter.get("quarter") or "unknown"
        fund_id = str(letter.get("fund_id") or letter.get("fund") or "").strip().lower()
        if not fund_id or "-" not in fund_id:
            continue
        prefix = fund_id.split("-", 1)[0]
        if len(prefix) < 3:
            continue
        fund_names[fund_id] = letter.get("fund") or fund_id
        for pos in letter.get("positions") or []:
            tk = str(pos.get("ticker") or "").upper()
            norm = normalize_commentary(pos.get("commentary") or pos.get("thesis"))
            if not tk or len(norm) < MIN_COLLAPSE_COMMENT_LEN:
                continue
            clusters[(q, prefix, tk, norm)].add(fund_id)

    # prefix -> fund_ids that co-occur on ≥2 identical snippets
    prefix_hits: dict[str, set[str]] = defaultdict(set)
    prefix_snippet_count: dict[str, int] = defaultdict(int)
    for (_q, prefix, _tk, _norm), fids in clusters.items():
        if len(fids) < 2:
            continue
        prefix_hits[prefix].update(fids)
        prefix_snippet_count[prefix] += 1

    known = set(load_fund_families())
    proposals: list[dict] = []
    for prefix, fids in sorted(prefix_hits.items()):
        if prefix in known:
            continue
        if prefix_snippet_count[prefix] < 2 or len(fids) < 2:
            continue
        proposals.append(
            {
                "family_id": prefix,
                "display": prefix.replace("-", " ").title(),
                "fund_ids": sorted(fids),
                "shared_snippet_clusters": prefix_snippet_count[prefix],
                "fund_labels": {fid: fund_names.get(fid, fid) for fid in sorted(fids)},
            }
        )
    return proposals


def write_family_proposals(proposals: list[dict], *, as_of: str) -> Path | None:
    if not proposals:
        return None
    REVIEWS_PENDING.mkdir(parents=True, exist_ok=True)
    path = REVIEWS_PENDING / f"fund_family_proposals_{as_of}.md"
    lines = [
        f"# Fund family proposals ({as_of})",
        "",
        "Auto-detected multi-strategy shops from shared prefix + identical letter snippets.",
        "Promote confirmed rows into `_system/data/fund_families.json`.",
        "",
    ]
    for p in proposals:
        lines.append(f"## `{p['family_id']}` — {p['display']}")
        lines.append(f"- Shared snippet clusters: **{p['shared_snippet_clusters']}**")
        lines.append("- Fund IDs:")
        for fid in p["fund_ids"]:
            label = (p.get("fund_labels") or {}).get(fid, fid)
            lines.append(f"  - `{fid}` ({label})")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    p["family_id"]: {
                        "display": p["display"],
                        "fund_ids": p["fund_ids"],
                    }
                },
                indent=2,
            )
        )
        lines.append("```")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
