# Framework simplification — orthogonal questions + analysis arsenal

**Date:** 2026-06-01  
**Status:** Implemented

---

## Problem

MOI integration duplicated existing gates:

| Removed requirement | Already covered by |
|---------------------|-------------------|
| MOI three-question table | Lawrence gate 6 / Q5 why mispriced |
| Margin of safety (MOI) | Q3 dhando + asset floor tools |
| Uses & misuses subsection | Risks + one-line **lens failure mode** |
| `moi_inefficiency` footer field | Q5 prose + predictive attribute |
| 10-value `moi_bucket` mandatory tag | 4-value `payoff_lens` |

---

## Solution: two layers

### Layer 1 — Six orthogonal questions (required)

| # | Question |
|---|----------|
| 1 | What is it? |
| 2 | Will it last? |
| 3 | Is the bear bounded? |
| 4 | What return at this price? |
| 5 | Why mispriced? |
| 6 | What do we do? |

Single home: `decision_stack.md`. Gate table in Payoff & return.

### Layer 2 — Analysis arsenal (triggered)

Full breadth preserved in `analysis_arsenal.md`: MOI chapters, Hohn, HK curve, optionality, segment SOTP, AI overlay, Milly, clone verify, idea funnel, etc.

Open tools by `payoff_lens`:

- `operating` — default compounders/croupiers  
- `asset` — SOTP, NAV, deep value  
- `event` — spinoffs, special situations  
- `levered` — equity stubs  

---

## What changed in lint / template

- Removed: mandatory MOI table, Uses & misuses section, moi_inefficiency  
- Added: optional warning if Payoff lens missing from Classification  
- Risks: **Lens failure mode** one line when lens ≠ operating  

---

## [HUMAN REVIEW]

- Migrate existing `moi_bucket` values to `payoff_lens` on next dive refresh?  
- Drop `moi_bucket` from footer entirely after migration?
