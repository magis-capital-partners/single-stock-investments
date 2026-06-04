#!/usr/bin/env python3
"""Portfolio research anomaly scan (copper leaks, classification drift, synthesis labels).

Usage:
  python _system/scripts/audit_research_anomalies.py
  python _system/scripts/audit_research_anomalies.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from fetch_market_inputs import (  # noqa: E402
    COPPER_INPUT_KEYS,
    commodities_for_ticker,
    is_copper_only_market_inputs,
)
from sync_classification import (  # noqa: E402
    CLASS_PATH,
    check_ticker,
    load_valuation,
    parse_thesis_classification,
    valuation_classification,
)

COPPER_ONLY_MI_KEYS = frozenset({"copper", "scenario_grid"})


def phantom_segment_label(val: dict) -> bool:
    has_seg = bool((val.get("segment_build") or {}).get("segments"))
    for p in (val.get("synthesis") or {}).get("paths") or []:
        if p.get("id") == "theory_implied" and "segment_build" in (p.get("source") or ""):
            if not has_seg:
                return True
    return False


def copper_leak(val: dict, ticker: str) -> bool:
    if commodities_for_ticker(ticker, val):
        return False
    inp = val.get("inputs") or {}
    if any(k in inp for k in COPPER_INPUT_KEYS):
        return True
    if (val.get("market_inputs") or {}).get("copper"):
        return True
    if (val.get("optionality_gate") or {}).get("copperwood_option_yield_pct") is not None:
        return True
    return False


def audit() -> list[dict]:
    findings: list[dict] = []
    portfolio = json.loads(CLASS_PATH.read_text(encoding="utf-8"))

    for vp in sorted(ROOT.glob("*/research/valuation.json")):
        ticker = vp.parts[-3]
        try:
            val = json.loads(vp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append({"ticker": ticker, "kind": "bad_valuation_json"})
            continue
        if copper_leak(val, ticker):
            findings.append({"ticker": ticker, "kind": "copper_leak"})
        if phantom_segment_label(val):
            findings.append({"ticker": ticker, "kind": "phantom_segment_synthesis_label"})
        imp = val.get("implied_return") or {}
        law = (val.get("results") or {}).get("base", {}).get("return_pct")
        syn = imp.get("synthesis_pct")
        if law is not None and syn is not None and abs(float(law) - float(syn)) > 25:
            findings.append(
                {
                    "ticker": ticker,
                    "kind": "lawrence_vs_synthesis_gap",
                    "lawrence_pct": law,
                    "synthesis_pct": syn,
                }
            )

    for mp in sorted(ROOT.glob("*/research/market_inputs.json")):
        ticker = mp.parts[-3]
        val = load_valuation(ticker)
        if commodities_for_ticker(ticker, val):
            continue
        try:
            payload = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        mi = payload.get("market_inputs") or {}
        if is_copper_only_market_inputs(mi):
            findings.append({"ticker": ticker, "kind": "orphan_copper_market_inputs"})

    for ticker in sorted(portfolio.keys()):
        val = load_valuation(ticker)
        if not val:
            if portfolio[ticker].get("archetype") == "unknown":
                findings.append({"ticker": ticker, "kind": "onboard_no_valuation"})
            continue
        from_val = valuation_classification(val)
        from_json = portfolio.get(ticker, {})
        if from_val.get("implied_irr") and from_json.get("implied_irr"):
            if from_val["implied_irr"] != from_json["implied_irr"]:
                findings.append(
                    {
                        "ticker": ticker,
                        "kind": "classification_json_drift",
                        "valuation": from_val["implied_irr"],
                        "json": from_json["implied_irr"],
                    }
                )
        thesis = parse_thesis_classification(ROOT / ticker)
        if thesis.get("implied_irr") and from_val.get("implied_irr"):
            t_pct = re.search(r"([\d.]+)%", thesis["implied_irr"])
            v_pct = re.search(r"([\d.]+)%", from_val["implied_irr"])
            if t_pct and v_pct and abs(float(t_pct.group(1)) - float(v_pct.group(1))) > 0.15:
                findings.append(
                    {
                        "ticker": ticker,
                        "kind": "thesis_classification_irr_drift",
                        "thesis": thesis["implied_irr"],
                        "valuation": from_val["implied_irr"],
                    }
                )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = audit()
    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        if not findings:
            print("OK: no anomalies")
            return 0
        for f in findings:
            print(f"{f['ticker']}: {f['kind']}" + (
                "" if len(f) == 2 else f" ({', '.join(f'{k}={v}' for k, v in f.items() if k not in ('ticker', 'kind'))})"
            ))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
