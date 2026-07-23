# FNV valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-23 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_royalty_stream` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $142.18 |
| `development_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $18.34 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $27.51 |
| `depletion_and_realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$27.51 |

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` carries `calculation_proof` with approved `method_id@1.0`; proof validation passes with zero calculation errors. |
| source path | `FNV/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): $142.18 + $18.34 + $27.51 - $27.51 = **$160.52/sh** vs price **$229.28** (2026-06-03 refresh price). |
| remaining uncertainty | FY2025 owner cash embeds record gold/silver prices; Q1 2026 OCF includes one-time CRA refund; development inventory conversion timing remains judgment-heavy. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract advances from legacy_sensitivity to bounded_estimate; Lawrence synthesis **6.12%** per year unchanged. |
| falsifier | Two consecutive quarters with operating cash flow below $300M annualized run-rate without matching commodity-price disclosure. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 annual report: operating cash flow **$1,493.7M** on **192.7M** weighted-average shares = **$7.75/sh** owner cash; Q1 2026 available capital **$3.4B** (cash **$714.7M**, equity investments **$1,142.4M**, unused credit **$1.0B**); company reports **no debt**. |
| source path | `FNV/investor-documents/ir-fnv/10249_Franco_Nevada_2025_Annual_Report_Ph14_F_Digital.pdf`, `FNV/investor-documents/ir-fnv/NR-Franco-Nevada-Reports-Record-Q1-2026-Results-vFinal-2026-05-12.pdf` |
| calculation | Owner cash $7.75/sh × capitalization multiple 18.35 (base) = $142.18 producing stream; net cash $714.7M + deployable-capital judgment = $27.51/sh net financial base. |
| remaining uncertainty | CRA refund **$49.5M** in Q1 2026 OCF excluded from normalized growth; Cobre Panamá restart timing not in 2026 GEO guidance. |
| affected components | `producing_royalty_stream`, `net_financial_claims`, `depletion_and_realization_reserve` |
| valuation consequence | Filing-locked facts drive calculated/bounded proofs; price premium to component sum implies quality-premium compression risk. |
| falsifier | Available capital revised below $2.0B without matching acquisition disclosure or dividend increase above 25% YoY. |

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping overlap keys map one diluted share claim each: producing stream, development inventory, net financial position, depletion reserve. |
| source path | `FNV/research/valuation.json` → `economic_value.component_groups[]` |
| calculation | `double_counting_flags` empty; producing cash excluded from development conversion; CRA refund reserved in depletion band. |
| remaining uncertainty | Cobre Panamá option appears in segment overlay and development inventory; segment overlay marked `not_in_lawrence_base`. |
| affected components | All |
| valuation consequence | Component sum is additive once at **$160.52/sh** base. |
| falsifier | New component added without unique overlap_key. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Debt-free balance sheet; explicit depletion reserve scales with owner-cash run-rate; net financial band includes unused credit capacity judgment separate from producing stream. |
| source path | FY2025 annual report MD&A; Q1 2026 results NR |
| calculation | Depletion reserve base -$27.51/sh = 3.55× normalized owner cash $7.75/sh; net financial low case $6.88/sh = filing cash only ($714.7M / 192.8M). |
| remaining uncertainty | Credit facility draw and large acquisition could shift deployable-capital judgment quickly. |
| affected components | `net_financial_claims`, `depletion_and_realization_reserve` |
| valuation consequence | Downside capital claims bounded; partial dhando from zero recourse leverage preserved. |
| falsifier | Recourse debt above $500M disclosed without offsetting contracted cash-flow asset. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys on all four components; segment Cobre Panamá overlay excluded from Lawrence base component sum. |
| source path | `FNV/research/valuation.json` |
| calculation | No additive overlap key duplicates. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | Segment option value moved into producing stream without overlap_key change. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$1,822.8M**; operating cash flow **$1,493.7M**; GEOs **519,106**; weighted-average shares **192.7M**; Q1 2026 revenue **$650.7M**; Q1 OCF **$520.4M** (includes CRA **$49.5M**); available capital **$3.4B**; cash **$714.7M**; equity investments **$1,142.4M**; **no debt**; dividend **$0.44/quarter** ($1.76 annualized).

**Judgments (bounded):** Producing capitalization multiple **12.4–24.3×** owner cash; development conversion **0–15×** equity investments; deployable-capital claim **$612M–$8.1B** above filing cash; depletion multiple **0.9–7.4×** owner cash.

## Valuation consequence

Proof-complete additive schedule base case **$160.52 per share** vs price **$229.28** implies **-30%** upside/downside gap and Lawrence synthesis **6.12%** per year (stance gate **4.5%**). Security remains **watch**; no human capital decision recorded.
