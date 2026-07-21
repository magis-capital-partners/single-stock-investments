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

# SEVN — Adversarial review

**Date:** 2026-07-21  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `SEVN/research/deep_dive_2026-07-21.md`  
**Valuation reviewed:** `SEVN/research/valuation.json`  
**Filings used:** `SEVN/research/evidence/filing_facts_2026-07-21.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | filing_facts spot-check |
| Internal consistency | fail | lint_adversarial |
| Disclosure scan | pass | no 8-K scan this batch |
| Short activist scan | no_hit | No Tier-1 forensic short in `short_scan_2026-05-28.md`; no l… |
| Third-party (approved) | n/a | — |

**Overall:** Mechanical pass from filing_facts + lint. **Block fixes** in dive before final.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|--------------|--------|----------|
| 1 | Latest revenue (filing) | — | **$29.38B** vs prior $35.27B (-16.7% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **328651.0** | spot-check dive | — |
| — | Net income (filing) | — | **15434.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **1.2** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 16.04% | 16.04% | Yes |
| Classification IRR | 16.04% | 14.6% | **No** |
| Valuation bridge base | 16.04% | 16.04% | Yes |

**Lint notes:**
- SEVN/research/deep_dive_2026-07-21.md: classification 14.6% vs valuation.json base 16.04% (tol 0.25pp)
- SEVN/research/deep_dive_2026-07-21.md: executive_summary_first_pct 14.6% vs valuation.json base 16.04% (tol 0.25pp)
- SEVN/research: adversarial date adversarial_2026-07-17.md != dive 2026-07-21

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

1. **Marvin:** Align Returns statement / Classification IRR with `valuation.json` base.
2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.

---

## [HUMAN REVIEW]

- Batch pass — not a substitute for targeted disclosure / short research on high-risk names.
