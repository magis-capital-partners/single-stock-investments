"""The hypothesis registry: pre-registered research questions and the rule that
a published result must cite one declared before the result was built.

``hypotheses.jsonl`` sits beside the ledger. Each row is one hypothesis with
its cohort, horizon, exit, cost model, metric, success and kill criteria, the
split it is evaluated on, a status, and ``declared_at``. A research JSON in
the ledger directory that carries ``hypothesis_ids`` must cite registered ids
whose ``declared_at`` precedes its own ``built_at``, must declare
``aggregate_only: true`` and must not contain per-event or per-symbol-day
detail. ``check_reverse_splits.py`` runs these checks; nothing here needs
pandas or a network.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .ledger import load_jsonl, parse_stamp

REGISTRY_NAME = "hypotheses.jsonl"
REQUIRED = ("id", "family", "hypothesis", "cohort", "horizon", "exit", "cost_model",
            "metric", "success", "kill", "split", "status", "declared_at", "declared_in")
STATUSES = frozenset({"registered", "measured", "validated", "killed", "superseded"})
# Keys that identify a single event or a single licensed price observation.
# An aggregate-only publication must not contain them anywhere.
DETAIL_KEYS = frozenset({"event_id", "gross_short_return", "net_return", "symbol_day", "ticker_day"})


def registry_path(ledger_dir: Path) -> Path:
    return Path(ledger_dir) / REGISTRY_NAME


def load_registry(ledger_dir: Path) -> list[dict]:
    path = registry_path(ledger_dir)
    return load_jsonl(path) if path.exists() else []


def registry_errors(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        prefix = f"hypotheses[{index}]"
        missing = [k for k in REQUIRED if not row.get(k)]
        if missing:
            errors.append(f"{prefix}: missing {missing}")
        hid = str(row.get("id") or "")
        if hid in seen:
            errors.append(f"{prefix}: duplicate id {hid} (first at hypotheses[{seen[hid]}])")
        seen.setdefault(hid, index)
        if parse_stamp(row.get("declared_at")) is None:
            errors.append(f"{prefix}: declared_at must be an ISO timestamp")
        if row.get("status") not in STATUSES:
            errors.append(f"{prefix}: status must be one of {sorted(STATUSES)}")
        if row.get("resolved_at") is not None and parse_stamp(row.get("resolved_at")) is None:
            errors.append(f"{prefix}: resolved_at must be an ISO timestamp or null")
    return errors


def detail_keys(value) -> set[str]:
    """Every DETAIL_KEYS member used as a dictionary key anywhere in ``value``."""
    found: set[str] = set()
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            found.update(k for k in node if k in DETAIL_KEYS)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def citation_errors(ledger_dir: Path, registry: list[dict] | None = None) -> list[str]:
    """Check every top-level ``*.json`` in the ledger directory that cites hypotheses."""
    ledger_dir = Path(ledger_dir)
    registry = load_registry(ledger_dir) if registry is None else registry
    declared = {str(r.get("id")): parse_stamp(r.get("declared_at")) for r in registry}
    errors: list[str] = []
    for path in sorted(ledger_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or "hypothesis_ids" not in doc:
            continue
        name = path.name
        ids = doc.get("hypothesis_ids")
        if not isinstance(ids, list) or not ids:
            errors.append(f"{name}: hypothesis_ids must be a non-empty list")
            continue
        built = parse_stamp(doc.get("built_at"))
        if built is None:
            errors.append(f"{name}: built_at required and must be an ISO timestamp")
        for hid in ids:
            when = declared.get(str(hid))
            if str(hid) not in declared:
                errors.append(f"{name}: hypothesis {hid} is not registered in {REGISTRY_NAME}")
            elif when is None:
                errors.append(f"{name}: hypothesis {hid} has an unparseable declared_at")
            elif built is not None and not when < built:
                errors.append(f"{name}: hypothesis {hid} declared at {when.isoformat()} is not before built_at {built.isoformat()}")
        if doc.get("aggregate_only") is not True:
            errors.append(f"{name}: a published hypothesis result must declare aggregate_only: true")
        else:
            leaked = detail_keys(doc)
            if leaked:
                errors.append(f"{name}: aggregate-only publication contains detail keys {sorted(leaked)}")
    return errors


def hypothesis(registry: list[dict], hid: str) -> dict | None:
    return next((r for r in registry if str(r.get("id")) == hid), None)


def declared_before(registry: list[dict], ids: list[str], built_at: str | datetime) -> bool:
    built = built_at if isinstance(built_at, datetime) else parse_stamp(built_at)
    if built is None:
        return False
    for hid in ids:
        row = hypothesis(registry, hid)
        when = parse_stamp(row.get("declared_at")) if row else None
        if when is None or not when < built:
            return False
    return True
