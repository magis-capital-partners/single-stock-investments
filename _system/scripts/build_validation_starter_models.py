#!/usr/bin/env python3
"""Build explicit, auditable starter models for the method-validation cohort.

These are not committee-approved targets.  They ensure every material economic
claim is represented, keep facts separate from analyst ranges, and deliberately
remain evidence-blocked until the research follow-ups are closed.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AS_OF = "2026-07-15"


def component(cid, label, category, method, values, evidence, assumption, *, option=False):
    valuation = {
        "method": method,
        "basis": "per_share",
        "low": values[0], "base": values[1], "high": values[2],
        "evidence_tier": "analyst_estimate",
        "evidence": evidence,
        "assumption_summary": assumption,
        "cross_check": "Range must be reconciled to primary filings, normalized economics, and relevant transaction or public-market evidence before IC approval.",
        "falsifier": "Primary evidence or through-cycle results support economics below the low case or reveal an omitted claim.",
    }
    return {
        "id": cid, "label": label, "category": category,
        "overlap_key": cid, "treatment": "additive", "valuation": valuation,
    }


def model(ticker, profile, archetype, price, shares, source, components, wisdom):
    groups = []
    for row in components:
        group = {
            "id": row["id"], "label": row["label"], "component_ids": [row["id"]],
            "economic_claim": row["label"],
            "valuation_basis": row["valuation"]["assumption_summary"],
            "adjustments": "Low/base/high values incorporate ownership, tax, funding, cycle, and realization adjustments described in the component evidence.",
            "overlap_control": f"Unique overlap key {row['id']}; no other component capitalizes the same claim.",
        }
        if row["category"] == "real_option":
            group["risk_and_timing"] = {
                "probability_basis": "Starter probability is an explicit analyst judgment pending base-rate and milestone reconciliation.",
                "timing_basis": "Scenario range includes delay and failure outcomes.",
                "remaining_capital_basis": "Remaining capital and financing are deducted in the stated option range.",
            }
        groups.append(group)
    return {
        "ticker": ticker, "as_of": AS_OF, "method": "pending",
        "valuation_mode": "economic_value", "method_profile": profile,
        "classification_inputs": {"archetype": archetype, "cycle": "mid"},
        "inputs": {"price": price, "price_source": f"Market close retrieved {AS_OF}", "shares_outstanding": shares},
        "valuation_methodology": {
            "mode": "component_economic_value", "horizon_years": 7,
            "decision_rule": "Use one complete component schedule; preserve the range and evidence block until every material assumption is reconciled.",
        },
        "component_valuation": {
            "schema_version": "1.0", "all_material_components_identified": True,
            "coverage_statement": "Every currently identified material ownership claim, liability, and option is valued once. Unknown claims remain an evidence blocker, not an unvalued line item.",
            "components": components,
        },
        "economic_value": {
            "schema_version": "1.0", "method": "component_economic_value",
            "economic_claim": {
                "description": f"One diluted share of {ticker}, including every identified operating claim, asset, liability, and option.",
                "unit_label": "diluted share", "unit_count": shares,
                "unit_source": source,
                "enterprise_to_equity_reconciliation": "Operating and asset claims are valued once; cash, debt, financing, reserves, and other senior claims are included as separate components or within the stated equity basis.",
            },
            "gaap_role": "cross_check",
            "accounting_reference": source,
            "component_groups": groups,
            "wisdom_applied": wisdom,
            "limitations": [
                "Starter ranges are analyst estimates, not committee-approved price targets.",
                "The model remains evidence-blocked until primary-source normalization, comparable selection, and downside cases pass independent review.",
            ],
        },
    }


MODELS = {
    "C": model(
        "C", "credit_and_normalized_returns", "bank", 134.89, 1_747_500_000,
        "Citigroup 2025 Annual Report: 1.7475bn common shares, $169.618bn tangible common equity, $97.06 tangible book value per share, 7.7% RoTCE, 13.18% CET1.",
        [
            component("tangible_common_equity", "Tangible common equity", "financial_asset", "adjusted_tangible_book", (72, 97, 107), "2025 annual report tangible common equity and TBVPS.", "Marks tangible capital for credit, asset quality, and regulatory constraints rather than treating all book value as distributable."),
            component("normalized_franchise_returns", "Normalized franchise return value", "operating_business", "excess_return_on_tangible_equity", (-10, 15, 45), "2025 RoTCE was 7.7%; a full-cycle, segment-level return bridge is still required.", "Present value of sustainable returns above or below the required return on tangible common equity."),
            component("transformation_and_excess_capital", "Transformation and excess-capital realization", "real_option", "probability_weighted_capital_release", (0, 10, 25), "CET1 was 13.18%; release timing and regulatory minimums remain unverified.", "Only value capital that can be returned after transformation costs, stress losses, and regulatory buffers.", option=True),
            component("credit_funding_and_regulatory_reserve", "Credit, funding, and regulatory reserve", "liability_or_reserve", "stress_loss_reserve", (-30, -15, -5), "Annual-report credit, funding, and regulatory disclosures; detailed stress reconciliation pending.", "Explicit deduction for a worse credit cycle, funding pressure, conduct costs, and capital trapped above management targets."),
        ],
        ["Howard Marks/Oaktree: normalize credit losses and test refinancing and cycle downside.", "Buffett/Weschler: value the durable deposit and service franchise only through normalized owner returns.", "Klarman: tangible capital is an anchor, not automatically realizable value."],
    ),
    "NVR": model(
        "NVR", "quality_reinvestment", "compounder", 6497.57, 2_793_760,
        "NVR 2025 Form 10-K: 2.794m shares outstanding, $1.340bn net income, $1.610bn homebuilding pretax income, $152m mortgage-banking pretax income, $1.916bn cash, and $909m senior notes.",
        [
            component("homebuilding_owner_earnings", "Homebuilding owner earnings", "operating_business", "normalized_owner_earnings", (3300, 5600, 8000), "2025 Form 10-K homebuilding earnings and cash-flow disclosures.", "Normalize margins, cancellations, housing starts, and working capital; capitalize cash earnings after maintenance needs, not peak GAAP earnings."),
            component("mortgage_banking", "Mortgage banking", "operating_business", "normalized_earnings", (200, 400, 650), "2025 Form 10-K mortgage-banking pretax income of $152m.", "Separate mortgage economics from homebuilding and normalize origination volumes, gain-on-sale margins, and repurchase exposure."),
            component("net_surplus_cash", "Net surplus cash", "financial_asset", "net_cash_after_operating_buffer", (250, 350, 450), "2025 Form 10-K cash less senior notes; operating and mortgage liquidity buffers require further review.", "Credit only cash demonstrably surplus to land deposits, working capital, mortgage funding, and debt."),
            component("lot_control_and_future_communities", "Controlled-lot and future-community optionality", "real_option", "risked_lot_option_value", (200, 600, 1200), "NVR primarily controls lots through forfeitable deposits rather than owning land; community-level inventory remains to be reconciled.", "Value the asymmetric lot-control structure separately from current earnings, net of deposits, abandonment, and time-to-open.", option=True),
            component("housing_cycle_and_execution_reserve", "Housing-cycle and execution reserve", "liability_or_reserve", "cycle_reserve", (-800, -400, -150), "2025 backlog was 8,448 units and cancellation rate 17%; regional and affordability stresses require normalization.", "Deduct for lower volumes/margins, cancellation risk, community delays, and buybacks executed above intrinsic value."),
        ],
        ["Buffett/Weschler: measure owner earnings and per-share compounding.", "Marathon/Capital Returns: NVR's lot-option model changes the capital-cycle exposure.", "Pabrai: preserve the asymmetric ability to abandon lots while testing housing-cycle downside."],
    ),
    "NUE": model(
        "NUE", "capital_cycle", "capital_cycle", 236.87, 230_900_000,
        "Nucor FY2025 results: 230.9m diluted shares, segment pretax income of $2.383bn steel mills, $1.229bn steel products, and $153m raw materials; $2.699bn cash/investments and $7.121bn debt/lease obligations.",
        [
            component("steel_mills", "Steel mills through-cycle value", "operating_business", "normalized_segment_earnings", (70, 110, 170), "Nucor FY2025 results and segment operating statistics.", "Normalize shipments, spread, utilization, maintenance capital, and tax across a full steel cycle rather than capitalizing 2025 or spot margins."),
            component("steel_products", "Downstream steel products", "operating_business", "normalized_segment_earnings", (35, 65, 105), "FY2025 steel-products pretax income of $1.229bn and product-volume disclosures.", "Value downstream earnings separately using normalized backlog, margins, and maintenance capital."),
            component("raw_materials", "Raw materials and recycling", "operating_business", "normalized_segment_earnings", (0, 8, 20), "FY2025 raw-materials pretax income of $153m; commodity and outage normalization pending.", "Use through-cycle DRI, scrap, and brokerage economics after sustaining capital."),
            component("net_debt_and_leases", "Net debt and lease claims", "liability_or_reserve", "net_debt", (-22, -19, -16), "FY2025 cash/investments of $2.699bn and debt/lease obligations of $7.121bn.", "Deduct all debt and finance leases net of cash and short-term investments; range reflects required operating liquidity."),
            component("new_project_ramp", "New-project ramp and replacement-cost optionality", "real_option", "risked_incremental_roic", (5, 25, 55), "Management identified new rebar, melt-shop, towers, and coating projects; project-level invested capital and returns remain to be reconciled.", "Credit only probability-weighted after-tax cash returns above the cost of capital, net of remaining spend and ramp losses.", option=True),
            component("supply_response_and_downcycle_reserve", "Supply-response and downcycle reserve", "liability_or_reserve", "capital_cycle_reserve", (-20, -10, 0), "Steel is cyclical and exposed to global capacity, imports, and new domestic supply.", "Explicitly deduct for margin mean reversion, supply response, and projects earning below their cost of capital."),
        ],
        ["Marathon/Capital Returns: supply response and reinvestment determine normalized value.", "Howard Marks/Oaktree: liquidity and debt must survive the low case.", "Greenblatt: segment separation prevents a blended multiple from hiding weak capital allocation."],
    ),
    "BIIB": model(
        "BIIB", "binary_milestone", "biotech", 197.24, 147_000_000,
        "Biogen FY2025 results and 2025 Form 10-K: $9.891bn revenue, $2.1bn free cash flow, $4.2bn cash, $6.3bn debt, and approximately 147m diluted shares; Apellis transaction terms disclosed in 2026.",
        [
            component("legacy_products", "Legacy marketed products", "operating_business", "product_level_dcf", (35, 55, 75), "FY2025 product disclosures; product-level patent and erosion schedules pending.", "After-tax product cash flow net of erosion, rebates, sustaining commercial cost, and patent loss."),
            component("growth_products", "Growth marketed products", "operating_business", "product_level_dcf", (25, 55, 95), "FY2025 growth-product disclosures; launch curves and geographic economics pending.", "Risked product cash flows with explicit penetration, duration, pricing, and commercial reinvestment."),
            component("pipeline", "Research pipeline", "real_option", "milestone_probability_tree", (20, 60, 130), "Biogen pipeline and clinical-stage disclosures; indication-level probabilities and remaining spend pending.", "Each indication must have non-overlapping technical/regulatory probabilities, timing, remaining R&D, launch cost, and failure value.", option=True),
            component("apellis_assets", "Apellis marketed and pipeline assets", "real_option", "transaction_anchored_probability_tree", (20, 45, 75), "$5.6bn cash consideration plus CVRs; 2025 product sales of $689m and management growth expectations.", "Value acquired assets independently of purchase price, then deduct all acquisition financing and contingent consideration.", option=True),
            component("net_debt_acquisition_and_cvrs", "Net debt, acquisition financing, and CVRs", "liability_or_reserve", "senior_claims", (-70, -55, -40), "FY2025 cash/debt plus disclosed Apellis cash consideration and CVRs; closing balance sheet pending.", "Deduct existing net debt, acquisition borrowings, contingent payments, and required liquidity without double counting transaction cost."),
            component("patent_failure_and_burn_reserve", "Patent, clinical-failure, and cash-burn reserve", "liability_or_reserve", "risk_reserve", (-25, -15, -5), "Product concentration, patent cliffs, clinical failure, and integration risks in company filings.", "Explicit reserve for correlated downside not captured by independent product and pipeline ranges."),
        ],
        ["Greenblatt/Pabrai: use a finite, non-overlapping event tree.", "Klarman: transaction price is an evidence anchor, not proof of value.", "Marks/Oaktree: acquisition financing and cash burn precede equity optionality."],
    ),
    "MSB": model(
        "MSB", "scarce_asset_optionality", "resource", 25.68, 7_800_000,
        "Mesabi Trust filings and existing royalty/distribution research; unit count is an analyst working estimate pending exact trust-unit reconciliation.",
        [
            component("producing_royalty_stream", "Producing royalty and bonus stream", "operating_business", "royalty_distribution_curve", (30, 35, 42), "Trust distribution history and royalty terms; reserve and production reconciliation pending.", "Present value of after-trust royalty distributions under explicit volume, pellet-price, bonus, and discount-rate cases."),
            component("depletion_and_concentration_reserve", "Finite reserve and counterparty concentration reserve", "liability_or_reserve", "depletion_reserve", (-5, -3, -1), "Finite mineral claim and concentrated operator exposure.", "Deduction for depletion, operator concentration, interruption, and terminal-value uncertainty."),
            component("arbitration_and_bonus_option", "Arbitration and bonus-payment option", "real_option", "probability_weighted_legal_option", (0, 7, 13), "September 2025 arbitration and bonus-payment research; legal record and collectible amount pending.", "Risked present value of incremental distributions only; ordinary producing royalties remain in the core stream.", option=True),
            component("trust_cash_and_other_claims", "Trust cash and other net claims", "financial_asset", "net_asset_value", (1, 2, 3), "Trust financial statements; exact cash, expenses, and other claims pending.", "Net realizable trust assets after administrative costs and non-royalty claims."),
        ],
        ["Horizon Kinetics: treat the royalty as a long-lived economic claim rather than a one-year yield security.", "Marathon/Capital Returns: production and reserve response determine duration.", "Klarman: legal recovery is separate, probability-weighted optionality."],
    ),
}

EVIDENCE_GAPS = {
    "C": [
        ("segment_rotce_normalization", ["normalized_franchise_returns"], "Reconcile segment tangible capital, through-cycle credit costs, expenses, taxes, and normalized RoTCE."),
        ("distributable_capital", ["transformation_and_excess_capital"], "Reconcile regulatory minimums, management buffers, stress losses, transformation costs, and the timing of actual capital return."),
        ("stress_claims", ["credit_funding_and_regulatory_reserve"], "Build an independently reviewed credit, funding, legal, and regulatory stress bridge."),
    ],
    "NVR": [
        ("owner_earnings_cycle", ["homebuilding_owner_earnings", "housing_cycle_and_execution_reserve"], "Normalize community-level volume, margin, cancellations, working capital, and maintenance needs across a housing cycle."),
        ("controlled_lot_inventory", ["lot_control_and_future_communities"], "Reconcile controlled lots, deposits, ownership, opening cadence, abandonment rates, and remaining development obligations."),
        ("surplus_cash", ["net_surplus_cash"], "Separate truly distributable cash from homebuilding, mortgage, and stress-liquidity requirements."),
    ],
    "NUE": [
        ("through_cycle_segments", ["steel_mills", "steel_products", "raw_materials"], "Reconcile segment shipments, spreads, utilization, maintenance capital, tax, and mid-cycle earnings over multiple cycles."),
        ("industry_capacity_map", ["supply_response_and_downcycle_reserve"], "Map domestic and global additions, closures, imports, replacement costs, and the likely supply response by product."),
        ("project_roic", ["new_project_ramp"], "Reconcile project-level invested capital, remaining spend, ramp curves, incremental returns, and overlap with normalized segment earnings."),
    ],
    "BIIB": [
        ("product_cash_flows", ["legacy_products", "growth_products"], "Build product-level revenue, patent, rebate, margin, tax, and commercial reinvestment schedules."),
        ("pipeline_event_trees", ["pipeline", "apellis_assets"], "Build indication-level, non-overlapping probability trees using clinical base rates, milestones, timing, remaining R&D, and launch capital."),
        ("closing_claims", ["net_debt_acquisition_and_cvrs", "patent_failure_and_burn_reserve"], "Reconcile the acquisition closing balance sheet, borrowings, CVRs, integration costs, cash burn, and correlated downside."),
    ],
    "MSB": [
        ("royalty_reserve_reconciliation", ["producing_royalty_stream", "depletion_and_concentration_reserve"], "Reconcile trust units, contractual royalty tiers, reserves, production, realized pellet prices, bonuses, taxes, and depletion."),
        ("legal_option_record", ["arbitration_and_bonus_option"], "Reconcile the primary legal record, outcomes, timing, collectibility, and ensure ordinary royalties are not counted twice."),
        ("trust_net_assets", ["trust_cash_and_other_claims"], "Reconcile current trust cash, expenses, liabilities, and other senior claims from primary statements."),
    ],
}


def main() -> None:
    for ticker, payload in MODELS.items():
        path = ROOT / ticker / "research" / "valuation.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        preserved = {key: deepcopy(existing[key]) for key in ("biotech_overlay",) if key in existing}
        payload = deepcopy(payload)
        payload.update(preserved)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(path.relative_to(ROOT))
    followup_path = ROOT / "_system" / "reference" / "valuation_followups.json"
    followups = json.loads(followup_path.read_text(encoding="utf-8"))
    tickers = followups.setdefault("tickers", {})
    for ticker, gaps in EVIDENCE_GAPS.items():
        tickers[ticker] = {
            "method_profile": MODELS[ticker]["method_profile"],
            "evidence_gaps": [
                {
                    "id": gid, "priority": "critical", "component_ids": component_ids,
                    "question": question,
                    "evidence_required": "Primary filings or contracts plus an independently reproducible calculation and relevant cross-check.",
                    "acceptance_test": "The evidence reproduces the low/base/high bridge, resolves overlap, and identifies a falsifier and monitoring source.",
                    "status": "open",
                }
                for gid, component_ids, question in gaps
            ],
        }
    followup_path.write_text(json.dumps(followups, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
