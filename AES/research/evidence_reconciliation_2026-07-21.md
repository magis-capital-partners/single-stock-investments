# AES — Evidence reconciliation (2026-07-21)

**Ticker:** AES · **As-of:** 2026-07-21 · **Run:** universal valuation contract upgrade

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components + one embedded recourse-debt reference in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 segment Adjusted EBITDA **$2,890M** anchors platform owner cash |
| Downside capital claims | **met** — parent recourse debt **$6.0B** less cash **$1,382M** embedded in platform multiple |
| Double-counting | **met** — non-overlapping overlap keys; merger catalyst paired to platform + backlog |

**Contract status after agent pass:** pending mechanical refresh (`marvin_cloud_refresh.py` 2026-07-21).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: contracted platform owner cash, renewables backlog option, merger-close catalyst, regulatory execution reserve; embedded net recourse claims |
| **Source** | `AES/investor-documents/sec-edgar/10-K_20260302_rpt20251231_acc0000874761_26_000063.htm` segment note; `8-K_20260302` merger agreement |
| **Calculation** | Base component sum **$14.73/sh** = $11.31 + $1.00 + $2.69 − $0.27 |
| **Remaining uncertainty** | Deal-break standalone repricing uses JPM fairness floor context; regulatory timeline remains judgment |
| **Affected components** | All four additive |
| **Valuation consequence** | Lawrence yield_curve base **7.1%** unchanged; component fair value ties to price **$14.73** |
| **Falsifier** | Merger terminated without superior bid and standalone Adjusted EBITDA falls below **$2.4B** run-rate |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 segment Adjusted EBITDA **$2,890M**; OCF **$4,306M**; capex **$5,929M** |
| **Source** | FY2025 10-K cash-flow statement and segment Adjusted EBITDA table |
| **Calculation** | $2,890M ÷ 713M shares = **$4.05/sh** owner-cash proxy × ~2.79× capitalization = **$11.31/sh** platform base |
| **Remaining uncertainty** | Growth capex keeps reported FCF negative; merger event supersedes standalone path for stance gate |
| **Affected components** | contracted_platform_owner_cash |
| **Valuation consequence** | Standalone floor aligns with JPM fairness low **$11.31/sh** (context tier) |
| **Falsifier** | Segment Adjusted EBITDA falls below **$2.5B** for two consecutive quarters while merger is pending |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Parent recourse debt **$6.0B**; cash **$1,382M**; net recourse **~$4.6B** (**~$6.48/sh**) |
| **Source** | 10-K Note 12 — Recourse Debt |
| **Calculation** | Recourse burden embedded in platform capitalization multiple, not additive with merger catalyst |
| **Remaining uncertainty** | Project-level non-recourse debt (~$23B+ maturity schedule) stays with operating assets; buyer assumes capital structure |
| **Affected components** | net_recourse_financial_claims (embedded) |
| **Valuation consequence** | Break scenario repricing toward **$11/sh** range per fairness materials, not zero |
| **Falsifier** | Parent recourse debt rises above **$7B** without commensurate Adjusted EBITDA growth |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| contracted_platform_owner_cash | owner_cash_or_dividend_discount@1.0 | 11.31 | valid |
| renewables_backlog_option | risk_adjusted_milestone_value@1.0 | 1.00 | valid |
| merger_close_catalyst | probability_weighted_catalyst_nav@1.0 | 2.69 | valid |
| regulatory_and_execution_reserve | net_asset_value@1.0 | −0.27 | valid |
| **Sum** | | **14.73** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Segment Adjusted EBITDA disclosed; consolidated OCF used for context |
| Deal-break probability tree | partially_met | Merger catalyst uses judgment uplift; full probability tree in scenarios only |
| Live price confirmation | open | `human_review.live_price_confirmed` false; refresh updates market inputs |
