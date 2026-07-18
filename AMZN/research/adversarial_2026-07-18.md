---
filing: pass
consistency: fail
disclosure: pass
short: no_hit
third_party: n/a
block_final: true
blocking_issues: ["classification_irr"]
re_pass: false
---

# AMZN — Adversarial review

**Date:** 2026-07-18  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `AMZN/research/deep_dive_2026-07-18.md`  
**Valuation reviewed:** `AMZN/research/valuation.json`  
**Filings used:** `AMZN/research/evidence/filing_facts_2026-07-18.json`

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
| 1 | Latest revenue (filing) | — | **$255.89B** vs prior $272.31B (-6.0% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **285970.0** | spot-check dive | — |
| — | Net income (filing) | — | **30425.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **2.95** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 3.68% | 3.68% | Yes |
| Classification IRR | 3.68% | -1.49% | **No** |
| Valuation bridge base | 3.68% | 3.68% | Yes |

**Lint notes:**
- AMZN/research/deep_dive_2026-07-18.md: classification -1.49% vs valuation.json base 3.68% (tol 0.25pp)
- AMZN/research/deep_dive_2026-07-18.md: executive_summary_first_pct 3.2% vs valuation.json base 3.68% (tol 0.25pp)
- AMZN/research: adversarial date adversarial_2026-05-29.md != dive 2026-07-18

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
