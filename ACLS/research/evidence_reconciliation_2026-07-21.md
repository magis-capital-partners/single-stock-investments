# ACLS valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-21 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `midcycle_implant_operations` | unvalued | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $59.80 |
| `systems_backlog_conversion_option` | unvalued | risk_adjusted_milestone_value@1.0 | bounded_estimate | $22.00 |
| `net_financial_claims` | unvalued | net_asset_value@1.0 | bounded_estimate | $4.60 |
| `cycle_and_concentration_reserve` | unvalued | net_asset_value@1.0 | bounded_estimate | -$20.00 |

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` now carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all four graphs. |
| source path | `ACLS/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): $59.80 + $22.00 + $4.60 - $20.00 = **$66.40/sh** vs price **$131.70**. |
| remaining uncertainty | Mid-cycle normalization and backlog conversion timing remain judgment-heavy; Q1 2026 revenue still below prior-year pace. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Two consecutive quarters of systems backlog below $350M and gross margin below 40%; owner cash per share below $2.50 on filing-locked bridge. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 10-K: OCF $118.3M, capex $11.3M, FCF $107.0M on 31.668M diluted shares = **$3.38/sh**; cash $145.5M = **$4.59/sh**; no term debt. |
| source path | `ACLS/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001104659_26_020461.htm` |
| calculation | Three-year average FCF/sh **$3.81** anchors mid-cycle owner cash; net financial proof base **$4.60/sh** after operating liquidity reserve. |
| remaining uncertainty | Working-capital swings with backlog; international receivable collection in China-heavy mix. |
| affected components | `midcycle_implant_operations`, `net_financial_claims` |
| valuation consequence | Filing-locked facts drive calculated/bounded proofs; legacy price stub excluded from decision-grade sum. |
| falsifier | FY2026 cash balance revised downward >20% without matching debt or buyback disclosure. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys on all four components; services cash flow embedded in core engine, backlog option non-overlapping. |
| source path | `ACLS/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue $839M (systems $571M, services $268M); OCF $118.3M; FCF $107M; cash $145.5M; systems backlog $457M (down from $646M); gross margin 44.9%; diluted shares 31.668M; debt-free balance sheet.

**Judgments (bounded):** Mid-cycle owner cash $3.20–$4.50/sh; backlog milestone $0–$48/sh; cycle reserve -$42 to -$8/sh.

## Valuation consequence

Proof-complete additive schedule base case **$66.40 per share** vs price **$131.70** implies negative annualized return on component economic value. Lawrence synthesis **-3.78%** remains the stance reference on normalized owner-cash path. Security remains **watch**; no human capital decision recorded.
