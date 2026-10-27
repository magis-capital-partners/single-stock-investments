---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
option_coverage: partial
---

# ECOR.L — Adversarial review

**Date:** 2026-10-27
**Agent:** Milly
**Dive reviewed:** `ECOR.L/research/deep_dive_2026-10-27.md`
**Valuation reviewed:** `ECOR.L/research/valuation.json`
**Evidence:** `ECOR.L/research/evidence/primary_financials_2026-10-27.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

## Summary verdict

| Area | Status | One line |
| --- | --- | --- |
| Filing reconciliation | pass | 2025 royalty revenue, company free cash flow, and Kestrel volumes match the results release |
| Internal consistency | pass | Headline is 2.01, not the 0.6 owner-cash path |
| Disclosure scan | pass | This is not the Nasdaq electroCore ticker |
| Short activist scan | no_hit | No local short report reviewed |
| Third-party | n/a | Not in the weights |

**Overall:** No blocking factual error. The London line is identified, and the ending share count is left missing.

## Filing reconciliation

| Claim in dive | Filing or file value | Match? | Severity |
| --- | --- | --- | --- |
| Royalty and stream revenue $55.9 million | FY2025 results release | yes | none |
| Company free cash flow $27.4 million | Same release, after finance costs | yes | none |
| Weighted average shares 248.944 million | Same release | yes | none |
| Kestrel contribution guided to end in 2030 | Same release | yes | none |
| Base case 2.01% per year | valuation.json implied_return.base_pct | yes | none |
| Price in dollars from pence times the pound | 151.2 pence and the 27 October pound print | yes, stored as 2.015 | none |

## Internal consistency

Net debt is described and not deducted a second time from cash flow that is already after interest. The ending share count is an explicit gap. The SEC electroCore name is rejected.

## [HUMAN REVIEW]

ISIN is still open. Do not swap in the OTC line as the model price.
