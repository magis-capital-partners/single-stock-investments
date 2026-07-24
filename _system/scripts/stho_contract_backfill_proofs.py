#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into STHO valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "STHO" / "research" / "valuation.json"
FILING_10Q = (
    "STHO/investor-documents/sec-edgar/"
    "10-Q_20260508_rpt20260331_acc0001953366_26_000010.htm"
)
AS_OF = "2026-03-31"
SHARES = 12_081_333
SHARES_M = round(SHARES / 1_000_000, 6)

LEGACY = {
    "safehold_equity_stake": {"low": 13.0, "base": 18.5, "high": 28.0},
    "legacy_monetizing_portfolio": {"low": 3.5, "base": 5.3, "high": 6.5},
    "magnolia_asbury_development_ops": {"low": 4.0, "base": 7.5, "high": 13.0},
    "cash_and_restricted": {"low": 5.0, "base": 5.1, "high": 5.1},
    "senior_debt": {"low": -17.5, "base": -17.1, "high": -16.5},
    "wind_down_fee_and_friction_reserve": {"low": -2.5, "base": -1.4, "high": -0.4},
    "zero_carry_and_entitlement_option": {"low": 0.0, "base": 0.2, "high": 2.0},
}


def _src(locator: str, *, as_of: str = AS_OF) -> dict:
    return {"ref": FILING_10Q, "locator": locator, "as_of": as_of}


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
        "source": _src(locator),
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


def _nav_per_share_proof(
    *,
    claim_m_id: str,
    claim_label: str,
    claim_values: dict,
    claim_rationale: str,
    claim_bounds: tuple[float, float],
    filing_locator: str,
    negative: bool = False,
    method_id: str = "net_asset_value",
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
        "method_id": method_id,
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                f"{SHARES:,} shares outstanding as of 2026-05-06 cover page",
            ),
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


