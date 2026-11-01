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

# NRP — Adversarial review

**Date:** 2026-10-27
**Agent:** Milly
**Dive reviewed:** `NRP/research/deep_dive_2026-10-27.md`
**Valuation reviewed:** `NRP/research/valuation.json`
**Evidence:** `NRP/research/evidence/primary_financials_2026-10-27.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

## Summary verdict

| Area | Status | One line |
| --- | --- | --- |
| Filing reconciliation | pass | Half-year mineral revenue, Sisecam loss, and the $0.75 declarations match the 10-Q |
| Internal consistency | pass | Headline is -9.91. Operating cash is not used as owner cash |
| Disclosure scan | pass | No August distribution is claimed |
| Short activist scan | no_hit | No local short report reviewed |
| Third-party | n/a | Not added |

**Overall:** No blocking factual error. The $3.00 input is the distribution. The segment rows add to that $3.00.

## Filing reconciliation

| Claim in dive | Filing or file value | Match? | Severity |
| --- | --- | --- | --- |
| Fiscal 2025 operating cash $165.863 million | Form 10-K accession 0001437749-26-006147 | yes, and excluded from owner cash | none |
| Mineral revenue $100.152 million | Form 10-Q accession 0001437749-26-025856 | yes | none |
| Sisecam equity loss $12.733 million | Same 10-Q | yes | none |
| Distributions $0.75, $0.12, $0.75 | Same 10-Q | yes | none |
| Segment owner cash $2.95 and $0.05 | valuation.json segment_build | yes, sum $3.00 | none |
| Base case -9.91% | implied_return.base_pct | yes | none |

## Internal consistency

The owner-cash series is shown at -10.7 and is not the returns statement. The tape at $117.06 is not written into the model price of $106.995. The general partner interest is flagged as not restated.

## [HUMAN REVIEW]

Confirm any distribution after the May 2026 declaration before changing the $0.75 run rate.
