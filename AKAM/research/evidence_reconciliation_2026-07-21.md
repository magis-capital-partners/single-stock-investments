# AKAM — Evidence reconciliation (2026-07-21)

**Ticker:** AKAM · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF $1,519M less capex $508M anchors FCF/sh $6.88 |
| Downside capital claims | **met** — cloud competition reserve; $4.14B convertible notes in net claims inputs |
| Double-counting | **met** — non-overlapping overlap keys; RPO not double-counted in core engine |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: edge platform owner-cash engine, Compute/GPU option, net financial claims, cloud competition reserve |
| **Source** | `AKAM/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001086222_26_000022.htm` segment note (Compute $2.24B, Security $1.26B, Delivery $708M) |
| **Calculation** | FY2025 revenue $4.21B; OCF $1,519M less capex $508M = FCF $1,011M |
| **Remaining uncertainty** | Segment-level FCF not separately disclosed; consolidated FCF engine with Compute option overlay |
| **Affected components** | All four |
| **Valuation consequence** | Base component sum **~$125/sh** vs price **~$130** |
| **Falsifier** | 10-K restates segment economics or shows material intersegment eliminations breaking consolidated FCF bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$1,519M**; capital spending **$508M**; diluted shares **147.0M** |
| **Source** | FY2025 10-K cash-flow statement and diluted share count |
| **Calculation** | ($1,519M − $508M) ÷ 147.0M = **$6.88/sh** normalized owner cash |
| **Remaining uncertainty** | Q1 2026 operating profit fell 26% YoY; peak-cycle vs normalized FCF is judgment |
| **Affected components** | edge_platform_owner_cash_engine |
| **Valuation consequence** | Lawrence base uses $6.88/sh starting owner cash |
| **Falsifier** | OCF falls below $1.2B for two consecutive fiscal years without one-time explanation |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$930M**; convertible senior notes **$4.14B** principal ($1.15B/2027, $1.27B/2029, $1.73B/2033); net debt **~$3.21B** (~$21.84/sh) |
| **Source** | FY2025 10-K balance sheet and debt footnote |
| **Calculation** | cloud_competition_reserve base **−$8/sh**; net_financial_claims base **−$21.84/sh** filing-locked |
| **Remaining uncertainty** | Convertible note equity conversion could reduce net debt; cloud price war could compress margins faster than low growth scenario |
| **Affected components** | net_financial_claims, cloud_competition_reserve |
| **Valuation consequence** | Bear reserve −$20/sh; low case component sum **~$50/sh** |
| **Falsifier** | Operating margin stays below 10% for four consecutive quarters with Security revenue declining |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| edge_platform_owner_cash_engine | owner_cash_or_dividend_discount@1.0 | 145.00 | valid |
| compute_gpu_platform_option | risk_adjusted_milestone_value@1.0 | 10.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −21.84 | valid |
| cloud_competition_reserve | net_asset_value@1.0 | −8.00 | valid |
| **Sum** | | **125.16** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Compute/Security/Delivery revenue in 10-K; consolidated FCF engine used |
| Q1 2026 margin recovery path | partially_met | Q1 2026 operating income −26% YoY; management guidance not in base proof |
| Third-party approved sources | not_met | No approved Substacks/HK in base IRR; context tier only |
