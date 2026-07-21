# ALB valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `midcycle_lithium_and_specialty_operations` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $32.43 |
| `conversion_capacity_and_contract_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $15.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | −$6.68 |
| `lithium_cycle_and_capex_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$22.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: mid-cycle lithium and specialty operations, conversion capacity option, net financial claims, cycle/capex reserve. No embedded double-count. |
| source path | `ALB/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$18.75/sh** = $32.43 + $15.00 − $6.68 − $22.00. |
| remaining uncertainty | Conversion ramp timing and contract pricing remain judgment-heavy; bromine cash embedded in operations OCF. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$1,282M**; three-year average OCF **$1,099M**; Q1 2026 diluted **118.6M** shares; net income **$319M** / EPS **$2.34**. |
| source path | `ALB/investor-documents/sec-edgar/10-K_20260211_rpt20251231_acc0000915913_26_000018.htm`, `10-Q_20260506_rpt20260331_acc0000915913_26_000072.htm` |
| calculation | Operations proof: **$9.27/sh** three-year average OCF × 3.5× capitalization ≈ **$32.43/sh**. Net financial: ($1,090M cash − $1,882M debt) / 118.6M ≈ **−$6.68/sh**. |
| remaining uncertainty | Capitalization multiple and conversion milestone band are bounded judgments, not filing marks. |
| affected components | `midcycle_lithium_and_specialty_operations`, `net_financial_claims`, `conversion_capacity_and_contract_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter operating cash flow per share falls below **$6.00** for four quarters without offsetting debt reduction. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 cash **$1,090M**; long-term debt **$1,807M** plus current **$75M**; FY2025 capital spending **$590M**; stockholders' equity **$9,533M** (FY2025). |
| source path | `10-K_20260211`, `10-Q_20260506` balance sheet and cash-flow extracts |
| calculation | Net debt **$792M** filing-locked at Q1 2026; cycle reserve base **−$22.00/sh** separate from net financial claim. |
| remaining uncertainty | Lithium spot price path and conversion project delays remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `lithium_cycle_and_capex_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from operations capitalization. |
| falsifier | Total debt rises above **$2.5B** while operating cash flow stays below **$800M** for two consecutive years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; contracted volumes flowing through OCF embedded in operations component, not double-counted in conversion option. |
| source path | `ALB/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 net sales **$5,143M**, operating loss **$367M**, net loss **$511M**, operating cash flow **$1,282M**, capital spending **$590M**; Q1 2026 net income **$319M**, diluted EPS **$2.34**; cash **$1,090M**; total debt **$1,882M**; diluted shares **118.6M**.

**Judgments (bounded):** Owner-cash capitalization multiple 2.0–5.5× on three-year average OCF per share; conversion milestone **$0–$40/sh**; cycle reserve **−$40 to −$10/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$18.75 per share** vs price **~$118.20** implies the market prices lithium cycle recovery and conversion ramp beyond filing-locked trough components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
