# ADSK — Evidence reconciliation (2026-07-21)

**Ticker:** ADSK · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2026 OCF $2.45B less capex $43M anchors FCF/sh $11.20 |
| Downside capital claims | **met** — transition/competition reserve; Q1 FY2027 debt $2.48B in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; RPO backlog not double-counted in core engine |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: subscription owner-cash engine, construction cloud/AI option, net financial claims, subscription transition/competition reserve |
| **Source** | `ADSK/investor-documents/sec-edgar/10-K_20260303_rpt20260131_acc0000769397_26_000015.htm` Item 7; subscription revenue mix |
| **Calculation** | FY2026 revenue $6.74B (+18% YoY vs $5.72B); OCF $2.45B less capex $43M = FCF $2.41B |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; consolidated subscription engine with cloud/AI option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$254/sh** vs price **~$218** |
| **Falsifier** | 10-K restates subscription economics or shows material revenue recognition change breaking FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2026 operating cash flow **$2,452M**; capital spending **$43M**; diluted shares **215M** |
| **Source** | FY2026 10-K cash-flow statement and diluted EPS $5.23 |
| **Calculation** | ($2,452M − $43M) ÷ 215M = **$11.20/sh** normalized owner cash |
| **Remaining uncertainty** | Stock-based compensation ($788M FY2026) affects working capital; peak-cycle vs normalized FCF is judgment |
| **Affected components** | subscription_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $11.20/sh starting owner cash |
| **Falsifier** | OCF falls below $1.8B for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Q1 FY2027 cash **$2,671M**; long-term debt **$2,484M**; net cash **~$187M** (~$0.87/sh) |
| **Source** | `ADSK/investor-documents/sec-edgar/10-Q_20260529_rpt20260430_acc0000769397_26_000044.htm` balance sheet |
| **Calculation** | subscription_transition_and_competition_reserve base **−$12/sh**; net_financial_claims base **+$0.87/sh** filing-locked |
| **Remaining uncertainty** | SBC dilution ($788M FY2026) could compress per-share FCF faster than low growth scenario |
| **Affected components** | net_financial_claims, subscription_transition_and_competition_reserve |
| **Valuation consequence** | Bear reserve −$30/sh; low case component sum **~$130/sh** |
| **Falsifier** | Non-GAAP operating margin falls below 30% for four consecutive quarters with flat billings |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| subscription_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 255.00 | valid |
| construction_cloud_and_ai_option | risk_adjusted_milestone_value@1.0 | 10.00 | valid |
| net_financial_claims | net_asset_value@1.0 | 0.87 | valid |
| subscription_transition_and_competition_reserve | net_asset_value@1.0 | −12.00 | valid |
| **Sum** | | **253.87** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | AEC/MFG/AutoCAD growth rates in 10-K narrative; consolidated FCF engine used |
| Construction cloud/AI probability | partially_met | RPO $8.3B disclosed; milestone band is judgment |
| Starboard activist campaign | partially_met | DFAN14A Mar 2025 filed; governance context only, not in base IRR |
| Full-tier evidence sync | partially_met | Mechanical refresh will rebuild filing digest for 2026-07-21 |
