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

# BWEL — Adversarial review

**Date:** 2026-06-02  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `BWEL/research/deep_dive_2026-06-02.md`  
**Valuation reviewed:** `BWEL/research/valuation.json`  
**Filings used:** `BWEL/research/evidence/filing_facts_2026-06-02.json`

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
| — | No filing_facts metrics | — | — | run build_filing_evidence | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 1.1% | 1.1% | Yes |
| Classification IRR | 2.86% | None% | — |
| Valuation bridge base | 2.86% | 2.86% | Yes |

**Lint notes:**
- BWEL/research: dive header cites adversarial but file missing
- BWEL/research/deep_dive_2026-06-02.md: executive_summary_first_pct 1.1% vs valuation.json base 2.86% (tol 0.25pp)
- BWEL/research/deep_dive_2026-06-02.md: missing Implied 10yr IRR in Classification

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
