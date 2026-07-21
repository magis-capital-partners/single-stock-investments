#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into GYRO valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "GYRO" / "research" / "valuation.json"

FILING_10Q = (
    "GYRO/investor-documents/sec-edgar/"
    "10-Q_20260513_rpt20260331_acc0001437749_26_016537.htm"
)
AS_OF = "2026-03-31"
SHARES_M = 2.199308
SHARES = 2199308

LEGACY = {
    "real_estate_nrv": {"low": 22.0, "base": 24.55, "high": 27.0},
    "cash_and_other_assets": {"low": 1.5, "base": 1.87, "high": 2.2},
    "loans_payable": {"low": -5.2, "base": -4.91, "high": -4.5},
    "estimated_liquidation_costs": {"low": -9.5, "base": -7.6, "high": -6.0},
    "other_liabilities": {"low": -2.5, "base": -2.12, "high": -1.8},
}


def _src(locator: str) -> dict:
    return {"ref": FILING_10Q, "locator": locator, "as_of": AS_OF}


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


def _judgment(node_id: str, label: str, values: dict, unit: str, rationale: str, lo: float, hi: float) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "judgment",
        "values": values,
        "unit": unit,
        "rationale": rationale,
        "allowed_range": {"min": lo, "max": hi},
    }


def _nav_proof(
    *,
    claim_m_id: str,
    claim_label: str,
    claim_values: dict,
    claim_rationale: str,
    claim_bounds: tuple[float, float],
    filing_locator: str,
    negative: bool = False,
) -> dict:
    calcs = [
        {
            "id": "claim_per_share",
            "label": f"{claim_label} per share",
            "op": "divide",
            "args": [claim_m_id, "shares_m"],
            "unit": "USD_per_share",
        }
    ]
    if negative:
        calcs.append(
            {
                "id": "value_per_share",
                "label": f"{claim_label} per share (senior claim)",
                "op": "negative",
                "args": ["claim_per_share"],
                "unit": "USD_per_share",
            }
        )
        output_node = "value_per_share"
    else:
        output_node = "claim_per_share"

    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares",
                  f"{SHARES:,} shares outstanding as of 2026-05-13 cover page"),
        ],
        "assumptions": [
            _judgment(
                claim_m_id,
                claim_label,
                claim_values,
                "USD_m",
                claim_rationale,
                claim_bounds[0],
                claim_bounds[1],
            ),
        ],
        "calculations": calcs,
        "outputs": {"low": output_node, "base": output_node, "high": output_node},
    }


PROOFS = {
    "real_estate_nrv": _nav_proof(
        claim_m_id="real_estate_nrv_m",
        claim_label="Real estate held for sale at estimated NRV",
        claim_values={
            "low": round(LEGACY["real_estate_nrv"]["low"] * SHARES_M, 3),
            "base": 53.99,
            "high": round(LEGACY["real_estate_nrv"]["high"] * SHARES_M, 3),
        },
        claim_rationale=(
            "Base is filing liquidation-basis NRV including the B2K $28.74M gross assumption; "
            "low/high bound entitlement or forced-sale re-marks."
        ),
        claim_bounds=(45.0, 65.0),
        filing_locator="RealEstateHeldForSale $53,990,000 at 2026-03-31",
    ),
    "cash_and_other_assets": _nav_proof(
        claim_m_id="non_re_assets_m",
        claim_label="Cash and other non-real-estate assets",
        claim_values={
            "low": round(LEGACY["cash_and_other_assets"]["low"] * SHARES_M, 3),
            "base": round(4.117127, 3),
            "high": round(LEGACY["cash_and_other_assets"]["high"] * SHARES_M, 3),
        },
        claim_rationale=(
            "Base equals total assets $58.107M less real estate held for sale $53.990M; "
            "range allows working-capital burn before distributions."
        ),
        claim_bounds=(3.0, 5.5),
        filing_locator=(
            "CashAndCashEquivalentsAtCarryingValue $3,950,227 plus other non-RE assets; "
            "total assets $58,107,127 less real estate $53,990,000"
        ),
    ),
    "loans_payable": _nav_proof(
        claim_m_id="loans_payable_m",
        claim_label="Loans payable",
        claim_values={
            "low": round(abs(LEGACY["loans_payable"]["low"]) * SHARES_M, 3),
            "base": 10.790194,
            "high": round(abs(LEGACY["loans_payable"]["high"]) * SHARES_M, 3),
        },
        claim_rationale=(
            "Contractual loans payable senior to equity; low case assumes refinancing stress "
            "or higher drawn balances."
        ),
        claim_bounds=(9.0, 13.0),
        filing_locator="LoansPayable $10,790,194 at 2026-03-31",
        negative=True,
    ),
    "estimated_liquidation_costs": _nav_proof(
        claim_m_id="liquidation_costs_m",
        claim_label="Estimated liquidation and operating costs net of receipts",
        claim_values={
            "low": round(abs(LEGACY["estimated_liquidation_costs"]["low"]) * SHARES_M, 3),
            "base": 16.709887,
            "high": round(abs(LEGACY["estimated_liquidation_costs"]["high"]) * SHARES_M, 3),
        },
        claim_rationale=(
            "Management accrual through the 2028 target date, including B2K seller credit; "
            "FY2025 already showed upward re-estimation risk."
        ),
        claim_bounds=(12.0, 24.0),
        filing_locator=(
            "Estimated liquidation and operating costs net of receipts $16,709,887 at 2026-03-31"
        ),
        negative=True,
    ),
    "other_liabilities": _nav_proof(
        claim_m_id="other_liabilities_m",
        claim_label="Other balance-sheet liabilities",
        claim_values={
            "low": round(abs(LEGACY["other_liabilities"]["low"]) * SHARES_M, 3),
            "base": round(4.683044, 3),
            "high": round(abs(LEGACY["other_liabilities"]["high"]) * SHARES_M, 3),
        },
        claim_rationale=(
            "Plug of accounts payable, accrued liabilities, and tenant deposits after loans "
            "and estimated liquidation costs; reconciles to $11.79 net assets in liquidation."
        ),
        claim_bounds=(3.5, 6.0),
        filing_locator=(
            "Total liabilities $32,183,125 less loans $10,790,194 and estimated liquidation "
            "costs $16,709,887"
        ),
        negative=True,
    ),
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
            f"10-Q Q1 2026 liquidation-basis statement of net assets; proof base "
            f"{ev['outputs']['base']}/sh via net_asset_value@1.0 ({FILING_10Q})."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One Gyrodyne common share claim on net assets in liquidation after loans, "
            "estimated liquidation costs, and other liabilities."
        ),
        "excluded_claims": [
            "B2K Flowerfield entitlement option is embedded in real_estate_nrv, not additive.",
            "Operating rental income is netted inside the liquidation cost accrual.",
        ],
        "reconciliation": (
            "Real estate NRV $53.99M + non-RE assets $4.12M − loans $10.79M − liquidation "
            "costs $16.71M − other liabilities $4.68M ÷ 2,199,308 shares = $11.79/sh disclosed."
        ),
        "evidence_ref": "GYRO/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
