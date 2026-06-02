# Architecture review template

Use when proposing pipeline changes, new frameworks, or consolidation. Copy into `_system/proposals/{name}_{date}.md`.

## Goal

What problem are we solving? (agent read load / script drift / onboarding / robustness)

## Constraints

- Must keep: …
- Must not break: …
- Non-goals: …

## Success criteria

Measurable checks, e.g.:

- Batch and cloud run identical mechanical steps
- New overlay = `valuation.json` only, no new framework file
- Agent mandatory read list ≤ N files for a standard compounder dive

## Proposed change

Architecture diagram or bullet list (normative / operative / narrative / adversarial).

## Risks of simplification

What redundancy or enforcement do we lose?

## Redundancy we keep on purpose

(e.g. Milly, 7-day commodity gate, cross-check verify, lint)

## Implementation scope

- [ ] Docs only
- [ ] Scripts
- [ ] Cursor rules
- [ ] CI

## Arsenal row (if new trigger)

| Tool | Trigger | Doc |
|------|---------|-----|
| … | … | … |
