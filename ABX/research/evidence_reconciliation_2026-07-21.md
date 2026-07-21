# ABX valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `life_solutions_engine` | unvalued | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $3.58 |
| `asset_management_franchise` | unvalued | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $0.68 |
| `technology_platform_option` | unvalued | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.20 |
| `net_financial_claims` | unvalued | net_asset_value@1.0 | bounded_estimate | −$2.57 |
| `longevity_and_funding_reserve` | unvalued | net_asset_value@1.0 | bounded_estimate | −$0.60 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Five additive components with unique overlap keys: life solutions engine, asset management franchise, technology platform option, net financial claims, longevity/funding reserve. Policy portfolio fair value embedded in Life Solutions earnings, not a separate additive NAV. |
| source path | `ABX/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$1.29/sh** = $3.58 + $0.68 + $0.20 − $2.57 − $0.60. |
| remaining uncertainty | Asset Management segment margin and non-recourse securitization carve-out remain judgment-heavy. |
| affected components | All five additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating income **$88.8M**; OCF **$25.7M**; capex **$0.9M**; GAAP FCF **~$0.25/sh** on **99.23M** diluted shares; Q1 2026 cash **$37.2M**; reported debt **~$291.8M**. |
| source path | `ABX/investor-documents/sec-edgar/10-K_20260313_rpt20251231_acc0001628280_26_017775.htm`; `10-Q_20260511_rpt20260331_acc0001628280_26_033136.htm` |
| calculation | Life Solutions proof: $0.895/sh operating income × 4.0 reinvestment multiple ≈ **$3.58/sh**. Net financial: ($37.2M − $291.8M) / 99.23M ≈ **−$2.57/sh**. |
| remaining uncertainty | Reinvestment multiple and fee-franchise margin are bounded judgments, not filing marks. |
| affected components | `life_solutions_engine`, `net_financial_claims`, `asset_management_franchise` |
| valuation consequence | Filing-locked facts anchor proofs; legacy Lawrence path remains separate stance gate. |
| falsifier | Trailing four-quarter operating income falls below **$60M** without offsetting cash generation. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Long-term debt **$405.8M** FY2025; Q1 2026 reported debt **$291.8M** including securitized notes; adjusted EBITDA **$132.6M** FY2025. |
| source path | FY2025 10-K balance sheet and non-GAAP reconciliation; Q1 2026 10-Q |
| calculation | Net financial claims base **−$2.57/sh**; longevity reserve base **−$0.60/sh** tied to GAAP FCF and funding-risk band. |
| remaining uncertainty | ABXL note spread and warehouse line capacity remain widest bands. |
| affected components | `net_financial_claims`, `longevity_and_funding_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from operating engine. |
| falsifier | Recourse debt rises above **$450M** while GAAP operating cash flow stays below **$30M** for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; policy portfolio not double-counted as separate NAV floor. |
| source path | `ABX/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$235.2M**; operating income **$88.8M**; OCF **$25.7M**; adjusted EBITDA **$132.6M**; diluted shares **99.23M**; Q1 2026 cash **$37.2M**; Q1 reported debt **~$291.8M**; GAAP FCF **~$0.25/sh**.

**Judgments (bounded):** Life Solutions reinvestment multiple 2.0–6.0× operating income per share; fee-franchise margin **25%** of segment revenue; technology milestone **$0–$79M**; net debt stress bands on cash and recourse debt; longevity reserve **−$1.25 to −$0.15/sh**.

## Valuation consequence

Proof-complete additive schedule base case **~$1.29 per share** vs price **~$9.25** implies component economic value well below market; Lawrence seven-year synthesis base **0.32%** remains below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
