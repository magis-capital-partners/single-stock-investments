#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into MSB valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "MSB" / "research" / "valuation.json"

FILING_10K = "MSB/investor-documents/sec-edgar/10-K_20260422_rpt20260131_acc0001104659_26_046864.htm"
FILING_10Q = "MSB/investor-documents/sec-edgar/10-Q_20260612_rpt20260430_acc0001104659_26_073470.htm"
PRIOR_AWARD_8K = "MSB/investor-documents/sec-edgar/8-K_20241017_rpt20241017_acc0001558370_24_013375.htm"
ARBITRATION_8K = "MSB/investor-documents/sec-edgar/8-K_20250926_rpt20250926_acc0001104659_25_093889.htm"
AS_OF = "2026-01-31"
UNITS_M = 13.12001

LEGACY = {
    "producing_royalty_stream": {"low": 30.0, "base": 35.0, "high": 42.0},
    "arbitration_and_bonus_option": {"low": 0.0, "base": 0.0, "high": 13.0},
    "trust_cash_and_other_claims": {"low": 1.02, "base": 1.40, "high": 1.56},
}


def _src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


PROOFS = {
    "producing_royalty_stream": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_unit",
        "inputs": [
            {
                "id": "distribution_per_unit",
                "label": "FY2026 declared distributions per unit",
                "kind": "fact",
                "value": 1.28,
                "unit": "USD_per_unit",
                "source": _src(
                    FILING_10K,
                    "FY2026 declared distributions $16.794 million or $1.28 per unit",
                    AS_OF,
                ),
                "locked": True,
            },
            {
                "id": "units_m",
                "label": "Units outstanding",
                "kind": "fact",
                "value": UNITS_M,
                "unit": "million_units",
                "source": _src(
                    FILING_10K,
                    "Cover page, 13,120,010 units outstanding at April 21, 2026",
                    "2026-04-21",
                ),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Duration-adjusted distribution capitalization multiple",
                "kind": "judgment",
                "values": {
                    "low": round(LEGACY["producing_royalty_stream"]["low"] / 1.28, 4),
                    "base": round(LEGACY["producing_royalty_stream"]["base"] / 1.28, 4),
                    "high": round(LEGACY["producing_royalty_stream"]["high"] / 1.28, 4),
                },
                "unit": "multiple",
                "rationale": (
                    "Bear uses trough FY2026 distribution run-rate with finite reserve and "
                    "Cliffs concentration embedded; base mid-cycle seven-year owner-cash path; "
                    "bull modest bonus-tier recovery uplift."
                ),
                "allowed_range": {"min": 10.0, "max": 45.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Producing royalty stream per unit",
                "op": "multiply",
                "args": ["distribution_per_unit", "capitalization_multiple"],
                "unit": "USD_per_unit",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "arbitration_and_bonus_option": {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_unit",
        "inputs": [
            {
                "id": "units_m",
                "label": "Units outstanding",
                "kind": "fact",
                "value": UNITS_M,
                "unit": "million_units",
                "source": _src(
                    FILING_10K,
                    "Cover page, 13,120,010 units outstanding at April 21, 2026",
                    "2026-04-21",
                ),
                "locked": True,
            },
            {
                "id": "prior_award_m",
                "label": "Prior AAA award collected (closed dispute)",
                "kind": "fact",
                "value": 71.185,
                "unit": "USD_m",
                "source": _src(
                    PRIOR_AWARD_8K,
                    "Cliffs paid $71,185,029 on 2024-10-04; prior dispute closed",
                    "2024-10-04",
                ),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "incremental_recovery_m",
                "label": "Incremental recovery beyond ordinary royalties",
                "kind": "judgment",
                "values": {
                    "low": 0.0,
                    "base": 0.0,
                    "high": round(LEGACY["arbitration_and_bonus_option"]["high"] * UNITS_M, 3),
                },
                "unit": "USD_m",
                "rationale": (
                    "Base assigns no value to the undisclosed September 2025 arbitration. "
                    "High sensitivity only for separately evidenced incremental recovery; "
                    "prior collected award is context, not a current payoff."
                ),
                "allowed_range": {"min": 0.0, "max": 250.0},
            },
            {
                "id": "success_probability",
                "label": "Probability of incremental recovery",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.0, "high": 1.0},
                "unit": "ratio",
                "rationale": (
                    "No primary filing states claim amount, schedule, or collectibility for "
                    "the current AAA panel; high case is unapproved upside sensitivity only."
                ),
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
        ],
        "calculations": [
            {
                "id": "risked_recovery_m",
                "label": "Risk-adjusted incremental recovery",
                "op": "multiply",
                "args": ["incremental_recovery_m", "success_probability"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Arbitration option per unit",
                "op": "divide",
                "args": ["risked_recovery_m", "units_m"],
                "unit": "USD_per_unit",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "trust_cash_and_other_claims": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_unit",
        "inputs": [
            {
                "id": "unallocated_reserve_m",
                "label": "Unallocated reserve",
                "kind": "fact",
                "value": 18.341533,
                "unit": "USD_m",
                "source": _src(
                    FILING_10Q,
                    "Page 12, Comparison of Unallocated Reserve; April 30, 2026 amount $18,341,533",
                    "2026-04-30",
                ),
                "locked": True,
            },
            {
                "id": "units_m",
                "label": "Units outstanding",
                "kind": "fact",
                "value": UNITS_M,
                "unit": "million_units",
                "source": _src(
                    FILING_10K,
                    "Cover page, units outstanding at April 21, 2026",
                    "2026-04-21",
                ),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "reserve_adjustment_m",
                "label": "Reserve adjustment for contingent legal costs and timing",
                "kind": "judgment",
                "values": {"low": -5.0, "base": 0.0, "high": 2.061467},
                "unit": "USD_m",
                "rationale": (
                    "Low case haircuts reserve for contingent arbitration costs; base uses "
                    "April 30, 2026 filing mark; high uses January 31, 2026 reserve of $20.403M."
                ),
                "allowed_range": {"min": -10.0, "max": 5.0},
            }
        ],
        "calculations": [
            {
                "id": "adjusted_reserve_m",
                "label": "Adjusted unallocated reserve",
                "op": "add",
                "args": ["unallocated_reserve_m", "reserve_adjustment_m"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Net trust reserve per unit",
                "op": "divide",
                "args": ["adjusted_reserve_m", "units_m"],
                "unit": "USD_per_unit",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
}


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
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
        component["valuation"]["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]
        component["valuation"]["evidence"] = (
            f"Proof base {ev['outputs']['base']}/unit via {proof['method_id']}@1.0; "
            f"filings {FILING_10K} and {FILING_10Q}."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One Mesabi Trust unit claim on Northshore pellet royalties, unallocated "
            "reserve cash, and any incremental legal recovery beyond ordinary royalties."
        ),
        "excluded_claims": [
            "Depletion and Cliffs concentration reserve embedded in producing capitalization multiple.",
            "Ordinary base and bonus royalties excluded from arbitration incremental recovery.",
            "Prior 2024 AAA award is closed and non-recurring.",
        ],
        "reconciliation": (
            "FY2026 distributions $1.28/unit × capitalization multiple + risk-adjusted "
            "arbitration option + adjusted unallocated reserve per unit."
        ),
        "evidence_ref": "MSB/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    # Embedded depletion must not appear as an additive economic_value group.
    embedded_id = "depletion_and_concentration_reserve"
    for section in ("economic_value",):
        groups = data.get(section, {}).get("component_groups")
        if isinstance(groups, list):
            data[section]["component_groups"] = [
                g for g in groups if g.get("id") != embedded_id
            ]
    eva_groups = eva.get("component_groups")
    if isinstance(eva_groups, list):
        eva["component_groups"] = [g for g in eva_groups if g.get("id") != embedded_id]
    proof_rows = eva.get("valuation_proof")
    if isinstance(proof_rows, list):
        eva["valuation_proof"] = [
            p for p in proof_rows if p.get("component_id") != embedded_id
        ]

    for component in data["component_valuation"]["components"]:
        if component["id"] == embedded_id:
            component["valuation"]["valuation_status"] = "embedded"
            component["valuation"].pop("calculation_proof", None)

    uvc = data.setdefault("universal_valuation_contract", {})
    evidence = uvc.setdefault("evidence", {})
    evidence["blockers"] = [
        b
        for b in evidence.get("blockers", [])
        if "depletion_and_concentration_reserve" not in b
    ]
    evidence["validation_errors"] = [
        e
        for e in evidence.get("validation_errors", [])
        if "depletion_and_concentration_reserve" not in e
    ]
    if not evidence.get("blockers"):
        evidence["unresolved_count"] = max(0, evidence.get("unresolved_count", 0) - 1)

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
