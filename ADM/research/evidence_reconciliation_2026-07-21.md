# ADM — Evidence reconciliation (2026-07-21)

**Ticker:** ADM · **As-of:** 2026-07-21 · **Run:** valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $5.45B less capex $1.25B anchors FCF/sh $8.69 |
| Downside capital claims | **met** — net debt ~$7.4B in net claims; commodity-cycle reserve band |
| Double-counting | **met** — non-overlapping overlap keys; intersegment sales not double-counted |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: origination/processing owner cash, Nutrition specialty option, net financial claims, commodity-cycle/execution reserve |
| **Source** | `ADM/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0000007084_26_000011.htm` segment note; Item 7 MD&A |
| **Calculation** | FY2025 revenue $80.3B; adjusted segment OP $3.24B (Ag $1.61B + Carb $1.21B + Nutrition $0.42B); OCF $5.45B less capex $1.25B = FCF $4.20B |
| **Remaining uncertainty** | Segment-level FCF not disclosed; consolidated FCF engine with Nutrition option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$68.58/sh** vs price **~$85.67** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$5,452M**; capital spending **$1,248M**; diluted shares **484M** |
| **Source** | FY2025 10-K cash-flow statement and diluted EPS $2.23 |
| **Calculation** | ($5,452M − $1,248M) ÷ 484M = **$8.69/sh** normalized owner cash |
| **Remaining uncertainty** | FY2025 OCF recovery may overstate trough earnings power; mid-cycle normalization is judgment |
| **Affected components** | origination_processing_owner_cash |
| **Valuation consequence** | Lawrence base uses $8.69/sh starting owner cash |
| **Falsifier** | OCF falls below $3.5B for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$1,015M**; total debt **~$8,410M** (ST borrowings + current LT + noncurrent LT); net debt **~$7,395M** (~$15.28/sh) |
| **Source** | FY2025 10-K balance sheet; Q1 2026 10-Q confirms debt stack |
| **Calculation** | commodity_cycle_and_execution_reserve base **−$12/sh**; net_financial_claims base **−$15.28/sh** filing-locked |
| **Remaining uncertainty** | Commodity margin compression and leverage through troughs; SEC/DOJ investigations closed Jan 2026 |
| **Affected components** | net_financial_claims, commodity_cycle_and_execution_reserve |
| **Valuation consequence** | Bear reserve −$28/sh; low case component sum **~$13/sh** |
| **Falsifier** | Net debt exceeds $10B while adjusted segment operating profit stays below $2.5B |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| origination_processing_owner_cash | owner_cash_or_dividend_discount@1.0 | 87.86 | valid |
| nutrition_and_specialty_option | risk_adjusted_milestone_value@1.0 | 8.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −15.28 | valid |
| commodity_cycle_and_execution_reserve | net_asset_value@1.0 | −12.00 | valid |
| **Sum** | | **68.58** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Segment adjusted OP in 10-K; consolidated FCF engine used |
| Mid-cycle owner cash normalization | partially_met | FY2025 OCF recovery year; earnings trough ($1.08B NI) lags cash |
