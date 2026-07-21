# ACHR valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `net_liquid_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | $2.21 |
| `midnight_certification_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $3.50 |
| `dilution_and_burn_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$1.50 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Three additive components with unique overlap keys: net liquid claims, Midnight certification/partner option, dilution and burn reserve. No embedded double-count. |
| source path | `ACHR/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$4.21/sh** = $2.21 + $3.50 − $1.50. |
| remaining uncertainty | Certification milestone band ($0–$10/sh) and burn reserve remain widest judgment bands. |
| affected components | All three additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 cash **$951.1M**, short-term investments **$824.8M**, restricted cash **$7.3M**; long-term debt **$80.2M**; warrant liabilities **$7.1M**; diluted shares **766.9M**. |
| source path | `ACHR/investor-documents/sec-edgar/10-Q_20260511_rpt20260331_acc0001824502_26_000038.htm` |
| calculation | Net liquid **$1,695.9M** / 766.85M shares ≈ **$2.21/sh**. FY2025 net loss **$618.2M** on revenue **$0.3M**; R&D **$493.9M**. |
| remaining uncertainty | Short-term investment marks and warrant fair value can move with rates and equity price. |
| affected components | `net_liquid_claims`, `dilution_and_burn_reserve` |
| valuation consequence | Filing-locked liquid stack anchors NAV floor; price stub replaced by component schedule. |
| falsifier | Combined cash and short-term investments fall below **$800M** while annual net loss stays above **$500M** for four quarters. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Accumulated deficit **$2,303.8M**; FY2025 operating loss **$729.3M**; shares grew from **624.3M** (FY2025) to **766.9M** (Q1 2026). |
| source path | `10-K_20260302`, `10-Q_20260511` |
| calculation | Dilution reserve base **−$1.50/sh** separate from filing-locked net liquid claim. Debt modest at **~$80M** versus **~$1.78B** liquid assets. |
| remaining uncertainty | ATM/S-3 issuance pace and certification timeline drive reserve band width. |
| affected components | `dilution_and_burn_reserve`, `net_liquid_claims` |
| valuation consequence | Downside claims reconciled to filings; burn reserve separate from liquid NAV. |
| falsifier | Diluted share count rises above **850M** without proportional liquid asset growth for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; interest income on cash embedded in liquid asset marks, not double-counted in certification option. |
| source path | `ACHR/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Q1 2026 cash **$951.1M**, short-term investments **$824.8M**, debt **$80.2M**, warrant liabilities **$7.1M**, diluted shares **766.9M**; FY2025 revenue **$0.3M**, R&D **$493.9M**, operating loss **$729.3M**, net loss **$618.2M**; United conditional purchase up to **$1.0B** aircraft disclosed in 10-K.

**Judgments (bounded):** Certification milestone **$0–$10/sh**; dilution reserve **−$3.00 to −$0.50/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$4.21 per share** vs price **~$5.31** implies the market prices certification success and partner conversion slightly above the conservative component sum. Lawrence scenario IRR and synthesis are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
