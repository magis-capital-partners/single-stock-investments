# ABMD.CVR valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per CVR |
|-----------|--------------|--------|--------------|--------------|
| `net_sales_milestone` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $8.31 |
| `fda_stemi_milestone` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $2.63 |
| `clinical_recommendation_milestone` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $4.50 |
| `timing_execution_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$2.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: net-sales, FDA STEMI, clinical recommendation, timing/execution reserve. No embedded double-count. |
| source path | `ABMD.CVR/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once; sum base **$13.44/CVR** = $8.31 + $2.63 + $4.50 − $2.00. Maximum contractual stack **$35/CVR**. |
| remaining uncertainty | Milestone probabilities are bounded judgments; JNJ net-sales measurement and trial outcomes remain open. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing or Milestone Notice shows an unmodeled claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | Security is a pure milestone cash claim under the Dec 22, 2022 CVR Agreement (EX-10.1). No operating owner-cash path. |
| source path | `https://www.sec.gov/Archives/edgar/data/200406/000119312522311072/d428734dex101.htm` |
| calculation | Expected value bridge sums probability-weighted milestone payments less execution reserve; not a GAAP NAV. |
| remaining uncertainty | Abiomed/JNJ post-close net sales are not publicly broken out in workspace filings. |
| affected components | All milestone components |
| valuation consequence | Yield-curve method replaces price stub; reference price = base component sum. |
| falsifier | JNJ publishes audited Net Sales Statement showing aggregate Product net sales trajectory incompatible with base net-sales probability. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Contractual downside per milestone is **$0** payment if threshold missed; no recourse debt or dilution on the CVR itself. |
| source path | CVR Agreement Sections 2.4, 4.5 (2028 Non-Achievement Notice / Expiry Notice) |
| calculation | `timing_execution_reserve` base **−$2.00/CVR** captures tax withholding, delay, and illiquidity separately from milestone zeros. |
| remaining uncertainty | Withholding rates and payment timing vary by holder tax status. |
| affected components | `timing_execution_reserve` |
| valuation consequence | Bounded bear case remains zero-to-minimal cash, not negative equity. |
| falsifier | CVR Agreement amendment reduces milestone amounts or adds holder-funded capital calls. |

### Market price — partially met [HUMAN REVIEW]

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Non-tradeable CVR; broker screens show **0.000** quote (Moomoo, Jul 2026). No Stooq/Yahoo close available. |
| source path | `ABMD.CVR/research/valuation.json` inputs.price_source |
| calculation | Reference price **$13.44/CVR** = base component sum for yield-curve math only. |
| remaining uncertainty | Holders must substitute actual cost basis or any private secondary trade price for entry IRR. |
| affected components | Contract market block |
| valuation consequence | `valuation_contract.json` may reach decision_grade on proofs while price remains model-reference, not exchange-traded. |
| falsifier | Verified OTC trade prints establish a positive, liquid reference price. |

## Facts vs judgments

**Facts (locked):** CVR Agreement dated **2022-12-22**; milestone payments **$17.50 / $8.75** (net sales), **$7.50** (FDA), **$10.00** (clinical); maximum **$35/CVR**; net-sales threshold **$3.7B**; Abiomed FY2022 revenue **$1.032B**; merger closed **2022-12-22** with **~25.76M** shares tendered.

**Judgments (bounded):** Net-sales success **P=40%** full / **15%** delayed; FDA **P=35%**; clinical **P=45%**; execution reserve **$2/CVR** base.

## Valuation consequence

Proof-complete additive schedule base **$13.44 per CVR** versus maximum **$35** contractual stack. Lawrence yield-curve base annual return is computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
