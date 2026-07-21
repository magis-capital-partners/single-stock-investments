#!/usr/bin/env python3
"""Validate that a Cursor research PR carries its immutable evidence provenance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    try:
        from marvin_pipeline_common import load_research_json

        value = load_research_json(path)
    except (OSError, json.JSONDecodeError, ImportError) as exc:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as fallback_exc:
            raise ValueError(f"cannot read {path}: {exc}") from fallback_exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate(manifest: dict, state: dict, ticker: str) -> list[str]:
    """Return all provenance contract violations for one ticker."""
    ticker = ticker.upper()
    errors: list[str] = []
    evidence_hash = manifest.get("evidence_hash")
    if not isinstance(evidence_hash, str) or len(evidence_hash) != 64:
        errors.append("manifest has no valid evidence_hash")
    if manifest.get("ticker") != ticker:
        errors.append(f"manifest ticker must be {ticker}")
    if not manifest.get("primary_evidence_ready"):
        errors.append("manifest does not authorize primary evidence")
    if state.get("ticker") != ticker:
        errors.append(f"agent state ticker must be {ticker}")
    if state.get("consumer") not in {"marvin_research", "marvin_contract_backfill"}:
        errors.append("agent state consumer must be marvin_research or marvin_contract_backfill")
    if state.get("evidence_hash") != evidence_hash:
        errors.append("agent state evidence_hash does not match manifest")
    if not state.get("completed_at"):
        errors.append("agent state has no completed_at timestamp")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        errors = validate(read_json(args.manifest), read_json(args.state), args.ticker)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"OK: {args.ticker.upper()} research PR provenance is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
