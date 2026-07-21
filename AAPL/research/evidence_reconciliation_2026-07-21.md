# AAPL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_products_services_engine` | unpriced | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $171.03 |
| `services_installed_base_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $35.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | $3.00 |
| `regulatory_and_cycle_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$22.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: core products and services engine, Services installed-base option, net financial claims, regulatory and cycle reserve. No embedded double-count. |
| source path | `AAPL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$187.03/sh** = $171.03 + $35.00 + $3.00 − $22.00. |
| remaining uncertainty | Services milestone band ($0–$85/sh) remains judgment-heavy; deferred Services value partially embedded in consolidated free cash flow. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$111,482M**; capital spending **$12,715M**; free cash flow **$98,767M**; diluted **~15,015M** shares ($112,010M net income / $7.46 EPS). |
| source path | `AAPL/investor-documents/sec-edgar/10-K_20251031_rpt20250927_acc0000320193_25_000079.htm` |
| calculation | Core proof: **$6.58/sh** FCF × 26× capitalization ≈ **$171.03/sh**. Cash and marketable securities **$132,420M** less total debt **$90,678M** reconciles to net financial judgment band. |
| remaining uncertainty | Capitalization multiple and Services milestone band are bounded judgments, not filing marks. |
| affected components | `core_products_services_engine`, `net_financial_claims`, `services_installed_base_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter free cash flow per share falls below **$5.50** for four quarters without offsetting Services mix improvement. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash and marketable securities **$132,420M**; long-term debt **$78,328M** plus current **$12,350M**; operating lease noncurrent **$10,911M**; research and development **$34,550M**. |
| source path | `10-K_20251031_rpt20250927` balance sheet and income statement extracts |
| calculation | Net securities less debt filing-locked at **+$41,742M**; regulatory reserve base **−$22.00/sh** separate from core capitalization. |
| remaining uncertainty | China revenue concentration and antitrust outcomes remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `regulatory_and_cycle_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from core owner-cash multiple. |
| falsifier | Total debt rises above **$100B** while free cash flow per share falls below **$5.00** for two consecutive fiscal years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; Services revenue embedded in consolidated FCF is not double-counted in core engine multiple; incremental option is a separate milestone band. |
| source path | `AAPL/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 consolidated net sales **$307,003M**; disaggregated Services **$109,158M**; operating income **$133,050M**; net income **$112,010M**; operating cash flow **$111,482M**; capital spending **$12,715M**; cash and marketable securities **$132,420M**; total debt **$90,678M**; diluted EPS **$7.46**.

**Judgments (bounded):** Owner free-cash-flow capitalization multiple 20–32×; Services milestone **$0–$85/sh**; net financial claim **−$6 to +$10/sh**; regulatory reserve **−$45 to −$8/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$187.03 per share** vs price **~$326.59** implies the market prices ecosystem durability and Services growth beyond filing-locked conservative components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
