# Optionality rules upgrade — 2026-06-01

**Trigger:** Human feedback — analyses auto-zero every option; TPL GAAP book misstates land; need systemic rules not one-off fixes.

## New framework

- **`_system/frameworks/option_treatment.md`** — canonical guide:
  - Three layers: Lawrence gate vs overlay base vs bull sensitivity
  - Mandatory **Option scan** on every deep dive
  - Treatment ladder: `zero`, `embedded_in_segment`, `milestone_nav`, `probability_weighted`, `nav_floor`, `yield_curve`
  - Segment + `nav_overlay` patterns (TPL undeveloped reserves, GOOGL backlog embedded in Cloud)
  - Anti-patterns: auto-zero, GAAP book as floor when assets unmarked

## Updated files

| File | Change |
|------|--------|
| `.cursor/rules/optionality-valuation.mdc` | New always-on research rule |
| `.cursor/rules/investment-frameworks.mdc` | `option_treatment.md` on every dive |
| `.cursor/rules/marvin-core.mdc` | Option scan + nav_overlay requirements |
| `.cursor/rules/segment-valuation.mdc` | Removed "base = zero terminal" default |
| `_system/frameworks/optionality_valuation.md` | TPL, GAAP misstatement triggers, KEWL/TPL mineral section |
| `_system/frameworks/segment_cashflow_valuation.md` | Tiered option treatment |
| `_system/frameworks/deep_dive_structure.md` | Option scan in §6; overlay in §11 |
| `_system/frameworks/archetype_valuation_prose.md` | TPL infrastructure + optionality prose |
| `_system/agents/MARVIN.md` | Overlay table + every-dive scan |
| `_system/agents/MILLY.md` | Option coverage workstream |
| `_system/prompts/deep_dive_template.md` | Option scan template block |

## Agent behavior change

**Before:** Waymo / RL / undeveloped acreage → terminal $0 by default in segment and narrative.

**After:** Complete option scan → assign `option_treatment` with evidence → Lawrence gate stays conservative; overlay base may partially value options (NRA comps, backlog in Cloud growth, external marks).

## [HUMAN REVIEW]

- Approve treatment ladder thresholds (e.g. when `probability_weighted` is OK in overlay base).
- Prioritize TPL full NAV SOTP as first application of new rules.
