# Framework governance

**Purpose:** Stop framework sprawl. Reuse `decision_stack.md`, `analysis_arsenal.md`, and `valuation.json` before adding files under `_system/frameworks/`.

## Four layers (all required for robustness)

| Layer | Role | Canonical paths |
|-------|------|-----------------|
| **Normative** | How to think | `decision_stack.md`, `option_treatment.md`, triggered arsenal rows |
| **Operative** | How machines run | `valuation_route.json`, `valuation_contract.json`, `run_security_decision_pipeline.py` |
| **Narrative** | How reports read | `deep_dive_structure.md`, `report_prose.md`, `archetype_valuation_prose.md` |
| **Adversarial** | What must not ship | `MILLY.md`, `lint_deep_dive.py`, `check_evidence_completeness.py`, CI |

Robustness = layers **agree**, not **one mega-file**.

## Before creating `_system/frameworks/new_thing.md`

Answer all four:

1. Which **decision-stack question** (1–6) does it answer?
2. Can it be a **section** of an existing triggered doc (usually `analysis_arsenal.md` row)?
3. Can it be a **`valuation.json` key** + script handler instead?
4. Which **lint or script** enforces it?

If 2 or 3 is yes → **do not** create a new framework file. Update arsenal + JSON schema in `classification.md` trigger map.

If none apply → write proposal in `_system/proposals/` first; use `_system/prompts/architecture_review_template.md`.

## Anti-patterns

- New framework per ticker (use `evidence_refresh` in JSON)
- Duplicate mechanical steps in runbook and `marvin_cloud_refresh` (runbook points to script only)
- 30-row “read everything” tables in `.mdc` rules (use decision tree in `investment-frameworks.mdc`)
- Merging Milly/freshness gates into narrative frameworks (keep gates visible)

## Agent read order (every research task)

1. `decision_stack.md`
2. `{TICKER}/research/valuation_route.json` and `valuation_contract.json`, then `valuation.json` inputs → open only triggered arsenal rows
3. Primary PDFs in `{TICKER}/`
4. Mechanical close: `marvin_cloud_refresh.py` only
