# CRWD — Cross-Check: Third-Party Sources

**Date:** 2026-09-12  
**Agent:** Marvin  
**Marvin dive:** `CRWD/research/deep_dive_2026-09-12.md`  
**Source inventory:** primary filings only (no `source_inventory_2026-09-12.md`; prior scan 2026-07-10)  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for CRWD as of 2026-09-12. The third-party scan from 2026-07-10 found no Substacks, fund letters, or HK commentaries in scope. Marvin stance rests on **primary filings only** (10-K FY2026, 10-Q Q1 FY2027, prior quarterly filings). **Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Used in base IRR? |
|--------|------|--------|-----------------|
| SEC 10-K / 10-Q | Primary | fact | yes (via contract) |
| Third-party analyses folder | Activist SC-13G filings | context | no |
| Approved registry | — | none | no |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale | $4.81B FY2026 | — | 10-K acc0001535527-26-000010 |
| Operating cash flow | $1.61B FY2026 | — | same |
| GAAP net loss | $(162.5)M FY2026 | — | same |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external view to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Base PV **$109/sh** | Forward return withheld | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **withheld** | **watch** |

**Weights:** 100% primary filings; 0% external (none approved).

## Missing data / follow-ups

- Re-run `scan_third_party_sources.py CRWD --with-hk --date 2026-09-12` when new external material is added.
- Promote any approved Substack or fund letter via human review before base IRR blend.
