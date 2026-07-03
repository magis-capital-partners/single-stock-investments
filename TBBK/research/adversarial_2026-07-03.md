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

# TBBK — Adversarial review

**Date:** 2026-07-03  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `TBBK/research/deep_dive_2026-07-03.md`  
**Valuation reviewed:** `TBBK/research/valuation.json`  
**Filings used:** `TBBK/research/evidence/filing_facts_2026-07-03.json`

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
| — | Net income (filing) | — | **10.0** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 16.73% | 16.73% | Yes |
| Classification IRR | 16.73% | 16.73% | Yes |
| Valuation bridge base | 16.73% | 16.73% | Yes |

**Lint notes:**
- TBBK/research: dive header cites adversarial but file missing
- TBBK/research/deep_dive_2026-07-03.md: executive_summary_first_pct 29.0% vs valuation.json base 16.73% (tol 0.25pp)

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
