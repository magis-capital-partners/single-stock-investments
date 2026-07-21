# KEWL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `current_operating_claim` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $27.50 |
| `asset_option_inventory` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $9.90 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $6.60 |
| `realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$8.25 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: current operating lease claim, copper/land/water options, net financial claims, realization reserve. No embedded double-count. |
| source path | `KEWL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$35.75/sh** = $27.50 + $9.90 + $6.60 − $8.25. |
| remaining uncertainty | Copperwood timing and spot-copper royalty bridge remain judgment-heavy. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2024 mineral lease income **$349,700**; **~1,126,284** shares; cash and treasuries **~$4M**; H1 2025 lease income **$189,101** vs **$149,310** prior year; 2024 mineral purchase **$1,016,102**. |
| source path | `KEWL/investor-documents/ir-kewl/2024-12-31_Annual_Report.pdf`; `2025-06-30_Semi-Annual_Report.pdf` |
| calculation | Operating proof: $349,700 × 88.57 capitalization multiple ÷ 1,126,284 ≈ **$27.50/sh**. Option proof: $12.59M spot royalty × 35% × 2.53 years ÷ shares ≈ **$9.90/sh**. |
| remaining uncertainty | Capitalization multiple and Copperwood probability are bounded judgments, not filing marks. |
| affected components | `current_operating_claim`, `asset_option_inventory`, `net_financial_claims` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Trailing mineral lease income falls below **$300K** for two consecutive fiscal years without offsetting royalty commencement. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Steady-state overhead burn **~$160K/yr** (FY2024 MD&A); 2024 mineral rights purchase **$1,016,102** (H1 2025 cash flow); H1 2025 net loss **($51,156)**; no material debt disclosed. |
| source path | `2024-12-31_Annual_Report.pdf`; `2025-06-30_Semi-Annual_Report.pdf` |
| calculation | Realization reserve base **−$8.25/sh** = −7.90× ($160K burn + $1.016M purchase proxy) ÷ shares. Net financial claims base **$6.60/sh** from $4M cash plus bounded supplemental liquid claim. |
| remaining uncertainty | Management “cash-flow positive from 2026” claim unverified vs H1 2025 loss. |
| affected components | `realization_reserve`, `net_financial_claims` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from operating capitalization. |
| falsifier | Operating burn exceeds **$250K/yr** for two consecutive years while lease income stays flat. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; lease rent capitalized in operating claim does not re-enter option royalty stream; cash not double-counted in book anchor. |
| source path | `KEWL/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2024 lease income **$349,700**; **~1,126,284** shares; cash **~$4M**; 2024 mineral purchase **$1,016,102**; H1 2025 lease income **$189,101**; mineral rights on balance sheet **$7,978,390** (H1 2025).

**Judgments (bounded):** Lease capitalization multiple 56.7–124.0×; Copperwood success probability 0–75%; royalty cap years 0–3.1; supplemental liquid claim **−$2.1M to +$8.4M**; realization reserve multiple 2.1–15.8× on burn-plus-purchase proxy.

## Valuation consequence

Proof-complete additive schedule base case **~$35.75 per share** vs price **~$55** implies component economic value below market; Lawrence seven-year base **−8.3%** remains below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
