---
filing: pass
consistency: partial
disclosure: pass
short: no_hit
third_party: n/a
valuation_staleness: warn
ai_coverage: n/a
option_coverage: partial
growth_explanation: n/a
block_final: false
blocking_issues: []
re_pass: false
---

# FICO: Adversarial review

**Date:** 2026-09-29
**Agent:** Milly
**Dive reviewed:** `FICO/research/deep_dive_2026-09-29.md`
**Valuation reviewed:** `FICO/research/valuation.json` (price still the July 20, 2026 close)
**Filings used:** annual report filed November 7, 2025 (year ended September 30, 2025); quarterly report filed July 29, 2026 (quarter ended June 30, 2026); 8-K filed June 8, 2026 (June 5 term loan and accelerated share repurchase)

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | Dollar figures in the dive match the annual and quarterly reports |
| Internal consistency | partial | The 9% path is in the dive only. `valuation.json` still prices July 20 |
| Disclosure scan | pass | No late filing or restatement in the local set. Newest 8-K is July 29, 2026 |
| Short activist scan | no_hit | No Hindenburg or Muddy Waters report. Steve Eisman's public short is the same mechanism the dive uses |
| Third-party (approved) | n/a | The July 10 cross-check predates this event and is not in the base return |

**Overall:** The selloff note does not invent a mortgage profit share, and the cash-flow starting point is the annual report's $778.8 million. The open gap is that the valuation file was not recompiled to the new price.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing | Match? | Severity |
|---|---------------|------------|--------|--------|----------|
| 1 | Close $617.87 on September 29, 2026 | News print | Not a filing | News, labeled | none |
| 2 | 21,597,635 shares on July 17, 2026 | Quarterly report cover | Cover page | yes | none |
| 3 | Quarter revenue $674 million vs $536 million; Scores $459 million vs $324 million | Quarterly report | Income statement columns | yes | none |
| 4 | Nine-month operating income $999 million | Quarterly report | Operating income line | yes | none |
| 5 | Cash $248 million; long-term debt $5.28 billion | June 30 balance sheet | $248.444 million cash; $5,282.389 million long-term debt | yes | none |
| 6 | Starting cash from operations $778.8 million | Annual report narrative | "Net cash provided by operating activities totaled $778.8 million in fiscal 2025" | yes | none |
| 7 | Business-to-business increase "primarily" mortgage unit price | Quarterly report | Same sentence | yes | none |
| 8 | Bureaus 63% of the June quarter | Quarterly report | 63% and 54% | yes | none |
| 9 | June 5, 2026 $1.5 billion term loan for an accelerated share repurchase | Quarterly report and June 8 8-K | Both say the full incremental term loan was borrowed June 5 and used for the repurchase | yes | none |
| 10 | Stance watch | Thesis and holdings | Not taken from `human_decision.json` | disclosed as not a capital decision | none |

Companyfacts locks operating cash flow at $769.885 million for the same annual accession. The dive uses the annual report sentence of $778.8 million. The gap is about $9 million, under 2%. It is not hidden. The sentence in the report is the one a reader can check.

Net income is not used in the return. The quarterly report's net income line was not needed for the claim set above.

---

## Internal consistency

| Check | Expected | Found in dive | OK? |
|-------|----------|---------------|-----|
| Base return in the executive summary | 9% | 9% | yes |
| Returns statement | 9% | 9% | yes |
| `valuation.json` price | July 20 close $1,263.83 | Dive says that file is stale | disclosed |
| `valuation.json` base percent | Not set | Dive does not pretend the file has 9% | yes |
| Classification | watch, operating | watch, operating | yes |

`valuation_staleness: warn` because starting cash flow is fiscal 2025, while the June quarter already shows a much larger Scores line. Using the older year is conservative. It is also stale relative to nine months of fiscal 2026.

---

## AI & valuation staleness

Not an AI infrastructure name. No overlay.

| Check | Status | Note |
|-------|--------|------|
| AI section | n/a | |
| Cash flow period vs latest filing | warn | Fiscal 2025 cash from operations, not the nine months ended June 30, 2026 |

---

## Option coverage

The scan is in the dive. Mortgage exclusivity is marked contested and is not given a dollar value. That is an explicit omission, not a silent zero. Software stays inside reported cash flow. `option_coverage: partial` because the filing still does not isolate mortgage score profit, so the contested option cannot be sized.

---

## Short activist scan

No report from the Tier 1 list in `short_reports/`. Web search on September 29, 2026 did not surface a Hindenburg or Muddy Waters note on Fair Isaac.

Steve Eisman has said publicly that he is short the stock because mortgage score prices rose for years and the mortgage giants now accept VantageScore. The dive's primary risk is that claim. His dollar-per-score comparison is not in the filings, and the dive does not use it in the 9% path.

---

## Disclosure scan

Local 8-Ks run through July 29, 2026 (earnings). The June 8, 2026 8-K is the term loan and repurchase. No late-filing notice and no non-reliance item in that set. The September 29 policy news is not a company filing, and no later 8-K is in the folder.

---

## Third-party reconciliation

`cross_check_third_party_2026-07-10.md` is not an input to the 9% path. HousingWire and the closing print are labeled as news.

---

## What would change the verdict

A filing that splits mortgage origination scores out of business-to-business scores. Until then, any percent of profit "lost" on September 29 is a guess.
