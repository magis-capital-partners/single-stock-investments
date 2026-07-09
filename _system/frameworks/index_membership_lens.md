# Index membership lens

**Date:** 2026-07-09  
**Status:** Active (dashboard research trigger)  
**Config:** `_system/data/index_rules.json`, `_system/data/index_calendar.json`  
**Research:** `_system/reference/index-effects/SYNTHESIS.md`

## Purpose

Track **potential** (proximity to eligibility boundaries) and **confirmed** (provider-announced) index inclusion and exclusion for every holding. This is a research / watch trigger, not a mechanical trade signal.

## Status definitions

| Status | Meaning |
|--------|---------|
| `member` | Seed or constituent list says the name is in the index |
| `inclusion_candidate` | Not a member; passes most gates; within distance band of the boundary |
| `deletion_risk` | Member that fails continued-eligibility checks, or M&A / going-private news |
| `ineligible` | Security type or venue cannot join (CVR, OTC Pink, preferred, private, etc.) |
| `n_a` | Applicable in principle, but required inputs missing (float, ADV, earnings, FIF) |

## Confidence

| Tag | Meaning |
|-----|---------|
| `rules_only` | Deterministic scorecard from rules + fundamentals |
| `news_unconfirmed` | News classified as index change; not matched to provider notice |
| `provider_confirmed` | Provider notice or committee release with effective date |

## Priority score (0–1)

Weights in `index_rules.json` → `scoring.weights`:

1. **Boundary closeness** (0.35) — closer absolute distance to cutoff → higher  
2. **Calendar proximity** (0.25) — nearer reconstitution / review → higher  
3. **Demand shock** (0.30) — estimated shares forced / ADV (capped)  
4. **Illiquidity** (0.10) — lower ADV → higher residual impact for small names  

Do **not** rank by the mere fact of a membership change. Large-cap S&P 500 addition returns have fallen toward zero (Greenwood & Sammon 2022); residual edge is anticipation and smaller / less liquid names.

## Inclusion probability band

Deterministic heuristic from distance, days-to-event, and fraction of gates passed (`high` / `medium` / `low` / `n_a`). Not a machine-learning model. S&P committee discretion keeps S&P candidates at `rules_only` confidence even when the band is `high`.

## UI caption (required)

> The average large-cap S&P 500 index effect has fallen to near zero since 2010; treat these as research triggers, weighted by demand-shock size, not mechanical trades.

## Guardrails

- Never invent float, ADV, or earnings; emit `n_a` with a reason  
- Provider thresholds live only in dated config  
- Confirmed vs potential always visually distinct  
