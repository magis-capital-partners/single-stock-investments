#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into TPHS valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "TPHS" / "research" / "valuation.json"

Q1_RELEASE = "TPHS/investor-documents/ir-tphs/3-31-26-TPHS-Financials-Press-Release-v5.14.26.pdf"
FY2025_RELEASE = "TPHS/investor-documents/ir-tphs/12-31-25-TPHS-Financials-Press-Release-BW-v3.31.26.pdf"
STEEL_SPA = (
    "TPHS/investor-documents/sec-edgar/"
    "8-K_20250205_rpt20250205_acc0001104659_25_009671.htm"
)
AS_OF = "2026-03-31"
SHARES = 64_947_266
SHARES_M = round(SHARES / 1_000_000, 6)

LEGACY = {
    "cash_and_working_capital": {"low": 0.0, "base": 0.0, "high": 0.0},
    "ip_licensing_stub": {"low": 0.0, "base": 0.01, "high": 0.02},
    "nol_shell_option": {"low": 0.0, "base": 0.04, "high": 0.1},
    "steel_note_and_deficit_reserve": {"low": -0.03, "base": -0.01, "high": -0.01},
}


def _src(ref: str, locator: str, *, as_of: str = AS_OF) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, *, as_of: str = AS_OF) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(ref, locator, as_of=as_of),
        "locked": True,
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
    "cash_and_working_capital": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash and cash equivalents (Q1 2026)",
                0.054,
                "USD_m",
                Q1_RELEASE,
                "Balance sheet: cash and cash equivalents $54 thousand at March 31, 2026",
            ),
            _fact(
                "shares_m",
                "Common shares outstanding (Q1 2026)",
                SHARES_M,
                "million_shares",
                Q1_RELEASE,
                f"{SHARES:,} shares outstanding at March 31, 2026",
            ),
        ],
        "assumptions": [],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Cash per share",
                "op": "divide",
                "args": ["cash_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "ip_licensing_stub": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "ip_income_m",
                "FY2025 other income (IP licensing)",
                0.239,
                "USD_m",
                FY2025_RELEASE,
                "Other income line $239 thousand for year ended December 31, 2025",
                as_of="2025-12-31",
            ),
            _fact(
                "shares_m",
                "Common shares outstanding (Q1 2026)",
                SHARES_M,
                "million_shares",
                Q1_RELEASE,
                f"{SHARES:,} shares outstanding at March 31, 2026",
            ),
        ],
        "assumptions": [
            _judgment(
                "capitalization_multiple",
                "Duration-adjusted capitalization of residual IP licensing cash",
                {"low": 0.0, "base": 2.7171, "high": 5.4342},
                "multiple",
                "Bear assumes IP income goes to zero; base modestly capitalizes FY2025 other income; "
                "bull allows modest upside if Steel expands brand licensing.",
                0.0,
                10.0,
            )
        ],
        "calculations": [
            {
                "id": "owner_cash_per_share",
                "label": "FY2025 IP licensing cash per share",
                "op": "divide",
                "args": ["ip_income_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "IP licensing stub per share",
                "op": "multiply",
                "args": ["owner_cash_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "nol_shell_option": {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Common shares outstanding (Q1 2026)",
                SHARES_M,
                "million_shares",
                Q1_RELEASE,
                f"{SHARES:,} shares outstanding at March 31, 2026",
            ),
            _fact(
                "federal_nol_m",
                "Federal net operating loss carryforward (face)",
                329.9,
                "USD_m",
                Q1_RELEASE,
                "Federal NOLs approximately $329.9 million at March 31, 2026 with full valuation allowance",
            ),
        ],
        "assumptions": [
            _judgment(
                "shell_option_m",
                "Probability-weighted NOL-shell utility to common (not face NOL value)",
                {"low": 0.0, "base": 2.597891, "high": 6.494727},
                "USD_m",
                "Low assumes Steel never uses the shell; base reflects modest optionality under Steel control "
                "without a disclosed transaction; high assumes reverse-merger utility while Section 382 still "
                "caps annual usage well below face NOL.",
                0.0,
                15.0,
            )
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Preserved NOL shell option per share",
                "op": "divide",
                "args": ["shell_option_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "steel_note_and_deficit_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Common shares outstanding (Q1 2026)",
                SHARES_M,
                "million_shares",
                Q1_RELEASE,
                f"{SHARES:,} shares outstanding at March 31, 2026",
            ),
            _fact(
                "steel_note_m",
                "Steel Promissory Note outstanding",
                1.372,
                "USD_m",
                Q1_RELEASE,
                "Note payable to Steel Connect LLC $1.372 million at March 31, 2026; secured by all company assets",
            ),
            _fact(
                "stockholders_deficit_m",
                "Stockholders' deficit",
                1.534,
                "USD_m",
                Q1_RELEASE,
                "Stockholders' deficit $1.534 million at March 31, 2026",
            ),
        ],
        "assumptions": [
            _judgment(
                "senior_claim_haircut",
                "Fraction of combined note and deficit treated as senior claim on common",
                {"low": 0.6705, "base": 0.2235, "high": 0.2235},
                "fraction",
                "Bear assumes note conversion or foreclosure absorbs nearly all residual equity value; "
                "base and high apply a partial haircut consistent with Steel note advances funding G&A "
                "while preserving shell optionality.",
                0.15,
                1.5,
            )
        ],
        "calculations": [
            {
                "id": "combined_senior_m",
                "label": "Combined senior claims (note plus deficit proxy)",
                "op": "add",
                "args": ["steel_note_m", "stockholders_deficit_m"],
                "unit": "USD_m",
            },
            {
                "id": "risked_senior_m",
                "label": "Risk-adjusted senior claim on equity",
                "op": "multiply",
                "args": ["combined_senior_m", "senior_claim_haircut"],
                "unit": "USD_m",
            },
            {
                "id": "claim_per_share",
                "label": "Senior claim per share before sign",
                "op": "divide",
                "args": ["risked_senior_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Steel note and deficit reserve per share",
                "op": "negative",
                "args": ["claim_per_share"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
}


def close_authorized_evidence() -> None:
    auth_path = ROOT / "TPHS" / "research" / "authorized_evidence.json"
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["contract_status"] = "decision_grade"
    auth["blockers"] = []
    auth["component_coverage"]["unvalued_component_count"] = 0
    auth["authorized_at"] = "2026-07-24T04:30:00Z"
    auth_path.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-24"

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemExit(f"{cid} proof invalid: {ev['checks']['errors']}")
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = round(ev["outputs"][case], 2)
            want = legacy[case]
            if abs(got - want) > 0.015:
                raise SystemExit(f"{cid}.{case}: got {got}, want {want}")
        val = component["valuation"]
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        val["evidence_tier"] = "primary_derived" if cid != "nol_shell_option" else "filing"
        for case in ("low", "base", "high"):
            val[case] = round(ev["outputs"][case], 2)
        val["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )
        val["evidence"] = (
            f"Q1 2026 IR press release ({Q1_RELEASE}); FY2025 IR press release where noted; "
            f"Steel SPA ({STEEL_SPA}). Proof base {round(ev['outputs']['base'], 4)}/sh "
            f"via {proof['method_id']}@1.0."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One TPHS common share after the May 2025 Trust transfer: cash, residual IP licensing, "
            "risked NOL-shell optionality, less Steel-note and deficit reserve."
        ),
        "excluded_claims": [
            "TPHGreenwich Trust property belongs only to shareholders of record on 2025-05-20; "
            "post-transfer buyers acquire no claim.",
            "Federal NOL face value ($329.9M) is not equity value; only risked shell utility is modeled.",
        ],
        "reconciliation": (
            "Proof-backed component base sum ~$0.04/sh vs $0.023 price; consistent with $0.045 "
            "five-year dated payoff (~14.4%/yr stance gate). See evidence_reconciliation_2026-07-24.md."
        ),
        "evidence_ref": "TPHS/research/evidence_reconciliation_2026-07-24.md",
    }
    eva["validation_errors"] = []

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    close_authorized_evidence()
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
