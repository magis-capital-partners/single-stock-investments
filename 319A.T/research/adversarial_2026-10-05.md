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

# 319A.T — Adversarial review

**Date:** 2026-10-05  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `319A.T/research/deep_dive_2026-10-05.md`  
**Valuation reviewed:** `319A.T/research/valuation.json`  
**Filings used:** `319A.T/research/evidence/filing_facts_2026-10-05.json`

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

The batch pass ran while `INDEX.csv` still listed only the scaffold files, so `filing_facts` had no metrics. A later index rebuild inventoried 123 PDFs. The ownership, half-year earnings, net debt, and share-count figures in the dive were checked against the securities report and the June 30, 2026 English results, not against that empty fact file.

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
| Returns statement | -4.45% | -4.45% | Yes |
| Classification IRR | -4.45% | None% | — |
| Valuation bridge base | -4.45% | -4.45% | Yes |

**Lint notes:**
- 319A.T\research\deep_dive_2026-10-05.md: missing Implied 7yr IRR in Classification
- 319A.T/research: missing adversarial_*.md — run Milly standard pass
- 319A.T\research\deep_dive_2026-10-05.md: header missing **Adversarial review:** link

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
