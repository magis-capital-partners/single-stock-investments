# ADI valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `analog_semiconductor_engine` | unpriced | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $223.96 |
| `ai_data_center_edge_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $18.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | −$12.00 |
| `cycle_integration_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$20.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: analog semiconductor engine, AI/data-center edge option, net financial claims, cycle/integration reserve. No embedded double-count. |
| source path | `ADI/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$209.96/sh** = $223.96 + $18.00 − $12.00 − $20.00. |
| remaining uncertainty | AI/data-center milestone band ($0–$45/sh) remains judgment-heavy; industrial revenue already in consolidated free cash flow. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$4,812.2M**; capital spending **$533.6M**; free cash flow **$4,278.6M**; diluted **496.709M** shares ($2,267.3M net income / $4.56 EPS). |
| source path | `ADI/investor-documents/sec-edgar/10-K_20251125_rpt20251101_acc0000006281_25_000153.htm` |
| calculation | Core proof: **$8.61/sh** free cash flow × 26× capitalization ≈ **$223.96/sh**. Cash **$2,499.4M** less total debt **$8,599.9M** reconciles to net financial judgment band. |
| remaining uncertainty | Capitalization multiple and AI milestone band are bounded judgments, not filing marks. |
| affected components | `analog_semiconductor_engine`, `net_financial_claims`, `ai_data_center_edge_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter free cash flow per share falls below **$6.50** for four quarters without offsetting industrial mix improvement. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash **$2,499.4M**; long-term debt **$8,145.1M** plus current debt and short-term borrowings **$454.8M**; research and development **$1,766.0M**; operating income **$2,932.5M**. |
| source path | `10-K_20251125_rpt20251101` balance sheet and income statement extracts |
| calculation | Filing-locked net debt **~$6,100.5M** (~$12.28/sh); cycle reserve base **−$20.00/sh** separate from core capitalization. |
| remaining uncertainty | Industrial inventory correction and communications end-market softness remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `cycle_integration_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from core owner-cash multiple. |
| falsifier | Total debt rises above **$9.5B** while free cash flow per share falls below **$6.00** for two consecutive fiscal years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; industrial and automotive revenue embedded in consolidated free cash flow is not double-counted in core engine multiple; incremental AI option is a separate milestone band. |
| source path | `ADI/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 consolidated revenue **$11,019.7M**; Industrial end market **$4,929.4M** (45%); Automotive **$3,277.9M** (30%); operating income **$2,932.5M**; net income **$2,267.3M**; operating cash flow **$4,812.2M**; capital spending **$533.6M**; cash **$2,499.4M**; total debt **$8,599.9M**; diluted EPS **$4.56**.

**Judgments (bounded):** Owner free-cash-flow capitalization multiple 20–32×; AI/data-center milestone **$0–$45/sh**; net financial claim **−$16 to −$8/sh**; cycle reserve **−$35 to −$10/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$209.96 per share** vs price **~$372.46** implies the market prices analog moat durability, AI/data-center mix, and capital returns beyond filing-locked conservative components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
