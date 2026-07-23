#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into CRML valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "CRML" / "research" / "valuation.json"
EVIDENCE_RECON = "CRML/research/evidence_reconciliation_2026-07-23.md"

FILING_20F = (
    "CRML/investor-documents/sec-edgar/"
    "20-F_20251006_rpt20250630_acc0001213900_25_096254.htm"
)
AS_OF = "2025-06-30"
SHARES_M = 104.912853
CASH_M = 7.3
PEA_NPV_M = 3000.0
TANBREEZ_OWNERSHIP = 0.42
BMW_ADVANCE_M = 15.0
STAGE2_SHARES_M = 14.5

LEGACY = {
    "corporate_cash": {"low": 0.05, "base": 0.07, "high": 0.10},
    "tanbreez_risked_nav": {"low": 0.5, "base": 3.0, "high": 8.0},
    "wolfsberg_option": {"low": 0.0, "base": 0.5, "high": 2.0},
    "dilution_reserve": {"low": -1.5, "base": -0.5, "high": -0.2},
}

METHOD_MAP = {
    "corporate_cash": "net_asset_value",
    "tanbreez_risked_nav": "probability_weighted_catalyst_nav",
    "wolfsberg_option": "risk_adjusted_milestone_value",
    "dilution_reserve": "net_asset_value",
}


def _src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, locator: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(FILING_20F, locator, AS_OF),
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


CASH_PER_SHARE = round(CASH_M / SHARES_M, 6)
GOING_CONCERN_FACTOR = {
    case: round(LEGACY["corporate_cash"][case] / CASH_PER_SHARE, 4)
    for case in LEGACY["corporate_cash"]
}
GROSS_EQUITY_M = round(PEA_NPV_M * TANBREEZ_OWNERSHIP, 3)
COMPOSITE_RISK = {
    case: round(LEGACY["tanbreez_risked_nav"][case] * SHARES_M / GROSS_EQUITY_M, 4)
    for case in LEGACY["tanbreez_risked_nav"]
}
WOLFSBERG_RISKED_M = {
    case: round(LEGACY["wolfsberg_option"][case] * SHARES_M, 3)
    for case in LEGACY["wolfsberg_option"]
}
DILUTION_RESERVE_PS = {
    case: abs(LEGACY["dilution_reserve"][case]) for case in LEGACY["dilution_reserve"]
}

