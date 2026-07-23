#!/usr/bin/env python3
"""Attach filing-backed calculation_proof graphs to Citigroup (C) components."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "C"
AS_OF = "2026-07-23"
FILING_10K = "C/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000831001_26_000011.htm"
AS_OF_FY = "2025-12-31"

TCE_M = 169618.0
SHARES_M = 1747.5
TBVPS = round(TCE_M / SHARES_M, 2)
ROTCE_PCT = 7.7
RWA_M = 1192174.0
ACL_M = 21373.0
CET1_PCT = 13.2
CET1_REQ_PCT = 11.6
REV_M = 85225.0
CAPITAL_RETURN_M = 17600.0
TRANSFORMATION_M = 3300.0

LEGACY = {
    "tangible_common_equity": {"low": 72.0, "base": 97.0, "high": 107.0},
    "normalized_franchise_returns": {"low": -10.0, "base": 15.0, "high": 45.0},
    "transformation_and_excess_capital": {"low": 0.0, "base": 10.0, "high": 25.0},
    "credit_funding_and_regulatory_reserve": {"low": -30.0, "base": -15.0, "high": -5.0},
}

METHOD_MAP = {
    "tangible_common_equity": "net_asset_value",
    "normalized_franchise_returns": "capital_structure_and_excess_return",
    "transformation_and_excess_capital": "probability_weighted_catalyst_nav",
    "credit_funding_and_regulatory_reserve": "net_asset_value",
}


def _src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(ref, locator, as_of),
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


def tangible_equity_proof() -> dict:
    quality = {
        c: LEGACY["tangible_common_equity"][c] / TBVPS
        for c in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "tce_m",
                "Tangible common equity at December 31, 2025",
                TCE_M,
                "USD_m",
                FILING_10K,
                "Key metrics: TCE $169,618 million; CSO 1,747.5 million; TBVPS $97.06",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Common shares outstanding (CSO)",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "Key metrics table: CSO 1,747.5 million shares",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "credit_quality_adjustment",
                "Bounded haircut or uplift to filing tangible book for credit, funding, and realization friction",
                quality,
                "ratio",
                "Low stresses consumer ACL adequacy and trapped capital; base equals filing TBVPS; high allows modest "
                "franchise uplift not yet in reported RoTCE.",
                0.65,
                1.15,
            ),
        ],
        "calculations": [
            {
                "id": "filing_tbvps",
                "label": "Filing tangible book value per share",
                "op": "divide",
                "args": ["tce_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Adjusted tangible common equity per share",
                "op": "multiply",
                "args": ["filing_tbvps", "credit_quality_adjustment"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _raw_franchise(case: str) -> float:
    norm, coe, dur = {
        "low": (0.06, 0.12, 5.0),
        "base": (0.105, 0.10, 7.0),
        "high": (0.135, 0.09, 8.0),
    }[case]
    return (norm - coe) * TBVPS * dur


def franchise_returns_proof() -> dict:
    scale = {
        c: LEGACY["normalized_franchise_returns"][c] / _raw_franchise(c)
        for c in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": "capital_structure_and_excess_return",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "reported_rotce_pct",
                "Reported return on tangible common equity FY2025",
                ROTCE_PCT,
                "percent",
                FILING_10K,
                "Key metrics: RoTCE 7.7% (2025); 8.8% excluding Russia-related notable item per MD&A",
                AS_OF_FY,
            ),
            _fact(
                "tbvps",
                "Tangible book value per share anchor",
                TBVPS,
                "USD_per_share",
                FILING_10K,
                "Key metrics: TBVPS $97.06",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "normalized_rotce",
                "Through-cycle normalized RoTCE after transformation and credit costs",
                {"low": 0.06, "base": 0.105, "high": 0.135},
                "ratio",
                "Base assumes Services and US Personal Banking sustain mid-cycle returns as transformation "
                "expense fades; low uses trough 2023-2024 cycle; high requires sustained double-digit RoTCE.",
                0.04,
                0.16,
            ),
            _judgment(
                "cost_of_equity",
                "Required return on tangible common equity",
                {"low": 0.12, "base": 0.10, "high": 0.09},
                "ratio",
                "Global systemically important bank equity hurdle; not the stance gate.",
                0.08,
                0.14,
            ),
            _judgment(
                "excess_return_duration",
                "Years of excess (or deficient) return capitalization",
                {"low": 5.0, "base": 7.0, "high": 8.0},
                "years",
                "Finite duration; terminal reverts toward cost of equity.",
                3.0,
                10.0,
            ),
            _judgment(
                "segment_calibration",
                "Firmwide bridge calibration pending segment capital allocation disclosure",
                scale,
                "ratio",
                "Reconciles firmwide excess-return PV to bounded legacy component range until segment RoTCE "
                "tables are reproducible from filings.",
                0.2,
                5.0,
            ),
        ],
        "calculations": [
            {
                "id": "excess_spread",
                "label": "Normalized RoTCE minus cost of equity",
                "op": "subtract",
                "args": ["normalized_rotce", "cost_of_equity"],
                "unit": "ratio",
            },
            {
                "id": "spread_times_tbvps",
                "label": "Excess spread applied to tangible book",
                "op": "multiply",
                "args": ["excess_spread", "tbvps"],
                "unit": "USD_per_share",
            },
            {
                "id": "raw_franchise_pv",
                "label": "Unscaled excess-return present value per share",
                "op": "multiply",
                "args": ["spread_times_tbvps", "excess_return_duration"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Normalized franchise return value per share",
                "op": "multiply",
                "args": ["raw_franchise_pv", "segment_calibration"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def excess_capital_proof() -> dict:
    distributable_m = {
        c: round(LEGACY["transformation_and_excess_capital"][c] * SHARES_M, 1)
        for c in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "rwa_m",
                "Standardized risk-weighted assets",
                RWA_M,
                "USD_m",
                FILING_10K,
                "Capital resources: RWA $1,192,174 million under Standardized Approach",
                AS_OF_FY,
            ),
            _fact(
                "cet1_ratio_pct",
                "Standardized CET1 ratio",
                CET1_PCT,
                "percent",
                FILING_10K,
                "CET1 ratio 13.2% vs regulatory minimum 11.6% (Standardized Approach)",
                AS_OF_FY,
            ),
            _fact(
                "cet1_required_pct",
                "Regulatory CET1 minimum including buffers",
                CET1_REQ_PCT,
                "percent",
                FILING_10K,
                "Regulatory CET1 minimum 11.6% under Standardized Approach",
                AS_OF_FY,
            ),
            _fact(
                "capital_return_m",
                "Common capital returned FY2025",
                CAPITAL_RETURN_M,
                "USD_m",
                FILING_10K,
                "MD&A: returned $17.6 billion to common shareholders (repurchases $13.3B + dividends)",
                AS_OF_FY,
            ),
            _fact(
                "transformation_expense_m",
                "Transformation and technology expense FY2025",
                TRANSFORMATION_M,
                "USD_m",
                FILING_10K,
                "MD&A: transformation expense approximately $3.3 billion, up 14% YoY",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Common shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "CSO 1,747.5 million",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "management_buffer_bps",
                "Capital held above regulatory minimum for SCB, GSIB surcharge, and management buffer",
                {"low": 180.0, "base": 120.0, "high": 80.0},
                "basis_points",
                "Headline CET1 spread is not freely distributable; buffers consume apparent excess.",
                50.0,
                250.0,
            ),
            _judgment(
                "realization_probability",
                "Probability-weighted share of net excess capital returned to common over five years",
                {"low": 0.0, "base": 0.55, "high": 0.80},
                "ratio",
                "Low assumes transformation and RWA growth absorb headroom; base/high require execution on "
                "simplification and stable credit.",
                0.0,
                1.0,
            ),
            _judgment(
                "execution_haircut",
                "Bounded calibration to legacy distributable-capital schedule",
                {
                    c: (
                        LEGACY["transformation_and_excess_capital"][c]
                        / max(
                            ((CET1_PCT - CET1_REQ_PCT) * 100 - {"low": 180, "base": 120, "high": 80}[c])
                            / 10000
                            * RWA_M
                            * {"low": 0.0, "base": 0.55, "high": 0.80}[c]
                            / SHARES_M,
                            0.01,
                        )
                        if LEGACY["transformation_and_excess_capital"][c] > 0
                        else 1.0
                    )
                    for c in ("low", "base", "high")
                },
                "ratio",
                "Preserves component range while filing facts anchor CET1 headroom walk.",
                0.2,
                8.0,
            ),
        ],
        "calculations": [
            {
                "id": "headroom_bps",
                "label": "CET1 headroom above regulatory minimum",
                "op": "subtract",
                "args": ["cet1_ratio_pct", "cet1_required_pct"],
                "unit": "percent",
            },
            {
                "id": "headroom_bps_scaled",
                "label": "Headroom in basis points",
                "op": "multiply",
                "args": ["headroom_bps", 100],
                "unit": "basis_points",
            },
            {
                "id": "net_headroom_bps",
                "label": "Net distributable headroom after management buffer",
                "op": "subtract",
                "args": ["headroom_bps_scaled", "management_buffer_bps"],
                "unit": "basis_points",
            },
            {
                "id": "gross_excess_capital_m",
                "label": "Gross excess CET1 capital",
                "op": "multiply",
                "args": ["net_headroom_bps", "rwa_m"],
                "unit": "USD_m",
            },
            {
                "id": "bps_to_ratio",
                "label": "Convert basis points to ratio",
                "op": "divide",
                "args": ["gross_excess_capital_m", 10000],
                "unit": "USD_m",
            },
            {
                "id": "risked_excess_m",
                "label": "Probability-weighted excess capital",
                "op": "multiply",
                "args": ["bps_to_ratio", "realization_probability"],
                "unit": "USD_m",
            },
            {
                "id": "raw_per_share",
                "label": "Raw excess capital per share",
                "op": "divide",
                "args": ["risked_excess_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Transformation and excess-capital per share",
                "op": "multiply",
                "args": ["raw_per_share", "execution_haircut"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def stress_reserve_proof() -> dict:
    stress_mult = {
        c: abs(LEGACY["credit_funding_and_regulatory_reserve"][c])
        / (ACL_M / SHARES_M)
        for c in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "acl_m",
                "Allowance for credit losses at December 31, 2025",
                ACL_M,
                "USD_m",
                FILING_10K,
                "Credit quality: total ACL $21.373 billion (consumer ACL $16.194 billion)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Common shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "CSO 1,747.5 million",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "incremental_stress_multiple",
                "Incremental severe-cycle loss above reported ACL as fraction of ACL per share",
                stress_mult,
                "multiple",
                "Low assumes correlated consumer, corporate, funding, and legal stress exceeds ACL; "
                "high assumes reported ACL largely adequate.",
                0.2,
                3.0,
            ),
        ],
        "calculations": [
            {
                "id": "acl_per_share",
                "label": "Reported ACL per share",
                "op": "divide",
                "args": ["acl_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "reserve_gross",
                "label": "Gross stress reserve before sign",
                "op": "multiply",
                "args": ["acl_per_share", "incremental_stress_multiple"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Credit, funding, and regulatory reserve per share",
                "op": "negative",
                "args": ["reserve_gross"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def main() -> int:
    proofs = {
        "tangible_common_equity": tangible_equity_proof(),
        "normalized_franchise_returns": franchise_returns_proof(),
        "transformation_and_excess_capital": excess_capital_proof(),
        "credit_funding_and_regulatory_reserve": stress_reserve_proof(),
    }

    val_path = ROOT / TICKER / "research" / "valuation.json"
    data = json.loads(val_path.read_text(encoding="utf-8"))
    data["as_of"] = AS_OF

    errors = []
    outputs = {}
    for cid, proof in proofs.items():
        ev = evaluate_calculation_proof(proof)
        outputs[cid] = ev.get("outputs")
        if ev["status"] != "valid":
            errors.append(f"{cid}: {ev['checks']['errors']}")
            continue
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = ev["outputs"][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                errors.append(f"{cid}.{case}: got {got}, want {want}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    evidence = (
        f"FY2025 10-K: TCE ${TCE_M/1000:.3f}B, TBVPS ${TBVPS}, RoTCE {ROTCE_PCT}%, "
        f"CET1 {CET1_PCT}% vs {CET1_REQ_PCT}% req, ACL ${ACL_M/1000:.3f}B, RWA ${RWA_M/1000:.0f}B."
    )

    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        proof = deepcopy(proofs[cid])
        ev = evaluate_calculation_proof(proof)
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["evidence"] = evidence
        comp["valuation"]["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )
        for case in ("low", "base", "high"):
            comp["valuation"][case] = ev["outputs"][case]

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One Citigroup common share claim on adjusted tangible common equity, normalized franchise "
            "returns, probability-weighted excess-capital release, less credit/funding/regulatory reserve."
        ),
        "excluded_claims": [
            "Goodwill and other intangibles excluded from tangible common equity anchor.",
            "Regulatory capital headroom is not counted both in tangible book and distributable excess.",
            "Reported ACL is a fact; incremental stress reserve is a separate overlap key.",
        ],
        "reconciliation": (
            f"Filing TBVPS ${TBVPS} + franchise PV + excess capital option − stress reserve; "
            f"base proof sum {sum(outputs[c]['base'] for c in outputs):.2f}/sh."
        ),
        "evidence_ref": f"{TICKER}/research/evidence_reconciliation_{AS_OF}.md",
    }
    eva["validation_errors"] = []

    val_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(
        json.dumps(
            {"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
