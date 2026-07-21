# RGLD valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_royalty_stream` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $134.39 |
| `development_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $17.34 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $26.01 |
| `depletion_and_realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$26.01 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: producing royalty stream, development inventory option, net financial claims, depletion reserve. No embedded double-count. |
| source path | `RGLD/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$151.73/sh** = $134.39 + $17.34 + $26.01 − $26.01. |
| remaining uncertainty | Sandstorm deferred tax timing and development conversion remain judgment-heavy. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$704.846M**; normalized owner cash **~$9/sh** on ~78.3M diluted share base; Q1 FY2026 diluted **~85.2M** shares ($281.130M net income / $3.30 EPS). |
| source path | `RGLD/investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0000085535_26_000008.htm`, `10-Q_20260507_rpt20260331_acc0000085535_26_000028.htm` |
| calculation | Producing proof: $9.0 × 14.93 capitalization multiple ≈ **$134.39/sh**. Net financial: ($234.142M cash − $595.689M debt + $2,577M judgment claim) / 85.2M ≈ **$26.01/sh**. |
| remaining uncertainty | Capitalization multiple and Sandstorm balance-sheet claim band are bounded judgments, not filing marks. |
| affected components | `producing_royalty_stream`, `net_financial_claims`, `development_inventory_option` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Trailing four-quarter operating cash flow per share falls below **$7.50** for four quarters without offsetting portfolio growth. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 FY2026 cash **$234.142M**; long-term debt **$595.689M** (after **$300M** repayment in Q1); FY2025 deferred tax liability **$1,191M** (purchase accounting context). Depletion reserve proof ties to $9/sh owner-cash proxy. |
| source path | `10-Q_20260507`, `10-K_20260219` balance sheet and cash-flow extracts |
| calculation | Net cash **−$361.5M** filing-locked; depletion reserve base **−$26.01/sh** = −2.89× owner-cash proxy. |
| remaining uncertainty | Gold-price trough severity and operator delays on development assets remain widest bands. |
| affected components | `net_financial_claims`, `depletion_and_realization_reserve`, `development_inventory_option` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from producing stream. |
| falsifier | Long-term debt rises above **$900M** without proportional operating cash flow growth for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; depletion reserve does not re-deduct inside producing capitalization multiple. |
| source path | `RGLD/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$1,030M**, operating income **$638M**, net income **$466M**, operating cash flow **$704.846M**; Q1 FY2026 revenue **$469M**, net income **$281.1M**, diluted EPS **$3.30**; cash **$234.1M** and long-term debt **$595.7M** at 3/31/26; equity method investments **$300.9M** at 12/31/25; Sandstorm net cash paid **$411.3M** in FY2025 investing.

**Judgments (bounded):** Owner-cash capitalization multiple 10.1–19.7×; equity-method conversion multiple 0–15.3×; Sandstorm balance-sheet claim **$915M–$4,054M**; depletion multiple 0.72–6.02× owner cash.

## Valuation consequence

Proof-complete additive schedule base case **~$151.73 per share** vs price **~$217** implies component economic value below market; Lawrence seven-year base **6.7%** and total synthesis **8.06%** remain below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
