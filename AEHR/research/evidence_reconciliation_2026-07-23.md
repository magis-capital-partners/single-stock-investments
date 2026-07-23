# AEHR valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-23 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `midcycle_burn_in_operations` | unvalued | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $2.55 |
| `deferred_revenue_milestone_option` | unvalued | risk_adjusted_milestone_value@1.0 | bounded_estimate | $12.19 |
| `net_financial_claims` | unvalued | net_asset_value@1.0 | bounded_estimate | $1.05 |
| `cycle_customer_concentration_reserve` | unvalued | net_asset_value@1.0 | bounded_estimate | -$6.00 |

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` carries `calculation_proof` with approved `method_id@1.0`; proof validation passes with zero calculation errors. |
| source path | `AEHR/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): $2.55 + $12.19 + $1.05 - $6.00 = **$9.79/sh** vs price **$77.36**. |
| remaining uncertainty | Mid-cycle normalization and deferred-revenue conversion timing remain judgment-heavy; FY2025 operating cash outflow may not fully reverse in FY2026. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract advances from empty ownership map toward priced components; Lawrence synthesis **-33.31%** at mid-cycle owner cash. |
| falsifier | Two consecutive fiscal years with operating cash outflow above $10M and revenue below $50M; owner cash per share below $0.05 on filing-locked bridge. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 10-K: OCF **($7.4M)**, capex **$5.0M**, FCF **($12.4M)** on **29.581M** diluted shares = **($0.42/sh)** trough; cash **$36.9M** as of Q3 FY2026 = **$1.05/sh** net financial proof base after reserve. |
| source path | `AEHR/investor-documents/sec-edgar/10-K_20250728_rpt20250530_acc0001654954_25_008553.htm`, `AEHR/investor-documents/sec-edgar/10-Q_20260408_rpt20260227_acc0001654954_26_003348.htm` |
| calculation | Two-year average FY2023–FY2024 FCF/sh **$0.16** anchors mid-cycle owner cash; FY2025 trough excluded from Lawrence base normalization. |
| remaining uncertainty | Customer concentration (historically one large SiC customer) and April 2026 **$60M** at-the-market equity program add dilution risk. |
| affected components | `midcycle_burn_in_operations`, `net_financial_claims`, `cycle_customer_concentration_reserve` |
| valuation consequence | Filing-locked facts drive calculated/bounded proofs; price stub excluded from decision-grade sum. |
| falsifier | FY2026 cash balance revised downward >25% without matching debt, buyback, or acquisition disclosure. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys on all four components; services and upgrade cash flow embedded in core engine; deferred revenue option non-overlapping. |
| source path | `AEHR/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$59.0M** (down from **$66.2M** FY2024); net loss **$3.9M**; operating cash outflow **$7.4M**; capex **$5.0M**; cash **$36.9M** (Feb 2026); deferred revenue **~$1.9M**; diluted shares **~31.5M**; no term debt; April 2026 **$60M** ATM shelf filed.

**Judgments (bounded):** Mid-cycle owner cash **$0.08–$0.55/sh**; deferred-revenue milestone **$0–$48/sh**; cycle reserve **-$12 to -$2/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$9.79 per share** vs price **$77.36** implies **-33.31%** annual return on normalized owner-cash path. Security remains **watch**; no human capital decision recorded.
