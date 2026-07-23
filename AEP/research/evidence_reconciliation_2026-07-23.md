# AEP — Evidence reconciliation (2026-07-23)

**Scope:** Contract backfill refresh per authorized evidence packet (`DOWNLOAD_MANIFEST.json` + `authorized_evidence.json`).

## Proofs attached (unchanged evidence packet)

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `regulated_owner_cash_engine` | owner_cash_or_dividend_discount@1.0 | valid | $119.00 |
| `data_center_load_option` | risk_adjusted_milestone_value@1.0 | valid | $12.00 |
| `net_financial_claims` | net_asset_value@1.0 | valid | −$88.40 |
| `regulatory_execution_reserve` | net_asset_value@1.0 | valid | −$18.00 |

Additive base sum **$24.60/sh** (119 + 12 − 88.40 − 18). Proofs in `valuation_contract.json` and `valuation.json` → `component_valuation`.

## Acceptance test: complete economic ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys map 100% of material owner claims: regulated owner-cash engine, data-center load option, net financial claims, regulatory execution reserve |
| source path | `AEP/investor-documents/sec-edgar/10-K_20260212_rpt20251231_acc0000004904_26_000013.htm` (MD&A, segments, balance sheet) |
| calculation | FY2025 revenue **$21.9B**; net income to common **$3.6B** (**$6.66** diluted EPS); **$72B** 2026–2030 capital plan; debt **$47.7B**; cash **$197M** |
| remaining uncertainty | Segment-level owner earnings not separately modeled; consolidated regulated engine with non-overlapping load option overlay |
| affected components | All four |
| valuation consequence | Closes `authorized_evidence.json` blocker: *"A complete economic ownership map has not been supplied."* |
| falsifier | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated earnings bridge |

## Acceptance test: primary cash / owner-cash bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 diluted EPS **$6.66**; normalized owner cash **$6.40/sh** (4% haircut [Assumption]) |
| source path | FY2025 10-K income statement and EPS note |
| calculation | Regulated utility lens: OCF **$6.9B** minus investing **$11.9B** is negative raw FCF; rate-base recovery is correct owner-cash path |
| remaining uncertainty | Weather and regulatory timing may make FY2025 EPS step-up non-durable |
| affected components | `regulated_owner_cash_engine` |
| valuation consequence | Lawrence base uses **$6.40/sh** starting owner earnings |
| falsifier | Diluted EPS falls below **$5.50** for two consecutive years without one-time explanation |

## Acceptance test: downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Net debt **~$47.5B** (**~$88.40/sh**); **$5.6B** planned equity issuance; **$72B** capex plan |
| source path | FY2025 10-K balance sheet, debt footnote, MD&A Liquidity and Capital Resources |
| calculation | `net_financial_claims` base **−$88.40/sh** filing-locked; `regulatory_execution_reserve` base **−$18/sh** |
| remaining uncertainty | ATM timing and allowed ROE trajectory in Ohio, Texas, West Virginia |
| affected components | `net_financial_claims`, `regulatory_execution_reserve` |
| valuation consequence | Low case component sum **~$−42/sh** |
| falsifier | Allowed ROE cuts in two or more major jurisdictions within 24 months |

## Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys: `regulated_owner_cash_engine`, `data_center_load_option`, `net_financial_claims`, `regulatory_execution_reserve` |
| source path | `AEP/research/valuation.json` |
| calculation | Additive base sum **$24.60/sh**; data-center option is non-overlapping incremental load claim |
| remaining uncertainty | None on overlap map |
| affected components | All additive |
| valuation consequence | Component sum is additive once |
| falsifier | New component added without unique overlap_key |

## Open gaps (partially_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner earnings split | partially_met | Vertically Integrated vs T&D segments in 10-K; consolidated engine used |
| Data-center load probability | partially_met | 10-K cites data centers in large-load category; milestone band is judgment |
| Approved third-party sources | partially_met | No approved Substacks or fund letters; primary filings only in base IRR |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$21.9B**; operating income **$5.3B**; diluted EPS **$6.66**; dividend **$3.74/sh**; debt **$47.7B**; cash **$197M**; diluted shares **537.5M**; **$72B** capital plan 2026–2030; **$5.6B** equity issuance plan.

**Judgments (bounded):** Normalized owner cash **$6.40/sh**; data-center option **$0–$30/sh**; regulatory reserve **−$32 to −$8/sh**; Lawrence seven-year base **7.3%** per year at **$131.05**.

## Valuation consequence

Proof-complete additive schedule base **~$24.60 per share** vs price **~$131** implies the market prices regulated growth, dividend yield, and credit quality above Marvin's component sum. Lawrence seven-year synthesis **7.3%** per year remains the stance gate (below **~15%** hurdle). Security remains **watch**; no human capital decision recorded.
