# AJG — Evidence reconciliation (2026-07-21)

**Ticker:** AJG · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $1.93B less estimated maintenance capex $0.18B anchors FCF/sh $6.72 |
| Downside capital claims | **met** — integration/leverage reserve; net debt ~$12.4B in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; fiduciary pass-through not in owner cash |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: brokerage/risk-management owner-cash engine, AssuredPartners integration option, net financial claims, integration/leverage reserve |
| **Source** | `AJG/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001628280_26_008662.htm` Item 7; brokerage and risk-management segment notes |
| **Calculation** | FY2025 total revenue $13.94B; brokerage $8.02B + risk management $4.20B before reimbursements; OCF $1.93B less capex $0.18B = FCF $1.75B |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; maintenance capex estimated from depreciation |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$102/sh** vs price **~$254** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$1,930M**; estimated maintenance capex **$180M**; diluted shares **~260.3M** |
| **Source** | FY2025 10-K cash-flow statement; net income $1,494M / diluted EPS $5.74 |
| **Calculation** | ($1,930M − $180M) ÷ 260.3M = **$6.72/sh** normalized owner cash |
| **Remaining uncertainty** | AssuredPartners acquisition year may depress GAAP OCF; fiduciary cash flows excluded but not separately quantified in bridge |
| **Affected components** | brokerage_and_risk_management_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $6.72/sh starting owner cash |
| **Falsifier** | OCF falls below $1.5B for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$1,155M**; short-term borrowings **$640M**; long-term debt **$12,873M**; net debt **~$12,358M** (~$47.48/sh) |
| **Source** | FY2025 10-K balance sheet and debt footnote |
| **Calculation** | integration_and_leverage_reserve base **−$18/sh**; net_financial_claims base **−$47.48/sh** filing-locked |
| **Remaining uncertainty** | Interest expense $639M (+68% YoY) may rise further if rates stay elevated; earnout obligations on tuck-ins |
| **Affected components** | net_financial_claims, integration_and_leverage_reserve |
| **Valuation consequence** | Bear reserve −$35/sh; low case component sum **~$25/sh** |
| **Falsifier** | Interest coverage falls below 2× for four consecutive quarters with flat commission revenue |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| brokerage_and_risk_management_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 157.25 | valid |
| assured_partners_integration_option | risk_adjusted_milestone_value@1.0 | 10.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −47.48 | valid |
| integration_and_leverage_reserve | net_asset_value@1.0 | −18.00 | valid |
| **Sum** | | **101.77** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Brokerage $8.02B and risk management $4.20B revenue in 10-K; consolidated FCF engine used |
| AssuredPartners synergy probability | partially_met | $3.56B annualized revenue disclosed; milestone band is judgment |
| Maintenance capex estimate | partially_met | $180M estimated from PP&E depreciation $206M; no separate capex line in XBRL |
