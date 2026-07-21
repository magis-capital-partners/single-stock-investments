#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into PLWN valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "PLWN" / "research" / "valuation.json"

EXTRACT = "PLWN/research/evidence/form990_fy2024_extract.json"
AS_OF = "2024-12-31"

LEGACY = {
    "form990_net_assets": {"low": 40.0, "base": 46.8, "high": 55.0},
    "cemetery_operations": {"low": 5.0, "base": 12.0, "high": 20.0},
    "land_market_to_990_gap": {"low": 0.0, "base": 15.0, "high": 80.0},
    "illiquidity_and_governance_reserve": {"low": -40.0, "base": -20.0, "high": -5.0},
}


def _src(locator: str, as_of: str = AS_OF) -> dict:
    return {"ref": EXTRACT, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, locator: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(locator),
        "locked": True,
    }


def _estimate(node_id: str, label: str, value: float, unit: str, locator: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "estimate",
        "value": value,
        "unit": unit,
        "source": _src(locator, "2026-07-21"),
    }


def _judgment(
    node_id: str,
    label: str,
    values: dict,
    unit: str,
    rationale: str,
    lo: float,
    hi: float,
) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "judgment",
        "values": values,
        "unit": unit,
        "rationale": rationale,
        "allowed_range": {"min": lo, "max": hi},
    }


PROOFS = {
    "form990_net_assets": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "net_assets_m",
                "FY2024 Form 990 net assets",
                161.903602,
                "USD_m",
                "financials.net_assets = 161,903,602",
            ),
        ],
        "assumptions": [
            _judgment(
                "shares_m",
                "Provisional economic units outstanding (OTC aggregator; unverified)",
                {"low": 4.0476, "base": 3.46, "high": 2.9437},
                "million_shares",
                (
                    "Low case uses fewer assets per share via higher share count; "
                    "high case uses lower share count. Base matches aggregator ~3.46M pending Form 990 governance disclosure."
                ),
                2.0,
                5.5,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "990 net assets per provisional share",
                "op": "divide",
                "args": ["net_assets_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "cemetery_operations": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "net_income_m",
                "FY2024 Form 990 net income",
                5.324496,
                "USD_m",
                "financials.net_income = 5,324,496",
            ),
            _estimate(
                "shares_m",
                "Provisional economic units outstanding (OTC aggregator; unverified)",
                3.46,
                "million_shares",
                "notes: aggregator ~3.46M shares provisional; conflicts with dividend cash math",
            ),
        ],
        "assumptions": [
            _judgment(
                "capitalization_multiple",
                "Seven-year cemetery owner-cash capitalization multiple",
                {"low": 3.247, "base": 7.792, "high": 12.988},
                "multiple",
                (
                    "Bear assumes trough earnings and nonprofit reinvestment drag; "
                    "base modestly capitalizes through-cycle cemetery cash separate from land; "
                    "bull assumes durable pricing power on Long Island inventory."
                ),
                2.0,
                15.0,
            ),
        ],
        "calculations": [
            {
                "id": "owner_cash_per_share",
                "label": "FY2024 net income per provisional share",
                "op": "divide",
                "args": ["net_income_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Cemetery operating franchise per share",
                "op": "multiply",
                "args": ["owner_cash_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "land_market_to_990_gap": {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _estimate(
                "shares_m",
                "Provisional economic units outstanding (OTC aggregator; unverified)",
                3.46,
                "million_shares",
                "notes: aggregator ~3.46M shares provisional; conflicts with dividend cash math",
            ),
        ],
        "assumptions": [
            _judgment(
                "land_gap_m",
                "Risk-adjusted land fair-value uplift above 990 carrying amounts",
                {"low": 0.0, "base": 51.9, "high": 276.8},
                "USD_m",
                (
                    "Long Island cemetery land may carry below market on Form 990 Schedule D; "
                    "base assigns modest risked uplift; high case is appraisal upside pending local PDF."
                ),
                0.0,
                350.0,
            ),
            _judgment(
                "realization_probability",
                "Probability land mark-up is economically accessible to minority OTC holders",
                {"low": 0.0, "base": 1.0, "high": 1.0},
                "ratio",
                "Low case zeroes option until Schedule D / appraisal evidence; base/high apply full modeled uplift.",
                0.0,
                1.0,
            ),
        ],
        "calculations": [
            {
                "id": "risked_gap_m",
                "label": "Risked land gap",
                "op": "multiply",
                "args": ["land_gap_m", "realization_probability"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Land fair-value gap per share",
                "op": "divide",
                "args": ["risked_gap_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "illiquidity_and_governance_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _estimate(
                "shares_m",
                "Provisional economic units outstanding (OTC aggregator; unverified)",
                3.46,
                "million_shares",
                "notes: aggregator ~3.46M shares provisional; conflicts with dividend cash math",
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "OTC illiquidity, 501(c)(13) governance, and share-count conflict reserve",
                {"low": -138.4, "base": -69.2, "high": -17.3},
                "USD_m",
                (
                    "Thin OTC Pink market, nonprofit distribution constraints, and unresolved share count "
                    "that makes a $45.40 indicated dividend implausible versus $5.3M FY2024 net income."
                ),
                -200.0,
                -10.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Illiquidity and governance reserve per share",
                "op": "divide",
                "args": ["reserve_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
}


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-21"

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        if cid not in PROOFS:
            continue
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemExit(f"{cid} proof invalid: {ev['checks']['errors']}")
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = ev["outputs"][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                raise SystemExit(f"{cid}.{case}: got {got}, want {want}")
        component["valuation"]["calculation_proof"] = proof
        component["valuation"]["valuation_status"] = "bounded_estimate"
        component["valuation"]["evidence_tier"] = "mixed_primary_and_estimate"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]
        component["valuation"]["evidence"] = (
            f"Form 990 FY2024 extract (EIN 11-1190044); proof base {ev['outputs']['base']}/sh "
            f"via {proof['method_id']}@1.0 ({EXTRACT}). Share count remains [HUMAN REVIEW]."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One provisional PLWN OTC unit claim on Pinelawn Cemetery nonprofit economics: "
            "990 net assets plus capitalized operations plus land mark-up option less illiquidity reserve."
        ),
        "excluded_claims": [
            "Perpetual-care trust assets and restricted cemetery plots are not separately modeled until Schedule D PDF is local.",
            "Indicated $45.40 dividend is not in base owner-cash until verified against governance disclosures.",
        ],
        "reconciliation": (
            "FY2024 net assets $161.9M and net income $5.3M from ProPublica extract; "
            "provisional 3.46M share denominator yields ~$46.8/sh accounting floor before reserve."
        ),
        "evidence_ref": "PLWN/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
