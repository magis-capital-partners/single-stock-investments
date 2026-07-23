# AES — Evidence reconciliation (2026-07-23)

**Ticker:** AES · **As-of:** 2026-07-23 · **Run:** contract backfill refresh (authorized evidence packet unchanged)

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components + one embedded recourse-debt reference |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 segment Adjusted EBITDA **$2,890M** anchors platform owner cash |
| Downside capital claims | **met** — parent recourse debt **$6.0B** less cash **$1,382M** embedded in platform multiple |
| Double-counting | **met** — non-overlapping overlap keys; merger catalyst paired to platform + backlog |

**Prior blocker resolved:** `authorized_evidence.json` previously flagged *"A complete economic ownership map has not been supplied."* The map and proofs were built on **2026-07-21**; this refresh syncs authorization state to `valuation_contract.json` without changing proof outputs.

---

## Proofs attached (unchanged evidence packet)

| Component | Method | Proof status | Base ($/sh) |
|-----------|--------|--------------|-------------|
| `contracted_platform_owner_cash` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | 11.31 |
| `renewables_backlog_option` | risk_adjusted_milestone_value@1.0 | bounded_estimate | 1.00 |
| `merger_close_catalyst` | probability_weighted_catalyst_nav@1.0 | bounded_estimate | 2.69 |
| `regulatory_and_execution_reserve` | net_asset_value@1.0 | bounded_estimate | −0.27 |
| `net_recourse_financial_claims` | net_asset_value (embedded) | legacy_sensitivity | embedded |

Additive base sum **$14.73/sh** = $11.31 + $1.00 + $2.69 − $0.27.

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: contracted platform owner cash, renewables backlog option, merger-close catalyst, regulatory execution reserve; embedded net recourse claims in platform capitalization |
| **Source** | `AES/investor-documents/sec-edgar/10-K_20260302_rpt20251231_acc0000874761_26_000063.htm` segment note; `8-K_20260302` merger agreement |
| **Calculation** | Base component sum **$14.73/sh** reconciles to `valuation_contract.json` additive schedule |
| **Remaining uncertainty** | Deal-break standalone repricing uses JPM fairness floor context; regulatory timeline remains judgment |
| **Affected components** | All four additive |
| **Valuation consequence** | Lawrence yield_curve base **2.5%** per year (merger path) unchanged; component fair value ties to price **~$14.82** |
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
| **Remaining uncertainty** | Project-level non-recourse debt stays with operating assets; buyer assumes capital structure |
| **Affected components** | net_recourse_financial_claims (embedded) |
| **Valuation consequence** | Break scenario repricing toward **$11/sh** range per fairness materials, not zero |
| **Falsifier** | Parent recourse debt rises above **$7B** without commensurate Adjusted EBITDA growth |

---

## Open gaps (partially_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Segment Adjusted EBITDA disclosed; consolidated OCF used for context |
| Deal-break probability tree | partially_met | Merger catalyst uses judgment uplift; full probability tree in scenarios only |
| Live price confirmation | open | `human_review.live_price_confirmed` false; mechanical refresh updates market inputs |

---

## Facts vs judgments

**Facts (locked):** FY2025 segment Adjusted EBITDA **$2,890M**; OCF **$4,306M**; capex **$5,929M**; recourse debt **$6.0B**; cash **$1,382M**; **713M** diluted shares; merger consideration **$15.00/sh**; **12.0 GW** contracted backlog.

**Judgments (bounded):** Platform capitalization multiple **2.47×–3.21×** on Adjusted EBITDA per share; backlog option **$0.50–$2.50/sh**; merger catalyst uplift **$1.50–$4.00/sh** above platform + backlog; regulatory reserve **−$1.00–$0/sh**.

## Valuation consequence

Proof-complete additive schedule base **$14.73 per share** matches prior refresh. Lawrence merger-arbitrage base **2.5%** per year over ~0.75 years remains the stance gate. Security stays **watch** pending human merger-arb sizing decision. No human capital decision recorded.
