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

# UROY — Adversarial review

**Date:** 2026-10-27
**Agent:** Milly
**Dive reviewed:** `UROY/research/deep_dive_2026-10-27.md`
**Valuation reviewed:** `UROY/research/valuation.json`
**Evidence:** `UROY/research/evidence/primary_financials_2026-10-27.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

## Summary verdict

| Area | Status | One line |
| --- | --- | --- |
| Filing reconciliation | pass | Royalty versus inventory, the bridge, the notes, and the going-concern sentence match the 10-Q |
| Internal consistency | pass | No base percent. The retired scenario is not restored |
| Disclosure scan | pass | CIK 0002143673 is the filer. The old Canadian CIK is not |
| Short activist scan | no_hit | No local short report reviewed |
| Third-party | n/a | Not used to fill the empty return |

**Overall:** No blocking factual error. Fiscal 2026 operating cash is inventory liquidation and is not owner earnings.

## Filing reconciliation

| Claim in dive | Filing or file value | Match? | Severity |
| --- | --- | --- | --- |
| Royalty revenue $682,000, about $0.6 million Sweetwater for four days | Form 10-Q accession 0001193125-26-390681 | yes | none |
| Inventory sales $50.967 million | Same 10-Q | yes, excluded from owner cash | none |
| Bridge $40.0 million due 31 January 2027, all-in 7.80% | Same 10-Q note on the facility | yes | none |
| Notes fair value $552.758 million | Same 10-Q note 10. Current $17.097 million and noncurrent $535.661 million | yes | none |
| Operating cash $178.456 million for the year ended 30 April 2026 | Form 10-K accession 0001193125-26-321135 | yes, and not used | none |
| Shares issued 223,252,749 | Same 10-Q | yes | none |
| Substantial doubt not alleviated | Same 10-Q | yes | none |
| Base return | implied_return.base_pct null | dive says not computed | none |

## Internal consistency

The segment map names claims and does not add them to a payoff. The S-1 filed 1 October 2026 is a stated gap. Restricted cash is not called free cash.

## [HUMAN REVIEW]

Read the S-1 and confirm the Delaware ISIN before a per-share model is built. Do not put the retired scenario percent back into the base case.
