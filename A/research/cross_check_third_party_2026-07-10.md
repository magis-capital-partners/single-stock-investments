# A — Cross-Check: Third-Party Sources

**Date:** 2026-07-10
**Agent:** Marvin
**Marvin dive:** `A/research/deep_dive_2026-07-10.md`
**Source inventory:** `A/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

**Marvin floor only** for Agilent-specific stance and IRR. The automated source inventory for ticker **A** incorrectly matched five **APLD** (Applied Digital) approved sources from the global registry; none discuss Agilent Technologies. No Agilent-specific third-party PDFs, Substacks, activist filings, or HK commentaries are indexed in `A/third-party-analyses/` as of 2026-07-10.

The only potentially relevant approved item is **Verdad Capital — Biotech Investing (2026)**, a **sector-level** paper on biotech spend and valuation — **context tier only**, not Agilent-specific. We do not blend it into base IRR.

**Synthesis (best estimate):** Marvin filing-based floor stands alone: **4.19% per year** synthesis IRR at ~**$134** on FY2025 normalized free cash flow per share **$4.04**. Stance **watch**.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| apld_pf3_summary | Applied Digital / Marvin shop summary (PF3 PR) | `APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md` | approved | [x] reviewed — **not relevant to A** |
| apld_reiterate_buy | Research note (run-the-table bull case) | `APLD/investor-documents/research-notes/What Would A Run The Table Scenario Look Like_ Reiterate BUY.pdf` | approved | [x] reviewed — **not relevant to A** |
| apld_oasis_13d | Oasis Management (SC 13D/A) | `APLD/third-party-analyses/activist_reports_index.json` | approved | [x] reviewed — **not relevant to A** |
| apld_wolfpack_short | Wolfpack Research short cache (Jul 2023) | `APLD/third-party-analyses/short_reports/wolfpack_2023-07.md` | approved | [x] reviewed — **not relevant to A** |
| verdad_biotech_2026 | Verdad Capital — Biotech Investing (2026) | `_system/reference/biotech-quant/papers/verdad_biotech_investing_2026.pdf` | approved (context) | [x] reviewed — sector context only |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Biopharma funding cyclicality | LS&D instrument demand tied to customer capital budgets; FY2023–FY2024 softness, FY2025 recovery | Verdad discusses biotech spend cycles and valuation compression in downturns | `verdad_biotech_2026` (context) |
| Quality franchise premium | ~21% operating margin; consumables/services mix | No Agilent-specific external floor | Marvin only |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Agilent IRR at price | 4.19% synthesis on $4.04/sh FCF | No Agilent-specific external return | **100% Marvin weight** |
| Stance | watch (<15% bar) | N/A | No external stance input |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $4.04/sh FCF FY2025 | 4.19% / 7yr synthesis | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$4.04/sh** | **4.19% per year** | **watch** |

**Weights:** 100% Marvin — no Agilent-specific approved third-party in base IRR. Verdad biotech paper is sector context only per `third_party_sources.md` context tier.

**Returns statement (blended):** At about **$134** per share, blended best estimate is **4.19% per year** on Marvin's normalized FY2025 owner cash (no external IRR blended).

## [HUMAN REVIEW]

- [x] Every inventory source reviewed; four APLD items flagged as registry false positives for ticker A
- [x] Verdad biotech paper used as context only, not in `valuation.json` base
- [ ] Human to add Agilent-specific third-party sources to inventory when available
- [ ] Promote any new approved sources via `third_party_sources.md` before blending into IRR

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] A: third-party cross-check 2026-07-10 — Marvin floor only; APLD registry matches are false positives for Agilent.

## Primary sources cited

1. `A/research/deep_dive_2026-07-10.md`
2. `A/third-party-analyses/source_inventory_2026-07-10.md`
3. `A/investor-documents/sec-edgar/10-K_20251222_rpt20251031_acc0001090872_25_000087.htm`
4. `_system/reference/biotech-quant/papers/verdad_biotech_investing_2026.pdf` (context only)
