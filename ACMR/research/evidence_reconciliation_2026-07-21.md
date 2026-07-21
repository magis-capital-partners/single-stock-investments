# ACMR valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `wet_clean_equipment_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $15.52 |
| `advanced_packaging_backlog_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $6.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | $8.08 |
| `cycle_and_concentration_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$7.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: wet clean equipment engine, advanced packaging backlog option, net financial claims, cycle and concentration reserve. No embedded double-count. |
| source path | `ACMR/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$22.60/sh** = $15.52 + $6.00 + $8.08 − $7.00. |
| remaining uncertainty | Backlog milestone band ($0–$18/sh) and cycle reserve remain widest judgment bands. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 revenue **$901.3M** (+15% YoY); operating income **$109.4M** (down from **$151.0M**); operating cash flow **$10.3M** (down from **$152.5M**); diluted **~67.3M** shares ($92.1M net income / $1.37 EPS). |
| source path | `ACMR/investor-documents/sec-edgar/10-K_20260302_rpt20251231_acc0001628280_26_013231.htm` |
| calculation | Core proof: **$1.94/sh** mid-cycle operating income × 8× capitalization ≈ **$15.52/sh**. Cash **$757.4M** less total debt **$214.0M** reconciles to net financial judgment band. |
| remaining uncertainty | Capitalization multiple and backlog milestone band are bounded judgments, not filing marks. |
| affected components | `wet_clean_equipment_engine`, `net_financial_claims`, `advanced_packaging_backlog_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter operating income per share falls below **$1.00** for four quarters without offsetting backlog conversion. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash **$757.4M**; current debt **$35.1M** plus noncurrent **$178.9M**; deferred revenue **$252.5M**; noncontrolling interest **$27.8M**. |
| source path | `10-K_20260302_rpt20251231` balance sheet and cash flow extracts |
| calculation | Net cash less debt filing-locked at **+$543.4M** (~**$8.08/sh**); cycle reserve base **−$7.00/sh** separate from core capitalization. |
| remaining uncertainty | China customer concentration and working-capital absorption remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `cycle_and_concentration_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from core owner-cash multiple. |
| falsifier | Total debt rises above **$280M** while operating cash flow stays below **$25M** for two consecutive fiscal years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; deferred revenue converting in normalized owner cash is not double-counted in backlog milestone band. |
| source path | `ACMR/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 consolidated revenue **$901.3M**; operating income **$109.4M**; net income **$94.1M**; operating cash flow **$10.3M**; cash **$757.4M**; total debt **$214.0M**; deferred revenue **$252.5M**; diluted EPS **$1.37** on **~67.3M** shares.

**Judgments (bounded):** Owner-cash capitalization multiple 5–12×; backlog milestone **$0–$18/sh**; net financial claim **$6–$10/sh**; cycle reserve **−$15 to −$2/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$22.60 per share** vs price **~$82.52** implies the market prices advanced packaging adoption and semicap recovery beyond filing-locked conservative components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
