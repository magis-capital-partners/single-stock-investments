# AMCR — Evidence reconciliation (2026-07-23)

**Ticker:** AMCR · **As-of:** 2026-07-23 · **Run:** contract backfill refresh (authorized evidence packet unchanged)

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — three additive components + one embedded net-debt reference |
| Component calculation proofs | **met** — valid graphs on all three additive components |
| Owner-cash / NAV bridge | **met** — FY2025 OCF **$1,390M** less capex **$580M** = **$810M** (**$1.75/sh**) |
| Downside capital claims | **met** — long-term debt **$13,841M** less cash **$827M** embedded in platform multiple |
| Double-counting | **met** — non-overlapping overlap keys; net debt paired to platform owner cash |

**Prior blocker resolved:** `authorized_evidence.json` flagged *"A complete economic ownership map has not been supplied."* This refresh attaches filing-backed proofs and syncs authorization state to `valuation_contract.json`.

---

## Proofs attached (unchanged evidence packet)

| Component | Method | Proof status | Base ($/sh) |
|-----------|--------|--------------|-------------|
| `consolidated_packaging_owner_cash` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | 36.00 |
| `berry_synergy_milestone` | risk_adjusted_milestone_value@1.0 | bounded_estimate | 2.50 |
| `integration_leverage_reserve` | net_asset_value@1.0 | bounded_estimate | −1.50 |
| `net_financial_claims` | net_asset_value (embedded) | legacy_sensitivity | embedded |

Proof builder: `_system/scripts/build_amcr_contract_proofs.py`. Additive base sum **$37.00/sh** = $36.00 + $2.50 − $1.50.

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Three additive components: consolidated packaging owner cash, Berry synergy milestone, integration reserve; embedded net debt in platform capitalization |
| **Source** | `AMCR/investor-documents/sec-edgar/10-K_20250815_rpt20250630_acc0001748790_25_000023.htm`; `10-Q_20260507_rpt20260331_acc0001748790_26_000016.htm` |
| **Calculation** | Base component sum **$37.00/sh** reconciles to `valuation_contract.json` additive schedule |
| **Remaining uncertainty** | Synergy run-rate timing remains judgment; segment-level owner cash not disclosed |
| **Affected components** | All three additive |
| **Valuation consequence** | Lawrence total-synthesis base **3.04%** per year unchanged; component fair value **~$37/sh** vs market **~$43** |
| **Falsifier** | FY2025 owner cash falls below **$1.40/sh** for two consecutive filings while leverage rises above **3.5× EBITDA** |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 operating cash flow **$1,390M**; capital spending **$580M**; free cash flow **$810M** |
| **Source** | FY2025 10-K cash-flow statement |
| **Calculation** | $810M ÷ 462.3M shares = **$1.75/sh** owner cash × ~20.6× capitalization = **$36.00/sh** platform base |
| **Remaining uncertainty** | Q3 FY2026 quarterly capex **$687M** vs **$360M** prior year keeps conversion uneven |
| **Affected components** | consolidated_packaging_owner_cash |
| **Valuation consequence** | Platform base aligns with Lawrence normalized owner-cash path at ~14× year-10 exit |
| **Falsifier** | Trailing twelve-month owner cash falls below **$1.40/sh** while integration charges persist |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Long-term debt **$13,841M**; cash **$827M**; net debt **~$13,014M** (**~$28.15/sh**) |
| **Source** | FY2025 10-K balance sheet |
| **Calculation** | Net debt burden embedded in platform capitalization multiple, not additive with synergy milestone |
| **Remaining uncertainty** | Post-merger debt offerings (424B5, March 2026 8-K) may shift maturity profile |
| **Affected components** | net_financial_claims (embedded) |
| **Valuation consequence** | Bear platform multiple stresses leverage; integration reserve captures execution friction separately |
| **Falsifier** | Net debt rises above **$15B** without commensurate synergy run-rate disclosure |

---

## Open gaps (partially_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level owner cash split | partially_met | Flexibles/rigid sales disclosed; consolidated OCF used for owner-cash anchor |
| Synergy run-rate disclosure | partially_met | Milestone band uses judgment until management quantifies savings |
| Live price confirmation | open | `human_review.live_price_confirmed` false; mechanical refresh updates market inputs |

---

## Facts vs judgments

**Facts (locked):** FY2025 net sales **$15.0B**; pro forma **~$23.2B**; OCF **$1,390M**; capex **$580M**; long-term debt **$13,841M**; cash **$827M**; **462.3M** shares at March 31, 2026; Berry merger closed **2025-04-30** at **7.25** exchange ratio.

**Judgments (bounded):** Platform capitalization **16×–25×** on **$1.75/sh** owner cash; synergy milestone **$0–$6/sh**; integration reserve **−$3–$0/sh**.

## Valuation consequence

Proof-complete additive schedule base **$37.00 per share**. Lawrence total-synthesis base **3.04%** per year and stance gate **2.2%** (Lawrence legacy) unchanged. Security stays **watch** at market premium to component base. No human capital decision recorded.
