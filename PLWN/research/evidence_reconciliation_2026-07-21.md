# PLWN valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `form990_net_assets` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $46.79 |
| `cemetery_operations` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $11.99 |
| `land_market_to_990_gap` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $15.00 |
| `illiquidity_and_governance_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$20.00 |

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` now carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all four graphs. |
| source path | `PLWN/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): $46.79 + $11.99 + $15.00 - $20.00 = **$53.78/sh** vs legacy component schedule **$53.8/sh**. |
| remaining uncertainty | Share count remains unverified; Form 990 PDF not yet local; land gap is judgment until Schedule D. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Verified share count or Schedule D shows net assets per economic unit far from the proof band. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2024 Form 990 extract: revenue $42.9M, expenses $37.5M, net income $5.3M, net assets $161.9M, liabilities $0. |
| source path | `PLWN/research/evidence/form990_fy2024_extract.json` |
| calculation | Net assets proof: $161.904M / 3.46M shares = **$46.79/sh**. Owner-cash proof: ($5.324M / 3.46M) × 7.79× cap = **$11.99/sh**. |
| remaining uncertainty | Provisional share denominator; indicated $45.40 dividend implies ~$157M cash need versus $5.3M NI. |
| affected components | `form990_net_assets`, `cemetery_operations`, `illiquidity_and_governance_reserve` |
| valuation consequence | Filing-locked 990 facts drive bounded proofs; share-count conflict captured in governance reserve. |
| falsifier | Local Form 990 PDF shows materially different net assets or governance-restricted equity claims. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; land gap is incremental to 990 net assets (not double-counted inside accounting floor). |
| source path | `PLWN/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | Perpetual-care trust assets not yet split from unrestricted net assets. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | Schedule D shows land already marked at fair value inside net assets, requiring land_gap reduction to zero. |

## Facts vs judgments

**Facts (locked):** FY2024 revenue $42,855,178; expenses $37,530,682; net income $5,324,496; net assets $161,903,602; liabilities $0 on extract.

**Judgments (bounded):** Provisional shares 2.94M–4.05M; cemetery cap multiple 3.2×–13.0×; land gap $0–$80/sh risked; illiquidity reserve -$40 to -$5/sh.

## Valuation consequence

Proof-complete additive schedule base case **~$53.8 per share** vs price **$575** implies deeply negative seven-year annualized return on component economic value (~**-29%** base case per contract). Lawrence consolidated IRR remains **pending** until share count is verified. Security stays **watch**; no human capital decision recorded.
