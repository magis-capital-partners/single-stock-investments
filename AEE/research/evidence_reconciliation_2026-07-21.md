# AEE valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (hash `83b49cbd…`).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `regulated_owner_cash_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $113.00 |
| `large_load_interconnection_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $3.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | −$0.47 |
| `equity_dilution_and_regulatory_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$4.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: regulated owner-cash engine, large-load interconnection option, minority financial claims, equity dilution/regulatory reserve. No embedded double-count. |
| source path | `AEE/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$111.53/sh** = $113.00 + $3.00 − $0.47 − $4.00. |
| remaining uncertainty | Large-load pipeline timing and Illinois MYRP appeals remain widest judgment bands. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 diluted EPS **$5.35/sh**; normalized owner cash **$5.10/sh**; OCF **$3,353M**; capex **$4,128M**; **276.4M** shares outstanding. |
| source path | `AEE/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001002910_26_000009.htm`, `10-Q_20260508_rpt20260331_acc0001002910_26_000015.htm` |
| calculation | Owner-cash DCF proof anchors engine at **$113/sh** base on $5.10 starting cash, 6%/5% growth, 17× exit. |
| remaining uncertainty | Normalization haircut and exit multiple are bounded judgments. |
| affected components | `regulated_owner_cash_engine` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter diluted EPS falls below **$4.50/sh** without offsetting rate-base recovery. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | ~**$4.0B** equity issuance planned 2026–2030; NCI **~$129M**; long-term debt **~$19.2B** recovered through rates (not double-subtracted). |
| source path | `10-K_20260218` Outlook, Liquidity, and balance-sheet extracts |
| calculation | Dilution reserve base **−$4.00/sh**; minority claim **−$0.47/sh** separate from regulated debt. |
| remaining uncertainty | Equity issuance timing and MYRP appeal outcomes drive reserve band width. |
| affected components | `equity_dilution_and_regulatory_reserve`, `net_financial_claims` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from owner-cash engine. |
| falsifier | Equity issuance exceeds **$5B** through 2030 without proportional rate-base growth disclosure. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; large-load revenue in base rate-base path embedded in owner-cash engine, not double-counted in option row. |
| source path | `AEE/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$8,799M**, net income **$1,456M**, diluted EPS **$5.35**, OCF **$3,353M**, capex **$4,128M**, shares **276.4M**, dividend **$3.00/sh** annualized, capex plan **$30.5–33.1B** (2026–2030), equity plan **~$4.0B**.

**Judgments (bounded):** Owner-cash exit multiple 14–18×; large-load option **$0–$8/sh**; dilution/regulatory reserve **−$8 to −$1/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$111.53 per share** vs price **~$111.77** implies the market prices Ameren near filing-anchored regulated owner-cash components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
