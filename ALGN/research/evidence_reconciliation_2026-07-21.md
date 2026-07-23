# ALGN — Evidence reconciliation (2026-07-21)

**Ticker:** ALGN · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $785.8M less capex $177.7M anchors FCF/sh $7.94 |
| Downside capital claims | **met** — competition/ASP reserve; net cash ~$13.6/sh gross in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; deferred revenue embedded in Clear Aligner engine |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: Clear Aligner owner-cash engine, scanner platform option, net financial claims, competition/ASP reserve |
| **Source** | `ALGN/investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001097149_26_000014.htm` Item 7; Clear Aligner and Systems segment note |
| **Calculation** | FY2025 consolidated revenue $3,862.3M; Clear Aligner $3,245.4M (~84%); Systems & Services $789.6M; OCF $785.8M less capex $177.7M = FCF $608.1M |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; consolidated FCF engine with scanner option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$175/sh** vs price **~$175** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$785.8M**; capital spending **$177.7M**; diluted shares **76.568M** |
| **Source** | FY2025 10-K cash-flow statement and diluted EPS $5.81 |
| **Calculation** | ($785.8M − $177.7M) ÷ 76.568M = **$7.94/sh** normalized owner cash |
| **Remaining uncertainty** | FY2025 revenue down from prior peak; teen-case volume recovery pace is judgment |
| **Affected components** | clear_aligner_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $7.94/sh starting owner cash |
| **Falsifier** | OCF falls below $600M for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$1,043.9M**; no long-term debt; $300M revolving credit facility undrawn; net cash **~$13.6/sh** gross |
| **Source** | FY2025 10-K balance sheet and debt footnote |
| **Calculation** | competition_and_asp_reserve base **−$6/sh**; net_financial_claims base **~$11/sh** after $200M operating minimum |
| **Remaining uncertainty** | Antitrust and Angelalign litigation outcomes; ASP compression faster than low growth scenario |
| **Affected components** | net_financial_claims, competition_and_asp_reserve |
| **Valuation consequence** | Bear reserve −$20/sh; low case component sum **~$98/sh** |
| **Falsifier** | Clear Aligner gross margin falls below 65% for four consecutive quarters with flat case volume |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| clear_aligner_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 160.00 | valid |
| scanner_platform_option | risk_adjusted_milestone_value@1.0 | 10.00 | valid |
| net_financial_claims | net_asset_value@1.0 | 11.02 | valid |
| competition_and_asp_reserve | net_asset_value@1.0 | −6.00 | valid |
| **Sum** | | **175.02** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Clear Aligner vs Systems revenue in 10-K; consolidated FCF engine used |
| Scanner platform probability | partially_met | Systems revenue $789.6M disclosed; milestone band is judgment |
| Q1 FY2026 full-tier evidence sync | partially_met | Mechanical refresh will rebuild filing digest for 2026-07-21 |
