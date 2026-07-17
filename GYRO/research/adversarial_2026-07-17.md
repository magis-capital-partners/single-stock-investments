---
filing: pass
consistency: pass
disclosure: pass
short: no_public_short_found
third_party: n/a
valuation_staleness: pass
ai_coverage: n/a
option_coverage: complete
block_final: false
blocking_issues: []
re_pass: false
---

# GYRO — Adversarial review

**Date:** 2026-07-17
**Agent:** Milly
**Dive reviewed:** `GYRO/research/deep_dive_2026-07-17.md`
**Valuation reviewed:** `GYRO/research/valuation.json`
**Filings used:** `GYRO/research/evidence/filing_digest_2026-07-17.md`, `GYRO/research/evidence/filing_facts_2026-07-17.json`, full-tier text extracts of the 10-K FY2025 (`10-K_20260327_rpt20251231_acc0001437749_26_010078.htm`), 10-Q Q1 2026 (`10-Q_20260513_rpt20260331_acc0001437749_26_016537.htm`), and DEF 14A (`DEF 14A_20251017_rpt20251105_acc0001437749_25_031274.htm`)

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | Every dollar figure and per-share figure in the dive traces to the 10-K FY2025 or 10-Q Q1 2026 |
| Internal consistency | pass | Base return (33.4%) matches across executive summary, IRR arithmetic, returns statement, classification, and `valuation.json` |
| Disclosure scan | pass | No restatement, no auditor change, no late-filing notice found in the reviewed filings; recent 8-Ks are debt modifications, entitlement updates, and the Star Equity settlement, all reflected in the dive |
| Short activist scan | no_public_short_found | No public short-seller report located; two governance activists (Star Equity Fund, Leap Tide Capital) have run board-related campaigns, both settled, and both are already discussed in the dive |
| Third-party (approved) | n/a | No approved or pending third-party sources indexed for GYRO yet |

**Overall:** The dive's numbers tie out to the filings, and the bull case for the stock (a large, disclosed discount to the company's own liquidation-basis NAV estimate) survives scrutiny. The main open items are legal and timing (the Article 78 appeal outcome and the B2K site-plan decision), which the dive already flags as [HUMAN REVIEW] rather than resolving with false precision.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing / filing_facts | Match? | Severity |
|---|---------------|------------|------------------------|--------|----------|
| 1 | Price $5.80 (2026-07-16) | Yahoo Finance | Not in SEC filings (market data, correctly sourced outside filings) | Match | n/a |
| 2 | Shares outstanding 2,199,308 | 10-Q Q1 2026 cover page | 10-Q Q1 2026 cover page states "On May 13, 2026, there were 2,199,308 common shares outstanding" | Match | - |
| 3 | Net assets in liquidation $25,924,002 total / $11.79 per share (3/31/2026) | 10-Q Q1 2026 | 10-Q Q1 2026 Note 4 / MD&A: "The net assets in liquidation as of March 31, 2026 ($25,924,002)... results in estimated distributions of approximately $11.79... per common share" | Match | - |
| 4 | Prior period $25,858,997 / $11.76 (12/31/2025) and $30,596,313 / $13.91 (12/31/2024) | 10-K FY2025 | 10-K FY2025: "$25,858,997... and December 31, 2024 ($30,596,313)... $11.76 and $13.91 per common share" | Match | - |
| 5 | Real estate held for sale $53,990,000 | 10-Q Q1 2026 balance sheet | Confirmed flat between 3/31/2026 and 12/31/2025 columns | Match | - |
| 6 | Loans payable $10,790,194 | 10-Q Q1 2026 balance sheet | Confirmed | Match | - |
| 7 | Estimated liquidation and operating costs net of estimated receipts $16,709,887 | 10-Q Q1 2026 Note 5 | Confirmed | Match | - |
| 8 | B2K Agreement, ~49 acres, $24.0M-$28.74M range, signed 2025-07-30 | 10-K FY2025 Item 1 / Item 7 | Confirmed verbatim in both Item 1 and Item 7 of the 10-K | Match | - |
| 9 | Article 78 Proceeding pending as of the reviewed filings | 10-K FY2025 Item 3 | Confirmed: appeal briefing completed July 2025, decision not yet reported in the 10-Q filed 2026-05-13 | Match | - |
| 10 | Star Equity Fund LP standstill through 2026/2027 | 10-K FY2025 | Confirmed: Star Agreement dated 2025-10-16, termination date December 31, 2026 or 2027 if conditions met | Match | - |
| 11 | Base / bear / bull annualized return (33.4% / 13.5% / 41.0%) in exec summary, IRR arithmetic, returns statement, and Classification | `valuation.json` `results` block | `marvin_valuation.py --write` output: bear 13.5, base 33.4, bull 41.0 | Match | - |
| 12 | Stance: dive recommends "hold"; mechanical tool proposes "accumulate" | `valuation.json` `stance_proposal.suggested: accumulate`; dive Classification lists "hold" | Both are disclosed and reconciled with a stated reason (thin volume, unresolved litigation) rather than silently overridden | Match | - |
| 13 | Option scan present (7 rows) covering GAAP-vs-fair-value, undeveloped/contingent parcel, and dated-payoff questions | Dive Business & moat | `option_treatment.md` mandatory scan; all 7 questions answered with evidence | Match | - |

