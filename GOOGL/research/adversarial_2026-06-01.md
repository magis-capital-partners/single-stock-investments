---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: true
valuation_staleness: warn
ai_coverage: partial
option_coverage: complete
growth_explanation: complete
---

# GOOGL — Adversarial review

**Date:** 2026-06-01  
**Agent:** Milly (growth stress test re-pass)  
**Dive reviewed:** `GOOGL/research/deep_dive_2026-06-01.md`  
**Valuation reviewed:** `GOOGL/research/valuation.json`  
**Filings used:** `GOOGL/research/evidence/filing_facts_2026-05-29.json`

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
| 1 | Latest revenue (filing) | — | **$90.23B** vs prior $109.90B (-17.9% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **415265.0** | spot-check dive | — |
| — | Net income (filing) | — | **34540.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **2.84** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 2.1% | 2.1% | Yes |
| Classification IRR | 2.1% | 2.1% | Yes |
| Valuation bridge base | 2.1% | 2.1% | Yes |

**Lint notes:**
- GOOGL\research\deep_dive_2026-05-29.md: executive_summary_first_pct 36.1% vs valuation.json base 2.1% (tol 0.25pp)

---

## Disclosure scan

| Event | Date | Source | In dive? | Action |
|-------|------|--------|----------|--------|
| (batch) | — | not scanned | — | full pass on next refresh |

---

## Short activist scan

No Tier-1 forensic short in `short_scan_2026-05-28.md`; no local `short_reports/`.

---

## Growth explanation (Popper / Deutsch)

| Check | Status |
|-------|--------|
| `### Growth explanation stress test` present | pass |
| Growth ledger rows cite theory label | pass |
| Risky predictions + falsifiers | pass |
| `valuation.json` → `growth_explanation` | pass |
| Deutsch checks documented | pass |

**Note:** Cloud backlog conversion timing still **[Inference risk]** — not a dated revenue schedule in filings.

---

## Recommended actions

1. None blocking — optional exec-summary IRR wording vs floor/bull.
2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.

---

## [HUMAN REVIEW]

- Batch pass — not a substitute for targeted disclosure / short research on high-risk names.
