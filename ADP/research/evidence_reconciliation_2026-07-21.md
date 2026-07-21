# ADP — Evidence reconciliation (2026-07-21)

**Ticker:** ADP · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $4.94B less capex $0.17B anchors FCF/sh $11.67 |
| Downside capital claims | **met** — competition/client-funds reserve; net debt ~$5.4B in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; client-fund pass-through not in owner cash |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: payroll/HCM owner-cash engine, PEO platform option, net financial claims, competition/client-funds reserve |
| **Source** | `ADP/investor-documents/sec-edgar/10-K_20250806_rpt20250630_acc0000008670_25_000037.htm` Item 7; Employer Services and PEO segment note |
| **Calculation** | FY2025 service revenue $20.56B (excludes $75.2B PEO pass-through); OCF $4.94B less capex $0.17B = FCF $4.77B |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; consolidated FCF engine with PEO option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$267/sh** vs price **~$255** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$4,939.7M**; capital spending **$168.7M**; diluted shares **408.7M** |
| **Source** | FY2025 10-K cash-flow statement and diluted EPS $9.98 |
| **Calculation** | ($4,939.7M − $168.7M) ÷ 408.7M = **$11.67/sh** normalized owner cash |
| **Remaining uncertainty** | Interest on client funds ($489M) is segment revenue, not additive to FCF; peak-cycle vs normalized FCF is judgment |
| **Affected components** | payroll_hcm_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $11.67/sh starting owner cash |
| **Falsifier** | OCF falls below $4.0B for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$3,347.8M**; commercial paper **$4,769.5M**; long-term debt **$3,974.7M**; net debt **~$5,396M** (~$13.20/sh) |
| **Source** | FY2025 10-K balance sheet and debt footnote |
| **Calculation** | competition_and_client_funds_reserve base **−$10/sh**; net_financial_claims base **−$13.20/sh** filing-locked |
| **Remaining uncertainty** | Rate cuts could compress client-fund interest faster than low growth scenario; refinancing risk on commercial paper |
| **Affected components** | net_financial_claims, competition_and_client_funds_reserve |
| **Valuation consequence** | Bear reserve −$25/sh; low case component sum **~$172/sh** |
| **Falsifier** | Employer Services margin falls below 25% for four consecutive quarters with flat retention |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| payroll_hcm_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 281.87 | valid |
| peo_workforce_platform_option | risk_adjusted_milestone_value@1.0 | 8.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −13.20 | valid |
| competition_and_client_funds_reserve | net_asset_value@1.0 | −10.00 | valid |
| **Sum** | | **266.67** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Employer Services vs PEO revenue in 10-K; consolidated FCF engine used |
| PEO platform probability | partially_met | PEO services revenue $1.53B disclosed; milestone band is judgment |
| Q2 FY2026 full-tier evidence sync | partially_met | Mechanical refresh will rebuild filing digest for 2026-07-21 |
