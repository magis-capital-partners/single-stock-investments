# AIG — Evidence reconciliation (2026-07-21)

**Ticker:** AIG · **As-of:** 2026-07-21

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — five additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all five additive components |
| Owner-cash / NAV bridge | **met** — FY2025 adjusted after-tax income anchors segment allocation |
| Downside capital claims | **met** — catastrophe_and_reserve_stress overlap key; total debt in reserve inputs |
| Double-counting | **met** — non-overlapping overlap keys; net reserves not subtracted twice |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py`).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Five additive components: North America Commercial, International Commercial, Global Personal underwriting engines, Corebridge stake and float surplus, catastrophe/reserve stress |
| **Source** | `AIG/investor-documents/sec-edgar/10-K_20260212_rpt20251231_acc0000005272_26_000023.htm` General Insurance segment table |
| **Calculation** | Underwriting income FY2025: North America $1,144M + International $1,118M + Global Personal $70M = $2,332M; adjusted after-tax income $4,044M allocated proportionally |
| **Remaining uncertainty** | Segment-level investment income not separately disclosed; proportional allocation is judgment |
| **Affected components** | All five |
| **Valuation consequence** | Base component sum **$76.00/sh** vs price **~$79.80** |
| **Falsifier** | 10-K restates segment underwriting income or shows material intersegment eliminations breaking proportional bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Adjusted after-tax income attributable to AIG common shareholders **$4,044M** FY2025; diluted shares **570.35M** |
| **Source** | `AIG/investor-documents/sec-edgar/10-K_20260212_rpt20251231_acc0000005272_26_000023.htm` non-GAAP reconciliation |
| **Calculation** | $4,044M ÷ 570.35M = **$7.09/sh** starting owner cash |
| **Remaining uncertainty** | Non-GAAP metric excludes investment marks and Fortitude Re noise; GAAP net income $3.1B includes volatility |
| **Affected components** | north_america_commercial_engine, international_commercial_engine, global_personal_engine |
| **Valuation consequence** | Lawrence base uses $7.09/sh, not GAAP EPS $5.43 |
| **Falsifier** | Company changes non-GAAP definition materially or adjusted after-tax income falls below $3.0B without cat explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Total net loss reserves **$41,665M**; total debt **$9,191M**; adjusted book value **$78.02/sh** |
| **Source** | FY2025 10-K balance sheet and General Insurance reserve table |
| **Calculation** | catastrophe_and_reserve_stress base **−$7/sh**; corebridge_and_float_surplus captures Corebridge stake $1.5B |
| **Remaining uncertainty** | Social inflation, California wildfire, and Fortitude runoff remain unmodeled event trees |
| **Affected components** | catastrophe_and_reserve_stress, corebridge_and_float_surplus |
| **Valuation consequence** | Bear reserve −$14/sh; low case component sum approximates adjusted book floor |
| **Falsifier** | General Insurance combined ratio above 95% for two years with reserve strengthening above $2B incremental |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| north_america_commercial_engine | owner_cash_or_dividend_discount@1.0 | 38.00 | valid |
| international_commercial_engine | owner_cash_or_dividend_discount@1.0 | 37.00 | valid |
| global_personal_engine | owner_cash_or_dividend_discount@1.0 | 2.00 | valid |
| corebridge_and_float_surplus | net_asset_value@1.0 | 6.00 | valid |
| catastrophe_and_reserve_stress | net_asset_value@1.0 | −7.00 | valid |
| **Sum** | | **76.00** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level investment income split | partially_met | Consolidated GI NII $3,433M; allocated via adjusted after-tax income proportion |
| Global Personal wildfire scenario tree | partially_met | Combined ratio 99.0% FY2025; California regulatory risk in reserve band |
| Q1 2026 full segment restatement | not_met | Q1 10-Q filed; mechanical refresh will sync market inputs |
