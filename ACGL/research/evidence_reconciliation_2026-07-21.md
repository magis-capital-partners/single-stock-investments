# ACGL — Evidence reconciliation (2026-07-21)

**Ticker:** ACGL · **As-of:** 2026-07-21

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — five additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all five additive components |
| Owner-cash / NAV bridge | **met** — FY2025 after-tax operating income anchors segment allocation |
| Downside capital claims | **met** — catastrophe_cycle_reserve overlap key; senior notes in float surplus inputs |
| Double-counting | **met** — non-overlapping overlap keys; net reserves not subtracted twice |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py`).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Five additive components: insurance underwriting, reinsurance underwriting, mortgage insurance, investment float surplus, catastrophe cycle reserve |
| **Source** | `ACGL/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0000947484_26_000017.htm` segment table (Note 4) |
| **Calculation** | Underwriting income FY2025: Insurance $375M + Reinsurance $1,558M + Mortgage $1,000M = $2,933M; after-tax operating income $3,700M allocated proportionally |
| **Remaining uncertainty** | Segment-level investment income not separately disclosed; proportional allocation is judgment |
| **Affected components** | All five |
| **Valuation consequence** | Base component sum **$97.00/sh** vs price **~$102** |
| **Falsifier** | 10-K restates segment underwriting income or shows material intersegment eliminations breaking proportional bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | After-tax operating income available to Arch common shareholders **$3,700M** FY2025; diluted shares **375.9M** |
| **Source** | `ACGL/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0000947484_26_000017.htm` non-GAAP reconciliation |
| **Calculation** | $3,700M ÷ 375.9M = **$9.84/sh** starting owner cash |
| **Remaining uncertainty** | Non-GAAP metric excludes realized gains; GAAP net income $4.4B includes marks |
| **Affected components** | insurance, reinsurance, mortgage engines |
| **Valuation consequence** | Lawrence base uses $9.84/sh, not GAAP EPS $11.60 |
| **Falsifier** | Company changes non-GAAP definition materially or operating income falls below $3.0B without cat explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Total net loss reserves **$24,493M**; senior notes **$2,729M**; book value **$65.11/sh** |
| **Source** | FY2025 10-K balance sheet and segment reserve table |
| **Calculation** | catastrophe_cycle_reserve base **−$8/sh**; investment_float_surplus captures equity cushion above modest debt |
| **Remaining uncertainty** | Social inflation and property-cat severity remain unmodeled event trees |
| **Affected components** | catastrophe_cycle_reserve, investment_float_surplus |
| **Valuation consequence** | Bear reserve −$18/sh; low case component sum **$65/sh** approximates book |
| **Falsifier** | Combined ratio above 100% for two years with reserve strengthening above $3B incremental |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| insurance_underwriting_engine | owner_cash_or_dividend_discount@1.0 | 14.00 | valid |
| reinsurance_underwriting_engine | owner_cash_or_dividend_discount@1.0 | 51.00 | valid |
| mortgage_insurance_engine | owner_cash_or_dividend_discount@1.0 | 33.00 | valid |
| investment_float_surplus | net_asset_value@1.0 | 7.00 | valid |
| catastrophe_cycle_reserve | net_asset_value@1.0 | −8.00 | valid |
| **Sum** | | **97.00** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level investment income split | partially_met | Consolidated NII $1,625M; allocated via ATOI proportion |
| Mortgage housing-cycle scenario tree | partially_met | Combined ratio 14.6% FY2025; credit cycle stress in reserve band |
| Q1 2026 full segment restatement | not_met | Q1 10-Q filed; mechanical refresh will sync market inputs |
