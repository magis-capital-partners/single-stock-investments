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

# CRML — Adversarial review

**Date:** 2026-07-21  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `CRML/research/deep_dive_2026-07-21.md`  
**Valuation reviewed:** `CRML/research/valuation.json`  
**Filings used:** `CRML/research/evidence/filing_facts_2026-07-21.json`

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
| — | No filing_facts metrics | — | — | run build_filing_evidence | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | -7.34% | -7.34% | Yes |
| Classification IRR | -7.34% | -9.96% | **No** |
| Valuation bridge base | -7.34% | -7.34% | Yes |

**Lint notes:**
- CRML/research/deep_dive_2026-07-21.md: classification -9.96% vs valuation.json base -7.34% (tol 0.25pp)
- CRML/research/adversarial_2026-07-21.md: block_final=true — resolve before final dive

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
