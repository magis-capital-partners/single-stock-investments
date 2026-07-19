# AMZN — Evidence reconciliation

**Date:** 2026-07-19  
**Agent:** Marvin (cloud evidence refresh)  
**Evidence task queue:** `AMZN/research/evidence_task_queue.json`  
**Contract status:** `valuation_contract.json` → evidence_blocked (provisional ranges only)

## Purpose

Close the three critical universal-contract acceptance tests using primary SEC extracts. Ranges in `valuation.json` remain provisional until human committee review; this pass moves gaps from **not_met** to **partially_met** with filing-grounded bridges.

---

## Gap 1 — Component ownership map

**Acceptance test:** Every material claim identified once, with provisional low/base/high and no double counting.

| Component ID | Economic claim | Overlap key | Treatment | Primary evidence |
|--------------|----------------|-------------|-----------|------------------|
| `primary_operating_segment` | North America retail, fulfillment, and logistics owner cash | `primary_operating_segment` | additive | FY2025 NA segment OI **$29.6B**; Q1 2026 consolidated revenue **$181.5B** with stores unit growth **15%** (`10-K`, Q1 earnings release) |
| `secondary_operating_segments` | AWS, advertising, and international owner cash | `secondary_operating_segments` | additive | FY2025 AWS OI **$45.6B**; Q1 2026 AWS sales **$37.6B** (+28%); ads **>$70B** TTM (earnings release) |
| `strategic_option` | Other Bets (Kuiper, Zoox, healthcare, etc.) | `strategic_option` | additive | 10-K segment note: three reported segments; Other Bets losses embedded in consolidated OI drag **[Assumption]** |
| `net_claims_and_reserve` | Net cash/debt plus AI-capital reserve | `net_claims_and_reserve` | additive | Cash **$86.8B**; stockholders' equity **$411.1B** Mar 2026 (`10-Q` extract); TTM capex **$151.0B** vs normalized **~$90B** reserve |

**Reconciliation:** Four non-overlapping overlap keys match `valuation.json` → `component_valuation`. Advertising is **embedded** in segment growth (not a fifth additive row). AI backlog/RPO is **embedded_in_segment** per option scan.

**Status:** **partially_met** — map is complete; per-component filing tie-out to low/base/high still judgment-heavy.

**Falsifier:** New 10-K/10-Q shows a material segment (e.g., ads broken out) that requires a new overlap key or reallocation of owner cash.

**Monitoring:** Next 10-Q segment note and capex supplemental table.

---

## Gap 2 — Primary owner-cash bridge

**Acceptance test:** Reproduce low/base/high bridge from primary filings with causal case differences.

### Filing facts (TTM through Q1 2026)

| Line | Amount ($B) | Source |
|------|-------------|--------|
| TTM operating cash flow | **148.5** | `NetCashProvidedByUsedInOperatingActivities` **148,531** ($M) · `10-Q` Mar 2026 extract |
| TTM payments to acquire productive assets | **151.0** | `PaymentsToAcquireProductiveAssets` **151,003** ($M) · same extract |
| Implied TTM FCF (OCF − productive-asset capex) | **(2.5)** | Mechanical subtraction |
| Company supplemental FCF (as cited in prior research) | **~1.2** | Q1 2026 earnings supplemental metrics (lease/cash definition differs) |
| FY2025 consolidated operating income | **80.0** | `OperatingIncomeLoss` **79,975** ($M) · `10-K` FY2025 extract |
| FY2025 net income | **77.7** | `NetIncomeLoss` **77,670** ($M) · `10-K` |
| Q1 2026 net income | **30.3** | `NetIncomeLoss` **30,255** ($M) · `10-Q` (includes **~$15.6B** other non-operating income, Anthropic-related) |

### Normalized owner cash (Lawrence base)

| Step | Calculation | Result |
|------|-------------|--------|
| 1 | TTM OCF | **$148.5B** |
| 2 | Less sustainable capex **[Assumption]** | **$90.0B** (mid-cycle vs **$151B** TTM productive-asset spend) |
| 3 | Normalized owner cash | **$58.5B** |
| 4 | Diluted shares **[HUMAN REVIEW]** | **~10.95B** |
| 5 | **Owner cash per share** | **~$5.35/sh** |

**Low/base/high causal drivers:**

- **Low:** Capex stays near **$151B**; AWS growth decelerates; multiple compression.
- **Base:** Capex moderates toward **~$90B** by year 5; AWS/ads/silicon growth **9%** years 1–5.
- **High:** FCF inflection to **~$9/sh** normalized **[Assumption]** if AI workload ROI visible by year 3–4.

**Status:** **partially_met** — OCF and capex are filing-sourced; **$90B** sustainable capex and share count remain **[Assumption]** / **[HUMAN REVIEW]**.

**Falsifier:** Two consecutive quarters with OCF growth below **5%** YoY while capex stays above **$140B**.

---

## Gap 3 — Downside and capital claims

**Acceptance test:** Debt, cash, reserves, dilution, and options reconciled with falsifier.

| Claim | Mar 2026 / latest | Source | Valuation treatment |
|-------|-------------------|--------|---------------------|
| Cash and equivalents | **$86.8B** | `10-Q` / `filing_facts_2026-06-01.json` | Net claims component (positive) |
| Stockholders' equity | **$411.1B** | same | Balance-sheet context; not NAV floor |
| Long-term debt (GAAP tag) | **$0.1B** current LT + lease stack | `10-Q` extract | Amazon funds via operating cash and short-term/commercial paper; full debt note in 10-K **[HUMAN REVIEW]** |
| TTM insider sales (Bezos) | **~$4.3B** net sell score | `valuation.json` insider_signal | Context only; not in base IRR |
| AI capex reserve | **~$61B** gap ($151B − $90B) | TTM capex vs normalized | Reserved in `net_claims_and_reserve` component |
| Anthropic investment mark | **~$15.6B** non-operating Q1 | `OtherNonoperatingIncomeExpense` **15,647** ($M) | Strip from earnings-power analysis |

**Status:** **partially_met** — liquidity and capex reserve identified; full debt/lease maturity schedule and option probability for Other Bets remain open.

**Falsifier:** Net cash position turns negative or equity issuance exceeds **2%** dilution per year without matching owner-cash growth.

---

## Committee conclusion

Evidence packet supports a **provisional** four-component map and a filing-grounded owner-cash bridge. Security remains **evidence_blocked** for decision-grade pricing until human reconciles sustainable capex, share count, and component ranges. Lawrence legacy IRR (**3.2%** total synthesis at **~$255**) stays the stance-context reference; `human_decision.json` holds **hold** override.

## Affected files

- `AMZN/research/valuation.json` (research inputs; component evidence strings)
- `AMZN/research/deep_dive_2026-07-19.md`
- `AMZN/research/valuation_contract.json` (mechanical refresh updates status)
