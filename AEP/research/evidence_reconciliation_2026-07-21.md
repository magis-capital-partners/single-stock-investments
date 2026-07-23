# AEP — Evidence reconciliation (2026-07-21)

**Ticker:** AEP · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 diluted EPS $6.66; normalized owner cash $6.40/sh |
| Downside capital claims | **met** — net debt ~$47.5B (~$88.40/sh); regulatory execution reserve |
| Double-counting | **met** — non-overlapping overlap keys; data-center option separate from base rate-base engine |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: regulated owner-cash engine, data-center load option, net financial claims, regulatory execution reserve |
| **Source** | `AEP/investor-documents/sec-edgar/10-K_20260212_rpt20251231_acc0000004904_26_000013.htm` MD&A and segment notes |
| **Calculation** | FY2025 revenue $21.9B; operating income $5.3B; net income to common $3.6B; $72B 2026-2030 capital plan |
| **Remaining uncertainty** | Segment-level owner earnings not separately disclosed; consolidated regulated engine with load option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$24.60/sh** vs price **~$131**; Lawrence synthesis is separate stance gate |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated earnings bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 diluted EPS **$6.66**; net income available to common **$3,580M**; diluted shares **537.5M** |
| **Source** | FY2025 10-K income statement and EPS note |
| **Calculation** | Normalized owner cash **$6.40/sh** (4% haircut on reported EPS for weather/regulatory timing [Assumption]) |
| **Remaining uncertainty** | Regulated utility: OCF $6.9B minus investing $11.9B is negative raw FCF; rate-base recovery is the correct owner-cash lens |
| **Affected components** | regulated_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $6.40/sh starting owner earnings |
| **Falsifier** | Diluted EPS falls below $5.50 for two consecutive years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$197M**; total debt carrying amount **$47.7B**; net debt **~$47.5B** (~**$88.40/sh**) |
| **Source** | FY2025 10-K balance sheet and debt footnote |
| **Calculation** | regulatory_execution_reserve base **−$18/sh**; net_financial_claims base **−$88.40/sh** filing-locked |
| **Remaining uncertainty** | $5.6B planned equity issuance and $72B capex plan create dilution and execution tail |
| **Affected components** | net_financial_claims, regulatory_execution_reserve |
| **Valuation consequence** | Bear reserve −$32/sh; low case component sum **~$−42/sh** |
| **Falsifier** | Allowed ROE cuts in two or more major jurisdictions within 24 months |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| regulated_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 119.00 | valid |
| data_center_load_option | risk_adjusted_milestone_value@1.0 | 12.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −88.40 | valid |
| regulatory_execution_reserve | net_asset_value@1.0 | −18.00 | valid |
| **Sum** | | **24.60** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner earnings split | partially_met | Vertically Integrated vs T&D segments in 10-K; consolidated engine used |
| Data-center load probability | partially_met | 10-K cites data centers in large-load category; milestone band is judgment |
| Full-tier filing digest sync | partially_met | Mechanical refresh will rebuild filing digest for 2026-07-21 |