No factual errors found. `filing_facts_2026-07-17.json` (XBRL auto-parse) only captured total assets, long-term debt, and cash, which is consistent with the dive's fuller manual pull from the full-tier text extract; the two do not conflict (XBRL cash $4,529,597 at 12/31/2025 matches the dive's 12/31/2025 balance-sheet column).

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|----------------|-----|
| Base IRR exec summary | 33.4% | "**33.4%** per year" | Yes |
| Base IRR returns statement | 33.4% | "We expect about **33.4% per year**" | Yes |
| valuation.json base_pct | 33.4 (`implied_return.base_pct`, `optionality_gate.primary_return_pct`) | Matches | Yes |
| Classification Implied 7yr IRR | 33.4% per year (base) | Matches; dive footnotes that the horizon is 2.46 years, not literally 7, to avoid a false precision error | Yes |
| Bear / bull scenarios | 13.5% / 41.0% | Matches in IRR arithmetic and Payoff & return | Yes |
| Optionality gate floor_pass | true | Dive states floor passes on the disclosed liquidation NAV, with a caveat that this is not risk-free | Yes |
| Stance (human-facing) vs stance_proposal (mechanical) | stance_proposal: accumulate; classification_inputs.stance: hold | Dive discloses both and explains the gap under [HUMAN REVIEW] | Yes |

---

## Option coverage

| Check | Status | Note |
|-------|--------|------|
| `#### Option scan` table in Business & moat | Present | 7 rows, all seven mandatory questions answered |
| Each material option has a treatment + rationale | Present | B2K parcel tagged `milestone_nav`; dissolution/distribution tagged `yield_curve`; GAAP-vs-fair-value question correctly answered "No" with the reasoning that liquidation-basis accounting already equals the fair-value estimate |
| GAAP book used as floor when filing assigns no value to core assets | Not applicable | GAAP (liquidation-basis) book is explicitly not treated as an understated floor; the dive is unusually careful to state this is the opposite of the typical `nav_overlay` case |
| Segment sum far below price with options at $0 | Not applicable | The "segment sum" here (the disclosed NAV) is above price, not below it |

**option_coverage: complete**

---

## Disclosure scan

| Event | Date | Source path | In dive? | Action |
|-------|------|--------------|----------|--------|
| Star Equity Fund LP board nomination notice, then settlement | 2025-06-04 notice; 2025-10-16 settlement | 10-K FY2025 Item 3 / Legal | Yes | None needed |
| Loan modification, 2023 Mortgage Loan (LLYR) extended 24 months at 15% | 2026-01-01 effective | 10-Q Q1 2026 Note 8 | Partially (aggregate debt total cited; individual facility terms in [HUMAN REVIEW] for reconciliation) | Marvin should reconcile the three named facilities to the $10,790,194 balance-sheet total in a future refresh |
| B2K Agreement (as amended) | 2025-07-30, amended since | 10-K FY2025, 10-Q Q1 2026 | Yes | None needed |
| No restatement / Item 4.02 disclosure found | n/a | 10-K FY2025 cover page checkbox ("No" on error-correction/restatement question) | Yes (absence noted) | None needed |
| No auditor change disclosed in reviewed filings | n/a | 10-K FY2025 | Yes (absence noted) | None needed |

---

## Short activist scan

**Registry:** `_system/frameworks/short_activist_registry.md`

| Firm | Report? | Date | Path/URL | Verdict |
|------|---------|------|----------|---------|
| (general web search) | No public short-seller report found | 2026-07-17 (search date) | n/a | no_public_short_found |
| Star Equity Fund, LP | Governance activist, not a short seller | 2025-06-04 notice; settled 2025-10-16 | 10-K FY2025 Item 3; `starequityfund.com` press release | refuted_by_filing (fully addressed in dive as a settled governance campaign, not a solvency or fraud claim) |
| Leap Tide Capital Management LLC | Governance activist, not a short seller | 2023 cooperation agreement | 10-K FY2025; DEF 14A | refuted_by_filing (already resolved, board seat granted, no longer a live claim) |

### Material claims (if any)

No falsifiable short-seller claims were found to test. Both named activists pursued board composition and compensation, not a bear thesis on asset value or going-concern risk. **no_public_short_found is not a clean bill of health**: a name this small and thinly traded could still attract an undisclosed short position without a public report, and the dive's own [HUMAN REVIEW] section already flags the two live uncertainties (Article 78 appeal outcome, B2K site-plan status) that a bear case would most likely target.

---

## Third-party reconciliation (approved only)

Not applicable. No approved or pending third-party sources are indexed for GYRO (`GYRO/third-party-analyses/source_inventory_2026-07-17.md`).

---

## Recommended actions

1. [Human] Confirm current status of the Article 78 appeal and the B2K site-plan submission before increasing position size beyond the recommended "hold."
2. [Marvin, next refresh] Reconcile the three named debt facilities (original bank line, 2021 Mortgage Loan / Rialto Capital, 2023 Mortgage Loan / LLYR) to the $10,790,194 balance-sheet total; the pieces identified in this pass do not fully add up in the available text extract.
3. [Marvin, next refresh] If a new 10-Q or 8-K discloses the Article 78 outcome or B2K closing, refresh `valuation.json` scenarios and re-run `marvin_valuation.py --write` before the next dive.

---

## Resolved in dive

n/a (first pass on this ticker).

---

## [HUMAN REVIEW]

- Human sign-off requested on stance: mechanical tool proposes "accumulate," Marvin recommends "hold." Both are disclosed in the dive and in `valuation.json` → `human_review`.
- No public short report found, but small illiquid names can carry undisclosed short interest; monitor if the Article 78 appeal is decided adversely.
