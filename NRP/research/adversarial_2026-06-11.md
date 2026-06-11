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

# NRP — Adversarial review

**Date:** 2026-06-11  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `NRP/research/deep_dive_2026-06-11.md`  
**Valuation reviewed:** `NRP/research/valuation.json`  
**Filings used:** `NRP/research/evidence/filing_facts_2026-06-11.json`

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
| 1 | Latest revenue (filing) | — | **$191.04B** vs prior $234.15B (-18.4% YoY) | spot-check dive | — |
| — | Net income (filing) | — | **136367.0** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | -9.91% | -9.91% | Yes |
| Classification IRR | -9.91% | -9.91% | Yes |
| Valuation bridge base | -9.91% | -9.91% | Yes |

**Lint notes:**
- NRP/research: dive header cites adversarial but file missing
- NRP/research/deep_dive_2026-06-11.md: executive_summary_first_pct 49.0% vs valuation.json base -9.91% (tol 0.25pp)

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
