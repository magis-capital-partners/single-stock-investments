# ADP — Cross-Check: Third-Party Sources

**Date:** 2026-07-21
**Agent:** Marvin
**Marvin dive:** `ADP/research/deep_dive_2026-07-21.md`
**Source inventory:** `ADP/third-party-analyses/source_inventory_2026-07-21.md` *(Phase 3 refresh)*
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for ADP as of this scan. Marvin stance rests on **primary filings only** (FY2025 10-K, Q2 FY2026 10-Q, proxy). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend in base IRR.

## Sources in scope

| Source | Tier | Path | Role |
|--------|------|------|------|
| (none approved) | — | — | Primary filings only |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 service revenue | $20.56B (+7% YoY) | — | `10-K_20250806...` |
| FY2025 FCF | OCF $4.94B less capex $0.17B | — | Same |
| Net debt | ~$5.4B (commercial paper + LT debt less cash) | — | Same balance sheet |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | ~$267/sh component sum | ~12% per year (7yr synthesis) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$267/sh** | **~12% per year** | **watch** |

**Weights:** 100% Marvin (no approved external sources).

**Returns statement (blended):** At **~$255** per share, Marvin filing-based synthesis implies about **12% per year** over 7 years; no external views in base case.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings when added
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## Primary sources cited

1. `ADP/investor-documents/sec-edgar/10-K_20250806_rpt20250630_acc0000008670_25_000037.htm`
2. `ADP/investor-documents/sec-edgar/10-Q_20260129_rpt20251231_acc0000008670_26_000011.htm`
3. `ADP/research/valuation.json`
4. `ADP/research/evidence_reconciliation_2026-07-21.md`
