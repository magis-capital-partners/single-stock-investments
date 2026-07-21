# DMLP valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_royalty_stream` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $17.04 |
| `development_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $2.21 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $3.30 |
| `depletion_and_realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$3.30 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: producing royalty stream, development inventory option, net financial claims, depletion reserve. No embedded double-count. |
| source path | `DMLP/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$19.24/sh** = $17.04 + $2.21 + $3.30 − $3.30. |
| remaining uncertainty | Undeveloped acreage conversion timing remains judgment-heavy. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 declared distributions **$2.775346/unit**; 48,255,450 units; cash **$41.937M**; liabilities **$4.315M**; 2024-2025 mineral acquisition consideration **$14.725M** and **$3.888M**. |
| source path | `DMLP/investor-documents/sec-edgar/10-K_20260224_rpt20251231_acc0001437749_26_005376.htm` |
| calculation | Producing proof: $2.775346 × 6.14 capitalization multiple ≈ **$17.04/sh**. Net financial: ($41.937M − $4.315M + $121.5M judgment) / 48.255M ≈ **$3.30/sh**. |
| remaining uncertainty | Capitalization multiple and conversion multiple are bounded judgments, not filing marks. |
| affected components | `producing_royalty_stream`, `net_financial_claims`, `development_inventory_option` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Trailing four-quarter distributions fall below **$2.50/unit** for four quarters without offsetting acquisition cash flow. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Partnership agreement limits aggregate indebtedness to **$50,000**; FY2025 liabilities **$4.315M**; no material debt. Depletion reserve proof ties to distribution run-rate. |
| source path | `10-K_20260224` balance sheet and risk factors |
| calculation | Net cash **$37.622M** ($0.78/unit) filing-locked; depletion reserve base **−$3.30/sh** = −1.189× distribution proxy. |
| remaining uncertainty | Commodity trough severity and unit dilution from Form S-4 exchanges remain widest bands. |
| affected components | `net_financial_claims`, `depletion_and_realization_reserve`, `development_inventory_option` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from producing stream. |
| falsifier | Unit issuance for acquisitions grows faster than per-unit distributions for two consecutive years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; depletion reserve does not re-deduct inside producing capitalization multiple. |
| source path | `DMLP/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 distributions **$2.775346/unit**; **48,255,450** units; cash **$41.937M**; liabilities **$4.315M**; 2024-2025 acquisition consideration **$14.725M** + **$3.888M**; partnership debt limit **$50k**.

**Judgments (bounded):** Distribution capitalization multiple 4.16–8.12×; conversion multiple on recent acquisitions 0–17.9×; non-cash balance-sheet claim **$0–227.5M**; depletion multiple 0.30–2.48× distribution.

## Valuation consequence

Proof-complete additive schedule base case **~$19.24 per unit** vs price **~$27.48** implies component economic value below market; Lawrence seven-year base **13.8%** remains below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
