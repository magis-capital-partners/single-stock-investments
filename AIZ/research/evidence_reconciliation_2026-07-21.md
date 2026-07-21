# AIZ — Evidence reconciliation (2026-07-21)

**Ticker:** AIZ · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — five additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all five additive components |
| Owner-cash / NAV bridge | **met** — FY2025 net income $872.7M anchors $17.09/sh owner cash |
| Downside capital claims | **met** — net debt ~$7.30/sh filing-locked; catastrophe reserve component |
| Double-counting | **met** — non-overlapping overlap keys; unearned premiums not subtracted twice |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Five additive components: Global Lifestyle owner-cash engine, Global Housing owner-cash engine, investment float surplus, net financial claims, catastrophe and cycle reserve |
| **Source** | `AIZ/investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0001267238_26_000010.htm` Item 7 segment tables |
| **Calculation** | Lifestyle Adjusted EBITDA $801.3M + Housing $858.7M − Corporate $(123.8)M = consolidated $1,536.2M Adjusted EBITDA; net income $872.7M allocated by segment EBITDA share |
| **Remaining uncertainty** | Segment-level net income not separately disclosed; Adjusted EBITDA allocation proxy |
| **Affected components** | All five |
| **Valuation consequence** | Base component sum **~$254.70/sh** vs price **~$275.47** |
| **Falsifier** | 10-K restates segment Adjusted EBITDA or shows material intersegment eliminations breaking consolidated net income bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 consolidated net income **$872.7M**; diluted EPS **$16.93**; weighted average diluted shares **51.1M** |
| **Source** | FY2025 10-K income statement and EPS footnote |
| **Calculation** | $872.7M ÷ 51.087M = **$17.09/sh** normalized owner cash; operating cash flow $1,833.9M ($35.90/sh) includes float movements |
| **Remaining uncertainty** | OCF includes premium float timing; net income is cleaner Lawrence anchor but includes realized investment gains |
| **Affected components** | global_lifestyle_owner_cash_engine, global_housing_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $17.09/sh starting owner cash |
| **Falsifier** | Consolidated net income falls below $700M for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$1,834.1M**; unsecured senior notes **$2,206.9M**; net debt **~$372.8M** (~**$7.30/sh**) |
| **Source** | FY2025 10-K balance sheet and debt footnote; August 2025 $300M 5.55% notes issued to redeem $175M 6.10% notes |
| **Calculation** | net_financial_claims base **−$7.30/sh** filing-locked; catastrophe_and_cycle_reserve base **−$14.00/sh** |
| **Remaining uncertainty** | Housing reportable catastrophes and lender-placed credit cycle remain widest judgment band |
| **Affected components** | net_financial_claims, catastrophe_and_cycle_reserve |
| **Valuation consequence** | Bear reserve −$28/sh low case; low component sum **~$148/sh** |
| **Falsifier** | Global Housing reportable catastrophes exceed $100M pre-tax for two consecutive years with no Lifestyle offset |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| global_lifestyle_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 125.01 | valid |
| global_housing_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 134.99 | valid |
| investment_float_surplus | net_asset_value@1.0 | 16.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −7.30 | valid |
| catastrophe_and_cycle_reserve | net_asset_value@1.0 | −14.00 | valid |
| **Sum** | | **254.70** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level net income split | partially_met | Adjusted EBITDA-proportional allocation; 10-K does not disclose segment net income |
| Realized investment gains in net income | partially_met | Adjusted EBITDA excludes gains; net income includes them; normalization judgment remains |
| Pending subsidiary sale loss | open | 10-K references loss on pending subsidiary sale and restructuring; monitor Q2 2026 filings |
