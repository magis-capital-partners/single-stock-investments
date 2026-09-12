# CRM — Cross-Check: Third-Party Sources

**Date:** 2026-09-12
**Agent:** Marvin
**Marvin dive:** `CRM/research/deep_dive_2026-09-12.md`
**Source inventory:** `CRM/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for CRM as of this scan. Marvin stance rests on **primary filings only** (10-K, 10-Q, proxy). Activist SC-13G filings appear in inventory as context tier only.

**Synthesis:** Marvin floor only; no external blend in base IRR.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary SEC filings | 10-K, 10-Q, DEF 14A | approved (primary) | Base case owner cash and capital structure |
| SC-13G cluster | activist filings | **[PENDING APPROVAL]** | Context only; not in base IRR |
| Substacks / HK | none indexed | n/a | Re-run scan when material added |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale | ~$41.5B FY2026 | n/a | `10-K_20260302_*.htm` |
| Buyback intensity | $12.6B FY2026 | n/a | `10-K_20260302_*.htm` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external view to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $282/sh base PV (contract) | 7.2% legacy audit | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **7.2% legacy base** | **watch** |

**Weights:** 100% primary filings; no approved external sources.

**Returns statement (blended):** Same as Marvin base (**7.2%** per year legacy audit at **$173.79**); pending sources not in base IRR.

## [HUMAN REVIEW]

- [ ] Re-run `scan_third_party_sources.py CRM --with-hk` when new material is added
- [ ] Promote any external source via `third_party_sources.md` before base IRR use

## Primary sources cited

1. `CRM/research/deep_dive_2026-09-12.md`
2. `CRM/research/evidence/filing_digest_2026-08-06.md`
3. `CRM/third-party-analyses/source_inventory_2026-07-10.md`
