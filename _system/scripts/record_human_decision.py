#!/usr/bin/env python3
"""Record the only actionable investment authority: an explicit human decision."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from build_valuation_workbench import write as write_valuation_workbench
from decision_authority import ACTIONABLE_DECISIONS, latest_committee

ROOT = Path(__file__).resolve().parents[2]
ATTESTATION = "I reviewed the frozen evidence, committee synthesis, and strongest dissent."


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def record(
    ticker: str,
    decision: str,
    sizing: str | None,
    owner: str,
    dissent_response: str,
    expires_at: str | None,
    attestation: str,
) -> Path:
    ticker = ticker.upper()
    decision = decision.lower()
    research = ROOT / ticker / "research"
    committee_path, committee = latest_committee(research)
    if not committee_path or not committee:
        raise ValueError(f"{ticker}: a completed Investment Committee record is required")
    if committee.get("final_state") != "committee_complete_decision_pending":
        raise ValueError(f"{ticker}: committee is {committee.get('final_state')}; human decision is not open")
    if decision not in ACTIONABLE_DECISIONS:
        raise ValueError(f"unsupported decision: {decision}")
    if not owner.strip():
        raise ValueError("owner is required")
    if not dissent_response.strip():
        raise ValueError("a response to the strongest dissent is required")
    if attestation != ATTESTATION:
        raise ValueError("the exact review attestation is required")
    sizing_required = decision in {"approve", "accumulate", "core"}
    if sizing_required and not (sizing or "").strip():
        raise ValueError(f"sizing is required for {decision}")

    output = research / "human_decision.json"
    record_value = {
        "schema_version": "1.0",
        "ticker": ticker,
        "status": "decided",
        "decision": decision,
        "stance": decision,
        "sizing": sizing,
        "owner": owner.strip(),
        "committee_source": committee_path.name,
        "committee_packet_hash": (committee.get("evidence_packet") or {}).get("packet_hash"),
        "top_dissent_response": dissent_response.strip(),
        "attestation": attestation,
        "expires_at": expires_at,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    if not record_value["committee_packet_hash"]:
        raise ValueError(f"{ticker}: committee packet hash missing")
    write_json(output, record_value)
    write_valuation_workbench(ticker, datetime.now(timezone.utc).date().isoformat())
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument("--decision", required=True, choices=sorted(ACTIONABLE_DECISIONS))
    parser.add_argument("--sizing")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--dissent-response", required=True)
    parser.add_argument("--expires-at")
    parser.add_argument("--attestation", required=True, help=f'Exact text: "{ATTESTATION}"')
    args = parser.parse_args()
    path = record(
        args.ticker,
        args.decision,
        args.sizing,
        args.owner,
        args.dissent_response,
        args.expires_at,
        args.attestation,
    )
    print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
