# Growth explanation stress test — rules upgrade

**Date:** 2026-06-01  
**Author:** Marvin (cloud agent)  
**Status:** Pending human review

## Summary

Every FCF growth rate in a Lawrence model is now treated as a **Popper conjecture** with **Deutsch explanatory quality** checks — not a silent CAGR in the assumption ledger.

## What changed

| Area | Change |
|------|--------|
| Framework | `_system/frameworks/growth_explanation_stress_test.md` — three layers (fact → theory → number), mandatory subsection, `valuation.json` shape |
| Philosophy library | `_system/reference/philosophy/deutsch-popper/` — Popper + Deutsch PDFs, extracts, INDEX, download script |
| Cursor rule | `.cursor/rules/growth-explanation-stress-test.mdc` |
| Structure | `deep_dive_structure.md`, `irr_assumption_ledger.md`, `deep_dive_template.md` — growth stress test after ledger, before IRR arithmetic |
| Agents | `MARVIN.md`, `MILLY.md` — `growth_explanation` YAML checks |
| Runbook | `cloud_marvin_runbook.md` |

## Popper / Deutsch in one sentence

**Popper:** State risky predictions and falsifiers; ban ad hoc rescues. **Deutsch:** Mechanism must be hard to vary, reach beyond the CAGR, and not be price-implied instrumentalism.

## Philosophy sources downloaded

Run: `python _system/scripts/download_philosophy_refs.py`

See `_system/reference/philosophy/deutsch-popper/INDEX.md` and `manifest.csv`.

## Human review asks

1. Approve mandatory stress-test subsection for all `full` / `scenario` dives (holdco `yield_curve` may stay `n/a`).
2. Confirm philosophy PDF hosting is acceptable (open-access arXiv + teaching mirrors).
3. Prioritize ticker refreshes: **GOOGL** (11% vs 2% base), **TPL** (5% vs land optionality).

## Not in this PR

- Retrofit of existing deep dives (GOOGL, TPL, etc.) — separate refresh passes
- Lint script enforcement of `growth_explanation` block (Milly manual for now)

## [PROPOSED MEMORY]

- **[PROPOSED MUNGER]** Growth without mechanism is curve-fitting; require falsifier before accepting rate in base case.
- **[PROPOSED COMPANY]** When Lawrence IRR is low, start stress test from **problem-situation** ("why 2% at $386?") not default CAGR.