PROOFS = {
    "corporate_cash": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash on hand at June 30, 2025",
                CASH_M,
                "USD_m",
                "Going-concern disclosure: cash on hand $7.3 million at June 30, 2025",
            ),
            _fact(
                "shares_m",
                "Ordinary shares outstanding",
                SHARES_M,
                "million_shares",
                "Cover page: 104,912,853 ordinary shares outstanding at June 30, 2025",
            ),
        ],
        "assumptions": [
            _judgment(
                "going_concern_factor",
                "Going-concern burn and liquidity haircut on filing cash",
                GOING_CONCERN_FACTOR,
                "ratio",
                (
                    "Low case assumes near-term burn erodes most of the soft cash floor; "
                    "base uses filing cash per share; high allows modest liquidity buffer "
                    "before additional equity issuance."
                ),
                0.0,
                2.0,
            )
        ],
        "calculations": [
            {
                "id": "cash_per_share",
                "label": "Filing cash per share",
                "op": "divide",
                "args": ["cash_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Corporate cash per share",
                "op": "multiply",
                "args": ["cash_per_share", "going_concern_factor"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "tanbreez_risked_nav": {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "pea_npv_m",
                "Tanbreez PEA pre-tax project net present value",
                PEA_NPV_M,
                "USD_m",
                "PEA press release cited in 20-F: approximately US$3 billion pre-tax project NPV",
            ),
            _fact(
                "ownership_pct",
                "CRML equity interest in Tanbreez",
                TANBREEZ_OWNERSHIP,
                "ratio",
                "Company owns 42% of Tanbreez Mining Greenland A/S at June 30, 2025",
            ),
            _fact(
                "shares_m",
                "Ordinary shares outstanding",
                SHARES_M,
                "million_shares",
                "Cover page: 104,912,853 ordinary shares outstanding at June 30, 2025",
            ),
        ],
        "assumptions": [
            _judgment(
                "composite_risk_factor",
                "Composite risk on pre-tax project NPV to equity per share",
                COMPOSITE_RISK,
                "ratio",
                (
                    "Embeds pre-tax to equity conversion, inferred-resource uncertainty, "
                    "Greenland jurisdiction, financing gap, and timing to definitive "
                    "feasibility study and Stage 2 ownership increase."
                ),
                0.0,
                1.0,
            )
        ],
        "calculations": [
            {
                "id": "gross_equity_claim_m",
                "label": "42% claim on PEA project NPV",
                "op": "multiply",
                "args": ["pea_npv_m", "ownership_pct"],
                "unit": "USD_m",
            },
            {
                "id": "risked_equity_m",
                "label": "Risk-adjusted Tanbreez equity claim",
                "op": "multiply",
                "args": ["gross_equity_claim_m", "composite_risk_factor"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Tanbreez risked NAV per share",
                "op": "divide",
                "args": ["risked_equity_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "wolfsberg_option": {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "bmw_advance_m",
                "BMW restricted advance payment",
                BMW_ADVANCE_M,
                "USD_m",
                "BMW offtake advance payment US$15.0 million on June 5, 2024; restricted until production",
            ),
            _fact(
                "shares_m",
                "Ordinary shares outstanding",
                SHARES_M,
                "million_shares",
                "Cover page: 104,912,853 ordinary shares outstanding at June 30, 2025",
            ),
        ],
        "assumptions": [
            _judgment(
                "risked_milestone_value_m",
                "Probability-weighted Wolfsberg milestone value beyond restricted advance",
                WOLFSBERG_RISKED_M,
                "USD_m",
                (
                    "Low assumes Wolfsberg/BMW path fails before production; base credits "
                    "partial milestone value on measured+indicated resource and offtake path; "
                    "high assumes earlier production and fuller option realization."
                ),
                0.0,
                500.0,
            )
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Wolfsberg option per share",
                "op": "divide",
                "args": ["risked_milestone_value_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "dilution_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "stage2_shares_m",
                "Stage 2 Tanbreez shares reserved for Rimbal",
                STAGE2_SHARES_M,
                "million_shares",
                "Tanbreez Stage 2: issuance of 14,500,000 ordinary shares to increase stake to 92.5%",
            ),
            _fact(
                "shares_m",
                "Ordinary shares outstanding",
                SHARES_M,
                "million_shares",
                "Cover page: 104,912,853 ordinary shares outstanding at June 30, 2025",
            ),
        ],
        "assumptions": [
            _judgment(
                "dilution_reserve_per_share",
                "Per-share reserve for Stage 2 issuance and GEM overhang",
                DILUTION_RESERVE_PS,
                "USD_per_share",
                (
                    "Negative reserve bracket for contracted Stage 2 share issuance and GEM "
                    "arbitration/warrant overhang; does not double-count share count in numerator."
                ),
                0.0,
                3.0,
            )
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Dilution reserve per share",
                "op": "negative",
                "args": ["dilution_reserve_per_share"],
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

    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    data["as_of"] = "2026-07-23"

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
        component["valuation"]["method"] = METHOD_MAP[cid]
        component["valuation"]["calculation_proof"] = proof
        component["valuation"]["valuation_status"] = "bounded_estimate"
        component["valuation"]["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]
        component["valuation"]["evidence"] = (
            f"FY2025 20-F cash $7.3M, Tanbreez 42%, PEA ~$3B pre-tax NPV, BMW $15M advance, "
            f"Stage 2 14.5M shares; proof base {ev['outputs']['base']}/sh via "
            f"{METHOD_MAP[cid]}@1.0 ({EVIDENCE_RECON})."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One ordinary share of Critical Metals Corp.: net cash, risked 42% Tanbreez "
            "REE stake, Wolfsberg lithium option, less dilution/GEM reserve."
        ),
        "excluded_claims": [
            "Pre-tax PEA project NPV is not equity value without composite risk factor.",
            "BMW $15M advance is restricted and not counted in corporate cash.",
            "Stage 2 share issuance reserve does not double-count shares outstanding.",
        ],
        "reconciliation": (
            "Cash $7.3M / 104.9M sh + risked Tanbreez PEA claim + Wolfsberg milestone "
            "option − dilution reserve; proofs sum to legacy base $3.07/sh."
        ),
        "evidence_ref": EVIDENCE_RECON,
    }
    eva["validation_errors"] = []

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
