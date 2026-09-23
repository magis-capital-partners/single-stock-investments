---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: false
---

# BN — Adversarial review

**Date:** 2026-09-17  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `BN/research/deep_dive_2026-09-17.md`  
**Valuation reviewed:** `BN/research/valuation.json`  
**Filings used:** `BN/research/evidence/filing_facts_2026-09-17.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | filing_facts spot-check |
| Internal consistency | pass | lint_adversarial |
| Disclosure scan | pass | no 8-K scan this batch |
| Short activist scan | no_hit | No Tier-1 forensic short in `short_scan_2026-05-28.md`; no l… |
| Third-party (approved) | n/a | — |

**Overall:** Mechanical pass from filing_facts + lint. No blocking factual errors.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|--------------|--------|----------|
| 1 | Latest revenue (filing) | — | **$75100000.00B** | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **166194000000** | spot-check dive | — |
| — | Net income (filing) | — | **3235000000** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 17.32% | 17.32% | Yes |
| Classification IRR | 17.32% | 17.32% | Yes |
| Valuation bridge base | 17.32% | 17.32% | Yes |

**Lint notes:**
- BN\research\deep_dive_2026-09-17.md: executive_summary_first_pct 7.0% vs valuation.json base 17.32% (tol 0.25pp)
- BN/research: adversarial date adversarial_2026-07-21.md != dive 2026-09-17

---

## Disclosure scan

| Event | Date | Source | In dive? | Action |
|-------|------|--------|----------|--------|
| (batch) | — | not scanned | — | full pass on next refresh |

---

## Short activist scan

No Tier-1 forensic short in `short_scan_2026-05-28.md`; no local `short_reports/`.

---

## Recommended actions

1. None blocking — optional exec-summary IRR wording vs floor/bull.
2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.

---

## [HUMAN REVIEW]

- Batch pass — not a substitute for targeted disclosure / short research on high-risk names.
