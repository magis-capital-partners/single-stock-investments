#!/usr/bin/env python3
"""Shared helpers for the agent data architecture: schemas, returns, tokens, embeddings.

Canonical return unit across the whole repo is ``percent_per_year``: a value
of ``13.98`` means 13.98% per year. Legacy fields (``base_irr_pct``,
``implied_return.base_pct``, ``results.*.return_pct``) already store percent;
this module is the single place that states that convention, builds the
canonical ``returns`` block, and validates payloads against ``_system/schemas/``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ROOT / "_system" / "schemas"
RETURN_UNIT = "percent_per_year"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate(payload: Any, schema_name: str) -> list[str]:
    """Validate with jsonschema when available; fall back to required/const checks."""
    schema = load_schema(schema_name)
    try:
        import jsonschema  # type: ignore

        validator = jsonschema.Draft202012Validator(schema)
        return [f"{list(e.absolute_path)}: {e.message}" for e in validator.iter_errors(payload)][:20]
    except ImportError:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["payload is not an object"]
        for field in schema.get("required", []):
            if field not in payload:
                errors.append(f"missing required field: {field}")
        for field, spec in (schema.get("properties") or {}).items():
            if isinstance(spec, dict) and "const" in spec and field in payload and payload[field] != spec["const"]:
                errors.append(f"{field} must equal {spec['const']!r}")
        return errors


def canonical_returns(valuation: dict[str, Any] | None, card: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the canonical returns block from legacy valuation/card fields.

    All legacy sources store percent (``display`` strings such as ``0.12%``
    confirm this even for sub-1 values), so no rescaling is applied; the
    migration only makes the unit explicit.
    """
    valuation = valuation or {}
    card = card or {}
    implied = valuation.get("implied_return") or {}
    results = valuation.get("results") or {}
    base = implied.get("base_pct")
    if base is None:
        base = (results.get("base") or {}).get("return_pct") if isinstance(results.get("base"), dict) else None
    if base is None:
        base = card.get("base_irr_pct")
    scenarios: dict[str, Any] = {}
    for name in ("bear", "base", "bull"):
        row = results.get(name)
        if isinstance(row, dict) and isinstance(row.get("return_pct"), (int, float)):
            scenarios[name] = row["return_pct"]
    if not scenarios and isinstance(card.get("scenarios"), dict):
        scenarios = {k: v for k, v in card["scenarios"].items() if isinstance(v, (int, float))}
    label = implied.get("label") or card.get("irr_label") or None
    display = implied.get("display") or (f"{base}% ({label})" if base is not None and label else (f"{base}%" if base is not None else None))
    return {
        "base_irr_pct": base,
        "unit": RETURN_UNIT,
        "label": label,
        "display": display,
        "scenarios_pct": scenarios,
    }


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4)) if text else 0


def hash_embedding(text: str, dim: int = 256) -> list[float]:
    """Deterministic signed hashing embedding (no external model dependency)."""
    vec = [0.0] * dim
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        vec[idx] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))
