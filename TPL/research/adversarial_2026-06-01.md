---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: true
option_coverage: complete
growth_explanation: complete
---

# TPL — Adversarial review

**Date:** 2026-06-01  
**Agent:** Milly (NAV SOTP + segment re-pass)  
**Dive reviewed:** `TPL/research/deep_dive_2026-06-01.md`  
**Valuation reviewed:** `TPL/research/valuation.json`  
**Filings used:** `TPL/research/evidence/filing_facts_2026-06-01.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | FY2025 segment + OCF spot-check |
| Internal consistency | pass | Lawrence -1.0%; segment implied -0.8% tie-out |
| Disclosure scan | pass | no 8-K scan this batch |
| Short activist scan | no_hit | No Tier-1 forensic short in registry |
| Third-party (approved) | n/a | — |
| Option coverage | complete | Option scan + nav_overlay SOTP + segment_build |
| Growth explanation | complete | Popper/Deutsch block present |

**Overall:** Mechanical pass. NAV overlay complete; floor_pass false at $393 (expected).

---

## Filing reconciliation

| # | Claim in dive | Filing value | Match? |
|---|---------------|--------------|--------|
| 1 | FY2025 revenue | **$798.2M** | Yes |
| 2 | Land & Resource revenue | **$490.7M** | Yes |
| 3 | Water revenue | **$307.5M** | Yes |
| 4 | FY2025 OCF | **$545.9M** | Yes |
| 5 | Q1 2026 cash | **$247.6M** | Yes |
| 6 | Surface acres | **~882k** | Yes (Item 1) |
| 7 | NRA | **~224k** | Yes (Item 1) |

---

## Internal consistency

| Check | Expected | Found | OK? |
|-------|----------|-------|-----|
| Returns statement | -1.0% | -1.0% | Yes |
| Classification IRR | -1.0% | -1.0% | Yes |
| Segment implied | -0.84% | -0.8% | Yes |
| Overlay base | ~$211/sh | ~$211/sh | Yes |
| floor_pass | false | false | Yes |

**Lint notes:**
- Em-dash count warning (non-blocking)
- Exec summary mentions bear -5.4% before base -1.0% (acceptable)

---

## Option coverage

| Check | Status |
|-------|--------|
| `#### Option scan` present | pass |
| `nav_overlay.status` complete | pass |
| `segment_build` with Land + Water | pass |
| Undeveloped NRA excluded from Lawrence growth | pass |
| GAAP book not used as floor | pass |
| Double-count note in SOTP | pass |

**Inference risks (non-blocking):**
- Surface **$2,500/ac** and NRA **P=25%** are [Assumption] — flagged [HUMAN REVIEW]
- Water PPE at book vs replacement cost

---

## Growth explanation (Popper / Deutsch)

| Check | Status |
|-------|--------|
| Stress test section present | pass |
| Risky predictions + falsifiers | pass |
| `valuation.json` → `growth_explanation` | pass |

---

## Recommended actions

1. None blocking.
2. **Human:** Review surface $/acre and NRA probability weight when new land-sale or acquisition comps file.

---

## [HUMAN REVIEW]

- Batch pass — surface/NRA marks are assumption-led pending more comps.
