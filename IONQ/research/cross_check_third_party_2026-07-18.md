# IONQ — Cross-Check: Third-Party Sources

**Date:** 2026-07-18
**Agent:** Marvin
**Marvin dive:** `IONQ/research/deep_dive_2026-07-18.md`
**Source inventory:** `IONQ/third-party-analyses/source_inventory_2026-07-18.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for IonQ as of this scan (`scan_third_party_sources.py` returned zero matches). Marvin stance rests on **primary SEC filings only** (10-K FY2025, 10-Q Q1 2026, DEF 14A, 8-K series). Re-run the third-party scan when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Lawrence base IRR pending mechanical price fetch.

## Sources in scope

| Source | Type | Date | Approval | Use in base IRR |
|--------|------|------|----------|-----------------|
| Primary filings | 10-K, 10-Q, 8-K, DEF 14A | 2022–2026 | n/a (primary) | Yes |
| Third-party scan | None indexed | 2026-07-18 | n/a | No |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue growth | FY2025 **$130.0M** (+202% YoY) | — | 10-K MD&A |
| Operating losses | FY2025 net loss **$512.1M**; Q1 2026 operating loss **($271.5M)** | — | 10-K / 10-Q |
| Acquisition strategy | id Quantique, Capella, Oxford Ionics, Vector Atomic, Skyloom | — | 10-K Item 9A; 10-Q Note 3 |
| Cash burn | FY2025 OCF **($283.2M)** | — | 10-K MD&A |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash | Normalized **$0.08/sh** base; excludes warrant gains | None indexed | Marvin only |
| Platform option value | Probability-weighted overlay; zero in Lawrence gate | None indexed | No blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$0.08/sh** normalized owner cash | Pending price | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$0.08/sh** | **Pending mechanical IRR** | **watch** |

**Weights:** 100% Marvin filings (no approved external sources).

**Returns statement (blended):** Pending `marvin_cloud_refresh.py` price and IRR sync.

## [HUMAN REVIEW]

- [ ] Re-scan third-party inventory when sell-side or Substack coverage appears
- [ ] No pending sources cited in base IRR
- [ ] Blended estimate remains Marvin-only until human promotes sources in `third_party_sources.md`

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] IONQ: third-party cross-check 2026-07-18 — filings only, no external blend

## Primary sources cited

1. `IONQ/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001193125_26_071562.htm`
2. `IONQ/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_211876.htm`
3. `IONQ/research/deep_dive_2026-07-18.md`
4. `IONQ/third-party-analyses/source_inventory_2026-07-18.md`
