# ACN — Evidence reconciliation (2026-07-21)

**Ticker:** ACN · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $11.47B less capex $0.60B anchors FCF/sh $17.19 |
| Downside capital claims | **met** — IT-cycle/AI disruption reserve; long-term debt $5.03B in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; managed-services backlog not double-counted |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py`).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: services owner-cash engine, Gen AI reinvention option, net financial claims, IT-cycle/AI disruption reserve |
| **Source** | `ACN/investor-documents/sec-edgar/10-K_20251010_rpt20250831_acc0001467373_25_000217.htm` Item 7; segment mix consulting vs managed services |
| **Calculation** | FY2025 revenue $69.7B; consulting ~50% / managed services ~50%; OCF $11.47B less capex $0.60B = FCF $10.87B |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; consolidated FCF engine with option overlay for Gen AI upside |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$302/sh** vs price **~$139** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$11,470M**; capital spending **$600M**; diluted shares **~632M** |
| **Source** | FY2025 10-K cash-flow statement and diluted EPS $12.15 |
| **Calculation** | ($11,470M − $600M) ÷ 632M = **$17.19/sh** normalized owner cash |
| **Remaining uncertainty** | Business optimization ($615M FY2025) already in OCF; peak-cycle vs normalized FCF is judgment |
| **Affected components** | services_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $17.19/sh starting owner cash |
| **Falsifier** | OCF falls below $9B for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$11,479M**; long-term debt and capital leases **$5,034M**; net cash **~$6,445M** (~$10.20/sh) |
| **Source** | FY2025 10-K balance sheet |
| **Calculation** | it_cycle_and_ai_disruption_reserve base **−$15/sh**; net_financial_claims base **+$10.20/sh** filing-locked |
| **Remaining uncertainty** | AI labor substitution could compress margins faster than low growth scenario |
| **Affected components** | net_financial_claims, it_cycle_and_ai_disruption_reserve |
| **Valuation consequence** | Bear reserve −$35/sh; low case component sum **~$194/sh** |
| **Falsifier** | Adjusted operating margin falls below 12% for four consecutive quarters with flat bookings |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| services_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 294.80 | valid |
| gen_ai_reinvention_option | risk_adjusted_milestone_value@1.0 | 12.00 | valid |
| net_financial_claims | net_asset_value@1.0 | 10.20 | valid |
| it_cycle_and_ai_disruption_reserve | net_asset_value@1.0 | −15.00 | valid |
| **Sum** | | **302.00** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Consulting vs managed services growth rates in 10-K; consolidated FCF engine used |
| Gen AI reinvention probability | partially_met | $3B investment disclosed; milestone band is judgment |
| Q2 FY2026 full-tier evidence sync | partially_met | Mechanical refresh will rebuild filing digest for 2026-07-21 |