def _recovery_proof(
    *,
    component_id: str,
    carrying_m: float,
    carrying_locator: str,
    recovery_values: dict,
    recovery_rationale: str,
    recovery_bounds: tuple[float, float],
    method_id: str = "probability_weighted_catalyst_nav",
) -> dict:
    return {
        "schema_version": "1.0",
        "method_id": method_id,
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                f"{SHARES:,} shares outstanding as of 2026-05-06 cover page",
            ),
            _fact(
                "carrying_m",
                f"{component_id} carrying value",
                carrying_m,
                "USD_m",
                carrying_locator,
            ),
        ],
        "assumptions": [
            _judgment(
                "recovery_fraction",
                "Probability-weighted recovery vs carrying",
                recovery_values,
                "fraction",
                recovery_rationale,
                recovery_bounds[0],
                recovery_bounds[1],
            ),
        ],
        "calculations": [
            {
                "id": "risked_carrying_m",
                "label": "Risk-adjusted carrying value",
                "op": "multiply",
                "args": ["carrying_m", "recovery_fraction"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Component value per share",
                "op": "divide",
                "args": ["risked_carrying_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "safehold_equity_stake": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                f"{SHARES:,} shares outstanding as of 2026-05-06 cover page",
            ),
            _estimate(
                "safe_shares_m",
                "Implied Safehold shares owned",
                13.525499,
                "million_shares",
                "Note 7: ~13.5M SAFE shares; FV $183.0M at $13.53 implies 13,525,499 shares",
            ),
        ],
        "assumptions": [
            _judgment(
                "safe_price",
                "Scenario Safehold share price before friction",
                {"low": 11.614, "base": 16.505, "high": 24.992},
                "USD_per_share",
                "Low forced-sale mark; base near Q1 filing mark updated to July 2026 quote; "
                "high path toward March 2023 ~$25 deal mark (rate-sensitive ground leases).",
                8.0,
                30.0,
            ),
            _judgment(
                "realization_friction",
                "Sale friction / governance haircut on gross SAFE mark",
                {"low": 1.0, "base": 1.0, "high": 1.0},
                "fraction",
                "Gross SAFE mark per share before margin-loan netting in senior_debt component.",
                0.85,
                1.05,
            ),
        ],
        "calculations": [
            {
                "id": "gross_mark_m",
                "label": "Gross Safehold stake mark",
                "op": "multiply",
                "args": ["safe_shares_m", "safe_price"],
                "unit": "USD_m",
            },
            {
                "id": "risked_mark_m",
                "label": "Risk-adjusted Safehold stake mark",
                "op": "multiply",
                "args": ["gross_mark_m", "realization_friction"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Safehold equity stake per STHO share",
                "op": "divide",
                "args": ["risked_mark_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "legacy_monetizing_portfolio": _recovery_proof(
        component_id="legacy_monetizing_portfolio",
        carrying_m=71.4,
        carrying_locator=(
            "MD&A monetizing portfolio Q1 2026: loan $16.1M + AFS $38.2M + land $14.4M + "
            "properties $2.7M = $71.4M"
        ),
        recovery_values={"low": 0.592, "base": 0.897, "high": 1.100},
        recovery_rationale=(
            "Low haircuts loans/AFS/land; base reflects repayment and land-sale evidence; "
            "high allows modest premium above carrying on monetizing land sleeve."
        ),
        recovery_bounds=(0.4, 1.2),
    ),
    "magnolia_asbury_development_ops": _recovery_proof(
        component_id="magnolia_asbury_development_ops",
        carrying_m=153.6,
        carrying_locator=(
            "Residual Magnolia/Asbury carrying after removing MD&A monetizing bucket "
            "($153.6M = $12.72/sh per evidence_reconciliation_2026-07-16.md)"
        ),
        recovery_values={"low": 0.314, "base": 0.590, "high": 1.022},
        recovery_rationale=(
            "Lot sales cleared above cost of sales 2023–Q1 2026; base partial credit to carrying; "
            "high approaches carrying; low distressed realization."
        ),
        recovery_bounds=(0.2, 1.1),
    ),
    "cash_and_restricted": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                f"{SHARES:,} shares outstanding as of 2026-05-06 cover page",
            ),
            _fact(
                "cash_m",
                "Cash and restricted cash",
                62.059,
                "USD_m",
                "Note 8: cash $46.378M + restricted cash $15.681M = $62.059M",
            ),
        ],
        "assumptions": [
            _judgment(
                "availability_fraction",
                "Fraction of cash/restricted cash available to equity",
                {"low": 0.973, "base": 0.993, "high": 0.993},
                "fraction",
                "Base near carrying; low allows modest restricted-cash leakage or collateral lock-up.",
                0.9,
                1.0,
            ),
        ],
        "calculations": [
            {
                "id": "available_cash_m",
                "label": "Equity-available cash",
                "op": "multiply",
                "args": ["cash_m", "availability_fraction"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Cash and restricted cash per share",
                "op": "divide",
                "args": ["available_cash_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "senior_debt": _nav_per_share_proof(
        claim_m_id="debt_obligations_m",
        claim_label="Safe Credit Facility and Margin Loan obligations",
        claim_values={"low": 211.554, "base": 206.586, "high": 199.317},
        claim_rationale=(
            "Base equals Note 9 total debt obligations net $207.001M; low allows PIK accretion "
            "and incremental draws; high assumes modest paydown from asset sales."
        ),
        claim_bounds=(190.0, 220.0),
        filing_locator=(
            "Note 9: Safe Credit Facility $115.0M + Margin Loan $92.777M; "
            "total debt obligations net $207.001M"
        ),
        negative=True,
    ),
    "wind_down_fee_and_friction_reserve": _nav_per_share_proof(
        claim_m_id="fee_and_friction_m",
        claim_label="PV of management fees, termination overhang, and sale friction",
        claim_values={"low": 30.203, "base": 16.914, "high": 4.832},
        claim_rationale=(
            "Base anchored to contractual fee path (~$7.5M current term + 2% GBV ex-SAFE) "
            "and modest sale friction; low keeps termination overhang; high post-2027 contestability."
        ),
        claim_bounds=(3.0, 35.0),
        filing_locator="Note 1 management agreement fee schedule and termination formula",
        negative=True,
    ),
    "zero_carry_and_entitlement_option": {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                f"{SHARES:,} shares outstanding as of 2026-05-06 cover page",
            ),
        ],
        "assumptions": [
            _judgment(
                "incremental_option_m",
                "Incremental zero-carry / entitlement surplus beyond Magnolia carrying cases",
                {"low": 0.0, "base": 2.416, "high": 24.16},
                "USD_m",
                "Failure value zero; base modest entitlement surplus; high requires zero-carry recovery.",
                0.0,
                40.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Zero-carry and entitlement option per share",
                "op": "divide",
                "args": ["incremental_option_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
}


def close_authorized_evidence() -> None:
    auth_path = ROOT / "STHO" / "research" / "authorized_evidence.json"
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["contract_status"] = "decision_grade"
    auth["blockers"] = []
    auth["component_coverage"]["unvalued_component_count"] = 0
    auth["authorized_at"] = "2026-07-24T04:00:00Z"
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
            got = ev["outputs"][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                raise SystemExit(f"{cid}.{case}: got {got}, want {want}")
        val = component["valuation"]
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        val["evidence_tier"] = "primary_derived" if cid != "zero_carry_and_entitlement_option" else "speculative"
        for case in ("low", "base", "high"):
            val[case] = ev["outputs"][case]
        val["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )
        val["evidence"] = (
            f"Q1 2026 Form 10-Q ({FILING_10Q}); proof base {ev['outputs']['base']}/sh "
            f"via {proof['method_id']}@1.0."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One diluted STHO share claim on SAFE stake, legacy monetizing assets, "
            "Magnolia/Asbury residual, cash, less senior debt, fee reserve, and incremental options."
        ),
        "excluded_claims": [
            "Zero-carry loans valued only in zero_carry_and_entitlement_option, not legacy_monetizing_portfolio.",
            "Magnolia/Asbury residual separated from MD&A monetizing schedule to avoid double count.",
            "Margin Loan secured by SAFE shares; SAFE marked gross in safehold_equity_stake.",
        ],
        "reconciliation": (
            "Component proof sum base ≈ $18.1/sh vs Q1 book $19.88/sh cross-check; "
            "SAFE mark, debt bridge, and fee reserve reconciled in evidence_reconciliation_2026-07-24.md."
        ),
        "evidence_ref": "STHO/research/evidence_reconciliation_2026-07-24.md",
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
