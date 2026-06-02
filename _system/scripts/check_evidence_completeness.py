#!/usr/bin/env python3
"""QA gate: evidence layers present for archetype."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def days_old(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
        return (date.today() - d).days
    except ValueError:
        return None


def check(ticker: str) -> list[str]:
    errs: list[str] = []
    td = ROOT / ticker
    research = td / "research"
    val_path = research / "valuation.json"
    if not val_path.exists():
        return [f"{ticker}: missing valuation.json"]
    val = json.loads(val_path.read_text(encoding="utf-8"))
    arch = (val.get("classification_inputs") or {}).get("archetype", "")
    mode = val.get("valuation_mode", "")

    evidence = research / "evidence"
    if not list(evidence.glob("filing_digest_*.md")):
        errs.append("missing filing_digest")
    facts = list(evidence.glob("filing_facts_*.json"))
    if facts:
        data = json.loads(facts[-1].read_text(encoding="utf-8"))
        if not (data.get("metrics") or data.get("claims")):
            errs.append("filing_facts empty metrics")

    mgmt = list(evidence.glob("management_facts_*.json"))
    tx = list((td / "investor-documents" / "transcripts").glob("*")) if (td / "investor-documents" / "transcripts").exists() else []
    if tx and not mgmt:
        errs.append("transcripts present but no management_facts")

    mi = research / "market_inputs.json"
    if arch == "optionality" or val.get("inputs", {}).get("copperwood_royalty_est_usd"):
        if not mi.exists():
            errs.append("missing market_inputs.json for commodity name")
        else:
            cu = (json.loads(mi.read_text(encoding="utf-8")).get("market_inputs") or {}).get("copper") or {}
            age = days_old(cu.get("as_of"))
            if age is not None and age > 7:
                errs.append(f"copper spot as_of {cu.get('as_of')} stale ({age}d)")

    nav = val.get("nav_overlay") or {}
    if mode == "optionality" and nav:
        if nav.get("status") != "complete":
            errs.append(f"nav_overlay status={nav.get('status')}")
        og = val.get("optionality_gate") or {}
        if og.get("floor_metric") == "book_per_share" and nav.get("gaap_vs_fair_value"):
            errs.append("floor_metric still book_per_share with economic misstatement")

    sotp = (val.get("scenarios") or {}).get("base", {}).get("sotp_build", {})
    for line in sotp.get("lines") or []:
        if line.get("id") == "tie_out" and (line.get("uplift_per_share") or 0) > 5:
            errs.append("large tie_out slack in sotp_build")

    return errs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    args = parser.parse_args()
    rc = 0
    for t in args.tickers:
        errs = check(t.upper())
        if errs:
            rc = 1
            print(f"FAIL {t}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK {t}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
