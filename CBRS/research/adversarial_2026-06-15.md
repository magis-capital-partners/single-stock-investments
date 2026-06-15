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

# CBRS — Adversarial review

**Date:** 2026-06-15  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `CBRS/research/deep_dive_2026-06-15.md`  
**Valuation reviewed:** `CBRS/research/valuation.json`  
**Filings used:** `CBRS/research/evidence/filing_facts_2026-06-15.json`

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
| — | filing_facts | — | no_full_tier_text_extract | — | inference |
| — | No filing_facts metrics | — | — | run build_filing_evidence | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | -2.4% | 758877548637257.5% | **No** |
| Classification IRR | -2.4% | -2.4% | Yes |
| Valuation bridge base | -2.4% | 758877548637257.5% | **No** |

**Lint notes:**
- CBRS/research: dive header cites adversarial but file missing
- CBRS/research/deep_dive_2026-06-15.md: executive_summary_first_pct 39.0% vs valuation.json base -2.4% (tol 0.25pp)
- CBRS/research/deep_dive_2026-06-15.md: returns_statement 758877548637257.5% vs valuation.json base -2.4% (tol 0.25pp)

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
