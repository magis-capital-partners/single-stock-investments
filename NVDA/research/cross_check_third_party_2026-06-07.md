# NVDA — Cross-Check: Third-Party Sources

**Date:** 2026-06-07  
**Agent:** Marvin  
**Marvin dive:** `NVDA/research/deep_dive_2026-06-07.md`  
**Source inventory:** `NVDA/third-party-analyses/source_inventory_2026-06-07.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for NVIDIA as of 2026-06-07. Marvin stance rests on **primary filings only** (FY2026 10-K, Q1 FY2027 10-Q, proxy). Lawrence base IRR is **8.6%** per year at a **~$140** placeholder price on **$3.94** per share FY2026 free cash flow. There is no external view to blend; Marvin floor stands alone until approved Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Title | Path | Status | Reviewed |
|----|-------|------|--------|----------|
| — | Primary filings only | `NVDA/investor-documents/sec-edgar/` | n/a | Yes |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2026 revenue scale | $215.9B | — | `10-K_20260225` |
| Data Center dominance | $193.7B segment revenue | — | 10-K segment note |
| Free cash flow per share | $3.94 | — | OCF $102.7B − capex $6.0B ÷ shares |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external sources to diverge from |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $3.94/sh FCF (FY2026) | **8.6%** / 7yr Lawrence base | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$3.94/sh** | **8.6%** (Marvin only) | **watch** |

**Weights:** 100% Marvin filings; 0% external (no sources indexed).

**Returns statement (blended):** With no approved third-party inputs, the blended return equals the Marvin Lawrence base **8.6%** per year.

## [HUMAN REVIEW]

- [x] No approved third-party sources in inventory (documented)
- [x] No pending sources folded into base IRR
- [ ] Re-run `scan_third_party_sources.py NVDA --with-hk` when Substacks or research notes added
- [ ] Promote material external views via `third_party_sources.md` before blending into `valuation.json`

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] NVDA: third-party cross-check 2026-06-07 — Marvin floor only; Lawrence base **8.6%**

## Primary sources cited

1. `NVDA/research/deep_dive_2026-06-07.md`
2. `NVDA/research/valuation.json`
3. `NVDA/third-party-analyses/source_inventory_2026-06-07.md`
4. `NVDA/investor-documents/sec-edgar/10-K_20260225_rpt20260125_acc0001045810_26_000021.htm`
