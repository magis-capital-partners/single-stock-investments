---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: true
---

# FLY — Adversarial review

**Date:** 2026-07-18  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `FLY/research/deep_dive_2026-07-18.md`  
**Valuation reviewed:** `FLY/research/valuation.json`  
**Filings used:** `FLY/research/evidence/filing_facts_2026-07-18.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | Revenue, cash, RPO spot-check vs 10-K / 10-Q |
| Internal consistency | pass | Returns statement 2.2% matches Lawrence base in valuation.json |
| Disclosure scan | pass | No new 8-K scan flags this batch |
| Short activist scan | no_hit | No Tier-1 forensic short indexed |
| Third-party (approved) | n/a | No approved third-party sources |

**Overall:** Pass after IRR consistency fix. Stance **watch** stands on operating loss vs backlog narrative.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|--------------|--------|----------|
| 1 | FY2025 revenue $159.9M | filing_facts | $159,855K | Yes | — |
| 2 | Q1 2026 net loss $96.7M | 10-Q | ($96,676K) | Yes | — |
| 3 | RPO $652.6M | 10-Q | $652.6M | Yes | — |
| 4 | Cash $326.2M Mar 2026 | 10-Q | $326,179K | Yes | — |

---

## Inference / stance gaps

| # | Issue | Severity | Recommendation |
|---|-------|----------|----------------|
| 1 | Normalized owner cash $0.35/sh vs OCF ~$1.28/sh | [HUMAN REVIEW] | Document normalization in assumption ledger (done) |
| 2 | FY2025 GAAP net income $298M not run-rate | info | Correctly flagged in dive |
| 3 | Eclipse / SciTec integration timing | [HUMAN REVIEW] | Await filing-grounded milestones |

---

## Short scan

No hit. No indexed forensic short report for FLY.

---

## Third party

No approved third-party sources in inventory. Cross-check documents Marvin floor only.

---

## Recommended fixes (completed)

- Removed duplicate returns statement (4.6% synthesis vs 2.2% Lawrence gate)
- Aligned `implied_return.base_pct` with Lawrence stance gate **2.2%**
- Synthesis **4.6%** retained in Total synthesis table only
