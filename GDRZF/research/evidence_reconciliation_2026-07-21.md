# GDRZF valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-21 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `corporate_cash` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.68 |
| `risked_award_citgo_recovery` | legacy_sensitivity | probability_weighted_catalyst_nav@1.0 | bounded_estimate | $5.50 |
| `arb_ii_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.00 |
| `legal_burn_and_senior_claims_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$0.50 |

## Acceptance tests

### component_proof_completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `GDRZF/research/valuation.json` → `component_valuation.components[]` |
| calculation | Proof sum (base): $0.68 + $5.50 + $0.00 − $0.50 = **$5.68/sh** vs price **$4.56**; Lawrence dated payoff **$7/sh** in four years remains stance-gate IRR bridge. |
| remaining uncertainty | SEDAR cash and share count; exact attached-judgment rank and dollar. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance toward `decision_grade` after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

### sedar_financials — open

| Field | Content |
|---|---|
| status | open |
| evidence | H1 2025 interim Note 5 (unpaid award ~$1.18B) cited via Arb II RFA and secondary copies; no local SEDAR PDF. |
| source path | `GDRZF/investor-documents/ir-gdrzf/GR_Vz_2025.03.05_Arb_II_Final_Draft_RFA__330pm_ET_.pdf` |
| calculation | Cash proof uses judgment band **$59M–$133M** on **147.9M** shares → **$0.40–$0.90/sh**. |
| remaining uncertainty | Audited cash, going-concern burn, and fully diluted share count after 2025/2026 placements. |
| affected components | `corporate_cash`, `legal_burn_and_senior_claims_reserve` |
| valuation consequence | Cash floor remains soft; contract stays analyst-estimated on cash until SEDAR intake. |
| falsifier | SEDAR cash balance or burn shows cash floor below low case after legal spend. |

### citgo_waterfall — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Delaware Sale Order (29 Nov 2025) approves Amber SPA; Incremental Consideration mechanics allow up to **$500M** use for Gold Reserve attached judgment. Mandamus petition documents GR bid/allegations. |
| source path | `GDRZF/investor-documents/ir-gdrzf/2025-11-29-2556-Crystallex-International-Corporation-v-ORDER-I-APPROVING-STOCK-PURCHASE-AGREEMENT-II.pdf` |
| calculation | Risked recovery proof: **$1,180M** face × **68.9%** net-to-equity (base judgment) / **147.9M** shares = **$5.50/sh**. |
| remaining uncertainty | Final Priority Order rank vs Crystallex/Conoco; OFAC license and closing timing. |
| affected components | `risked_award_citgo_recovery` |
| valuation consequence | Probability and senior-claim leakage live inside `net_to_equity_pct` judgment band. |
| falsifier | Amber sale closes with de minimis net cash to Gold Reserve after senior creditors. |

## Facts vs judgments

**Facts (locked or filing-backed):** ICSID award recognized in Portugal (Feb 2025); Delaware Sale Order entered Nov 2025; Arb II RFA filed Mar 2025; CVR **5.466%** and bonus-plan tiers per company Note 5 history in RFA.

**Judgments (bounded):** Corporate cash band; risked net recovery percentage on **$1.18B** face; Arb II base-zero / bull-only high case; legal burn and senior-claim reserve.

## Valuation consequence

Proof-complete additive schedule base case **$5.68 per share** vs market price **$4.56** implies modest headline upside on component NAV, but the stance-gate **11.3% per year** four-year dated payoff (**$7/sh**) still reflects process timing and sub-15% target. Security remains **watch**; no human capital decision in this agent run.
