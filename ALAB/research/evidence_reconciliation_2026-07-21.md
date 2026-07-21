# ALAB valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `ai_connectivity_semiconductor_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $8.06 |
| `design_win_scale_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $12.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | $6.45 |
| `customer_concentration_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$8.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: AI connectivity semiconductor engine, design-win scale option, net financial claims, customer concentration reserve. No embedded double-count. |
| source path | `ALAB/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$18.51/sh** = $8.06 + $12.00 + $6.45 − $8.00. |
| remaining uncertainty | Design-win milestone band ($0–$35/sh) and concentration reserve remain widest judgment bands. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 revenue **$852.5M** (+115% YoY); operating income **$173.4M**; operating cash flow **$319.3M**; diluted **~179.6M** shares ($219.1M net income / $1.22 EPS). |
| source path | `ALAB/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001736297_26_000010.htm` |
| calculation | Core proof: **$0.81/sh** two-year average operating income × 10× capitalization ≈ **$8.06/sh**. Cash **$167.6M** plus AFS **$1,021.2M** less lease **$31.0M** reconciles to net financial judgment band. |
| remaining uncertainty | Capitalization multiple and design-win milestone band are bounded judgments, not filing marks. |
| affected components | `ai_connectivity_semiconductor_engine`, `net_financial_claims`, `design_win_scale_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter operating income per share falls below **$0.50** for four quarters without offsetting design-win conversion. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash **$167.6M**; current AFS debt securities **$1,021.2M**; operating lease liabilities **$31.0M**; no traditional bank debt; Customer A **37%** of revenue; top customer **73%** of accounts receivable. |
| source path | `10-K_20260220_rpt20251231` balance sheet and customer concentration extracts |
| calculation | Net liquid filing-locked at **+$1,157.8M** (~**$6.45/sh**); concentration reserve base **−$8.00/sh** separate from core capitalization. |
| remaining uncertainty | Hyperscaler concentration and Amazon warrant overhang remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `customer_concentration_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from core owner-cash multiple. |
| falsifier | Customer A revenue share rises above **45%** while gross margin falls below **70%** for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; marketable securities counted only in net financial claims, not duplicated in engine multiple. |
| source path | `ALAB/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 consolidated revenue **$852.5M**; operating income **$173.4M**; net income **$219.1M**; operating cash flow **$319.3M**; cash **$167.6M**; current AFS securities **$1,021.2M**; operating lease liabilities **$31.0M**; diluted EPS **$1.22** on **~179.6M** shares; Customer A revenue concentration **37%**.

**Judgments (bounded):** Owner-cash capitalization multiple 6–14×; design-win milestone **$0–$35/sh**; net financial claim **$5.72–$6.63/sh**; concentration reserve **−$18 to −$2/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$18.51 per share** vs price **~$309.09** implies the market prices AI connectivity adoption and design-win scale far beyond filing-locked conservative components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
