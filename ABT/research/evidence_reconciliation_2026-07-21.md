# ABT valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_healthcare_franchise` | unmapped | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $96.02 |
| `net_financial_claims` | unmapped | net_asset_value@1.0 | bounded_estimate | $0.50 |
| `margin_and_competition_reserve` | unmapped | net_asset_value@1.0 | bounded_estimate | −$4.50 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Three additive components with unique overlap keys: core healthcare franchise, net financial claims, margin and competition reserve. Device pipeline (Libre, structural heart) embedded in core franchise; option scan found no separate milestone block. |
| source path | `ABT/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$92.02/sh** = $96.02 + $0.50 − $4.50. |
| remaining uncertainty | Segment-level owner-cash allocation remains consolidated; Q1 2026 margin bridge pending. |
| affected components | All three additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 revenue **$44,328M** (+5.7% YoY); operating income **$8,053M** (18.2% margin); cash from operations **$9,566M**; capital spending **$2,171M**; owner cash **~$4.23/sh**; cash **$8,522M**; long-term debt **$9,896M**; diluted shares **~1,748M**. |
| source path | `ABT/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001628280_26_010185.htm`; Q1 2026 `10-Q_20260429_rpt20260331_acc0001628280_26_028357.htm` |
| calculation | OCF **$9,566M** − capex **$2,171M** = **$7,395M** ÷ **1,748M** shares = **$4.23/sh**. Core proof: owner cash × capitalization multiple (22.7× base) = **$96.02/sh**. |
| remaining uncertainty | Q1 2026 operating income **$1,350M** vs **$1,690M** prior-year quarter; margin mix vs cost inflation not fully decomposed. |
| affected components | `core_healthcare_franchise`, `net_financial_claims` |
| valuation consequence | Filing-locked facts anchor proofs; legacy inferred-minimal fallback replaced. |
| falsifier | Two consecutive quarters of consolidated operating margin below **16%** without offsetting device growth. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Cash **$8,522M**; long-term debt **$9,896M** (down from **$12,625M** prior year); filing-locked net **~−$0.79/sh**; Q1 2026 revenue **$11,164M** (+7.8% YoY) with operating income down YoY. |
| source path | FY2025 10-K balance sheet and income statement; Q1 2026 10-Q |
| calculation | Margin reserve base **−$4.50/sh** = **−$7,866M** judgment reserve for CGM competition, nutrition pricing, and China volume risk (not full net debt double-count). Net financial claim **+$0.50/sh** = near-term surplus cash bridge separate from capitalized core engine. |
| remaining uncertainty | Dexcom CGM share gains and infant nutrition competition remain widest judgment bands. |
| affected components | `margin_and_competition_reserve`, `net_financial_claims` |
| valuation consequence | Capital and competition claims reconciled to filings; stress reserved once. |
| falsifier | Medical Devices segment operating earnings fall more than **10%** YoY for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; Libre and structural-heart growth embedded in core franchise only; surplus cash not capitalized twice inside core terminal. |
| source path | `ABT/research/valuation.json` |
| calculation | `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$44.3B**; operating income **$8.05B**; OCF **$9.57B**; capex **$2.17B**; owner cash **$4.23/sh**; cash **$8.52B**; long-term debt **$9.90B**; shares **~1.75B**; Medical Devices **$21.4B** sales / **$7.2B** OI.

**Judgments (bounded):** Core capitalization multiple **16–27×** on **$4.23/sh** owner cash; surplus cash claim **−$1.50 to +$2.00/sh**; margin reserve **−$9.00 to −$1.50/sh**.

## Valuation consequence

Proof-complete additive schedule base case **~$92.02 per share** vs price **~$94.4** implies component economic value slightly below market; Lawrence seven-year base **~11.4%** remains the stance gate. Security remains **watch**; no human capital decision recorded.
