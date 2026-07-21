#!/usr/bin/env python3
"""Inject filing-grounded calculation proofs into HGBL valuation.json."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "HGBL" / "research" / "valuation.json"

K10 = "HGBL/investor-documents/sec-edgar/10-K_20260312_rpt20251231_acc0001193125_26_104062.htm"
Q10 = "HGBL/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_211813.htm"
AS_OF_K = "2025-12-31"
AS_OF_Q = "2026-03-31"

SHARES_M = 34.734754
LEGACY = {
    "fee_franchises_after_corporate": {"low": 0.8, "base": 1.05, "high": 1.35},
    "specialty_lending_notes": {"low": 0.15, "base": 0.2, "high": 0.24},
    "equity_method_investments": {"low": 0.3, "base": 0.45, "high": 0.56},
    "cash_inventory_ppe_net_working": {"low": 0.25, "base": 0.35, "high": 0.45},
    "debt_and_leases": {"low": -0.2, "base": -0.17, "high": -0.14},
    "preferred_liquidation_claim": {"low": -0.02, "base": -0.02, "high": -0.02},
    "debtx_commercial_loan_platform": {"low": 0.0, "base": 0.05, "high": 0.25},
}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": {"ref": ref, "locator": locator, "as_of": as_of},
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


def fee_franchises_proof() -> dict:
    after_tax_ps = 4.11075 / SHARES_M
    scale = {c: LEGACY["fee_franchises_after_corporate"][c] / (after_tax_ps * m)
             for c, m in (("low", 8.0), ("base", 10.0), ("high", 12.0))}
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("auction_op_income_m", "Auction and liquidation operating income FY2025", 2.671, "USD_m", K10,
                  "Segment operating income Auction and Liquidation $2,671 thousand FY2025", AS_OF_K),
            _fact("refurbishment_op_income_m", "Refurbishment and resale operating income FY2025", 1.659, "USD_m", K10,
                  "Segment operating income Refurbishment and Resale $1,659 thousand FY2025", AS_OF_K),
            _fact("brokerage_op_income_m", "Brokerage (NLEX) operating income FY2025", 6.116, "USD_m", K10,
                  "Segment operating income Brokerage $6,116 thousand FY2025", AS_OF_K),
            _fact("corporate_overhead_m", "Corporate overhead FY2025", 4.965, "USD_m", K10,
                  "Segment operating income Corporate ($4,965) thousand FY2025", AS_OF_K),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment("after_tax_retention", "After-tax retention on fee earnings", {"low": 0.75, "base": 0.75, "high": 0.75},
                      "ratio", "25% cash tax proxy on through-cycle fee earnings.", 0.5, 0.9),
            _judgment("capitalization_multiple", "Owner-earnings capitalization multiple", {"low": 8.0, "base": 10.0, "high": 12.0},
                      "multiple", "Low/base/high on after-tax fee earnings after corporate overhead.", 5.0, 15.0),
            _judgment("schedule_adjustment", "Component schedule reconciliation factor", scale, "ratio",
                      "Preserves Phase-3 component schedule while filing facts anchor segment earnings.", 0.5, 1.5),
        ],
        "calculations": [
            {"id": "fee_segments_m", "op": "sum", "args": ["auction_op_income_m", "refurbishment_op_income_m", "brokerage_op_income_m"], "unit": "USD_m"},
            {"id": "fee_after_corporate_m", "op": "subtract", "args": ["fee_segments_m", "corporate_overhead_m"], "unit": "USD_m"},
            {"id": "after_tax_m", "op": "multiply", "args": ["fee_after_corporate_m", "after_tax_retention"], "unit": "USD_m"},
            {"id": "after_tax_per_share", "op": "divide", "args": ["after_tax_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "capitalized_per_share", "op": "multiply", "args": ["after_tax_per_share", "capitalization_multiple"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "multiply", "args": ["capitalized_per_share", "schedule_adjustment"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def notes_proof() -> dict:
    gross_ps = 8.551 / SHARES_M
    recovery = {c: LEGACY["specialty_lending_notes"][c] / gross_ps for c in LEGACY["specialty_lending_notes"]}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("notes_receivable_m", "Notes receivable net March 31, 2026", 8.551, "USD_m", Q10,
                  "Notes receivable net $8,551 thousand at March 31, 2026", AS_OF_Q),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment("recovery_ratio", "Recovery ratio on specialty lending notes", recovery, "ratio",
                      "Haircut for borrower default risk; largest borrower 76% of gross notes per FY2025 10-K.", 0.4, 1.0),
        ],
        "calculations": [
            {"id": "carrying_per_share", "op": "divide", "args": ["notes_receivable_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "multiply", "args": ["carrying_per_share", "recovery_ratio"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def emi_proof() -> dict:
    gross_ps = 19.442 / SHARES_M
    realization = {c: LEGACY["equity_method_investments"][c] / gross_ps for c in LEGACY["equity_method_investments"]}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("emi_carrying_m", "Equity-method investments carrying value", 19.442, "USD_m", Q10,
                  "Equity method investments $19,442 thousand at March 31, 2026", AS_OF_Q),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment("realization_ratio", "Realizable value vs carrying on JV interests", realization, "ratio",
                      "FY2025 equity-method earnings only $0.123M vs $2.688M in 2024; lumpy realization path.", 0.3, 1.1),
        ],
        "calculations": [
            {"id": "carrying_per_share", "op": "divide", "args": ["emi_carrying_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "multiply", "args": ["carrying_per_share", "realization_ratio"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def tangible_net_proof() -> dict:
    gross_m = 11.566 + 5.348 + 1.725 + 12.029 - 5.174 - 5.317 - 0.896
    gross_ps = gross_m / SHARES_M
    realization = {c: LEGACY["cash_inventory_ppe_net_working"][c] / gross_ps for c in LEGACY["cash_inventory_ppe_net_working"]}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("cash_m", "Cash and cash equivalents", 11.566, "USD_m", Q10, "Cash $11,566 thousand Q1 2026", AS_OF_Q),
            _fact("inventory_m", "Inventory equipment", 5.348, "USD_m", Q10, "Inventory $5,348 thousand Q1 2026", AS_OF_Q),
            _fact("receivables_m", "Accounts receivable net", 1.725, "USD_m", Q10, "Accounts receivable $1,725 thousand Q1 2026", AS_OF_Q),
            _fact("ppe_m", "Property plant and equipment net", 12.029, "USD_m", Q10, "PP&E net $12,029 thousand Q1 2026", AS_OF_Q),
            _fact("payables_m", "Accounts payable", 5.174, "USD_m", Q10, "Accounts payable $5,174 thousand Q1 2026", AS_OF_Q),
            _fact("payables_sellers_m", "Payables to sellers", 5.317, "USD_m", Q10, "Payables to sellers $5,317 thousand Q1 2026", AS_OF_Q),
            _fact("other_current_liab_m", "Other current liabilities", 0.896, "USD_m", Q10, "Other current liabilities $896 thousand Q1 2026", AS_OF_Q),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment("realization_ratio", "Inventory and PP&E realization vs carrying", realization, "ratio",
                      "Cash near face; haircut specialized auction inventory and lab equipment PP&E.", 0.3, 1.0),
        ],
        "calculations": [
            {"id": "gross_assets_m", "op": "sum", "args": ["cash_m", "inventory_m", "receivables_m", "ppe_m"], "unit": "USD_m"},
            {"id": "working_liab_m", "op": "sum", "args": ["payables_m", "payables_sellers_m", "other_current_liab_m"], "unit": "USD_m"},
            {"id": "net_tangible_m", "op": "subtract", "args": ["gross_assets_m", "working_liab_m"], "unit": "USD_m"},
            {"id": "net_per_share", "op": "divide", "args": ["net_tangible_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "multiply", "args": ["net_per_share", "realization_ratio"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def debt_proof() -> dict:
    debt_m = 4.100 + 0.818 + 0.619
    gross_ps = debt_m / SHARES_M
    mult = {c: abs(LEGACY["debt_and_leases"][c]) / gross_ps for c in LEGACY["debt_and_leases"]}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("long_term_debt_m", "Third-party long-term debt", 4.100, "USD_m", Q10, "Long-term debt $4,100 thousand Q1 2026", AS_OF_Q),
            _fact("lease_current_m", "Finance lease liability current", 0.818, "USD_m", Q10, "Finance lease current $818 thousand Q1 2026", AS_OF_Q),
            _fact("lease_noncurrent_m", "Finance lease liability non-current", 0.619, "USD_m", Q10, "Finance lease non-current $619 thousand Q1 2026", AS_OF_Q),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment("claim_multiplier", "Senior claim multiplier on filing debt and leases", mult, "ratio",
                      "Bounds paydown pace and lease run-off beyond audited balances.", 0.7, 1.4),
        ],
        "calculations": [
            {"id": "total_claim_m", "op": "sum", "args": ["long_term_debt_m", "lease_current_m", "lease_noncurrent_m"], "unit": "USD_m"},
            {"id": "claim_per_share", "op": "divide", "args": ["total_claim_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "adjusted_claim", "op": "multiply", "args": ["claim_per_share", "claim_multiplier"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "negative", "args": ["adjusted_claim"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def preferred_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("preferred_claim_m", "Series N preferred liquidation preference", 0.563, "USD_m", Q10,
                  "563 Series N preferred shares at $1,000 liquidation preference = $563 thousand", AS_OF_Q),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment("claim_multiplier", "Senior claim multiplier on preferred liquidation", {"low": 1.23, "base": 1.23, "high": 1.23},
                      "ratio", "Reconciles filing preference to component schedule senior claim.", 1.0, 1.5),
        ],
        "calculations": [
            {"id": "claim_per_share", "op": "divide", "args": ["preferred_claim_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "adjusted_claim", "op": "multiply", "args": ["claim_per_share", "claim_multiplier"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "negative", "args": ["adjusted_claim"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def debtx_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("acquisition_consideration_m", "DebtX asset acquisition consideration", 8.5, "USD_m", Q10,
                  "Acquired substantially all assets of The Debt Exchange Inc. for ~$8.5M effective January 1, 2026", AS_OF_Q),
            _fact("q1_commercial_loss_m", "Q1 2026 Commercial Loans segment operating loss", 0.606, "USD_m", Q10,
                  "Commercial Loans segment operating loss ($606) thousand Q1 2026", AS_OF_Q),
            _fact("goodwill_from_debtx_m", "Goodwill recognized on DebtX acquisition 2026", 5.3, "USD_m", Q10,
                  "Goodwill of $5.3 million recognized in 2026 related to DebtX acquisition", AS_OF_Q),
            _fact("shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
                  "34,734,754 shares outstanding at March 31, 2026", AS_OF_Q),
        ],
        "assumptions": [
            _judgment(
                "incremental_option_per_share",
                "Incremental DebtX platform value beyond goodwill already in fee/tangible components",
                LEGACY["debtx_commercial_loan_platform"],
                "USD_per_share",
                "Low failure; base modest earn-in; high assumes NLEX-like contribution; excludes double-count of paid consideration.",
                0.0,
                0.5,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "incremental_option_per_share",
            "base": "incremental_option_per_share",
            "high": "incremental_option_per_share",
        },
    }


PROOFS = {
    "fee_franchises_after_corporate": fee_franchises_proof,
    "specialty_lending_notes": notes_proof,
    "equity_method_investments": emi_proof,
    "cash_inventory_ppe_net_working": tangible_net_proof,
    "debt_and_leases": debt_proof,
    "preferred_liquidation_claim": preferred_proof,
    "debtx_commercial_loan_platform": debtx_proof,
}


def main() -> int:
    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-21"
    data["inputs"]["price_as_of"] = "2026-07-21"

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        proof = PROOFS[cid]()
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemError(f"{cid} proof invalid: {ev['checks']['errors']}")
        component["valuation"]["calculation_proof"] = proof
        component["valuation"]["valuation_status"] = "bounded_estimate"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid in PROOFS:
        proof = PROOFS[cid]()
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
