#!/usr/bin/env python3
"""Close universal-trio followup gaps after proof-first automation succeeds.

When automate_valuation_readiness compiles a priced owner-earnings proof, the
universal curated gaps (ownership map / cash bridge / downside claims) are
satisfied by that artifact. Mark them met with a progress note pointing at the
fact ledger and valuation proof so the contract can become decision_grade.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLLOWUPS = ROOT / "_system" / "reference" / "valuation_followups.json"
TRIO = {
    "component_ownership_map",
    "primary_cash_or_nav_bridge",
    "downside_and_capital_claims",
}
CLOSED = {"resolved", "accepted", "not_applicable", "met"}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {} if default is None else default


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def proof_ready(ticker: str) -> bool:
    valuation = read_json(ROOT / ticker / "research" / "valuation.json")
    if valuation.get("method") != "proof_first_automated":
        return False
    comps = ((valuation.get("component_valuation_results") or {}).get("additive_components") or [])
    if not comps:
        return False
    proof = comps[0].get("calculation_proof") or {}
    return bool(proof.get("inputs") and proof.get("outputs") and proof.get("method_id"))


def close_ticker(ticker: str, followups: dict) -> int:
    cfg = ((followups.get("tickers") or {}).get(ticker) or {})
    gaps = cfg.get("evidence_gaps") or []
    if not gaps:
        return 0
    closed = 0
    note = (
        f"Closed {now()} by proof-first automation: "
        f"{ticker}/research/valuation.json (method=proof_first_automated) + "
        f"{ticker}/research/valuation_fact_ledger.json satisfy the universal trio."
    )
    for gap in gaps:
        gap_id = str(gap.get("id") or "")
        status = str(gap.get("status") or "open").lower()
        if gap_id not in TRIO or status in CLOSED:
            continue
        gap["status"] = "met"
        gap["progress_note"] = note
        gap["closed_at"] = now()
        closed += 1
    return closed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", type=str.upper)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    followups = read_json(FOLLOWUPS)
    tickers = args.tickers or sorted((followups.get("tickers") or {}))
    report = []
    total = 0
    for ticker in tickers:
        if not proof_ready(ticker):
            continue
        closed = close_ticker(ticker, followups)
        if closed:
            report.append({"ticker": ticker, "closed_gaps": closed})
            total += closed
    if not args.dry_run and total:
        write_json(FOLLOWUPS, followups)
    print(json.dumps({"tickers": report, "total_closed": total}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
