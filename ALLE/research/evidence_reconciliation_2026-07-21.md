# ALLE — Evidence reconciliation (2026-07-21)

**Ticker:** ALLE · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $783.8M less capex $69.1M anchors FCF/sh $8.25 |
| Downside capital claims | **met** — housing-cycle reserve; net debt ~$1.62B in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; electronic option separate from owner-cash engine |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: security-products owner-cash engine, electronic/software option, net financial claims, housing-cycle reserve |
| **Source** | `ALLE/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001579241_26_000007.htm` Item 7; Americas and International segment note |
| **Calculation** | FY2025 revenue $4,067.3M; OCF $783.8M less capex $69.1M = FCF $714.7M |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; consolidated FCF engine with electronic option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$162/sh** vs price **~$138** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$783.8M**; capital spending **$69.1M**; diluted shares **86.6M** |
| **Source** | FY2025 10-K cash-flow statement and diluted EPS $7.44 |
| **Calculation** | ($783.8M − $69.1M) ÷ 86.6M = **$8.25/sh** normalized owner cash |
| **Remaining uncertainty** | FY2025 investing outflows included acquisition cash; peak-cycle vs normalized FCF is judgment |
| **Affected components** | security_products_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $8.25/sh starting owner cash |
| **Falsifier** | OCF falls below $650M for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$356.2M**; total debt **$1,980.1M**; revolver draw **$190.6M**; net debt **~$1,623.9M** (~$18.75/sh) |
| **Source** | FY2025 10-K balance sheet and debt footnote |
| **Calculation** | housing_cycle_and_competition_reserve base **−$8/sh**; net_financial_claims base **−$18.75/sh** filing-locked |
| **Remaining uncertainty** | Variable-rate revolver exposure; non-residential construction cycle could compress Americas volume faster than low growth case |
| **Affected components** | net_financial_claims, housing_cycle_and_competition_reserve |
| **Valuation consequence** | Bear reserve −$15/sh; low case component sum **~$85/sh** |
| **Falsifier** | Americas operating margin falls below 24% for four consecutive quarters with flat pricing |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| security_products_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 180.58 | valid |
| electronic_access_and_software_option | risk_adjusted_milestone_value@1.0 | 8.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −18.75 | valid |
| housing_cycle_and_competition_reserve | net_asset_value@1.0 | −8.00 | valid |
| **Sum** | | **161.83** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Americas vs International revenue and margin in 10-K; consolidated FCF engine used |
| Electronic option probability | partially_met | Electronic revenue $278M disclosed; milestone band is judgment |
| Q1 2026 full-tier evidence sync | partially_met | Mechanical refresh will rebuild filing digest for 2026-07-21 |
