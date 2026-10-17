#!/usr/bin/env python3
"""Structured agent write-back: validated proposals, never direct edits.

Agents submit claim, memory, valuation-assumption, or thesis-update proposals
as JSON validated against ``_system/schemas/agent_proposal.schema.json``.
Accepted proposals append to ``_system/data/agent_proposals/inbox.jsonl``
with status ``pending_human_review``. Nothing here writes ``valuation.json``,
thesis cards, or ``MEMORY.md``; a human promotes proposals through the normal
review pipeline (``_system/reviews/approved/``).

Usage:
  python _system/scripts/agent_proposals.py submit proposal.json
  python _system/scripts/agent_proposals.py list --ticker GOOGL
  python _system/scripts/agent_proposals.py validate proposal.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import validate  # noqa: E402
from atomic_io import now_iso  # noqa: E402

INBOX = ROOT / "_system" / "data" / "agent_proposals" / "inbox.jsonl"


def normalize_proposal(raw: dict[str, Any]) -> dict[str, Any]:
    proposal = dict(raw)
    if not proposal.get("proposal_id"):
        seed = json.dumps(proposal, sort_keys=True, ensure_ascii=False)
        proposal["proposal_id"] = f"prop-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"
    proposal["status"] = "pending_human_review"
    if not proposal.get("submitted_at"):
        proposal["submitted_at"] = now_iso()
    return proposal


def validate_proposal(raw: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    errors = validate(normalize_proposal(raw), "agent_proposal")
    provenance = raw.get("provenance") or {}
    for source in provenance.get("source_paths") or []:
        if not (root / str(source)).exists():
            errors.append(f"provenance source path does not exist: {source}")
    payload = raw.get("payload")
    if raw.get("kind") == "valuation_assumption" and isinstance(payload, dict):
        if "value" in payload and "unit" not in payload:
            errors.append("valuation_assumption payload requires an explicit unit")
    return errors


def submit(raw: dict[str, Any], *, inbox: Path = INBOX, root: Path = ROOT) -> dict[str, Any]:
    errors = validate_proposal(raw, root=root)
    if errors:
        raise ValueError(f"invalid proposal: {errors}")
    proposal = normalize_proposal(raw)
    inbox.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = set()
    if inbox.is_file():
        for line in inbox.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                try:
                    existing_ids.add(json.loads(line).get("proposal_id"))
                except json.JSONDecodeError:
                    continue
    if proposal["proposal_id"] in existing_ids:
        return {**proposal, "duplicate": True}
    with inbox.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(proposal, ensure_ascii=False, sort_keys=True) + "\n")
    return proposal


def list_proposals(*, ticker: str | None = None, inbox: Path = INBOX) -> list[dict[str, Any]]:
    if not inbox.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in inbox.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if ticker and str(row.get("ticker", "")).upper() != ticker.upper():
            continue
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    submit_parser = sub.add_parser("submit")
    submit_parser.add_argument("file", type=Path)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("file", type=Path)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--ticker", default=None)
    args = parser.parse_args(argv)

    if args.command == "list":
        rows = list_proposals(ticker=args.ticker)
        print(json.dumps({"count": len(rows), "proposals": rows}, indent=2, ensure_ascii=False))
        return 0
    raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if args.command == "validate":
        errors = validate_proposal(raw)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 1
    proposal = submit(raw)
    print(json.dumps({"submitted": proposal["proposal_id"], "status": proposal["status"], "duplicate": bool(proposal.get("duplicate"))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
