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

# RYN — Adversarial review

**Date:** 2026-06-10  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `RYN/research/deep_dive_2026-06-10.md`  
**Valuation reviewed:** `RYN/research/valuation.json`  
**Filings used:** `RYN/research/evidence/filing_facts_2026-06-10.json`

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
| 1 | Latest revenue (filing) | — | **$484.49B** vs prior $987.93B (-51.0% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **2209735.0** | spot-check dive | — |
| — | Net income (filing) | — | **474380.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **3.07** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | -4.05% | -4.05% | Yes |
| Classification IRR | -4.05% | -4.05% | Yes |
| Valuation bridge base | -4.05% | -4.05% | Yes |

**Lint notes:**
- RYN/research: dive header cites adversarial but file missing

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
